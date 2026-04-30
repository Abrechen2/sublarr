"""Tests for routes/whisper.py -- transcription jobs, backends, config, stats."""

import os
import sys
import tempfile
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Resolve once to avoid 8.3 short-name mismatch on Windows
_TEMP_DIR = os.path.realpath(tempfile.gettempdir())


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def client(temp_db):
    from app import create_app

    app = create_app(testing=True)
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


@pytest.fixture(autouse=True)
def reset_whisper_queue():
    """Reset the module-level _queue singleton between tests."""
    import routes.whisper as whisper_mod

    whisper_mod._queue = None
    yield
    whisper_mod._queue = None


# ---------------------------------------------------------------------------
# TestTranscribe — POST /api/v1/whisper/transcribe
# ---------------------------------------------------------------------------


class TestTranscribe:
    def test_400_when_file_path_missing(self, client):
        resp = client.post("/api/v1/whisper/transcribe", json={})
        assert resp.status_code == 400
        assert "file_path" in resp.get_json()["error"]

    def test_403_when_path_outside_media_path(self, client):
        with (
            patch("config.map_path", return_value="/etc/passwd"),
            patch("config.get_settings") as mock_gs,
        ):
            mock_gs.return_value = MagicMock(media_path=_TEMP_DIR, source_language="ja")
            resp = client.post(
                "/api/v1/whisper/transcribe",
                json={"file_path": "/etc/passwd"},
            )
        assert resp.status_code == 403

    def test_404_when_file_does_not_exist(self, client):
        nonexistent = os.path.join(_TEMP_DIR, "nonexistent_file.mkv")
        with patch("config.map_path", return_value=nonexistent):
            resp = client.post(
                "/api/v1/whisper/transcribe",
                json={"file_path": nonexistent},
            )
        assert resp.status_code == 404

    def test_400_invalid_audio_track_index(self, client, tmp_path):
        video = tmp_path / "video.mkv"
        video.write_text("fake")
        video_str = str(video)
        with (
            patch("config.map_path", return_value=video_str),
            patch("config.get_settings") as mock_gs,
        ):
            mock_gs.return_value = MagicMock(media_path=str(tmp_path), source_language="ja")
            resp = client.post(
                "/api/v1/whisper/transcribe",
                json={"file_path": video_str, "audio_track_index": -1},
            )
        assert resp.status_code == 400
        assert "audio_track_index" in resp.get_json()["error"]

    def test_202_on_success(self, client, tmp_path):
        video = tmp_path / "video.mkv"
        video.write_text("fake video content")
        video_str = str(video)

        mock_manager = MagicMock()
        mock_queue = MagicMock()

        with (
            patch("config.map_path", return_value=video_str),
            patch("config.get_settings") as mock_gs,
            patch("whisper.get_whisper_manager", return_value=mock_manager),
            patch("routes.whisper._get_queue", return_value=mock_queue),
            patch("translator._helpers._is_whisper_enabled", return_value=True),
        ):
            mock_gs.return_value = MagicMock(media_path=str(tmp_path), source_language="ja")
            resp = client.post(
                "/api/v1/whisper/transcribe",
                json={"file_path": video_str},
            )
        assert resp.status_code == 202
        data = resp.get_json()
        assert "job_id" in data
        assert data["status"] == "queued"
        mock_queue.submit.assert_called_once()

    def test_503_when_whisper_disabled(self, client, tmp_path):
        """Manual transcribe endpoint must honour the whisper_enabled toggle.

        The translator's whisper-as-fallback path already gates on this flag;
        without the matching gate here, the UI button bypassed the user's
        explicit "off" setting.
        """
        video = tmp_path / "video.mkv"
        video.write_text("fake video content")
        video_str = str(video)
        with (
            patch("config.map_path", return_value=video_str),
            patch("config.get_settings") as mock_gs,
            patch("translator._helpers._is_whisper_enabled", return_value=False),
        ):
            mock_gs.return_value = MagicMock(media_path=str(tmp_path), source_language="ja")
            resp = client.post(
                "/api/v1/whisper/transcribe",
                json={"file_path": video_str},
            )
        assert resp.status_code == 503
        assert "disabled" in resp.get_json()["error"].lower()


# ---------------------------------------------------------------------------
# TestListQueue — GET /api/v1/whisper/queue
# ---------------------------------------------------------------------------


class TestListQueue:
    def test_returns_jobs(self, client):
        jobs = [{"job_id": "abc", "status": "queued", "file_path": "/media/test.mkv"}]
        with patch("db.whisper.get_whisper_jobs", return_value=jobs):
            resp = client.get("/api/v1/whisper/queue")
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data) == 1
        assert data[0]["job_id"] == "abc"

    def test_status_filter(self, client):
        with patch("db.whisper.get_whisper_jobs", return_value=[]) as mock_fn:
            client.get("/api/v1/whisper/queue?status=completed")
        mock_fn.assert_called_once_with(status="completed", limit=50)

    def test_limit_capped_at_200(self, client):
        with patch("db.whisper.get_whisper_jobs", return_value=[]) as mock_fn:
            client.get("/api/v1/whisper/queue?limit=9999")
        mock_fn.assert_called_once_with(status=None, limit=200)

    def test_custom_limit(self, client):
        with patch("db.whisper.get_whisper_jobs", return_value=[]) as mock_fn:
            client.get("/api/v1/whisper/queue?limit=10")
        mock_fn.assert_called_once_with(status=None, limit=10)


# ---------------------------------------------------------------------------
# TestGetJob — GET /api/v1/whisper/jobs/<job_id>
# ---------------------------------------------------------------------------


class TestGetJob:
    def test_404_when_not_found(self, client):
        with patch("db.whisper.get_whisper_job", return_value=None):
            resp = client.get("/api/v1/whisper/jobs/nonexistent")
        assert resp.status_code == 404

    def test_200_with_job_data(self, client):
        job = {"job_id": "abc123", "status": "completed", "file_path": "/media/test.mkv"}
        with patch("db.whisper.get_whisper_job", return_value=job):
            resp = client.get("/api/v1/whisper/jobs/abc123")
        assert resp.status_code == 200
        assert resp.get_json()["status"] == "completed"


# ---------------------------------------------------------------------------
# TestDeleteJob — DELETE /api/v1/whisper/jobs/<job_id>
# ---------------------------------------------------------------------------


class TestDeleteJob:
    def test_404_when_not_found(self, client):
        with patch("db.whisper.get_whisper_job", return_value=None):
            resp = client.delete("/api/v1/whisper/jobs/nonexistent")
        assert resp.status_code == 404

    def test_cancel_queued_job(self, client):
        job = {"job_id": "abc", "status": "queued"}
        mock_queue = MagicMock()
        mock_queue.cancel_job.return_value = True
        with (
            patch("db.whisper.get_whisper_job", return_value=job),
            patch("routes.whisper._get_queue", return_value=mock_queue),
        ):
            resp = client.delete("/api/v1/whisper/jobs/abc")
        assert resp.status_code == 200
        assert resp.get_json()["action"] == "cancelled"
        mock_queue.cancel_job.assert_called_once_with("abc")

    def test_cancel_orphan_queued_job_marks_db_directly(self, client):
        """DB row says 'queued' but the in-memory queue dropped the job
        (e.g. service restart cleared the worker pool). The route must
        still terminate the orphan instead of returning a misleading
        success while leaving the row in 'queued' forever.
        """
        job = {"job_id": "orphan", "status": "queued"}
        mock_queue = MagicMock()
        mock_queue.cancel_job.return_value = False  # not in memory
        with (
            patch("db.whisper.get_whisper_job", return_value=job),
            patch("routes.whisper._get_queue", return_value=mock_queue),
            patch("db.whisper.update_whisper_job") as mock_update,
        ):
            resp = client.delete("/api/v1/whisper/jobs/orphan")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["action"] == "cancelled"
        assert data.get("orphan") is True
        mock_update.assert_called_once_with("orphan", status="cancelled")

    def test_delete_completed_job(self, client):
        job = {"job_id": "abc", "status": "completed"}
        with (
            patch("db.whisper.get_whisper_job", return_value=job),
            patch("db.whisper.delete_whisper_job") as mock_del,
        ):
            resp = client.delete("/api/v1/whisper/jobs/abc")
        assert resp.status_code == 200
        assert resp.get_json()["action"] == "deleted"
        mock_del.assert_called_once_with("abc")

    def test_delete_failed_job(self, client):
        job = {"job_id": "abc", "status": "failed"}
        with (
            patch("db.whisper.get_whisper_job", return_value=job),
            patch("db.whisper.delete_whisper_job"),
        ):
            resp = client.delete("/api/v1/whisper/jobs/abc")
        assert resp.status_code == 200
        assert resp.get_json()["action"] == "deleted"

    def test_409_when_job_in_progress(self, client):
        job = {"job_id": "abc", "status": "transcribing"}
        with patch("db.whisper.get_whisper_job", return_value=job):
            resp = client.delete("/api/v1/whisper/jobs/abc")
        assert resp.status_code == 409
        assert "in progress" in resp.get_json()["error"].lower()


# ---------------------------------------------------------------------------
# TestListBackends — GET /api/v1/whisper/backends
# ---------------------------------------------------------------------------


class TestListBackends:
    def test_returns_backends(self, client):
        mock_manager = MagicMock()
        mock_manager.get_all_backends.return_value = [
            {"name": "subgen", "label": "Subgen", "config_fields": []},
        ]
        with patch("whisper.get_whisper_manager", return_value=mock_manager):
            resp = client.get("/api/v1/whisper/backends")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "backends" in data
        assert len(data["backends"]) == 1
        assert data["backends"][0]["name"] == "subgen"


# ---------------------------------------------------------------------------
# TestTestBackend — POST /api/v1/whisper/backends/test/<name>
# ---------------------------------------------------------------------------


class TestTestBackend:
    def test_404_when_backend_not_found(self, client):
        mock_manager = MagicMock()
        mock_manager.get_backend.return_value = None
        with patch("whisper.get_whisper_manager", return_value=mock_manager):
            resp = client.post("/api/v1/whisper/backends/test/nonexistent")
        assert resp.status_code == 404

    def test_returns_health_check_result(self, client):
        mock_backend = MagicMock()
        mock_backend.health_check.return_value = (True, "OK")
        mock_manager = MagicMock()
        mock_manager.get_backend.return_value = mock_backend
        with patch("whisper.get_whisper_manager", return_value=mock_manager):
            resp = client.post("/api/v1/whisper/backends/test/subgen")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["healthy"] is True
        assert data["message"] == "OK"

    def test_unhealthy_backend(self, client):
        mock_backend = MagicMock()
        mock_backend.health_check.return_value = (False, "Connection refused")
        mock_manager = MagicMock()
        mock_manager.get_backend.return_value = mock_backend
        with patch("whisper.get_whisper_manager", return_value=mock_manager):
            resp = client.post("/api/v1/whisper/backends/test/subgen")
        assert resp.status_code == 200
        assert resp.get_json()["healthy"] is False


# ---------------------------------------------------------------------------
# TestGetBackendConfig — GET /api/v1/whisper/backends/config/<name>
# ---------------------------------------------------------------------------


class TestGetBackendConfig:
    def test_404_when_backend_not_found(self, client):
        mock_manager = MagicMock()
        mock_manager.get_all_backends.return_value = []
        with (
            patch("whisper.get_whisper_manager", return_value=mock_manager),
            patch("db.config.get_all_config_entries", return_value={}),
        ):
            resp = client.get("/api/v1/whisper/backends/config/nonexistent")
        assert resp.status_code == 404

    def test_returns_config_with_masked_passwords(self, client):
        mock_manager = MagicMock()
        mock_manager.get_all_backends.return_value = [
            {
                "name": "subgen",
                "config_fields": [
                    {"key": "url", "type": "text"},
                    {"key": "api_key", "type": "password"},
                ],
            }
        ]
        config_entries = {
            "whisper.subgen.url": "http://localhost:9000",
            "whisper.subgen.api_key": "secret123",
        }
        with (
            patch("whisper.get_whisper_manager", return_value=mock_manager),
            patch("db.config.get_all_config_entries", return_value=config_entries),
        ):
            resp = client.get("/api/v1/whisper/backends/config/subgen")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["url"] == "http://localhost:9000"
        assert data["api_key"] == "***"  # masked


# ---------------------------------------------------------------------------
# TestSaveBackendConfig — PUT /api/v1/whisper/backends/config/<name>
# ---------------------------------------------------------------------------


class TestSaveBackendConfig:
    def test_400_when_no_data(self, client):
        mock_manager = MagicMock()
        mock_manager.get_all_backends.return_value = [{"name": "subgen"}]
        with patch("whisper.get_whisper_manager", return_value=mock_manager):
            resp = client.put(
                "/api/v1/whisper/backends/config/subgen",
                json={},
            )
        assert resp.status_code == 400

    def test_404_when_backend_not_found(self, client):
        mock_manager = MagicMock()
        mock_manager.get_all_backends.return_value = []
        with patch("whisper.get_whisper_manager", return_value=mock_manager):
            resp = client.put(
                "/api/v1/whisper/backends/config/nonexistent",
                json={"url": "http://localhost"},
            )
        assert resp.status_code == 404

    def test_200_saves_and_invalidates(self, client):
        mock_manager = MagicMock()
        mock_manager.get_all_backends.return_value = [{"name": "subgen"}]
        with (
            patch("whisper.get_whisper_manager", return_value=mock_manager),
            patch("db.config.save_config_entry") as mock_save,
        ):
            resp = client.put(
                "/api/v1/whisper/backends/config/subgen",
                json={"url": "http://new-host:9000"},
            )
        assert resp.status_code == 200
        assert resp.get_json()["success"] is True
        mock_save.assert_called_once_with("whisper.subgen.url", "http://new-host:9000")
        mock_manager.invalidate_backend.assert_called_once()


# ---------------------------------------------------------------------------
# TestGetWhisperConfig — GET /api/v1/whisper/config
# ---------------------------------------------------------------------------


class TestGetWhisperConfig:
    def test_returns_config(self, client):
        def fake_config(key, default=""):
            mapping = {
                "whisper_backend": "subgen",
                "max_concurrent_whisper": "2",
                "whisper_enabled": "true",
            }
            return mapping.get(key, default)

        with patch("routes.whisper._get_config", side_effect=fake_config):
            resp = client.get("/api/v1/whisper/config")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["whisper_backend"] == "subgen"
        assert data["max_concurrent_whisper"] == 2
        assert data["whisper_enabled"] is True

    def test_defaults_when_no_config(self, client):
        """When _get_config returns default values (not empty strings)."""

        def fake_config(key, default=""):
            # Return the defaults that _get_config would return
            return default

        with patch("routes.whisper._get_config", side_effect=fake_config):
            resp = client.get("/api/v1/whisper/config")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["whisper_backend"] == "subgen"
        assert data["max_concurrent_whisper"] == 1
        assert data["whisper_enabled"] is False


# ---------------------------------------------------------------------------
# TestSaveWhisperConfig — PUT /api/v1/whisper/config
# ---------------------------------------------------------------------------


class TestSaveWhisperConfig:
    def test_400_when_no_data(self, client):
        resp = client.put("/api/v1/whisper/config", json={})
        assert resp.status_code == 400

    def test_saves_allowed_keys_only(self, client):
        with patch("db.config.save_config_entry") as mock_save:
            resp = client.put(
                "/api/v1/whisper/config",
                json={
                    "whisper_backend": "subgen",
                    "unknown_key": "ignored",
                },
            )
        assert resp.status_code == 200
        # Only whisper_backend saved, unknown_key skipped
        mock_save.assert_called_once_with("whisper_backend", "subgen")

    def test_boolean_converted_to_string(self, client):
        with patch("db.config.save_config_entry") as mock_save:
            resp = client.put(
                "/api/v1/whisper/config",
                json={"whisper_enabled": True},
            )
        assert resp.status_code == 200
        mock_save.assert_called_once_with("whisper_enabled", "true")

    def test_resets_queue_on_concurrency_change(self, client):
        import routes.whisper as whisper_mod

        whisper_mod._queue = MagicMock()  # pretend queue exists
        with patch("db.config.save_config_entry"):
            client.put(
                "/api/v1/whisper/config",
                json={"max_concurrent_whisper": 4},
            )
        assert whisper_mod._queue is None  # reset after concurrency change

    def test_400_when_max_concurrent_is_zero_or_negative(self, client):
        """max_concurrent < 1 would create a Semaphore that blocks every job
        forever, silently breaking the queue. Reject up-front."""
        for bad in (0, -1):
            resp = client.put(
                "/api/v1/whisper/config",
                json={"max_concurrent_whisper": bad},
            )
            assert resp.status_code == 400, f"expected 400 for {bad}, got {resp.status_code}"

    def test_400_when_max_concurrent_above_cap(self, client):
        resp = client.put(
            "/api/v1/whisper/config",
            json={"max_concurrent_whisper": 100},
        )
        assert resp.status_code == 400

    def test_400_when_max_concurrent_not_integer(self, client):
        resp = client.put(
            "/api/v1/whisper/config",
            json={"max_concurrent_whisper": "abc"},
        )
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# TestWhisperStats — GET /api/v1/whisper/stats
# ---------------------------------------------------------------------------


class TestWhisperStats:
    def test_returns_stats(self, client):
        stats = {
            "total": 42,
            "by_status": {"completed": 30, "failed": 12},
            "avg_processing_time": 5.3,
        }
        with patch("db.whisper.get_whisper_stats", return_value=stats):
            resp = client.get("/api/v1/whisper/stats")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["total"] == 42
        assert data["by_status"]["completed"] == 30
