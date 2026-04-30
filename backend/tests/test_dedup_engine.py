"""Tests for dedup_engine.py — SHA-256 hashing, duplicate scanning,
orphan detection, safe deletion, and disk space analysis.

Covers:
- compute_subtitle_hash(): file hashing with normalization, language extraction, errors
- compute_content_hash_from_bytes(): in-memory hashing (existing tests in test_dedup_detection.py)
- scan_for_duplicates(): directory walk, parallel hashing, DB upsert, progress emission
- delete_duplicates(): safety guards, path validation, symlink skip, DB cleanup
- scan_orphaned_subtitles(): media-matching logic, language tag stripping
- get_disk_space_analysis(): delegation to CleanupRepository
"""

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dedup_engine import (
    MEDIA_EXTENSIONS,
    SUBTITLE_EXTENSIONS,
    compute_content_hash_from_bytes,
    compute_subtitle_hash,
    delete_duplicates,
    get_disk_space_analysis,
    scan_for_duplicates,
    scan_orphaned_subtitles,
)

# ── Helpers ──────────────────────────────────────────────────────────────────


def _write_file(path: Path, content: str = "test content") -> Path:
    """Write a text file and return the Path object."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


# ── TestComputeSubtitleHash ─────────────────────────────────────────────────


class TestComputeSubtitleHash:
    """Tests for compute_subtitle_hash() — file-based hashing."""

    def test_returns_expected_keys(self, tmp_path):
        f = _write_file(tmp_path / "test.srt", "1\n00:00:01,000 --> 00:00:02,000\nHello\n")
        result = compute_subtitle_hash(str(f))
        assert set(result.keys()) == {
            "file_path",
            "content_hash",
            "file_size",
            "format",
            "language",
            "line_count",
        }

    def test_hash_is_sha256_hex(self, tmp_path):
        f = _write_file(tmp_path / "test.srt", "content")
        result = compute_subtitle_hash(str(f))
        assert len(result["content_hash"]) == 64
        assert all(c in "0123456789abcdef" for c in result["content_hash"])

    def test_deterministic(self, tmp_path):
        f = _write_file(tmp_path / "test.srt", "same content")
        r1 = compute_subtitle_hash(str(f))
        r2 = compute_subtitle_hash(str(f))
        assert r1["content_hash"] == r2["content_hash"]

    def test_crlf_and_lf_produce_same_hash(self, tmp_path):
        f_lf = tmp_path / "lf.srt"
        f_lf.write_bytes(b"line1\nline2\n")
        f_crlf = tmp_path / "crlf.srt"
        f_crlf.write_bytes(b"line1\r\nline2\r\n")
        assert (
            compute_subtitle_hash(str(f_lf))["content_hash"]
            == compute_subtitle_hash(str(f_crlf))["content_hash"]
        )

    def test_whitespace_stripped(self, tmp_path):
        f1 = _write_file(tmp_path / "a.srt", "content")
        f2 = _write_file(tmp_path / "b.srt", "  content  \n\n")
        assert (
            compute_subtitle_hash(str(f1))["content_hash"]
            == compute_subtitle_hash(str(f2))["content_hash"]
        )

    def test_different_content_different_hash(self, tmp_path):
        f1 = _write_file(tmp_path / "a.srt", "alpha")
        f2 = _write_file(tmp_path / "b.srt", "beta")
        assert (
            compute_subtitle_hash(str(f1))["content_hash"]
            != compute_subtitle_hash(str(f2))["content_hash"]
        )

    def test_file_size_matches(self, tmp_path):
        content = "hello world"
        f = _write_file(tmp_path / "test.srt", content)
        result = compute_subtitle_hash(str(f))
        assert result["file_size"] == os.path.getsize(str(f))

    def test_format_extracted_from_extension(self, tmp_path):
        for ext in (".srt", ".ass", ".ssa"):
            f = _write_file(tmp_path / f"test{ext}", "content")
            result = compute_subtitle_hash(str(f))
            assert result["format"] == ext.lstrip(".")

    def test_language_extracted_from_filename(self, tmp_path):
        f = _write_file(tmp_path / "episode.en.srt", "content")
        result = compute_subtitle_hash(str(f))
        assert result["language"] == "en"

    def test_language_three_letter_code(self, tmp_path):
        f = _write_file(tmp_path / "episode.jpn.ass", "content")
        result = compute_subtitle_hash(str(f))
        assert result["language"] == "jpn"

    def test_language_none_when_no_tag(self, tmp_path):
        f = _write_file(tmp_path / "episode.srt", "content")
        result = compute_subtitle_hash(str(f))
        assert result["language"] is None

    def test_line_count(self, tmp_path):
        f = _write_file(tmp_path / "test.srt", "line1\nline2\nline3")
        result = compute_subtitle_hash(str(f))
        assert result["line_count"] == 3

    def test_file_not_found_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            compute_subtitle_hash(str(tmp_path / "nonexistent.srt"))

    def test_file_path_in_result(self, tmp_path):
        f = _write_file(tmp_path / "test.srt", "content")
        result = compute_subtitle_hash(str(f))
        assert result["file_path"] == str(f)

    def test_hash_matches_bytes_function(self, tmp_path):
        """File hash and in-memory hash must agree for the same content."""
        content = "1\n00:00:01,000 --> 00:00:02,000\nHello\n"
        f = _write_file(tmp_path / "test.srt", content)
        file_hash = compute_subtitle_hash(str(f))["content_hash"]
        bytes_hash = compute_content_hash_from_bytes(content.encode("utf-8"))
        assert file_hash == bytes_hash


# ── TestScanForDuplicates ───────────────────────────────────────────────────


class TestScanForDuplicates:
    """Tests for scan_for_duplicates() — directory scanning + DB storage."""

    def test_invalid_path_returns_error(self):
        result = scan_for_duplicates("/nonexistent/path/xyz")
        assert result["total_scanned"] == 0
        assert "error" in result

    def test_empty_directory(self, tmp_path):
        with patch("db.repositories.cleanup.CleanupRepository") as MockRepo:
            mock_repo = MagicMock()
            mock_repo.get_duplicate_groups.return_value = []
            MockRepo.return_value = mock_repo
            result = scan_for_duplicates(str(tmp_path))
        assert result["total_scanned"] == 0
        assert result["duplicates_found"] == 0
        assert result["groups"] == []

    def test_scans_subtitle_files_only(self, tmp_path):
        _write_file(tmp_path / "episode.srt", "subtitle content")
        _write_file(tmp_path / "episode.mkv", "video content")
        _write_file(tmp_path / "readme.txt", "text content")

        with patch("db.repositories.cleanup.CleanupRepository") as MockRepo:
            mock_repo = MagicMock()
            mock_repo.get_duplicate_groups.return_value = []
            MockRepo.return_value = mock_repo
            result = scan_for_duplicates(str(tmp_path))

        assert result["total_scanned"] == 1
        assert mock_repo.upsert_hash.call_count == 1

    def test_scans_all_subtitle_extensions(self, tmp_path):
        for ext in SUBTITLE_EXTENSIONS:
            _write_file(tmp_path / f"test{ext}", f"content for {ext}")

        with patch("db.repositories.cleanup.CleanupRepository") as MockRepo:
            mock_repo = MagicMock()
            mock_repo.get_duplicate_groups.return_value = []
            MockRepo.return_value = mock_repo
            result = scan_for_duplicates(str(tmp_path))

        assert result["total_scanned"] == len(SUBTITLE_EXTENSIONS)

    def test_scans_subdirectories_recursively(self, tmp_path):
        _write_file(tmp_path / "season1" / "ep1.srt", "content1")
        _write_file(tmp_path / "season2" / "ep2.srt", "content2")
        _write_file(tmp_path / "ep3.ass", "content3")

        with patch("db.repositories.cleanup.CleanupRepository") as MockRepo:
            mock_repo = MagicMock()
            mock_repo.get_duplicate_groups.return_value = []
            MockRepo.return_value = mock_repo
            result = scan_for_duplicates(str(tmp_path))

        assert result["total_scanned"] == 3

    def test_upsert_called_for_each_file(self, tmp_path):
        _write_file(tmp_path / "a.srt", "aaa")
        _write_file(tmp_path / "b.srt", "bbb")

        with patch("db.repositories.cleanup.CleanupRepository") as MockRepo:
            mock_repo = MagicMock()
            mock_repo.get_duplicate_groups.return_value = []
            MockRepo.return_value = mock_repo
            scan_for_duplicates(str(tmp_path))

        assert mock_repo.upsert_hash.call_count == 2

    def test_duplicate_groups_returned(self, tmp_path):
        _write_file(tmp_path / "a.srt", "same")
        _write_file(tmp_path / "b.srt", "same")

        fake_groups = [{"content_hash": "abc", "count": 2, "files": [{}, {}]}]

        with patch("db.repositories.cleanup.CleanupRepository") as MockRepo:
            mock_repo = MagicMock()
            mock_repo.get_duplicate_groups.return_value = fake_groups
            MockRepo.return_value = mock_repo
            result = scan_for_duplicates(str(tmp_path))

        assert result["duplicates_found"] == 2
        assert len(result["groups"]) == 1

    def test_socketio_progress_emitted(self, tmp_path):
        # Create 20+ files to trigger the modulo-10 progress emit
        for i in range(20):
            _write_file(tmp_path / f"sub_{i:02d}.srt", f"content {i}")

        mock_socketio = MagicMock()

        with patch("db.repositories.cleanup.CleanupRepository") as MockRepo:
            mock_repo = MagicMock()
            mock_repo.get_duplicate_groups.return_value = []
            MockRepo.return_value = mock_repo
            scan_for_duplicates(str(tmp_path), socketio=mock_socketio)

        # At least the final 100% emit should fire
        assert mock_socketio.emit.call_count >= 1
        # Check the final emit has percent=100
        final_call = mock_socketio.emit.call_args_list[-1]
        assert final_call[0][0] == "scan_progress"
        assert final_call[0][1]["percent"] == 100.0

    def test_hashing_error_captured(self, tmp_path):
        _write_file(tmp_path / "good.srt", "good content")

        with (
            patch("db.repositories.cleanup.CleanupRepository") as MockRepo,
            patch(
                "dedup_engine.compute_subtitle_hash",
                side_effect=OSError("read error"),
            ),
        ):
            mock_repo = MagicMock()
            mock_repo.get_duplicate_groups.return_value = []
            MockRepo.return_value = mock_repo
            result = scan_for_duplicates(str(tmp_path))

        assert len(result["errors"]) == 1
        assert "read error" in result["errors"][0]["error"]

    def test_upsert_failure_does_not_crash(self, tmp_path):
        _write_file(tmp_path / "test.srt", "content")

        with patch("db.repositories.cleanup.CleanupRepository") as MockRepo:
            mock_repo = MagicMock()
            mock_repo.upsert_hash.side_effect = RuntimeError("DB error")
            mock_repo.get_duplicate_groups.return_value = []
            MockRepo.return_value = mock_repo
            # Should not raise
            result = scan_for_duplicates(str(tmp_path))

        assert result["total_scanned"] == 1


# ── TestDeleteDuplicates ────────────────────────────────────────────────────


class TestDeleteDuplicates:
    """Tests for delete_duplicates() — safe deletion with guards."""

    def _setup_mocks(self, tmp_path):
        """Return common mock patches for delete_duplicates."""
        mock_settings = MagicMock(media_path=str(tmp_path))
        mock_repo = MagicMock()
        return mock_settings, mock_repo

    def test_refuse_when_keep_path_outside_media_path(self, tmp_path):
        """Regression: without this gate the caller could probe arbitrary
        host paths (different errors for "exists" vs "in delete list" vs
        "doesn't exist") AND ask the engine to keep a file outside the
        configured library. Both surfaces are closed by an early
        is_safe_path check on keep_path."""
        # keep_path is OUTSIDE media_path
        outside_keep = str(tmp_path.parent / "outside_keep.srt")
        _write_file(Path(outside_keep), "keep")
        dup = _write_file(tmp_path / "dup.srt", "dup")

        mock_settings, mock_repo = self._setup_mocks(tmp_path)

        with (
            patch("config.get_settings", return_value=mock_settings),
            patch("db.repositories.cleanup.CleanupRepository", return_value=mock_repo),
        ):
            result = delete_duplicates([str(dup)], outside_keep)

        assert result["deleted"] == 0
        assert any(
            "SAFETY" in e and "outside media_path" in e and "keep_path" in e
            for e in result["errors"]
        )
        # The duplicate must NOT have been deleted because the engine
        # rejected the request before iterating file_paths.
        assert dup.exists()
        # The outside file must also still be intact (the engine never
        # touches keep_path; this assertion just guards against future
        # regressions where someone moves the rm into the early path).
        assert Path(outside_keep).exists()

    def test_refuse_when_keep_path_in_deletion_list(self, tmp_path):
        keep = str(tmp_path / "keep.srt")
        _write_file(Path(keep), "keep")

        mock_settings, mock_repo = self._setup_mocks(tmp_path)

        with (
            patch("config.get_settings", return_value=mock_settings),
            patch("db.repositories.cleanup.CleanupRepository", return_value=mock_repo),
        ):
            result = delete_duplicates([keep], keep)

        assert result["deleted"] == 0
        assert any("SAFETY" in e and "keep_path" in e for e in result["errors"])

    def test_refuse_when_keep_path_not_exists(self, tmp_path):
        to_delete = str(tmp_path / "dup.srt")
        keep = str(tmp_path / "nonexistent.srt")
        _write_file(Path(to_delete), "dup")

        mock_settings, mock_repo = self._setup_mocks(tmp_path)

        with (
            patch("config.get_settings", return_value=mock_settings),
            patch("db.repositories.cleanup.CleanupRepository", return_value=mock_repo),
        ):
            result = delete_duplicates([to_delete], keep)

        assert result["deleted"] == 0
        assert any("SAFETY" in e and "does not exist" in e for e in result["errors"])

    def test_successful_deletion(self, tmp_path):
        keep = _write_file(tmp_path / "keep.srt", "content")
        dup = _write_file(tmp_path / "dup.srt", "content")

        mock_settings, mock_repo = self._setup_mocks(tmp_path)

        with (
            patch("config.get_settings", return_value=mock_settings),
            patch("dedup_engine.is_safe_path", return_value=True),
            patch("db.repositories.cleanup.CleanupRepository", return_value=mock_repo),
        ):
            result = delete_duplicates([str(dup)], str(keep))

        assert result["deleted"] == 1
        assert result["bytes_freed"] > 0
        assert not dup.exists()

    def test_multiple_deletions(self, tmp_path):
        keep = _write_file(tmp_path / "keep.srt", "content")
        dup1 = _write_file(tmp_path / "dup1.srt", "content")
        dup2 = _write_file(tmp_path / "dup2.srt", "content")

        mock_settings, mock_repo = self._setup_mocks(tmp_path)

        with (
            patch("config.get_settings", return_value=mock_settings),
            patch("dedup_engine.is_safe_path", return_value=True),
            patch("db.repositories.cleanup.CleanupRepository", return_value=mock_repo),
        ):
            result = delete_duplicates([str(dup1), str(dup2)], str(keep))

        assert result["deleted"] == 2
        assert not dup1.exists()
        assert not dup2.exists()

    def test_skip_symlink(self, tmp_path):
        keep = _write_file(tmp_path / "keep.srt", "content")
        real_file = _write_file(tmp_path / "real.srt", "content")
        link_path = tmp_path / "link.srt"

        try:
            link_path.symlink_to(real_file)
        except OSError:
            pytest.skip("Symlink creation not supported on this platform")

        mock_settings, mock_repo = self._setup_mocks(tmp_path)

        with (
            patch("config.get_settings", return_value=mock_settings),
            patch("dedup_engine.is_safe_path", return_value=True),
            patch("db.repositories.cleanup.CleanupRepository", return_value=mock_repo),
        ):
            result = delete_duplicates([str(link_path)], str(keep))

        assert result["deleted"] == 0
        assert any("symlink" in e.lower() for e in result["errors"])

    def test_skip_path_outside_media_path(self, tmp_path):
        keep = _write_file(tmp_path / "keep.srt", "content")
        outside = _write_file(tmp_path / "dup.srt", "content")

        mock_settings, mock_repo = self._setup_mocks(tmp_path)

        with (
            patch("config.get_settings", return_value=mock_settings),
            patch("dedup_engine.is_safe_path", return_value=False),
            patch("db.repositories.cleanup.CleanupRepository", return_value=mock_repo),
        ):
            result = delete_duplicates([str(outside)], str(keep))

        assert result["deleted"] == 0
        assert any("outside media_path" in e for e in result["errors"])
        # File should still exist since it was skipped
        assert outside.exists()

    def test_skip_nonexistent_file(self, tmp_path):
        keep = _write_file(tmp_path / "keep.srt", "content")
        missing = str(tmp_path / "missing.srt")

        mock_settings, mock_repo = self._setup_mocks(tmp_path)

        with (
            patch("config.get_settings", return_value=mock_settings),
            patch("dedup_engine.is_safe_path", return_value=True),
            patch("db.repositories.cleanup.CleanupRepository", return_value=mock_repo),
        ):
            result = delete_duplicates([missing], str(keep))

        assert result["deleted"] == 0
        assert any("not found" in e.lower() for e in result["errors"])

    def test_db_cleanup_called_after_deletion(self, tmp_path):
        keep = _write_file(tmp_path / "keep.srt", "content")
        dup = _write_file(tmp_path / "dup.srt", "content")

        mock_settings, mock_repo = self._setup_mocks(tmp_path)

        with (
            patch("config.get_settings", return_value=mock_settings),
            patch("dedup_engine.is_safe_path", return_value=True),
            patch("db.repositories.cleanup.CleanupRepository", return_value=mock_repo),
        ):
            delete_duplicates([str(dup)], str(keep))

        mock_repo.delete_hashes_by_paths.assert_called_once_with([str(dup)])
        mock_repo.log_cleanup.assert_called_once()
        log_call_kwargs = mock_repo.log_cleanup.call_args
        assert log_call_kwargs[1]["action_type"] == "dedup_delete"
        assert log_call_kwargs[1]["files_deleted"] == 1

    def test_db_cleanup_not_called_when_nothing_deleted(self, tmp_path):
        keep = _write_file(tmp_path / "keep.srt", "content")
        missing = str(tmp_path / "missing.srt")

        mock_settings, mock_repo = self._setup_mocks(tmp_path)

        with (
            patch("config.get_settings", return_value=mock_settings),
            patch("dedup_engine.is_safe_path", return_value=True),
            patch("db.repositories.cleanup.CleanupRepository", return_value=mock_repo),
        ):
            delete_duplicates([missing], str(keep))

        mock_repo.delete_hashes_by_paths.assert_not_called()
        mock_repo.log_cleanup.assert_not_called()

    def test_db_error_during_cleanup_does_not_raise(self, tmp_path):
        keep = _write_file(tmp_path / "keep.srt", "content")
        dup = _write_file(tmp_path / "dup.srt", "content")

        mock_settings, mock_repo = self._setup_mocks(tmp_path)
        mock_repo.delete_hashes_by_paths.side_effect = RuntimeError("DB failure")

        with (
            patch("config.get_settings", return_value=mock_settings),
            patch("dedup_engine.is_safe_path", return_value=True),
            patch("db.repositories.cleanup.CleanupRepository", return_value=mock_repo),
        ):
            # Should not raise despite DB error
            result = delete_duplicates([str(dup)], str(keep))

        assert result["deleted"] == 1

    def test_os_remove_failure_captured(self, tmp_path):
        keep = _write_file(tmp_path / "keep.srt", "content")
        dup = _write_file(tmp_path / "dup.srt", "content")

        mock_settings, mock_repo = self._setup_mocks(tmp_path)

        with (
            patch("config.get_settings", return_value=mock_settings),
            patch("dedup_engine.is_safe_path", return_value=True),
            patch("db.repositories.cleanup.CleanupRepository", return_value=mock_repo),
            patch("dedup_engine.os.remove", side_effect=PermissionError("locked")),
        ):
            result = delete_duplicates([str(dup)], str(keep))

        assert result["deleted"] == 0
        assert any("Failed to delete" in e for e in result["errors"])

    def test_bytes_freed_accumulated(self, tmp_path):
        keep = _write_file(tmp_path / "keep.srt", "content")
        dup1 = _write_file(tmp_path / "dup1.srt", "aaa")
        dup2 = _write_file(tmp_path / "dup2.srt", "bbbbb")

        size1 = os.path.getsize(str(dup1))
        size2 = os.path.getsize(str(dup2))

        mock_settings, mock_repo = self._setup_mocks(tmp_path)

        with (
            patch("config.get_settings", return_value=mock_settings),
            patch("dedup_engine.is_safe_path", return_value=True),
            patch("db.repositories.cleanup.CleanupRepository", return_value=mock_repo),
        ):
            result = delete_duplicates([str(dup1), str(dup2)], str(keep))

        assert result["bytes_freed"] == size1 + size2


# ── TestScanOrphanedSubtitles ──────────────────────────────────────────────


class TestScanOrphanedSubtitles:
    """Tests for scan_orphaned_subtitles() — subtitle files without matching media."""

    def test_invalid_path_returns_empty(self):
        result = scan_orphaned_subtitles("/nonexistent/path/xyz")
        assert result == []

    def test_no_orphans_when_media_exists(self, tmp_path):
        _write_file(tmp_path / "Episode01.mkv", "video")
        _write_file(tmp_path / "Episode01.en.srt", "subtitle")

        result = scan_orphaned_subtitles(str(tmp_path))
        assert result == []

    def test_detects_orphan_without_media(self, tmp_path):
        _write_file(tmp_path / "Episode01.en.srt", "orphaned subtitle")

        result = scan_orphaned_subtitles(str(tmp_path))
        assert len(result) == 1
        assert result[0]["filename"] == "Episode01.en.srt"

    def test_orphan_result_fields(self, tmp_path):
        sub = _write_file(tmp_path / "orphan.srt", "content")
        result = scan_orphaned_subtitles(str(tmp_path))

        assert len(result) == 1
        assert result[0]["path"] == str(sub)
        assert result[0]["size"] > 0
        assert result[0]["filename"] == "orphan.srt"
        assert result[0]["directory"] == str(tmp_path)

    def test_subtitle_without_language_tag(self, tmp_path):
        _write_file(tmp_path / "Movie.mkv", "video")
        _write_file(tmp_path / "Movie.srt", "subtitle without lang tag")

        result = scan_orphaned_subtitles(str(tmp_path))
        assert result == []

    def test_subtitle_with_language_tag_matched(self, tmp_path):
        _write_file(tmp_path / "MyMovie.mkv", "video")
        _write_file(tmp_path / "MyMovie.de.srt", "german subtitle")
        _write_file(tmp_path / "MyMovie.en.ass", "english subtitle")

        result = scan_orphaned_subtitles(str(tmp_path))
        assert result == []

    def test_multiple_orphans(self, tmp_path):
        _write_file(tmp_path / "Deleted.en.srt", "orphan1")
        _write_file(tmp_path / "Gone.de.ass", "orphan2")

        result = scan_orphaned_subtitles(str(tmp_path))
        assert len(result) == 2

    def test_non_subtitle_files_ignored(self, tmp_path):
        _write_file(tmp_path / "readme.txt", "not a subtitle")
        _write_file(tmp_path / "image.png", "not a subtitle")

        result = scan_orphaned_subtitles(str(tmp_path))
        assert result == []

    def test_scans_subdirectories(self, tmp_path):
        _write_file(tmp_path / "season1" / "ep1.srt", "orphan")
        _write_file(tmp_path / "season2" / "ep2.mkv", "video")
        _write_file(tmp_path / "season2" / "ep2.srt", "has media")

        result = scan_orphaned_subtitles(str(tmp_path))
        assert len(result) == 1
        assert "season1" in result[0]["path"]

    def test_all_media_extensions_recognized(self, tmp_path):
        """Subtitle should not be orphaned if any media extension matches."""
        for ext in MEDIA_EXTENSIONS:
            subdir = tmp_path / f"test_{ext.lstrip('.')}"
            subdir.mkdir()
            _write_file(subdir / f"video{ext}", "video content")
            _write_file(subdir / "video.en.srt", "subtitle content")

        result = scan_orphaned_subtitles(str(tmp_path))
        assert result == []

    def test_case_insensitive_base_matching(self, tmp_path):
        _write_file(tmp_path / "EPISODE.mkv", "video")
        _write_file(tmp_path / "episode.srt", "subtitle")

        result = scan_orphaned_subtitles(str(tmp_path))
        assert result == []

    def test_three_letter_language_tag_stripped(self, tmp_path):
        _write_file(tmp_path / "MyMovie.mkv", "video")
        _write_file(tmp_path / "MyMovie.jpn.ass", "japanese subtitle")

        result = scan_orphaned_subtitles(str(tmp_path))
        assert result == []

    def test_oserror_on_getsize_returns_zero(self, tmp_path):
        _write_file(tmp_path / "orphan.srt", "content")

        with patch("dedup_engine.os.path.getsize", side_effect=OSError("access denied")):
            result = scan_orphaned_subtitles(str(tmp_path))

        assert len(result) == 1
        assert result[0]["size"] == 0


# ── TestGetDiskSpaceAnalysis ────────────────────────────────────────────────


class TestGetDiskSpaceAnalysis:
    """Tests for get_disk_space_analysis() — delegates to CleanupRepository."""

    def test_delegates_to_repo(self):
        fake_stats = {
            "total_files": 42,
            "total_size_bytes": 1024000,
            "by_format": {"srt": {"count": 30, "size": 600000}},
            "duplicate_count": 5,
            "duplicate_size_bytes": 50000,
            "potential_savings_bytes": 25000,
            "recent_cleanups": [],
        }

        with patch("db.repositories.cleanup.CleanupRepository") as MockRepo:
            mock_repo = MagicMock()
            mock_repo.get_disk_stats.return_value = fake_stats
            MockRepo.return_value = mock_repo
            result = get_disk_space_analysis("/some/path")

        assert result == fake_stats
        mock_repo.get_disk_stats.assert_called_once()


# ── TestModuleConstants ─────────────────────────────────────────────────────


class TestModuleConstants:
    """Verify module-level constants are correct."""

    def test_subtitle_extensions(self):
        assert ".srt" in SUBTITLE_EXTENSIONS
        assert ".ass" in SUBTITLE_EXTENSIONS
        assert ".ssa" in SUBTITLE_EXTENSIONS

    def test_media_extensions(self):
        assert ".mkv" in MEDIA_EXTENSIONS
        assert ".mp4" in MEDIA_EXTENSIONS
        assert ".avi" in MEDIA_EXTENSIONS
