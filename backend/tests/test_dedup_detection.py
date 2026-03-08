"""Duplicate detection tests: SHA-256 hash-based dedup at download time.

Tests:
- TestComputeContentHash: normalization, CRLF/LF, BOM, empty content
- TestDuplicateSubtitleError: error attributes and hierarchy
- TestSaveSubtitleDedup: first save, duplicate skip, stale hash cleanup,
                         cross-directory (not a duplicate), disabled via config
"""

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dedup_engine import compute_content_hash_from_bytes
from error_handler import DuplicateSubtitleError, SublarrError

# ── TestComputeContentHash ────────────────────────────────────────────────────


class TestComputeContentHash:
    def test_returns_sha256_hex(self):
        result = compute_content_hash_from_bytes(b"hello")
        assert len(result) == 64
        assert all(c in "0123456789abcdef" for c in result)

    def test_deterministic(self):
        assert compute_content_hash_from_bytes(b"abc") == compute_content_hash_from_bytes(b"abc")

    def test_crlf_equals_lf(self):
        crlf = compute_content_hash_from_bytes(b"line1\r\nline2\r\n")
        lf = compute_content_hash_from_bytes(b"line1\nline2\n")
        assert crlf == lf

    def test_leading_trailing_whitespace_stripped(self):
        stripped = compute_content_hash_from_bytes(b"content")
        padded = compute_content_hash_from_bytes(b"  content  ")
        assert stripped == padded

    def test_different_content_different_hash(self):
        assert compute_content_hash_from_bytes(b"aaa") != compute_content_hash_from_bytes(b"bbb")

    def test_utf8_bom_handled(self):
        # BOM is decoded as part of the string — normalization still applies
        with_bom = compute_content_hash_from_bytes(b"\xef\xbb\xbfcontent")
        assert len(with_bom) == 64  # just ensure it doesn't crash

    def test_empty_bytes(self):
        result = compute_content_hash_from_bytes(b"")
        assert len(result) == 64


# ── TestDuplicateSubtitleError ────────────────────────────────────────────────


class TestDuplicateSubtitleError:
    def test_is_sublarr_error(self):
        err = DuplicateSubtitleError("abc123", "/existing.srt", "/new.srt")
        assert isinstance(err, SublarrError)

    def test_http_status_409(self):
        err = DuplicateSubtitleError("abc123", "/existing.srt", "/new.srt")
        assert err.http_status == 409

    def test_attributes(self):
        err = DuplicateSubtitleError("deadbeef", "/old/path.srt", "/new/path.srt")
        assert err.content_hash == "deadbeef"
        assert err.existing_path == "/old/path.srt"
        assert err.attempted_path == "/new/path.srt"

    def test_context_populated(self):
        err = DuplicateSubtitleError("hash1", "/a.srt", "/b.srt")
        assert err.context["content_hash"] == "hash1"
        assert err.context["existing_path"] == "/a.srt"


# ── TestSaveSubtitleDedup ─────────────────────────────────────────────────────


def _make_result(content: bytes = b"1\n00:00:01,000 --> 00:00:02,000\nHello\n"):
    from providers.base import SubtitleFormat, SubtitleResult

    r = SubtitleResult.__new__(SubtitleResult)
    r.content = content
    r.format = SubtitleFormat.SRT
    r.provider_name = "test_provider"
    r.language = "de"
    r.score = 100
    r.subtitle_id = "sub123"
    return r


def _make_manager():
    from providers import ProviderManager

    mgr = ProviderManager.__new__(ProviderManager)
    mgr._providers = {}
    return mgr


class TestSaveSubtitleDedup:
    """Tests for dedup logic inside ProviderManager.save_subtitle()."""

    def _patch_save(self, tmp_path, dedup_enabled=True, repo_matches=None):
        """Return a context manager that patches all save_subtitle dependencies."""
        mock_settings = MagicMock(media_path=str(tmp_path), dedup_on_download=dedup_enabled)
        mock_repo = MagicMock()
        mock_repo.find_by_content_hash.return_value = repo_matches or []

        return (
            patch("config.get_settings", return_value=mock_settings),
            patch("security_utils.is_safe_path", return_value=True),
            patch("db.repositories.cleanup.CleanupRepository", return_value=mock_repo),
            mock_repo,
        )

    def test_first_save_writes_file(self, tmp_path):
        """First download should write the file normally."""
        mgr = _make_manager()
        result = _make_result()
        output = str(tmp_path / "episode.de.srt")

        mock_settings = MagicMock(media_path=str(tmp_path), dedup_on_download=True)
        mock_repo = MagicMock()
        mock_repo.find_by_content_hash.return_value = []

        with (
            patch("config.get_settings", return_value=mock_settings),
            patch("security_utils.is_safe_path", return_value=True),
            patch("db.repositories.cleanup.CleanupRepository", return_value=mock_repo),
        ):
            saved = mgr.save_subtitle(result, output)

        assert os.path.isfile(saved)
        assert open(saved, "rb").read() == result.content

    def test_duplicate_raises_error(self, tmp_path):
        """Identical content in the same directory raises DuplicateSubtitleError."""
        mgr = _make_manager()
        result = _make_result()
        existing = str(tmp_path / "episode.de.srt")
        open(existing, "wb").write(result.content)

        mock_settings = MagicMock(media_path=str(tmp_path), dedup_on_download=True)
        mock_repo = MagicMock()
        mock_repo.find_by_content_hash.return_value = [
            {"file_path": existing, "format": "srt", "language": "de"}
        ]

        with (
            patch("config.get_settings", return_value=mock_settings),
            patch("security_utils.is_safe_path", return_value=True),
            patch("db.repositories.cleanup.CleanupRepository", return_value=mock_repo),
            pytest.raises(DuplicateSubtitleError) as exc_info,
        ):
            mgr.save_subtitle(result, str(tmp_path / "episode2.de.srt"))

        assert exc_info.value.existing_path == existing

    def test_cross_directory_not_duplicate(self, tmp_path):
        """Same hash in a different directory is not a duplicate."""
        mgr = _make_manager()
        result = _make_result()
        other_dir = tmp_path / "other_series"
        other_dir.mkdir()
        existing = str(other_dir / "episode.de.srt")
        open(existing, "wb").write(result.content)
        output = str(tmp_path / "episode.de.srt")

        mock_settings = MagicMock(media_path=str(tmp_path), dedup_on_download=True)
        mock_repo = MagicMock()
        mock_repo.find_by_content_hash.return_value = [
            {"file_path": existing, "format": "srt", "language": "de"}
        ]

        with (
            patch("config.get_settings", return_value=mock_settings),
            patch("security_utils.is_safe_path", return_value=True),
            patch("db.repositories.cleanup.CleanupRepository", return_value=mock_repo),
        ):
            saved = mgr.save_subtitle(result, output)

        assert os.path.isfile(saved)

    def test_stale_hash_cleaned_and_write_proceeds(self, tmp_path):
        """Stale hash entries (file deleted) are cleaned up and write proceeds."""
        mgr = _make_manager()
        result = _make_result()
        stale_path = str(tmp_path / "deleted.de.srt")  # does NOT exist on disk
        output = str(tmp_path / "episode.de.srt")

        mock_settings = MagicMock(media_path=str(tmp_path), dedup_on_download=True)
        mock_repo = MagicMock()
        mock_repo.find_by_content_hash.return_value = [
            {"file_path": stale_path, "format": "srt", "language": "de"}
        ]

        with (
            patch("config.get_settings", return_value=mock_settings),
            patch("security_utils.is_safe_path", return_value=True),
            patch("db.repositories.cleanup.CleanupRepository", return_value=mock_repo),
        ):
            saved = mgr.save_subtitle(result, output)
            mock_repo.delete_hashes_by_paths.assert_called_once_with([stale_path])

        assert os.path.isfile(saved)

    def test_dedup_disabled_always_writes(self, tmp_path):
        """When dedup_on_download=False, no duplicate check is performed."""
        mgr = _make_manager()
        result = _make_result()
        existing = str(tmp_path / "episode.de.srt")
        open(existing, "wb").write(result.content)
        output = str(tmp_path / "episode2.de.srt")

        mock_settings = MagicMock(media_path=str(tmp_path), dedup_on_download=False)
        mock_repo = MagicMock()
        mock_repo.find_by_content_hash.return_value = [
            {"file_path": existing, "format": "srt", "language": "de"}
        ]

        with (
            patch("config.get_settings", return_value=mock_settings),
            patch("security_utils.is_safe_path", return_value=True),
            patch("db.repositories.cleanup.CleanupRepository", return_value=mock_repo),
        ):
            saved = mgr.save_subtitle(result, output)

        assert os.path.isfile(saved)
        mock_repo.find_by_content_hash.assert_not_called()
