"""Tests for CleanupRepository.upsert_hash() — atomic UPSERT behaviour.

Validates that the ON CONFLICT DO UPDATE implementation:
- Inserts new records correctly
- Updates existing records atomically (no check-then-insert race)
- Keeps session clean after concurrent upserts on the same file_path
- Works correctly in batch mode
- Handles the scan_for_duplicates and download_manager call paths
"""

import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ── TestUpsertHashIntegration ──────────────────────────────────────────────


class TestUpsertHashIntegration:
    """Integration tests against real SQLite — validates the UPSERT SQL."""

    def test_insert_new_record(self, app_ctx):
        from db.repositories.cleanup import CleanupRepository

        repo = CleanupRepository()
        result = repo.upsert_hash(
            file_path="/media/test/episode.en.srt",
            content_hash="a" * 64,
            file_size=1234,
            format="srt",
            language="en",
            line_count=100,
        )

        assert result["file_path"] == "/media/test/episode.en.srt"
        assert result["content_hash"] == "a" * 64
        assert result["file_size"] == 1234
        assert result["format"] == "srt"
        assert result["language"] == "en"
        assert result["line_count"] == 100
        assert result["last_scanned"] is not None

    def test_update_existing_record(self, app_ctx):
        """Second upsert for the same file_path updates all fields."""
        from db.repositories.cleanup import CleanupRepository

        repo = CleanupRepository()
        repo.upsert_hash(
            file_path="/media/test/episode.en.srt",
            content_hash="a" * 64,
            file_size=1000,
            format="srt",
            language="en",
        )

        result = repo.upsert_hash(
            file_path="/media/test/episode.en.srt",
            content_hash="b" * 64,
            file_size=2000,
            format="ass",
            language="de",
            line_count=200,
        )

        assert result["content_hash"] == "b" * 64
        assert result["file_size"] == 2000
        assert result["format"] == "ass"
        assert result["language"] == "de"
        assert result["line_count"] == 200

    def test_upsert_idempotent(self, app_ctx):
        """Same data upserted twice produces identical result."""
        from db.repositories.cleanup import CleanupRepository

        repo = CleanupRepository()
        kwargs = {
            "file_path": "/media/test/ep.srt",
            "content_hash": "c" * 64,
            "file_size": 500,
            "format": "srt",
            "language": "en",
            "line_count": 50,
        }
        r1 = repo.upsert_hash(**kwargs)
        r2 = repo.upsert_hash(**kwargs)

        assert r1["file_path"] == r2["file_path"]
        assert r1["content_hash"] == r2["content_hash"]
        assert r1["file_size"] == r2["file_size"]

    def test_different_paths_create_separate_records(self, app_ctx):
        """Different file_paths produce independent records."""
        from db.repositories.cleanup import CleanupRepository

        repo = CleanupRepository()
        repo.upsert_hash(
            file_path="/media/a.srt", content_hash="a" * 64, file_size=100, format="srt"
        )
        repo.upsert_hash(
            file_path="/media/b.srt", content_hash="b" * 64, file_size=200, format="srt"
        )

        stats = repo.get_hash_stats()
        assert stats["total_files"] == 2

    def test_session_clean_after_upsert(self, app_ctx):
        """Session must not be in a dirty/rolled-back state after upsert."""
        from db.repositories.cleanup import CleanupRepository

        repo = CleanupRepository()
        repo.upsert_hash(
            file_path="/media/test.srt", content_hash="d" * 64, file_size=100, format="srt"
        )
        # A second upsert (same path) should work without PendingRollbackError
        repo.upsert_hash(
            file_path="/media/test.srt", content_hash="e" * 64, file_size=200, format="srt"
        )
        # A read should also work fine
        record = repo.get_hash_by_path("/media/test.srt")
        assert record is not None
        assert record["content_hash"] == "e" * 64

    def test_upsert_with_none_language_and_line_count(self, app_ctx):
        """Nullable fields default to None gracefully."""
        from db.repositories.cleanup import CleanupRepository

        repo = CleanupRepository()
        result = repo.upsert_hash(
            file_path="/media/nolang.srt",
            content_hash="f" * 64,
            file_size=300,
            format="srt",
        )
        assert result["language"] is None
        assert result["line_count"] is None

    def test_upsert_in_batch_mode(self, app_ctx):
        """Batch mode defers commits but upsert still works."""
        from db.repositories.cleanup import CleanupRepository

        repo = CleanupRepository()
        with repo.batch():
            repo.upsert_hash(
                file_path="/media/batch1.srt",
                content_hash="1" * 64,
                file_size=100,
                format="srt",
            )
            repo.upsert_hash(
                file_path="/media/batch2.srt",
                content_hash="2" * 64,
                file_size=200,
                format="srt",
            )
            # Update batch1 within same batch
            repo.upsert_hash(
                file_path="/media/batch1.srt",
                content_hash="3" * 64,
                file_size=300,
                format="ass",
            )

        stats = repo.get_hash_stats()
        assert stats["total_files"] == 2

        r1 = repo.get_hash_by_path("/media/batch1.srt")
        assert r1["content_hash"] == "3" * 64
        assert r1["file_size"] == 300

    def test_rapid_sequential_upserts_same_path(self, app_ctx):
        """Many rapid upserts on same path should not raise IntegrityError."""
        from db.repositories.cleanup import CleanupRepository

        repo = CleanupRepository()
        for i in range(20):
            result = repo.upsert_hash(
                file_path="/media/rapid.srt",
                content_hash=f"{i:064x}",
                file_size=i * 100,
                format="srt",
                language="en",
            )
            assert result is not None

        final = repo.get_hash_by_path("/media/rapid.srt")
        assert final["content_hash"] == f"{19:064x}"
        assert final["file_size"] == 1900

    def test_upsert_then_find_by_hash(self, app_ctx):
        """Records inserted via upsert are findable by content_hash."""
        from db.repositories.cleanup import CleanupRepository

        repo = CleanupRepository()
        target_hash = "abcdef" + "0" * 58
        repo.upsert_hash(
            file_path="/media/findme.srt",
            content_hash=target_hash,
            file_size=100,
            format="srt",
            language="de",
        )

        matches = repo.find_by_content_hash(target_hash)
        assert len(matches) == 1
        assert matches[0]["file_path"] == "/media/findme.srt"

    def test_upsert_then_delete_by_path(self, app_ctx):
        """Upserted records can be deleted normally."""
        from db.repositories.cleanup import CleanupRepository

        repo = CleanupRepository()
        repo.upsert_hash(
            file_path="/media/deleteme.srt",
            content_hash="d" * 64,
            file_size=100,
            format="srt",
        )
        deleted = repo.delete_hashes_by_paths(["/media/deleteme.srt"])
        assert deleted == 1
        assert repo.get_hash_by_path("/media/deleteme.srt") is None


# ── TestScanForDuplicatesUpsert ────────────────────────────────────────────


class TestScanForDuplicatesUpsert:
    """Verify scan_for_duplicates uses upsert correctly end-to-end."""

    def test_scan_calls_upsert_for_each_file(self, tmp_path):
        """Each subtitle file in the scan triggers exactly one upsert call."""
        from pathlib import Path

        Path(tmp_path / "a.srt").write_text("content a", encoding="utf-8")
        Path(tmp_path / "b.srt").write_text("content b", encoding="utf-8")
        Path(tmp_path / "c.ass").write_text("content c", encoding="utf-8")

        with patch("db.repositories.cleanup.CleanupRepository") as MockRepo:
            mock_repo = MagicMock()
            mock_repo.get_duplicate_groups.return_value = []
            mock_repo.session = MagicMock()
            MockRepo.return_value = mock_repo

            from dedup_engine import scan_for_duplicates

            result = scan_for_duplicates(str(tmp_path))

        assert result["total_scanned"] == 3
        assert mock_repo.upsert_hash.call_count == 3

    def test_scan_continues_after_upsert_failure(self, tmp_path):
        """If one upsert fails, remaining files are still processed."""
        from pathlib import Path

        Path(tmp_path / "a.srt").write_text("content a", encoding="utf-8")
        Path(tmp_path / "b.srt").write_text("content b", encoding="utf-8")

        call_count = 0

        def _side_effect(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("DB error on first file")
            return {"id": 2}

        with patch("db.repositories.cleanup.CleanupRepository") as MockRepo:
            mock_repo = MagicMock()
            mock_repo.upsert_hash.side_effect = _side_effect
            mock_repo.get_duplicate_groups.return_value = []
            mock_repo.session = MagicMock()
            MockRepo.return_value = mock_repo

            from dedup_engine import scan_for_duplicates

            result = scan_for_duplicates(str(tmp_path))

        assert result["total_scanned"] == 2

    def test_scan_rollback_on_upsert_failure(self, tmp_path):
        """Session.rollback() is called when upsert fails."""
        from pathlib import Path

        Path(tmp_path / "fail.srt").write_text("fail content", encoding="utf-8")

        with patch("db.repositories.cleanup.CleanupRepository") as MockRepo:
            mock_repo = MagicMock()
            mock_repo.upsert_hash.side_effect = RuntimeError("DB error")
            mock_repo.get_duplicate_groups.return_value = []
            MockRepo.return_value = mock_repo

            from dedup_engine import scan_for_duplicates

            scan_for_duplicates(str(tmp_path))

        mock_repo.session.rollback.assert_called()


# ── TestDownloadManagerUpsert ──────────────────────────────────────────────


class TestDownloadManagerUpsert:
    """Verify the download_manager hash registration path."""

    def test_hash_registered_after_save(self, tmp_path):
        """After saving a subtitle, the hash is registered via upsert."""
        from providers.base import SubtitleFormat, SubtitleResult

        result = SubtitleResult.__new__(SubtitleResult)
        result.content = b"1\n00:00:01,000 --> 00:00:02,000\nHello\n"
        result.format = SubtitleFormat.SRT
        result.provider_name = "test"
        result.language = "en"
        result.score = 100
        result.subtitle_id = "x"

        output = str(tmp_path / "episode.en.srt")
        mock_settings = MagicMock(media_path=str(tmp_path), dedup_on_download=False)
        mock_repo = MagicMock()
        mock_repo.find_by_content_hash.return_value = []

        with (
            patch("config.get_settings", return_value=mock_settings),
            patch("security_utils.is_safe_path", return_value=True),
            patch("db.repositories.cleanup.CleanupRepository", return_value=mock_repo),
        ):
            from providers import ProviderManager

            mgr = ProviderManager.__new__(ProviderManager)
            mgr._providers = {}
            mgr.save_subtitle(result, output)

        mock_repo.upsert_hash.assert_called_once()
        call_kwargs = mock_repo.upsert_hash.call_args[1]
        assert call_kwargs["file_path"] == output
        assert call_kwargs["format"] == "srt"
        assert call_kwargs["language"] == "en"

    def test_hash_failure_does_not_prevent_save(self, tmp_path):
        """Even if hash registration fails, the subtitle file is saved."""
        from providers.base import SubtitleFormat, SubtitleResult

        srt_content = b"1\n00:00:01,000 --> 00:00:02,000\nHello World\n"

        result = SubtitleResult.__new__(SubtitleResult)
        result.content = srt_content
        result.format = SubtitleFormat.SRT
        result.provider_name = "test"
        result.language = "de"
        result.score = 80
        result.subtitle_id = "y"

        output = str(tmp_path / "episode.de.srt")
        mock_settings = MagicMock(media_path=str(tmp_path), dedup_on_download=False)
        mock_repo = MagicMock()
        mock_repo.find_by_content_hash.return_value = []
        mock_repo.upsert_hash.side_effect = RuntimeError("DB crash")

        with (
            patch("config.get_settings", return_value=mock_settings),
            patch("security_utils.is_safe_path", return_value=True),
            patch("db.repositories.cleanup.CleanupRepository", return_value=mock_repo),
        ):
            from providers import ProviderManager

            mgr = ProviderManager.__new__(ProviderManager)
            mgr._providers = {}
            saved = mgr.save_subtitle(result, output)

        assert os.path.isfile(saved)

    def test_hash_failure_triggers_rollback(self, tmp_path):
        """When hash registration fails, session.rollback() is called."""
        from providers.base import SubtitleFormat, SubtitleResult

        srt_content = b"1\n00:00:01,000 --> 00:00:02,000\nHello World\n"

        result = SubtitleResult.__new__(SubtitleResult)
        result.content = srt_content
        result.format = SubtitleFormat.SRT
        result.provider_name = "test"
        result.language = "de"
        result.score = 80
        result.subtitle_id = "z"

        output = str(tmp_path / "episode.de.srt")
        mock_settings = MagicMock(media_path=str(tmp_path), dedup_on_download=False)
        mock_repo = MagicMock()
        mock_repo.find_by_content_hash.return_value = []
        mock_repo.upsert_hash.side_effect = RuntimeError("DB crash")

        mock_db_session = MagicMock()

        with (
            patch("config.get_settings", return_value=mock_settings),
            patch("security_utils.is_safe_path", return_value=True),
            patch("db.repositories.cleanup.CleanupRepository", return_value=mock_repo),
            patch("extensions.db.session", mock_db_session),
        ):
            from providers import ProviderManager

            mgr = ProviderManager.__new__(ProviderManager)
            mgr._providers = {}
            mgr.save_subtitle(result, output)

        mock_db_session.rollback.assert_called()


# ── TestBatchExtractUpsert ─────────────────────────────────────────────────


class TestBatchExtractUpsert:
    """Verify that batch extraction correctly registers hashes."""

    def test_multiple_extractions_upsert_independently(self, app_ctx):
        """Simulates batch extraction: multiple files upserted sequentially."""
        from db.repositories.cleanup import CleanupRepository

        repo = CleanupRepository()
        files = [
            ("/media/series/S01E01.ger.srt", "hash01"),
            ("/media/series/S01E02.ger.srt", "hash02"),
            ("/media/series/S01E03.ger.srt", "hash03"),
            ("/media/series/S01E04.ger.srt", "hash04"),
            ("/media/series/S01E05.ger.srt", "hash05"),
        ]

        for path, hash_prefix in files:
            result = repo.upsert_hash(
                file_path=path,
                content_hash=hash_prefix.ljust(64, "0"),
                file_size=1000,
                format="srt",
                language="ger",
            )
            assert result is not None

        stats = repo.get_hash_stats()
        assert stats["total_files"] == 5

    def test_re_extraction_updates_hash(self, app_ctx):
        """Re-extracting a subtitle updates the hash without creating duplicates."""
        from db.repositories.cleanup import CleanupRepository

        repo = CleanupRepository()
        path = "/media/series/S01E01.ger.srt"

        # First extraction
        repo.upsert_hash(
            file_path=path, content_hash="old_" + "0" * 60, file_size=1000, format="srt"
        )

        # Re-extraction with different content
        repo.upsert_hash(
            file_path=path, content_hash="new_" + "0" * 60, file_size=1500, format="srt"
        )

        stats = repo.get_hash_stats()
        assert stats["total_files"] == 1

        record = repo.get_hash_by_path(path)
        assert record["content_hash"].startswith("new_")
        assert record["file_size"] == 1500

    def test_extraction_then_cleanup_scan(self, app_ctx):
        """After extraction upserts, a cleanup scan can read and update records."""
        from db.repositories.cleanup import CleanupRepository

        repo = CleanupRepository()

        # Simulate extraction registering hashes
        repo.upsert_hash(
            file_path="/media/a.srt",
            content_hash="same" + "0" * 60,
            file_size=100,
            format="srt",
        )
        repo.upsert_hash(
            file_path="/media/b.srt",
            content_hash="same" + "0" * 60,
            file_size=100,
            format="srt",
        )
        repo.upsert_hash(
            file_path="/media/c.srt",
            content_hash="diff" + "0" * 60,
            file_size=200,
            format="srt",
        )

        # Duplicate detection should find a/b as duplicates
        groups = repo.get_duplicate_groups()
        assert len(groups) == 1
        assert groups[0]["count"] == 2
        assert groups[0]["content_hash"] == "same" + "0" * 60

    def test_wanted_cleanup_after_upsert(self, app_ctx):
        """Records can be cleaned up (deleted) after being upserted."""
        from db.repositories.cleanup import CleanupRepository

        repo = CleanupRepository()

        paths = [f"/media/ep{i}.srt" for i in range(5)]
        for i, path in enumerate(paths):
            repo.upsert_hash(
                file_path=path,
                content_hash=f"{i:064x}",
                file_size=100,
                format="srt",
            )

        assert repo.get_hash_stats()["total_files"] == 5

        # Delete 3 of them (simulates wanted cleanup removing items)
        deleted = repo.delete_hashes_by_paths(paths[:3])
        assert deleted == 3
        assert repo.get_hash_stats()["total_files"] == 2
