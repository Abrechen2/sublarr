"""Tests for wanted_search/post_processor.py — post-download processing helpers.

Covers: _try_auto_sync, _process_forced_wanted_item, download_specific_for_item.
All external dependencies (DB, file I/O, providers, translator) are mocked.
"""

import sys
from importlib import reload
from unittest.mock import MagicMock, patch

import pytest

from error_handler import DuplicateSubtitleError
from providers.base import SubtitleFormat, SubtitleResult

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_settings(**overrides):
    """Create a mock settings object with sensible defaults."""
    s = MagicMock()
    s.auto_sync_after_download = overrides.get("auto_sync_after_download", False)
    s.auto_sync_engine = overrides.get("auto_sync_engine", "ffsubsync")
    s.target_language = overrides.get("target_language", "de")
    s.target_language_name = overrides.get("target_language_name", "German")
    s.source_language = overrides.get("source_language", "en")
    return s


def _make_result(
    provider="test_provider",
    subtitle_id="sub123",
    language="en",
    fmt=SubtitleFormat.SRT,
    content=b"subtitle content",
    score=80,
):
    """Create a SubtitleResult with reasonable defaults."""
    return SubtitleResult(
        provider_name=provider,
        subtitle_id=subtitle_id,
        language=language,
        format=fmt,
        content=content,
        score=score,
    )


def _make_wanted_item(**overrides):
    """Create a wanted item dict with sensible defaults."""
    item = {
        "id": 1,
        "file_path": "/media/anime/show/S01E01.mkv",
        "item_type": "episode",
        "target_language": "de",
        "sonarr_series_id": 10,
        "sonarr_episode_id": 100,
        "radarr_movie_id": None,
        "title": "Test Show",
        "season": 1,
        "episode": 1,
    }
    item.update(overrides)
    return item


# ===========================================================================
# _try_auto_sync
# ===========================================================================


class TestTryAutoSync:
    """Tests for _try_auto_sync — conditional auto-sync after download."""

    def test_disabled_does_nothing(self):
        """When auto_sync_after_download is False, no sync is attempted."""
        settings = _make_settings(auto_sync_after_download=False)
        from wanted_search.post_processor import _try_auto_sync

        _try_auto_sync("/path/sub.srt", "/path/video.mkv", settings)

    def test_alass_engine_skipped(self):
        """alass requires a reference track so auto-sync is skipped."""
        settings = _make_settings(auto_sync_after_download=True, auto_sync_engine="alass")
        from wanted_search.post_processor import _try_auto_sync

        _try_auto_sync("/path/sub.srt", "/path/video.mkv", settings)

    def test_ffsubsync_called(self, tmp_path):
        """When enabled + ffsubsync engine, sync_with_ffsubsync is invoked."""
        settings = _make_settings(auto_sync_after_download=True, auto_sync_engine="ffsubsync")
        # _try_auto_sync skips when the files do not exist on disk — provide
        # real tmp files so the guard lets the call through.
        sub = tmp_path / "sub.srt"
        sub.write_text("1\n00:00:01,000 --> 00:00:02,000\nHi\n")
        vid = tmp_path / "video.mkv"
        vid.touch()

        mock_sync_module = MagicMock()
        mock_sync_module.SyncUnavailableError = type("SyncUnavailableError", (Exception,), {})

        with patch.dict("sys.modules", {"services.video_sync": mock_sync_module}):
            import wanted_search.post_processor as mod

            reload(mod)
            mod._try_auto_sync(str(sub), str(vid), settings)

        mock_sync_module.sync_with_ffsubsync.assert_called_once_with(str(sub), str(vid))

    def test_ffsubsync_sync_unavailable_error_logged(self, tmp_path):
        """SyncUnavailableError is caught and logged, not propagated."""
        settings = _make_settings(auto_sync_after_download=True, auto_sync_engine="ffsubsync")
        sub = tmp_path / "sub.srt"
        sub.write_text("1\n00:00:01,000 --> 00:00:02,000\nHi\n")
        vid = tmp_path / "video.mkv"
        vid.touch()

        mock_sync_module = MagicMock()

        class FakeSyncUnavailableError(Exception):
            pass

        mock_sync_module.SyncUnavailableError = FakeSyncUnavailableError
        mock_sync_module.sync_with_ffsubsync.side_effect = FakeSyncUnavailableError("not installed")

        with patch.dict("sys.modules", {"services.video_sync": mock_sync_module}):
            import wanted_search.post_processor as mod

            reload(mod)
            # Should not raise
            mod._try_auto_sync(str(sub), str(vid), settings)

    def test_ffsubsync_generic_error_logged(self, tmp_path):
        """Generic exceptions from ffsubsync are caught and logged."""
        settings = _make_settings(auto_sync_after_download=True, auto_sync_engine="ffsubsync")
        sub = tmp_path / "sub.srt"
        sub.write_text("1\n00:00:01,000 --> 00:00:02,000\nHi\n")
        vid = tmp_path / "video.mkv"
        vid.touch()

        mock_sync_module = MagicMock()
        mock_sync_module.SyncUnavailableError = type("SyncUnavailableError", (Exception,), {})
        mock_sync_module.sync_with_ffsubsync.side_effect = RuntimeError("sync crashed")

        with patch.dict("sys.modules", {"services.video_sync": mock_sync_module}):
            import wanted_search.post_processor as mod

            reload(mod)
            # Should not raise
            mod._try_auto_sync(str(sub), str(vid), settings)

    def test_missing_subtitle_path_skipped_with_warning(self, tmp_path, caplog):
        """Guard test: if the subtitle path does not exist on disk, skip cleanly."""
        import logging

        settings = _make_settings(auto_sync_after_download=True, auto_sync_engine="ffsubsync")
        vid = tmp_path / "video.mkv"
        vid.touch()
        ghost = str(tmp_path / "ghost.de.ass")  # never created

        from wanted_search.post_processor import _try_auto_sync

        with caplog.at_level(logging.WARNING, logger="wanted_search.post_processor"):
            _try_auto_sync(ghost, str(vid), settings)

        assert any("subtitle path does not exist" in rec.message for rec in caplog.records), (
            "expected guard WARNING for missing subtitle path"
        )

    def test_missing_auto_sync_attr_treated_as_false(self):
        """If settings lacks auto_sync_after_download, treat as disabled."""
        settings = MagicMock(spec=[])  # empty spec -> getattr returns default
        from wanted_search.post_processor import _try_auto_sync

        _try_auto_sync("/path/sub.srt", "/path/video.mkv", settings)


# ===========================================================================
# _process_forced_wanted_item
# ===========================================================================


@patch("wanted_search.post_processor.delete_wanted_item")
@patch("wanted_search.post_processor.record_subtitle_download")
@patch("wanted_search.post_processor.get_forced_output_path", return_value="/out/forced.srt")
@patch("wanted_search.post_processor.build_query_from_wanted")
class TestProcessForcedWantedItem:
    """Tests for _process_forced_wanted_item — forced subtitle search + download."""

    def test_target_lang_found_ass(self, mock_build, mock_forced_path, mock_record, mock_delete):
        """First ASS search succeeds -> returns 'found' with forced=True."""
        from wanted_search.post_processor import _process_forced_wanted_item

        mock_build.return_value = MagicMock()
        result = _make_result(fmt=SubtitleFormat.ASS)
        manager = MagicMock()
        manager.search_and_download_best.return_value = result
        manager.save_subtitle.return_value = "/out/forced.ass"

        item = _make_wanted_item()
        out = _process_forced_wanted_item(item, 1, "de", manager)

        assert out["status"] == "found"
        assert out["forced"] is True
        assert out["wanted_id"] == 1
        mock_delete.assert_called_once_with(1)
        mock_record.assert_called_once()

    def test_target_lang_found_srt_after_ass_fails(
        self, mock_build, mock_forced_path, mock_record, mock_delete
    ):
        """ASS returns None, SRT succeeds -> returns 'found'."""
        from wanted_search.post_processor import _process_forced_wanted_item

        mock_build.return_value = MagicMock()
        srt_result = _make_result(fmt=SubtitleFormat.SRT)

        manager = MagicMock()
        manager.search_and_download_best.side_effect = [None, srt_result]
        manager.save_subtitle.return_value = "/out/forced.srt"

        item = _make_wanted_item()
        out = _process_forced_wanted_item(item, 1, "de", manager)

        assert out["status"] == "found"
        assert out["forced"] is True

    def test_duplicate_subtitle_returns_duplicate_skipped(
        self, mock_build, mock_forced_path, mock_record, mock_delete
    ):
        """DuplicateSubtitleError -> returns 'duplicate_skipped'."""
        from wanted_search.post_processor import _process_forced_wanted_item

        mock_build.return_value = MagicMock()
        result = _make_result(fmt=SubtitleFormat.ASS)

        manager = MagicMock()
        manager.search_and_download_best.return_value = result
        dup = DuplicateSubtitleError("hash1", "/existing/path.ass", "/new/path.ass")
        manager.save_subtitle.side_effect = dup

        item = _make_wanted_item()
        out = _process_forced_wanted_item(item, 1, "de", manager)

        assert out["status"] == "duplicate_skipped"
        assert out["output_path"] == "/existing/path.ass"
        mock_delete.assert_called_once_with(1)

    def test_save_oserror_tries_next_format(
        self, mock_build, mock_forced_path, mock_record, mock_delete
    ):
        """OSError on save -> tries next format."""
        from wanted_search.post_processor import _process_forced_wanted_item

        mock_build.return_value = MagicMock()
        ass_result = _make_result(fmt=SubtitleFormat.ASS)
        srt_result = _make_result(fmt=SubtitleFormat.SRT)

        manager = MagicMock()
        manager.search_and_download_best.side_effect = [ass_result, srt_result]
        manager.save_subtitle.side_effect = [OSError("disk full"), "/out/forced.srt"]

        item = _make_wanted_item()
        out = _process_forced_wanted_item(item, 1, "de", manager)

        assert out["status"] == "found"

    @patch("wanted_search.post_processor.get_settings")
    @patch("wanted_search.post_processor.update_wanted_status")
    def test_no_forced_found_returns_failed(
        self,
        mock_update_status,
        mock_get_settings,
        mock_build,
        mock_forced_path,
        mock_record,
        mock_delete,
    ):
        """No forced subtitle found from any provider -> returns 'failed'."""
        from wanted_search.post_processor import _process_forced_wanted_item

        mock_get_settings.return_value = _make_settings()
        mock_build.return_value = MagicMock()

        manager = MagicMock()
        manager.search_and_download_best.return_value = None

        item = _make_wanted_item()
        out = _process_forced_wanted_item(item, 1, "de", manager)

        assert out["status"] == "failed"
        assert "No forced subtitle found" in out["error"]
        assert out["forced"] is True
        mock_update_status.assert_called_once_with(1, "failed", error=out["error"])

    def test_search_exception_handled_gracefully(
        self, mock_build, mock_forced_path, mock_record, mock_delete
    ):
        """Exception during search is caught, loop continues."""
        from wanted_search.post_processor import _process_forced_wanted_item

        mock_build.return_value = MagicMock()

        manager = MagicMock()
        manager.search_and_download_best.side_effect = RuntimeError("network error")

        with (
            patch("wanted_search.post_processor.get_settings", return_value=_make_settings()),
            patch("wanted_search.post_processor.update_wanted_status"),
        ):
            item = _make_wanted_item()
            out = _process_forced_wanted_item(item, 1, "de", manager)

        assert out["status"] == "failed"

    @patch("wanted_search.post_processor.get_settings")
    def test_source_lang_fallback_found(
        self,
        mock_get_settings,
        mock_build,
        mock_forced_path,
        mock_record,
        mock_delete,
    ):
        """Target lang fails, source lang forced subtitle found."""
        from wanted_search.post_processor import _process_forced_wanted_item

        mock_get_settings.return_value = _make_settings(source_language="en")
        mock_build.return_value = MagicMock()
        en_result = _make_result(fmt=SubtitleFormat.ASS, language="en")

        manager = MagicMock()
        manager.search_and_download_best.side_effect = [None, None, en_result]
        manager.save_subtitle.return_value = "/out/forced.en.ass"

        item = _make_wanted_item()
        out = _process_forced_wanted_item(item, 1, "de", manager)

        assert out["status"] == "found"
        assert out["forced"] is True
        mock_delete.assert_called_once_with(1)

    @patch("wanted_search.post_processor.get_settings")
    def test_source_lang_duplicate_returns_duplicate_skipped(
        self,
        mock_get_settings,
        mock_build,
        mock_forced_path,
        mock_record,
        mock_delete,
    ):
        """Source lang forced subtitle save raises DuplicateSubtitleError."""
        from wanted_search.post_processor import _process_forced_wanted_item

        mock_get_settings.return_value = _make_settings(source_language="en")
        mock_build.return_value = MagicMock()
        en_result = _make_result(fmt=SubtitleFormat.ASS, language="en")

        manager = MagicMock()
        manager.search_and_download_best.side_effect = [None, None, en_result]
        dup = DuplicateSubtitleError("hash1", "/existing/en.ass", "/new/en.ass")
        manager.save_subtitle.side_effect = dup

        item = _make_wanted_item()
        out = _process_forced_wanted_item(item, 1, "de", manager)

        assert out["status"] == "duplicate_skipped"
        assert out["output_path"] == "/existing/en.ass"

    def test_unknown_format_uses_requested_format_ext(
        self, mock_build, mock_forced_path, mock_record, mock_delete
    ):
        """When result.format is UNKNOWN, the requested format ext is used."""
        from wanted_search.post_processor import _process_forced_wanted_item

        mock_build.return_value = MagicMock()
        result = _make_result(fmt=SubtitleFormat.UNKNOWN)

        manager = MagicMock()
        manager.search_and_download_best.return_value = result
        manager.save_subtitle.return_value = "/out/forced.ass"

        item = _make_wanted_item()
        out = _process_forced_wanted_item(item, 1, "de", manager)

        assert out["status"] == "found"
        mock_forced_path.assert_called()

    @patch("wanted_search.post_processor.get_settings")
    def test_source_lang_save_oserror_tries_next_format(
        self,
        mock_get_settings,
        mock_build,
        mock_forced_path,
        mock_record,
        mock_delete,
    ):
        """Source lang save fails with OSError -> tries SRT format next."""
        from wanted_search.post_processor import _process_forced_wanted_item

        mock_get_settings.return_value = _make_settings(source_language="en")
        mock_build.return_value = MagicMock()
        ass_result = _make_result(fmt=SubtitleFormat.ASS, language="en")
        srt_result = _make_result(fmt=SubtitleFormat.SRT, language="en")

        manager = MagicMock()
        # Target: None x2; Source: ASS found, SRT found
        manager.search_and_download_best.side_effect = [None, None, ass_result, srt_result]
        # ASS save fails, SRT save succeeds
        manager.save_subtitle.side_effect = [OSError("disk full"), "/out/forced.en.srt"]

        item = _make_wanted_item()
        out = _process_forced_wanted_item(item, 1, "de", manager)

        assert out["status"] == "found"

    @patch("wanted_search.post_processor.get_settings")
    def test_source_lang_search_exception_continues(
        self,
        mock_get_settings,
        mock_build,
        mock_forced_path,
        mock_record,
        mock_delete,
    ):
        """Source lang search exception -> continues to next format."""
        from wanted_search.post_processor import _process_forced_wanted_item

        mock_get_settings.return_value = _make_settings(source_language="en")
        mock_build.return_value = MagicMock()

        srt_result = _make_result(fmt=SubtitleFormat.SRT, language="en")
        manager = MagicMock()
        # Target: None x2; Source ASS: exception; Source SRT: found
        manager.search_and_download_best.side_effect = [
            None,
            None,
            RuntimeError("network"),
            srt_result,
        ]
        manager.save_subtitle.return_value = "/out/forced.en.srt"

        item = _make_wanted_item()
        out = _process_forced_wanted_item(item, 1, "de", manager)

        assert out["status"] == "found"


# ===========================================================================
# download_specific_for_item
# ===========================================================================


class TestDownloadSpecificForItem:
    """Tests for download_specific_for_item — interactive subtitle download.

    Uses module reload with patched sys.modules to handle lazy imports
    from the translator module. The _patched_module context manager keeps
    the translator mock active for the duration of each test.
    """

    from contextlib import contextmanager

    @contextmanager
    def _patched_module(self, translator_mock=None):
        """Yield post_processor reloaded with a mocked translator module.

        The translator patch stays active for the entire context block,
        so lazy imports inside download_specific_for_item resolve to the mock.
        """
        if translator_mock is None:
            translator_mock = MagicMock()
            translator_mock.get_output_path_for_lang.return_value = "/out/sub.srt"
            translator_mock.get_forced_output_path.return_value = "/out/forced.srt"
        with patch.dict("sys.modules", {"translator": translator_mock}):
            import wanted_search.post_processor as mod

            reload(mod)
            yield mod

    def test_item_not_found(self):
        """Returns error when wanted item does not exist."""
        with (
            self._patched_module() as mod,
            patch.object(mod, "get_wanted_item", return_value=None),
        ):
            out = mod.download_specific_for_item(999, "prov", "sub1", "en", False)

        assert out["success"] is False
        assert "not found" in out["error"].lower()

    def test_search_fails(self):
        """Returns error when provider search raises."""
        manager = MagicMock()
        manager.search.side_effect = RuntimeError("timeout")

        with (
            self._patched_module() as mod,
            patch.object(mod, "get_wanted_item", return_value=_make_wanted_item()),
            patch.object(mod, "get_settings", return_value=_make_settings()),
            patch.object(mod, "build_query_from_wanted", return_value=MagicMock()),
            patch.object(mod, "get_provider_manager", return_value=manager),
        ):
            out = mod.download_specific_for_item(1, "prov", "sub1", "en", False)

        assert out["success"] is False
        assert "Search failed" in out["error"]

    def test_result_not_found_in_search(self):
        """Returns error when specific subtitle_id not in search results."""
        other = _make_result(provider="other_prov", subtitle_id="other_id")
        manager = MagicMock()
        manager.search.return_value = [other]
        manager.download.return_value = b"content"

        with (
            self._patched_module() as mod,
            patch.object(mod, "get_wanted_item", return_value=_make_wanted_item()),
            patch.object(mod, "get_settings", return_value=_make_settings()),
            patch.object(mod, "build_query_from_wanted", return_value=MagicMock()),
            patch.object(mod, "get_provider_manager", return_value=manager),
        ):
            out = mod.download_specific_for_item(1, "test_provider", "sub123", "en", False)

        assert out["success"] is False
        assert "not found" in out["error"].lower()

    def test_download_fails(self):
        """Returns error when download returns None."""
        result = _make_result()
        manager = MagicMock()
        manager.search.return_value = [result]
        manager.download.return_value = None

        with (
            self._patched_module() as mod,
            patch.object(mod, "get_wanted_item", return_value=_make_wanted_item()),
            patch.object(mod, "get_settings", return_value=_make_settings()),
            patch.object(mod, "build_query_from_wanted", return_value=MagicMock()),
            patch.object(mod, "get_provider_manager", return_value=manager),
        ):
            out = mod.download_specific_for_item(1, "test_provider", "sub123", "en", False)

        assert out["success"] is False
        assert "Download failed" in out["error"]

    def test_download_only_no_translate(self):
        """translate=False: download, save, delete wanted item."""
        mock_translator = MagicMock()
        mock_translator.get_output_path_for_lang.return_value = "/out/sub.srt"

        result = _make_result()
        manager = MagicMock()
        manager.search.return_value = [result]
        manager.download.return_value = result.content
        manager.save_subtitle.return_value = "/out/sub.srt"

        mock_delete = MagicMock()
        mock_sync = MagicMock()
        mock_record = MagicMock()

        with (
            self._patched_module(mock_translator) as mod,
            patch.object(mod, "get_wanted_item", return_value=_make_wanted_item()),
            patch.object(mod, "get_settings", return_value=_make_settings()),
            patch.object(mod, "build_query_from_wanted", return_value=MagicMock()),
            patch.object(mod, "get_provider_manager", return_value=manager),
            patch.object(mod, "delete_wanted_item", mock_delete),
            patch.object(mod, "_try_auto_sync", mock_sync),
            patch.object(mod, "record_subtitle_download", mock_record),
        ):
            out = mod.download_specific_for_item(1, "test_provider", "sub123", "en", False)

        assert out["success"] is True
        assert out["translated"] is False
        assert out["format"] == "srt"
        mock_delete.assert_called_once_with(1)
        mock_sync.assert_called_once()
        mock_record.assert_called_once()

    def test_download_only_same_lang_no_translate(self):
        """translate=True but language == item_lang: no translation, just save."""
        mock_translator = MagicMock()
        mock_translator.get_output_path_for_lang.return_value = "/out/sub.de.srt"

        result = _make_result(language="de")
        manager = MagicMock()
        manager.search.return_value = [result]
        manager.download.return_value = result.content
        manager.save_subtitle.return_value = "/out/sub.de.srt"

        with (
            self._patched_module(mock_translator) as mod,
            patch.object(
                mod, "get_wanted_item", return_value=_make_wanted_item(target_language="de")
            ),
            patch.object(mod, "get_settings", return_value=_make_settings(target_language="de")),
            patch.object(mod, "build_query_from_wanted", return_value=MagicMock()),
            patch.object(mod, "get_provider_manager", return_value=manager),
            patch.object(mod, "delete_wanted_item"),
            patch.object(mod, "_try_auto_sync"),
            patch.object(mod, "record_subtitle_download"),
        ):
            out = mod.download_specific_for_item(1, "test_provider", "sub123", "de", True)

        assert out["success"] is True
        assert out["translated"] is False

    def test_download_only_duplicate(self):
        """DuplicateSubtitleError on save -> returns success with duplicate_skipped."""
        mock_translator = MagicMock()
        mock_translator.get_output_path_for_lang.return_value = "/out/sub.srt"

        result = _make_result()
        dup = DuplicateSubtitleError("hash1", "/existing.srt", "/new.srt")
        manager = MagicMock()
        manager.search.return_value = [result]
        manager.download.return_value = result.content
        manager.save_subtitle.side_effect = dup

        mock_delete = MagicMock()
        mock_sync = MagicMock()

        with (
            self._patched_module(mock_translator) as mod,
            patch.object(mod, "get_wanted_item", return_value=_make_wanted_item()),
            patch.object(mod, "get_settings", return_value=_make_settings()),
            patch.object(mod, "build_query_from_wanted", return_value=MagicMock()),
            patch.object(mod, "get_provider_manager", return_value=manager),
            patch.object(mod, "delete_wanted_item", mock_delete),
            patch.object(mod, "_try_auto_sync", mock_sync),
            patch.object(mod, "record_subtitle_download"),
        ):
            out = mod.download_specific_for_item(1, "test_provider", "sub123", "en", False)

        assert out["success"] is True
        assert out["duplicate_skipped"] is True
        assert out["path"] == "/existing.srt"
        mock_delete.assert_called_once_with(1)
        mock_sync.assert_called_once()

    def test_download_only_save_error(self):
        """OSError on save -> returns failure."""
        mock_translator = MagicMock()
        mock_translator.get_output_path_for_lang.return_value = "/out/sub.srt"

        result = _make_result()
        manager = MagicMock()
        manager.search.return_value = [result]
        manager.download.return_value = result.content
        manager.save_subtitle.side_effect = OSError("permission denied")

        with (
            self._patched_module(mock_translator) as mod,
            patch.object(mod, "get_wanted_item", return_value=_make_wanted_item()),
            patch.object(mod, "get_settings", return_value=_make_settings()),
            patch.object(mod, "build_query_from_wanted", return_value=MagicMock()),
            patch.object(mod, "get_provider_manager", return_value=manager),
            patch.object(mod, "record_subtitle_download"),
        ):
            out = mod.download_specific_for_item(1, "test_provider", "sub123", "en", False)

        assert out["success"] is False
        assert "save subtitle" in out["error"].lower()

    def test_translate_srt_success(self):
        """translate=True with SRT: saves source, runs translation, cleans up."""
        translate_result = {
            "success": True,
            "output_path": "/out/sub.de.ass",
            "stats": {"skipped": False, "format": "ass", "source": "provider_interactive"},
        }
        mock_translator = MagicMock()
        mock_translator.get_output_path_for_lang.return_value = "/out/sub.de.srt"
        mock_translator.translate_srt_from_file.return_value = translate_result

        result = _make_result(fmt=SubtitleFormat.SRT)
        manager = MagicMock()
        manager.search.return_value = [result]
        manager.download.return_value = result.content
        manager.save_subtitle.return_value = "/tmp/source.en.srt"

        mock_sync = MagicMock()
        mock_finalize = MagicMock()

        with (
            self._patched_module(mock_translator) as mod,
            patch.object(
                mod, "get_wanted_item", return_value=_make_wanted_item(target_language="de")
            ),
            patch.object(mod, "get_settings", return_value=_make_settings(target_language="de")),
            patch.object(mod, "build_query_from_wanted", return_value=MagicMock()),
            patch.object(mod, "get_provider_manager", return_value=manager),
            patch.object(mod, "record_subtitle_download"),
            patch.object(mod, "delete_wanted_item"),
            patch("services.mt_provisional.finalize_translation", mock_finalize),
            patch.object(mod, "_try_auto_sync", mock_sync),
            patch.object(mod, "create_job", return_value={"id": "job1"}),
            patch.object(mod, "update_job"),
            patch.object(mod, "record_stat"),
            patch("os.path.exists", return_value=True),
            patch("os.remove"),
        ):
            out = mod.download_specific_for_item(1, "test_provider", "sub123", "en", True)

        assert out["success"] is True
        assert out["translated"] is True
        assert out["format"] == "ass"
        # download_specific_for_item now delegates the keep-provisional-vs-delete
        # decision to services.mt_provisional.finalize_translation (source SRT ->
        # actual_source_path ends in ".srt" -> mt_fmt="srt").
        mock_finalize.assert_called_once_with(
            1, _make_wanted_item(target_language="de"), "/out/sub.de.ass", "de", "srt"
        )
        mock_sync.assert_called_once()

    def test_translate_ass_success(self):
        """translate=True with ASS: saves source, runs _translate_external_ass."""
        translate_result = {
            "success": True,
            "output_path": "/out/sub.de.ass",
            "stats": {"skipped": False, "format": "ass", "source": "provider_interactive"},
        }
        mock_translator = MagicMock()
        mock_translator.get_output_path_for_lang.return_value = "/out/sub.de.ass"
        mock_translator._translate_external_ass.return_value = translate_result

        result = _make_result(fmt=SubtitleFormat.ASS)
        manager = MagicMock()
        manager.search.return_value = [result]
        manager.download.return_value = result.content
        manager.save_subtitle.return_value = "/tmp/source.en.ass"

        with (
            self._patched_module(mock_translator) as mod,
            patch.object(
                mod, "get_wanted_item", return_value=_make_wanted_item(target_language="de")
            ),
            patch.object(mod, "get_settings", return_value=_make_settings(target_language="de")),
            patch.object(mod, "build_query_from_wanted", return_value=MagicMock()),
            patch.object(mod, "get_provider_manager", return_value=manager),
            patch.object(mod, "record_subtitle_download"),
            patch.object(mod, "delete_wanted_item"),
            patch("services.mt_provisional.finalize_translation"),
            patch.object(mod, "_try_auto_sync"),
            patch.object(mod, "create_job", return_value={"id": "job1"}),
            patch.object(mod, "update_job"),
            patch.object(mod, "record_stat"),
            patch("os.path.exists", return_value=True),
            patch("os.remove"),
        ):
            out = mod.download_specific_for_item(1, "test_provider", "sub123", "en", True)

        assert out["success"] is True
        assert out["translated"] is True

    def test_translate_exception_returns_error(self):
        """Translation exception -> returns failure, records stat, cleans up temp."""
        mock_translator = MagicMock()
        mock_translator.get_output_path_for_lang.return_value = "/out/sub.de.srt"
        mock_translator.translate_srt_from_file.side_effect = RuntimeError("LLM down")

        result = _make_result(fmt=SubtitleFormat.SRT)
        manager = MagicMock()
        manager.search.return_value = [result]
        manager.download.return_value = result.content
        manager.save_subtitle.return_value = "/tmp/source.en.srt"

        mock_update_job = MagicMock()
        mock_record_stat = MagicMock()

        with (
            self._patched_module(mock_translator) as mod,
            patch.object(
                mod, "get_wanted_item", return_value=_make_wanted_item(target_language="de")
            ),
            patch.object(mod, "get_settings", return_value=_make_settings(target_language="de")),
            patch.object(mod, "build_query_from_wanted", return_value=MagicMock()),
            patch.object(mod, "get_provider_manager", return_value=manager),
            patch.object(mod, "record_subtitle_download"),
            patch.object(mod, "delete_wanted_item"),
            patch.object(mod, "_try_auto_sync"),
            patch.object(mod, "create_job", return_value={"id": "job1"}),
            patch.object(mod, "update_job", mock_update_job),
            patch.object(mod, "record_stat", mock_record_stat),
            patch("os.path.exists", return_value=True),
            patch("os.remove"),
        ):
            out = mod.download_specific_for_item(1, "test_provider", "sub123", "en", True)

        assert out["success"] is False
        assert "Translation failed" in out["error"]
        # update_job called twice: once for "running", once for "failed"
        assert mock_update_job.call_count == 2
        mock_record_stat.assert_called_once_with(success=False)

    def test_translate_returns_unsuccessful_result(self):
        """Translation returns {success: False} -> records failure."""
        translate_result = {"success": False, "error": "Low quality translation"}
        mock_translator = MagicMock()
        mock_translator.get_output_path_for_lang.return_value = "/out/sub.de.srt"
        mock_translator.translate_srt_from_file.return_value = translate_result

        result = _make_result(fmt=SubtitleFormat.SRT)
        manager = MagicMock()
        manager.search.return_value = [result]
        manager.download.return_value = result.content
        manager.save_subtitle.return_value = "/tmp/source.en.srt"

        mock_record_stat = MagicMock()

        with (
            self._patched_module(mock_translator) as mod,
            patch.object(
                mod, "get_wanted_item", return_value=_make_wanted_item(target_language="de")
            ),
            patch.object(mod, "get_settings", return_value=_make_settings(target_language="de")),
            patch.object(mod, "build_query_from_wanted", return_value=MagicMock()),
            patch.object(mod, "get_provider_manager", return_value=manager),
            patch.object(mod, "record_subtitle_download"),
            patch.object(mod, "delete_wanted_item"),
            patch.object(mod, "_try_auto_sync"),
            patch.object(mod, "create_job", return_value={"id": "job1"}),
            patch.object(mod, "update_job"),
            patch.object(mod, "record_stat", mock_record_stat),
            patch("os.path.exists", return_value=False),
            patch("os.remove"),
        ):
            out = mod.download_specific_for_item(1, "test_provider", "sub123", "en", True)

        assert out["success"] is False
        assert "Low quality translation" in out["error"]
        mock_record_stat.assert_called_once_with(success=False)

    def test_translate_returns_none_result(self):
        """Translation returns None -> records failure with generic message."""
        mock_translator = MagicMock()
        mock_translator.get_output_path_for_lang.return_value = "/out/sub.de.srt"
        mock_translator.translate_srt_from_file.return_value = None

        result = _make_result(fmt=SubtitleFormat.SRT)
        manager = MagicMock()
        manager.search.return_value = [result]
        manager.download.return_value = result.content
        manager.save_subtitle.return_value = "/tmp/source.en.srt"

        with (
            self._patched_module(mock_translator) as mod,
            patch.object(
                mod, "get_wanted_item", return_value=_make_wanted_item(target_language="de")
            ),
            patch.object(mod, "get_settings", return_value=_make_settings(target_language="de")),
            patch.object(mod, "build_query_from_wanted", return_value=MagicMock()),
            patch.object(mod, "get_provider_manager", return_value=manager),
            patch.object(mod, "record_subtitle_download"),
            patch.object(mod, "delete_wanted_item"),
            patch.object(mod, "_try_auto_sync"),
            patch.object(mod, "create_job", return_value={"id": "job1"}),
            patch.object(mod, "update_job"),
            patch.object(mod, "record_stat"),
            patch("os.path.exists", return_value=False),
            patch("os.remove"),
        ):
            out = mod.download_specific_for_item(1, "test_provider", "sub123", "en", True)

        assert out["success"] is False
        assert "Translation failed" in out["error"]

    def test_translate_save_duplicate_uses_existing_path(self):
        """DuplicateSubtitleError on save during translate path uses existing_path."""
        translate_result = {
            "success": True,
            "output_path": "/out/sub.de.ass",
            "stats": {"skipped": False, "format": "ass", "source": "provider_interactive"},
        }
        mock_translator = MagicMock()
        mock_translator.get_output_path_for_lang.return_value = "/out/sub.de.srt"
        mock_translator.translate_srt_from_file.return_value = translate_result

        result = _make_result(fmt=SubtitleFormat.SRT)
        dup = DuplicateSubtitleError("hash1", "/existing/source.en.srt", "/new/source.en.srt")
        manager = MagicMock()
        manager.search.return_value = [result]
        manager.download.return_value = result.content
        manager.save_subtitle.side_effect = dup

        with (
            self._patched_module(mock_translator) as mod,
            patch.object(
                mod, "get_wanted_item", return_value=_make_wanted_item(target_language="de")
            ),
            patch.object(mod, "get_settings", return_value=_make_settings(target_language="de")),
            patch.object(mod, "build_query_from_wanted", return_value=MagicMock()),
            patch.object(mod, "get_provider_manager", return_value=manager),
            patch.object(mod, "record_subtitle_download"),
            patch.object(mod, "delete_wanted_item"),
            patch("services.mt_provisional.finalize_translation"),
            patch.object(mod, "_try_auto_sync"),
            patch.object(mod, "create_job", return_value={"id": "job1"}),
            patch.object(mod, "update_job"),
            patch.object(mod, "record_stat"),
            patch("os.path.exists", return_value=True),
            patch("os.remove"),
        ):
            out = mod.download_specific_for_item(1, "test_provider", "sub123", "en", True)

        assert out["success"] is True
        assert out["translated"] is True

    def test_translate_save_oserror_returns_failure(self):
        """OSError when saving source file during translate path."""
        result = _make_result(fmt=SubtitleFormat.SRT)
        manager = MagicMock()
        manager.search.return_value = [result]
        manager.download.return_value = result.content
        manager.save_subtitle.side_effect = RuntimeError("write error")

        with (
            self._patched_module() as mod,
            patch.object(
                mod, "get_wanted_item", return_value=_make_wanted_item(target_language="de")
            ),
            patch.object(mod, "get_settings", return_value=_make_settings(target_language="de")),
            patch.object(mod, "build_query_from_wanted", return_value=MagicMock()),
            patch.object(mod, "get_provider_manager", return_value=manager),
            patch.object(mod, "record_subtitle_download"),
        ):
            out = mod.download_specific_for_item(1, "test_provider", "sub123", "en", True)

        assert out["success"] is False
        assert "save subtitle" in out["error"].lower()

    def test_unknown_format_defaults_to_srt(self):
        """SubtitleFormat.UNKNOWN -> fmt_ext defaults to 'srt'."""
        mock_translator = MagicMock()
        mock_translator.get_output_path_for_lang.return_value = "/out/sub.srt"

        result = _make_result(fmt=SubtitleFormat.UNKNOWN)
        manager = MagicMock()
        manager.search.return_value = [result]
        manager.download.return_value = result.content
        manager.save_subtitle.return_value = "/out/sub.srt"

        with (
            self._patched_module(mock_translator) as mod,
            patch.object(mod, "get_wanted_item", return_value=_make_wanted_item()),
            patch.object(mod, "get_settings", return_value=_make_settings()),
            patch.object(mod, "build_query_from_wanted", return_value=MagicMock()),
            patch.object(mod, "get_provider_manager", return_value=manager),
            patch.object(mod, "delete_wanted_item"),
            patch.object(mod, "_try_auto_sync"),
            patch.object(mod, "record_subtitle_download"),
        ):
            out = mod.download_specific_for_item(1, "test_provider", "sub123", "en", False)

        assert out["success"] is True
        assert out["format"] == "srt"

    def test_item_lang_falls_back_to_settings(self):
        """When item has no target_language, falls back to settings.target_language."""
        mock_translator = MagicMock()
        mock_translator.get_output_path_for_lang.return_value = "/out/sub.srt"

        result = _make_result()
        manager = MagicMock()
        manager.search.return_value = [result]
        manager.download.return_value = result.content
        manager.save_subtitle.return_value = "/out/sub.srt"

        with (
            self._patched_module(mock_translator) as mod,
            patch.object(
                mod, "get_wanted_item", return_value=_make_wanted_item(target_language=None)
            ),
            patch.object(mod, "get_settings", return_value=_make_settings(target_language="de")),
            patch.object(mod, "build_query_from_wanted", return_value=MagicMock()),
            patch.object(mod, "get_provider_manager", return_value=manager),
            patch.object(mod, "delete_wanted_item"),
            patch.object(mod, "_try_auto_sync"),
            patch.object(mod, "record_subtitle_download"),
        ):
            out = mod.download_specific_for_item(1, "test_provider", "sub123", "en", False)

        assert out["success"] is True

    def test_translate_exception_cleanup_fails_gracefully(self):
        """When temp file cleanup after translation failure also fails, it's caught."""
        mock_translator = MagicMock()
        mock_translator.get_output_path_for_lang.return_value = "/out/sub.de.srt"
        mock_translator.translate_srt_from_file.side_effect = RuntimeError("LLM down")

        result = _make_result(fmt=SubtitleFormat.SRT)
        manager = MagicMock()
        manager.search.return_value = [result]
        manager.download.return_value = result.content
        manager.save_subtitle.return_value = "/tmp/source.en.srt"

        with (
            self._patched_module(mock_translator) as mod,
            patch.object(
                mod, "get_wanted_item", return_value=_make_wanted_item(target_language="de")
            ),
            patch.object(mod, "get_settings", return_value=_make_settings(target_language="de")),
            patch.object(mod, "build_query_from_wanted", return_value=MagicMock()),
            patch.object(mod, "get_provider_manager", return_value=manager),
            patch.object(mod, "record_subtitle_download"),
            patch.object(mod, "delete_wanted_item"),
            patch.object(mod, "_try_auto_sync"),
            patch.object(mod, "create_job", return_value={"id": "job1"}),
            patch.object(mod, "update_job"),
            patch.object(mod, "record_stat"),
            patch("os.path.exists", return_value=True),
            patch("os.remove", side_effect=OSError("locked")),
        ):
            out = mod.download_specific_for_item(1, "test_provider", "sub123", "en", True)

        assert out["success"] is False
        assert "Translation failed" in out["error"]

    def test_arr_context_passed_to_create_job(self):
        """arr context keys from wanted item are forwarded to create_job."""
        translate_result = {
            "success": True,
            "output_path": "/out/sub.de.ass",
            "stats": {"skipped": False, "format": "ass", "source": "provider_interactive"},
        }
        mock_translator = MagicMock()
        mock_translator.get_output_path_for_lang.return_value = "/out/sub.de.srt"
        mock_translator.translate_srt_from_file.return_value = translate_result

        result = _make_result(fmt=SubtitleFormat.SRT)
        manager = MagicMock()
        manager.search.return_value = [result]
        manager.download.return_value = result.content
        manager.save_subtitle.return_value = "/tmp/source.en.srt"

        mock_create_job = MagicMock(return_value={"id": "job1"})

        with (
            self._patched_module(mock_translator) as mod,
            patch.object(
                mod,
                "get_wanted_item",
                return_value=_make_wanted_item(
                    target_language="de", sonarr_series_id=10, sonarr_episode_id=100
                ),
            ),
            patch.object(mod, "get_settings", return_value=_make_settings(target_language="de")),
            patch.object(mod, "build_query_from_wanted", return_value=MagicMock()),
            patch.object(mod, "get_provider_manager", return_value=manager),
            patch.object(mod, "record_subtitle_download"),
            patch.object(mod, "delete_wanted_item"),
            patch("services.mt_provisional.finalize_translation"),
            patch.object(mod, "_try_auto_sync"),
            patch.object(mod, "create_job", mock_create_job),
            patch.object(mod, "update_job"),
            patch.object(mod, "record_stat"),
            patch("os.path.exists", return_value=True),
            patch("os.remove"),
        ):
            out = mod.download_specific_for_item(1, "test_provider", "sub123", "en", True)

        assert out["success"] is True
        # Verify arr_context was passed
        call_args = mock_create_job.call_args
        arr_ctx = (
            call_args[1].get("arr_context") or call_args[0][2]
            if len(call_args[0]) > 2
            else call_args[1].get("arr_context")
        )
        assert arr_ctx is not None
        assert "sonarr_series_id" in arr_ctx

    def test_download_only_runtime_error_on_save(self):
        """RuntimeError on save in download-only path -> returns failure."""
        mock_translator = MagicMock()
        mock_translator.get_output_path_for_lang.return_value = "/out/sub.srt"

        result = _make_result()
        manager = MagicMock()
        manager.search.return_value = [result]
        manager.download.return_value = result.content
        manager.save_subtitle.side_effect = RuntimeError("file system error")

        with (
            self._patched_module(mock_translator) as mod,
            patch.object(mod, "get_wanted_item", return_value=_make_wanted_item()),
            patch.object(mod, "get_settings", return_value=_make_settings()),
            patch.object(mod, "build_query_from_wanted", return_value=MagicMock()),
            patch.object(mod, "get_provider_manager", return_value=manager),
            patch.object(mod, "record_subtitle_download"),
        ):
            out = mod.download_specific_for_item(1, "test_provider", "sub123", "en", False)

        assert out["success"] is False
        assert "save subtitle" in out["error"].lower()
