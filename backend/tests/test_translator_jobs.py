"""Tests for translator.jobs — job queue, scan_directory, notify, config hash."""

import os
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# _get_job_queue
# ---------------------------------------------------------------------------


class TestGetJobQueue:
    """Tests for _get_job_queue."""

    def test_returns_none_outside_flask_context(self):
        from translator.jobs import _get_job_queue

        result = _get_job_queue()
        assert result is None

    def test_returns_queue_from_app(self, app_ctx):
        from translator.jobs import _get_job_queue

        app_ctx.job_queue = MagicMock()
        result = _get_job_queue()
        assert result is app_ctx.job_queue

    def test_returns_none_when_no_queue_attr(self, app_ctx):
        from translator.jobs import _get_job_queue

        # app_ctx does not have job_queue attribute
        if hasattr(app_ctx, "job_queue"):
            delattr(app_ctx, "job_queue")
        result = _get_job_queue()
        assert result is None


# ---------------------------------------------------------------------------
# _notify_integrations
# ---------------------------------------------------------------------------


class TestNotifyIntegrations:
    """Tests for _notify_integrations."""

    def test_no_context_does_nothing(self):
        from translator.jobs import _notify_integrations

        # Should not raise
        _notify_integrations(None, file_path="/media/test.mkv")

    def test_no_file_path_does_nothing(self):
        from translator.jobs import _notify_integrations

        _notify_integrations({"sonarr_series_id": 1}, file_path=None)

    @patch("mediaserver.get_media_server_manager")
    def test_sonarr_context_notifies_episode(self, mock_manager_fn):
        from translator.jobs import _notify_integrations

        mock_manager = MagicMock()
        mock_result = MagicMock(success=True, message="OK")
        mock_manager.refresh_all.return_value = [mock_result]
        mock_manager_fn.return_value = mock_manager

        _notify_integrations(
            {"sonarr_series_id": 5, "sonarr_episode_id": 10},
            file_path="/media/show.mkv",
        )

        mock_manager.refresh_all.assert_called_once_with("/media/show.mkv", "episode")

    @patch("mediaserver.get_media_server_manager")
    def test_radarr_context_notifies_movie(self, mock_manager_fn):
        from translator.jobs import _notify_integrations

        mock_manager = MagicMock()
        mock_result = MagicMock(success=True, message="OK")
        mock_manager.refresh_all.return_value = [mock_result]
        mock_manager_fn.return_value = mock_manager

        _notify_integrations(
            {"radarr_movie_id": 42},
            file_path="/media/movie.mkv",
        )

        mock_manager.refresh_all.assert_called_once_with("/media/movie.mkv", "movie")

    @patch("mediaserver.get_media_server_manager")
    def test_notification_failure_logged_not_raised(self, mock_manager_fn):
        from translator.jobs import _notify_integrations

        mock_manager_fn.side_effect = Exception("connection refused")

        # Should not raise
        _notify_integrations(
            {"sonarr_series_id": 1},
            file_path="/media/test.mkv",
        )


# ---------------------------------------------------------------------------
# _record_config_hash_for_result
# ---------------------------------------------------------------------------


class TestRecordConfigHash:
    """Tests for _record_config_hash_for_result."""

    def test_skips_when_result_none(self):
        from translator.jobs import _record_config_hash_for_result

        # Should not raise
        _record_config_hash_for_result(None, "/media/test.mkv")

    def test_skips_when_not_success(self):
        from translator.jobs import _record_config_hash_for_result

        result = {"success": False, "stats": {}}
        _record_config_hash_for_result(result, "/media/test.mkv")
        # No config_hash should be added
        assert "config_hash" not in result.get("stats", {})

    def test_skips_when_skipped(self):
        from translator.jobs import _record_config_hash_for_result

        result = {"success": True, "stats": {"skipped": True}}
        _record_config_hash_for_result(result, "/media/test.mkv")
        assert "config_hash" not in result["stats"]

    @patch("db.translation.record_translation_config")
    @patch("translator.jobs.get_settings")
    def test_records_hash_for_ollama(self, mock_settings, mock_record):
        from translator.jobs import _record_config_hash_for_result

        settings = MagicMock()
        settings.get_translation_config_hash.return_value = "abc123"
        settings.ollama_model = "anime-de-v3"
        settings.get_prompt_template.return_value = "Translate: {text}"
        settings.target_language = "de"
        mock_settings.return_value = settings

        result = {"success": True, "stats": {"backend_name": "ollama"}}
        _record_config_hash_for_result(result, "/media/test.mkv")

        mock_record.assert_called_once()
        assert result["stats"]["config_hash"] == "abc123"

    @patch("db.translation.record_translation_config")
    @patch("translator.jobs.get_settings")
    def test_records_hash_for_non_ollama(self, mock_settings, mock_record):
        from translator.jobs import _record_config_hash_for_result

        settings = MagicMock()
        settings.get_translation_config_hash.return_value = "def456"
        settings.ollama_model = "irrelevant"
        settings.get_prompt_template.return_value = "T"
        settings.target_language = "de"
        mock_settings.return_value = settings

        result = {"success": True, "stats": {"backend_name": "deepl"}}
        _record_config_hash_for_result(result, "/media/test.mkv")

        # model_info should be backend name, not ollama_model
        call_args = mock_record.call_args
        assert (
            call_args.kwargs.get("ollama_model") == "deepl"
            or call_args[1].get("ollama_model") == "deepl"
        )

    @patch("translator.jobs.get_settings", side_effect=Exception("settings error"))
    def test_exception_silently_caught(self, mock_settings):
        from translator.jobs import _record_config_hash_for_result

        result = {"success": True, "stats": {"backend_name": "ollama"}}
        # Should not raise
        _record_config_hash_for_result(result, "/media/test.mkv")


# ---------------------------------------------------------------------------
# scan_directory
# ---------------------------------------------------------------------------


class TestScanDirectory:
    """Tests for scan_directory."""

    @patch("translator.jobs.detect_existing_target")
    def test_finds_mkv_files(self, mock_detect, tmp_path):
        from translator.jobs import scan_directory

        mock_detect.return_value = None

        mkv1 = tmp_path / "video1.mkv"
        mkv2 = tmp_path / "video2.mkv"
        txt = tmp_path / "readme.txt"
        mkv1.write_bytes(b"\x00" * 100)
        mkv2.write_bytes(b"\x00" * 200)
        txt.write_text("not a video")

        files = scan_directory(str(tmp_path))

        assert len(files) == 2
        paths = [f["path"] for f in files]
        assert str(mkv1) in paths
        assert str(mkv2) in paths

    @patch("translator.jobs.detect_existing_target")
    def test_skips_existing_ass_unless_force(self, mock_detect, tmp_path):
        from translator.jobs import scan_directory

        mock_detect.return_value = "ass"

        mkv = tmp_path / "done.mkv"
        mkv.write_bytes(b"\x00" * 100)

        # Without force: skip
        files = scan_directory(str(tmp_path), force=False)
        assert len(files) == 0

        # With force: include
        files = scan_directory(str(tmp_path), force=True)
        assert len(files) == 1

    @patch("translator.jobs.detect_existing_target")
    def test_includes_srt_only(self, mock_detect, tmp_path):
        from translator.jobs import scan_directory

        mock_detect.return_value = "srt"

        mkv = tmp_path / "partial.mkv"
        mkv.write_bytes(b"\x00" * 1024)

        files = scan_directory(str(tmp_path))
        assert len(files) == 1
        assert files[0]["target_status"] == "srt"
        assert files[0]["size_mb"] == pytest.approx(1024 / (1024 * 1024), abs=0.001)

    @patch("translator.jobs.detect_existing_target")
    def test_empty_directory(self, mock_detect, tmp_path):
        from translator.jobs import scan_directory

        files = scan_directory(str(tmp_path))
        assert files == []
        mock_detect.assert_not_called()


# ---------------------------------------------------------------------------
# submit_translation_job
# ---------------------------------------------------------------------------


class TestSubmitTranslationJob:
    """Tests for submit_translation_job."""

    @patch("translator.core.translate_file")
    @patch("translator.jobs._get_job_queue", return_value=None)
    def test_direct_execution_when_no_queue(self, mock_queue, mock_translate):
        from translator.jobs import submit_translation_job

        mock_translate.return_value = {"success": True}
        result = submit_translation_job("/media/test.mkv", force=True)

        mock_translate.assert_called_once()
        assert result == {"success": True}

    @patch("translator.core.translate_file")
    @patch("translator.jobs._get_job_queue")
    def test_enqueues_when_queue_available(self, mock_queue_fn, mock_translate):
        from translator.jobs import submit_translation_job

        mock_queue = MagicMock()
        mock_queue.enqueue.return_value = "job-123"
        mock_queue_fn.return_value = mock_queue

        result = submit_translation_job(
            "/media/test.mkv",
            force=False,
            arr_context={"sonarr_series_id": 1},
            job_id="custom-id",
        )

        mock_queue.enqueue.assert_called_once()
        assert result == "job-123"
        mock_translate.assert_not_called()

    @patch("translator.core.translate_file")
    @patch("translator.jobs._get_job_queue")
    def test_falls_back_to_direct_on_queue_error(self, mock_queue_fn, mock_translate):
        from translator.jobs import submit_translation_job

        mock_queue = MagicMock()
        mock_queue.enqueue.side_effect = Exception("redis down")
        mock_queue_fn.return_value = mock_queue

        mock_translate.return_value = {"success": True}
        result = submit_translation_job("/media/test.mkv")

        mock_translate.assert_called_once()
        assert result == {"success": True}
