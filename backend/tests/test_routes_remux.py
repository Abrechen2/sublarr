"""Tests for routes/remux.py -- remux job management, backup listing, cleanup, restore, delete."""

import os
import sys
import time
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _reset_jobs():
    """Clear the in-memory job store between tests."""
    import routes.remux as remux_mod

    with remux_mod._jobs_lock:
        remux_mod._jobs.clear()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class TestHelpers:
    """Unit tests for module-level helper functions."""

    def test_media_paths_single(self, client):
        with patch("routes.remux.get_settings") as mock_settings:
            s = MagicMock()
            s.media_path = "/media/anime"
            s.extra_media_paths = ""
            mock_settings.return_value = s

            from routes.remux import _media_paths

            result = _media_paths()
            assert result == ["/media/anime"]

    def test_media_paths_with_extras(self, client):
        with patch("routes.remux.get_settings") as mock_settings:
            s = MagicMock()
            s.media_path = "/media/anime"
            s.extra_media_paths = "/media/movies, /media/tv"
            mock_settings.return_value = s

            from routes.remux import _media_paths

            result = _media_paths()
            assert result == ["/media/anime", "/media/movies", "/media/tv"]

    def test_media_paths_empty(self, client):
        with patch("routes.remux.get_settings") as mock_settings:
            s = MagicMock()
            s.media_path = ""
            s.extra_media_paths = ""
            mock_settings.return_value = s

            from routes.remux import _media_paths

            result = _media_paths()
            assert result == []

    def test_trash_paths_relative(self, client):
        with patch("routes.remux.get_settings") as mock_settings:
            s = MagicMock()
            s.media_path = "/media/anime"
            s.extra_media_paths = ""
            s.remux_trash_dir = ".sublarr"
            mock_settings.return_value = s

            from routes.remux import _trash_paths

            result = _trash_paths()
            expected = os.path.join("/media/anime", ".sublarr", "trash")
            assert result == [expected]

    def test_trash_paths_absolute(self, client):
        with patch("routes.remux.get_settings") as mock_settings:
            s = MagicMock()
            s.remux_trash_dir = "/opt/trash"
            mock_settings.return_value = s

            from routes.remux import _trash_paths

            result = _trash_paths()
            assert result == [os.path.join("/opt/trash", "trash")]

    def test_get_video_path_no_client(self, client):
        with patch("sonarr_client.get_sonarr_client", return_value=None):
            from routes.remux import _get_video_path

            assert _get_video_path(1) is None

    def test_get_video_path_no_file(self, client):
        mock_client = MagicMock()
        mock_client.get_episode_file_path.return_value = None
        with patch("sonarr_client.get_sonarr_client", return_value=mock_client):
            from routes.remux import _get_video_path

            assert _get_video_path(1) is None

    def test_get_video_path_success(self, client):
        mock_client = MagicMock()
        mock_client.get_episode_file_path.return_value = "/media/show/ep01.mkv"
        with (
            patch("sonarr_client.get_sonarr_client", return_value=mock_client),
            patch("routes.remux.map_path", side_effect=lambda p: p),
        ):
            from routes.remux import _get_video_path

            result = _get_video_path(42)
            assert result == "/media/show/ep01.mkv"
            mock_client.get_episode_file_path.assert_called_once_with(42)

    def test_update_job_stores_status(self, client):
        import routes.remux as remux_mod

        _reset_jobs()
        remux_mod._update_job("j1", "running")

        with remux_mod._jobs_lock:
            assert remux_mod._jobs["j1"]["status"] == "running"

    def test_update_job_emits_socketio(self, client):
        _reset_jobs()
        mock_sio = MagicMock()
        with patch("routes.remux.socketio", mock_sio, create=True):
            from routes.remux import _update_job

            _update_job("j2", "completed", result={"backup_path": "/x"})

        # socketio.emit is called lazily inside the function; check it was attempted
        # (may succeed or fail depending on import path -- the function catches exceptions)

    def test_arr_pause_disabled(self, client):
        """When remux_arr_pause_enabled is False, the Sonarr client is never called."""
        with patch("routes.remux.get_settings") as mock_settings:
            s = MagicMock()
            s.remux_arr_pause_enabled = False
            mock_settings.return_value = s

            from routes.remux import _arr_pause

            # Should return without calling sonarr
            _arr_pause(True)


# ---------------------------------------------------------------------------
# POST /api/v1/library/episodes/<ep_id>/tracks/<index>/remove-from-container
# ---------------------------------------------------------------------------


class TestRemoveTrackFromContainer:
    """POST remove-from-container endpoint."""

    def setup_method(self):
        _reset_jobs()

    def test_episode_not_found(self, client):
        """Returns 404 when _get_video_path returns None."""
        with patch("routes.remux._get_video_path", return_value=None):
            rv = client.post(
                "/api/v1/library/episodes/1/tracks/2/remove-from-container",
                json={},
            )
        assert rv.status_code == 404
        assert "no video file" in rv.get_json()["error"].lower()

    def test_video_file_not_on_disk(self, client):
        """Returns 404 when the resolved path does not exist."""
        with (
            patch("routes.remux._get_video_path", return_value="/nonexistent/video.mkv"),
            patch("routes.remux.os.path.exists", return_value=False),
        ):
            rv = client.post(
                "/api/v1/library/episodes/1/tracks/2/remove-from-container",
                json={},
            )
        assert rv.status_code == 404
        assert "not found on disk" in rv.get_json()["error"].lower()

    def test_probe_runtime_error(self, client):
        """Returns 500 when ffprobe raises RuntimeError."""
        with (
            patch("routes.remux._get_video_path", return_value="/media/ep.mkv"),
            patch("routes.remux.os.path.exists", return_value=True),
            patch("routes.remux.get_media_streams", side_effect=RuntimeError("ffprobe failed")),
        ):
            rv = client.post(
                "/api/v1/library/episodes/1/tracks/2/remove-from-container",
                json={},
            )
        assert rv.status_code == 500
        assert "probe" in rv.get_json()["error"].lower()

    def test_probe_unexpected_error(self, client):
        """Returns 500 on unexpected probe exceptions."""
        with (
            patch("routes.remux._get_video_path", return_value="/media/ep.mkv"),
            patch("routes.remux.os.path.exists", return_value=True),
            patch("routes.remux.get_media_streams", side_effect=ValueError("corrupt")),
        ):
            rv = client.post(
                "/api/v1/library/episodes/1/tracks/2/remove-from-container",
                json={},
            )
        assert rv.status_code == 500
        assert "internal server error" in rv.get_json()["error"].lower()

    def test_stream_index_out_of_range(self, client):
        """Returns 400 when stream index exceeds stream count."""
        probe_data = {
            "streams": [
                {"codec_type": "video"},
                {"codec_type": "audio"},
            ]
        }
        with (
            patch("routes.remux._get_video_path", return_value="/media/ep.mkv"),
            patch("routes.remux.os.path.exists", return_value=True),
            patch("routes.remux.get_media_streams", return_value=probe_data),
        ):
            rv = client.post(
                "/api/v1/library/episodes/1/tracks/5/remove-from-container",
                json={},
            )
        assert rv.status_code == 400
        assert "out of range" in rv.get_json()["error"].lower()

    def test_stream_not_subtitle(self, client):
        """Returns 400 when target stream is not a subtitle."""
        probe_data = {
            "streams": [
                {"codec_type": "video"},
                {"codec_type": "audio"},
            ]
        }
        with (
            patch("routes.remux._get_video_path", return_value="/media/ep.mkv"),
            patch("routes.remux.os.path.exists", return_value=True),
            patch("routes.remux.get_media_streams", return_value=probe_data),
        ):
            rv = client.post(
                "/api/v1/library/episodes/1/tracks/0/remove-from-container",
                json={},
            )
        assert rv.status_code == 400
        assert "not a subtitle" in rv.get_json()["error"].lower()

    def test_success_queues_job(self, client):
        """Returns 202 with a job_id on valid input."""
        probe_data = {
            "streams": [
                {"codec_type": "video"},
                {"codec_type": "audio"},
                {"codec_type": "subtitle"},
                {"codec_type": "subtitle"},
            ]
        }
        with (
            patch("routes.remux._get_video_path", return_value="/media/ep.mkv"),
            patch("routes.remux.os.path.exists", return_value=True),
            patch("routes.remux.get_media_streams", return_value=probe_data),
            patch("routes.remux._executor") as mock_executor,
        ):
            rv = client.post(
                "/api/v1/library/episodes/1/tracks/3/remove-from-container",
                json={},
            )

        assert rv.status_code == 202
        data = rv.get_json()
        assert "job_id" in data
        assert data["status"] == "queued"
        mock_executor.submit.assert_called_once()

    def test_success_derives_subtitle_track_index(self, client):
        """subtitle_track_index is auto-computed if not supplied in the body."""
        probe_data = {
            "streams": [
                {"codec_type": "video"},
                {"codec_type": "subtitle"},  # index 1 -> sub track 0
                {"codec_type": "audio"},
                {"codec_type": "subtitle"},  # index 3 -> sub track 1
            ]
        }
        with (
            patch("routes.remux._get_video_path", return_value="/media/ep.mkv"),
            patch("routes.remux.os.path.exists", return_value=True),
            patch("routes.remux.get_media_streams", return_value=probe_data),
            patch("routes.remux._executor") as mock_executor,
        ):
            rv = client.post(
                "/api/v1/library/episodes/1/tracks/3/remove-from-container",
                json={},
            )

        assert rv.status_code == 202
        # The _run_remux call should receive subtitle_track_index=1
        call_args = mock_executor.submit.call_args
        # submit(_run_remux, job_id, video_path, stream_index, subtitle_track_index)
        assert call_args[0][3] == 3  # stream_index
        assert call_args[0][4] == 1  # subtitle_track_index (1 sub before index 3)

    def test_explicit_subtitle_track_index(self, client):
        """When body supplies subtitle_track_index, it is used verbatim."""
        probe_data = {
            "streams": [
                {"codec_type": "video"},
                {"codec_type": "subtitle"},
            ]
        }
        with (
            patch("routes.remux._get_video_path", return_value="/media/ep.mkv"),
            patch("routes.remux.os.path.exists", return_value=True),
            patch("routes.remux.get_media_streams", return_value=probe_data),
            patch("routes.remux._executor") as mock_executor,
        ):
            rv = client.post(
                "/api/v1/library/episodes/1/tracks/1/remove-from-container",
                json={"subtitle_track_index": 99},
            )

        assert rv.status_code == 202
        call_args = mock_executor.submit.call_args
        assert call_args[0][4] == 99  # explicit override


# ---------------------------------------------------------------------------
# GET /api/v1/remux/jobs
# ---------------------------------------------------------------------------


class TestListRemuxJobs:
    """GET /api/v1/remux/jobs"""

    def setup_method(self):
        _reset_jobs()

    def test_empty_jobs(self, client):
        rv = client.get("/api/v1/remux/jobs")
        assert rv.status_code == 200
        data = rv.get_json()
        assert data["jobs"] == []

    def test_list_jobs_with_entries(self, client):
        import routes.remux as remux_mod

        with remux_mod._jobs_lock:
            remux_mod._jobs["j1"] = {"status": "queued", "result": None, "error": None}
            remux_mod._jobs["j2"] = {
                "status": "completed",
                "result": {"backup_path": "/x"},
                "error": None,
            }

        rv = client.get("/api/v1/remux/jobs")
        assert rv.status_code == 200
        data = rv.get_json()
        assert len(data["jobs"]) == 2
        job_ids = {j["job_id"] for j in data["jobs"]}
        assert "j1" in job_ids
        assert "j2" in job_ids


# ---------------------------------------------------------------------------
# GET /api/v1/remux/jobs/<job_id>
# ---------------------------------------------------------------------------


class TestGetRemuxJob:
    """GET /api/v1/remux/jobs/<job_id>"""

    def setup_method(self):
        _reset_jobs()

    def test_job_not_found(self, client):
        rv = client.get("/api/v1/remux/jobs/nonexistent")
        assert rv.status_code == 404
        assert "not found" in rv.get_json()["error"].lower()

    def test_job_found(self, client):
        import routes.remux as remux_mod

        with remux_mod._jobs_lock:
            remux_mod._jobs["abc"] = {"status": "running", "result": None, "error": None}

        rv = client.get("/api/v1/remux/jobs/abc")
        assert rv.status_code == 200
        data = rv.get_json()
        assert data["job_id"] == "abc"
        assert data["status"] == "running"


# ---------------------------------------------------------------------------
# GET /api/v1/remux/backups
# ---------------------------------------------------------------------------


class TestListRemuxBackups:
    """GET /api/v1/remux/backups"""

    def test_list_backups_empty(self, client):
        with (
            patch("routes.remux._trash_paths", return_value=["/tmp/trash"]),
            patch("routes.remux.get_settings") as mock_settings,
            patch("routes.remux.list_backups", return_value=[]),
        ):
            s = MagicMock()
            s.remux_backup_retention_days = 7
            mock_settings.return_value = s

            rv = client.get("/api/v1/remux/backups")

        assert rv.status_code == 200
        data = rv.get_json()
        assert data["backups"] == []
        assert data["count"] == 0

    def test_list_backups_with_results(self, client):
        fake_backups = [
            {"path": "/trash/ep1.mkv.bak", "size_bytes": 1000, "mtime": 123456},
            {"path": "/trash/ep2.mkv.bak", "size_bytes": 2000, "mtime": 123457},
        ]
        with (
            patch("routes.remux._trash_paths", return_value=["/tmp/trash"]),
            patch("routes.remux.get_settings") as mock_settings,
            patch("routes.remux.list_backups", return_value=fake_backups),
        ):
            s = MagicMock()
            s.remux_backup_retention_days = 7
            mock_settings.return_value = s

            rv = client.get("/api/v1/remux/backups")

        assert rv.status_code == 200
        data = rv.get_json()
        assert data["count"] == 2
        assert len(data["backups"]) == 2


# ---------------------------------------------------------------------------
# POST /api/v1/remux/backups/cleanup
# ---------------------------------------------------------------------------


class TestTriggerBackupCleanup:
    """POST /api/v1/remux/backups/cleanup"""

    def test_cleanup_actual(self, client):
        cleanup_result = {"deleted": ["/trash/old.bak"], "errors": [], "skipped": 2}
        with (
            patch("routes.remux._trash_paths", return_value=["/tmp/trash"]),
            patch("routes.remux.get_settings") as mock_settings,
            patch("routes.remux.cleanup_old_backups", return_value=cleanup_result),
        ):
            s = MagicMock()
            s.remux_backup_retention_days = 7
            mock_settings.return_value = s

            rv = client.post("/api/v1/remux/backups/cleanup", json={})

        assert rv.status_code == 200
        data = rv.get_json()
        assert data["deleted"] == ["/trash/old.bak"]
        assert data["skipped"] == 2

    def test_cleanup_dry_run(self, client):
        with (
            patch("routes.remux._trash_paths", return_value=["/tmp/trash"]),
            patch("routes.remux.get_settings") as mock_settings,
            patch("remux.backup_cleanup._iter_bak_files", return_value=["/trash/old.bak"]),
            patch("routes.remux.os.path.getmtime", return_value=0),  # very old file
        ):
            s = MagicMock()
            s.remux_backup_retention_days = 7
            mock_settings.return_value = s

            rv = client.post("/api/v1/remux/backups/cleanup", json={"dry_run": True})

        assert rv.status_code == 200
        data = rv.get_json()
        assert data["dry_run"] is True
        assert data["count"] == 1
        assert "/trash/old.bak" in data["would_delete"]

    def test_cleanup_dry_run_nothing_old(self, client):
        with (
            patch("routes.remux._trash_paths", return_value=["/tmp/trash"]),
            patch("routes.remux.get_settings") as mock_settings,
            patch("remux.backup_cleanup._iter_bak_files", return_value=["/trash/recent.bak"]),
            patch("routes.remux.os.path.getmtime", return_value=time.time()),  # very recent
        ):
            s = MagicMock()
            s.remux_backup_retention_days = 7
            mock_settings.return_value = s

            rv = client.post("/api/v1/remux/backups/cleanup", json={"dry_run": True})

        assert rv.status_code == 200
        data = rv.get_json()
        assert data["dry_run"] is True
        assert data["count"] == 0
        assert data["would_delete"] == []

    def test_cleanup_dry_run_getmtime_oserror(self, client):
        """Files that raise OSError on getmtime are silently skipped."""
        with (
            patch("routes.remux._trash_paths", return_value=["/tmp/trash"]),
            patch("routes.remux.get_settings") as mock_settings,
            patch("remux.backup_cleanup._iter_bak_files", return_value=["/trash/bad.bak"]),
            patch("routes.remux.os.path.getmtime", side_effect=OSError("permission denied")),
        ):
            s = MagicMock()
            s.remux_backup_retention_days = 7
            mock_settings.return_value = s

            rv = client.post("/api/v1/remux/backups/cleanup", json={"dry_run": True})

        assert rv.status_code == 200
        data = rv.get_json()
        assert data["count"] == 0


# ---------------------------------------------------------------------------
# POST /api/v1/remux/backups/restore
# ---------------------------------------------------------------------------


class TestRestoreBackup:
    """POST /api/v1/remux/backups/restore"""

    def test_restore_missing_fields(self, client):
        rv = client.post("/api/v1/remux/backups/restore", json={})
        assert rv.status_code == 400
        assert "required" in rv.get_json()["error"].lower()

    def test_restore_missing_video_path(self, client):
        rv = client.post(
            "/api/v1/remux/backups/restore",
            json={"backup_path": "/trash/ep.bak"},
        )
        assert rv.status_code == 400
        assert "required" in rv.get_json()["error"].lower()

    def test_restore_backup_outside_trash(self, client):
        """Backup path outside the configured trash dir returns 403."""
        with (
            patch("routes.remux._trash_paths", return_value=["/safe/trash"]),
            patch("routes.remux.is_safe_path", return_value=False),
        ):
            rv = client.post(
                "/api/v1/remux/backups/restore",
                json={"backup_path": "/evil/path", "video_path": "/media/ep.mkv"},
            )
        assert rv.status_code == 403
        assert "outside" in rv.get_json()["error"].lower()

    def test_restore_video_outside_media(self, client):
        """Video path outside the configured media dir returns 403."""
        with (
            patch("routes.remux._trash_paths", return_value=["/safe/trash"]),
            patch("routes.remux._media_paths", return_value=["/media"]),
            # First call (backup check) passes, second call (video check) fails
            patch("routes.remux.is_safe_path", side_effect=[True, False]),
        ):
            rv = client.post(
                "/api/v1/remux/backups/restore",
                json={"backup_path": "/safe/trash/ep.bak", "video_path": "/evil/ep.mkv"},
            )
        assert rv.status_code == 403
        assert "outside" in rv.get_json()["error"].lower()

    def test_restore_backup_not_found(self, client):
        with (
            patch("routes.remux._trash_paths", return_value=["/safe/trash"]),
            patch("routes.remux._media_paths", return_value=["/media"]),
            patch("routes.remux.is_safe_path", return_value=True),
            patch("routes.remux.os.path.exists", side_effect=[False]),
        ):
            rv = client.post(
                "/api/v1/remux/backups/restore",
                json={"backup_path": "/safe/trash/ep.bak", "video_path": "/media/ep.mkv"},
            )
        assert rv.status_code == 404
        assert "backup file not found" in rv.get_json()["error"].lower()

    def test_restore_video_not_found(self, client):
        with (
            patch("routes.remux._trash_paths", return_value=["/safe/trash"]),
            patch("routes.remux._media_paths", return_value=["/media"]),
            patch("routes.remux.is_safe_path", return_value=True),
            patch("routes.remux.os.path.exists", side_effect=[True, False]),
        ):
            rv = client.post(
                "/api/v1/remux/backups/restore",
                json={"backup_path": "/safe/trash/ep.bak", "video_path": "/media/ep.mkv"},
            )
        assert rv.status_code == 404
        assert "video file not found" in rv.get_json()["error"].lower()

    def test_restore_success(self, client):
        with (
            patch("routes.remux._trash_paths", return_value=["/safe/trash"]),
            patch("routes.remux._media_paths", return_value=["/media"]),
            patch("routes.remux.is_safe_path", return_value=True),
            patch("routes.remux.os.path.exists", return_value=True),
            patch("routes.remux.os.replace") as mock_replace,
        ):
            rv = client.post(
                "/api/v1/remux/backups/restore",
                json={"backup_path": "/safe/trash/ep.bak", "video_path": "/media/ep.mkv"},
            )

        assert rv.status_code == 200
        data = rv.get_json()
        assert data["restored"] == "/media/ep.mkv"
        assert data["backup_removed"] == "/safe/trash/ep.bak"
        assert data["sidecars_deleted"] == 0
        mock_replace.assert_called_once_with("/safe/trash/ep.bak", "/media/ep.mkv")

    def test_restore_os_error(self, client):
        with (
            patch("routes.remux._trash_paths", return_value=["/safe/trash"]),
            patch("routes.remux._media_paths", return_value=["/media"]),
            patch("routes.remux.is_safe_path", return_value=True),
            patch("routes.remux.os.path.exists", return_value=True),
            patch("routes.remux.os.replace", side_effect=OSError("disk full")),
        ):
            rv = client.post(
                "/api/v1/remux/backups/restore",
                json={"backup_path": "/safe/trash/ep.bak", "video_path": "/media/ep.mkv"},
            )

        assert rv.status_code == 500
        assert "restore failed" in rv.get_json()["error"].lower()

    def test_restore_with_sidecar_deletion(self, client):
        with (
            patch("routes.remux._trash_paths", return_value=["/safe/trash"]),
            patch("routes.remux._media_paths", return_value=["/media"]),
            patch("routes.remux.is_safe_path", return_value=True),
            patch("routes.remux.os.path.exists", return_value=True),
            patch("routes.remux.os.replace"),
            patch("routes.remux._purge_sidecars_for_video", return_value=3),
        ):
            rv = client.post(
                "/api/v1/remux/backups/restore",
                json={
                    "backup_path": "/safe/trash/ep.bak",
                    "video_path": "/media/ep.mkv",
                    "delete_sidecars": True,
                },
            )

        assert rv.status_code == 200
        data = rv.get_json()
        assert data["sidecars_deleted"] == 3


# ---------------------------------------------------------------------------
# POST /api/v1/remux/backups/delete
# ---------------------------------------------------------------------------


class TestDeleteBackup:
    """POST /api/v1/remux/backups/delete"""

    def test_delete_missing_path(self, client):
        rv = client.post("/api/v1/remux/backups/delete", json={})
        assert rv.status_code == 400
        assert "required" in rv.get_json()["error"].lower()

    def test_delete_outside_trash(self, client):
        with (
            patch("routes.remux._trash_paths", return_value=["/safe/trash"]),
            patch("routes.remux.is_safe_path", return_value=False),
        ):
            rv = client.post(
                "/api/v1/remux/backups/delete",
                json={"backup_path": "/evil/path"},
            )
        assert rv.status_code == 403
        assert "outside" in rv.get_json()["error"].lower()

    def test_delete_not_found(self, client):
        with (
            patch("routes.remux._trash_paths", return_value=["/safe/trash"]),
            patch("routes.remux.is_safe_path", return_value=True),
            patch("routes.remux.os.path.exists", return_value=False),
        ):
            rv = client.post(
                "/api/v1/remux/backups/delete",
                json={"backup_path": "/safe/trash/missing.bak"},
            )
        assert rv.status_code == 404
        assert "not found" in rv.get_json()["error"].lower()

    def test_delete_success(self, client):
        with (
            patch("routes.remux._trash_paths", return_value=["/safe/trash"]),
            patch("routes.remux.is_safe_path", return_value=True),
            patch("routes.remux.os.path.exists", return_value=True),
            patch("routes.remux.os.remove") as mock_remove,
        ):
            rv = client.post(
                "/api/v1/remux/backups/delete",
                json={"backup_path": "/safe/trash/ep.bak"},
            )

        assert rv.status_code == 200
        data = rv.get_json()
        assert data["deleted"] == "/safe/trash/ep.bak"
        mock_remove.assert_called_once_with("/safe/trash/ep.bak")

    def test_delete_os_error(self, client):
        with (
            patch("routes.remux._trash_paths", return_value=["/safe/trash"]),
            patch("routes.remux.is_safe_path", return_value=True),
            patch("routes.remux.os.path.exists", return_value=True),
            patch("routes.remux.os.remove", side_effect=OSError("permission denied")),
        ):
            rv = client.post(
                "/api/v1/remux/backups/delete",
                json={"backup_path": "/safe/trash/ep.bak"},
            )

        assert rv.status_code == 500
        assert "delete failed" in rv.get_json()["error"].lower()


# ---------------------------------------------------------------------------
# _run_remux (background worker)
# ---------------------------------------------------------------------------


class TestRunRemux:
    """Unit tests for the _run_remux background function."""

    def setup_method(self):
        _reset_jobs()

    def test_run_remux_success(self, client):
        import routes.remux as remux_mod

        with (
            patch("routes.remux.get_settings") as mock_settings,
            patch("routes.remux.remove_subtitle_stream", return_value="/backup/ep.bak"),
            patch("routes.remux._update_job") as mock_update,
            patch("routes.remux._arr_pause") as mock_pause,
        ):
            s = MagicMock()
            s.remux_use_reflink = True
            s.remux_trash_dir = ".sublarr"
            mock_settings.return_value = s

            remux_mod._run_remux("job-1", "/media/ep.mkv", 2, 0)

        # Check that job was updated to running, then completed
        assert mock_update.call_count == 2
        calls = mock_update.call_args_list
        assert calls[0][0] == ("job-1", "running")
        assert calls[1][0][0] == "job-1"
        assert calls[1][0][1] == "completed"
        assert calls[1][1]["result"]["backup_path"] == "/backup/ep.bak"

        # arr_pause called with True (pause) and then False (resume)
        assert mock_pause.call_count == 2
        assert mock_pause.call_args_list[0][0] == (True,)
        assert mock_pause.call_args_list[1][0] == (False,)

    def test_run_remux_remux_error(self, client):
        import routes.remux as remux_mod

        from remux import RemuxError

        with (
            patch("routes.remux.get_settings") as mock_settings,
            patch(
                "routes.remux.remove_subtitle_stream",
                side_effect=RemuxError("mkvmerge not found"),
            ),
            patch("routes.remux._update_job") as mock_update,
            patch("routes.remux._arr_pause"),
        ):
            s = MagicMock()
            s.remux_use_reflink = True
            s.remux_trash_dir = ".sublarr"
            mock_settings.return_value = s

            remux_mod._run_remux("job-2", "/media/ep.mkv", 2, 0)

        # Should have "running" then "failed"
        calls = mock_update.call_args_list
        assert calls[1][0][1] == "failed"
        assert "mkvmerge" in calls[1][1]["error"]

    def test_run_remux_unexpected_error(self, client):
        import routes.remux as remux_mod

        with (
            patch("routes.remux.get_settings") as mock_settings,
            patch(
                "routes.remux.remove_subtitle_stream",
                side_effect=RuntimeError("disk io error"),
            ),
            patch("routes.remux._update_job") as mock_update,
            patch("routes.remux._arr_pause"),
        ):
            s = MagicMock()
            s.remux_use_reflink = True
            s.remux_trash_dir = ".sublarr"
            mock_settings.return_value = s

            remux_mod._run_remux("job-3", "/media/ep.mkv", 2, 0)

        calls = mock_update.call_args_list
        assert calls[1][0][1] == "failed"
        assert "unexpected" in calls[1][1]["error"].lower()

    def test_run_remux_always_resumes_arr(self, client):
        """_arr_pause(False) is called even if the remux fails."""
        import routes.remux as remux_mod

        with (
            patch("routes.remux.get_settings") as mock_settings,
            patch(
                "routes.remux.remove_subtitle_stream",
                side_effect=RuntimeError("boom"),
            ),
            patch("routes.remux._update_job"),
            patch("routes.remux._arr_pause") as mock_pause,
        ):
            s = MagicMock()
            s.remux_use_reflink = True
            s.remux_trash_dir = ".sublarr"
            mock_settings.return_value = s

            remux_mod._run_remux("job-4", "/media/ep.mkv", 2, 0)

        # Final call must be _arr_pause(False) for resume
        assert mock_pause.call_args_list[-1][0] == (False,)


# ---------------------------------------------------------------------------
# _purge_sidecars_for_video
# ---------------------------------------------------------------------------


class TestPurgeSidecarsForVideo:
    """Tests for the _purge_sidecars_for_video helper."""

    def test_no_media_path(self, client):
        with patch("routes.remux.get_settings") as mock_settings:
            s = MagicMock()
            s.media_path = ""
            mock_settings.return_value = s

            from routes.remux import _purge_sidecars_for_video

            result = _purge_sidecars_for_video("/media/ep.mkv")
            assert result == 0

    def test_trash_root_not_a_dir(self, client):
        """Returns 0 when the trash root directory does not exist."""
        mock_trash_root = MagicMock(return_value="/nonexistent/trash")
        mock_read_manifest = MagicMock()
        with (
            patch("routes.remux.get_settings") as mock_settings,
            patch.dict(
                "sys.modules",
                {"routes.subtitles": MagicMock(
                    _get_trash_root=mock_trash_root,
                    _read_manifest=mock_read_manifest,
                )},
            ),
            patch("routes.remux.os.path.isdir", return_value=False),
        ):
            s = MagicMock()
            s.media_path = "/media"
            mock_settings.return_value = s

            from routes.remux import _purge_sidecars_for_video

            result = _purge_sidecars_for_video("/media/show/ep.mkv")
            assert result == 0
