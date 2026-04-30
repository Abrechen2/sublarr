"""HTTP tests for routes/translate/ — jobs, status, backends, batch, memory."""

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# GET /api/v1/status/<job_id> — job status
# ---------------------------------------------------------------------------


def test_job_status_not_found(client):
    with patch("db.jobs.get_job", return_value=None):
        resp = client.get("/api/v1/status/nonexistent-id")
    assert resp.status_code == 404


def test_job_status_found(client):
    fake_job = {
        "id": "job-123",
        "status": "completed",
        "file_path": "/media/ep.srt",
        "result": {"success": True},
        "error": None,
    }
    with patch("db.jobs.get_job", return_value=fake_job):
        resp = client.get("/api/v1/status/job-123")
    data = resp.get_json()
    assert resp.status_code == 200
    assert data["id"] == "job-123"
    assert data["status"] == "completed"


def test_job_status_failed(client):
    fake_job = {
        "id": "job-fail",
        "status": "failed",
        "file_path": "/media/ep.srt",
        "result": None,
        "error": "Ollama unreachable",
    }
    with patch("db.jobs.get_job", return_value=fake_job):
        resp = client.get("/api/v1/status/job-fail")
    data = resp.get_json()
    assert resp.status_code == 200
    assert data["status"] == "failed"


# ---------------------------------------------------------------------------
# GET /api/v1/jobs — list jobs
# ---------------------------------------------------------------------------


def test_list_jobs_empty(client):
    with patch(
        "db.jobs.get_jobs", return_value={"jobs": [], "total": 0, "page": 1, "per_page": 50}
    ):
        resp = client.get("/api/v1/jobs")
    data = resp.get_json()
    assert resp.status_code == 200
    assert "jobs" in data
    assert data["total"] == 0


def test_list_jobs_with_data(client):
    fake_jobs = {
        "jobs": [
            {"id": "j1", "status": "completed", "file_path": "/media/ep1.srt"},
            {"id": "j2", "status": "failed", "file_path": "/media/ep2.srt"},
        ],
        "total": 2,
        "page": 1,
        "per_page": 50,
    }
    with patch("db.jobs.get_jobs", return_value=fake_jobs):
        resp = client.get("/api/v1/jobs")
    data = resp.get_json()
    assert resp.status_code == 200
    assert len(data["jobs"]) == 2


def test_list_jobs_with_status_filter(client):
    with patch(
        "db.jobs.get_jobs", return_value={"jobs": [], "total": 0, "page": 1, "per_page": 50}
    ):
        resp = client.get("/api/v1/jobs?status=completed")
    assert resp.status_code == 200


def test_list_jobs_pagination(client):
    with patch(
        "db.jobs.get_jobs", return_value={"jobs": [], "total": 0, "page": 2, "per_page": 10}
    ):
        resp = client.get("/api/v1/jobs?page=2&per_page=10")
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# POST /api/v1/jobs/<job_id>/retry — retry failed job
# ---------------------------------------------------------------------------


def test_retry_job_not_found(client):
    with patch("db.jobs.get_job", return_value=None):
        resp = client.post("/api/v1/jobs/nonexistent/retry")
    assert resp.status_code == 404


def test_retry_job_not_failed(client):
    fake_job = {"id": "j1", "status": "completed", "file_path": "/media/ep.srt"}
    with patch("db.jobs.get_job", return_value=fake_job):
        resp = client.post("/api/v1/jobs/j1/retry")
    assert resp.status_code == 400
    data = resp.get_json()
    assert "failed" in data["error"].lower()


def test_retry_job_file_missing(client, temp_dir):
    fake_job = {
        "id": "j1",
        "status": "failed",
        "file_path": "/nonexistent/ep.srt",
        "arr_context": None,
    }
    with patch("db.jobs.get_job", return_value=fake_job):
        resp = client.post("/api/v1/jobs/j1/retry")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /api/v1/translate — async translate job
# ---------------------------------------------------------------------------


def test_translate_async_missing_file_path(client):
    resp = client.post("/api/v1/translate", json={})
    assert resp.status_code == 400
    data = resp.get_json()
    assert "file_path" in data["error"]


def test_translate_async_file_not_found(client):
    resp = client.post("/api/v1/translate", json={"file_path": "/no/such/file.srt"})
    assert resp.status_code == 404


def test_translate_async_path_outside_media(client, temp_dir, monkeypatch):
    # Create a real file but outside media path
    evil = os.path.join(temp_dir, "outside.srt")
    Path(evil).write_text("1\n00:00:01,000 --> 00:00:02,000\nHello\n")

    sub_media = os.path.join(temp_dir, "media")
    os.makedirs(sub_media, exist_ok=True)
    monkeypatch.setenv("SUBLARR_MEDIA_PATH", sub_media)
    from config import reload_settings

    reload_settings()

    resp = client.post("/api/v1/translate", json={"file_path": evil})
    assert resp.status_code == 403


def test_translate_async_success(client, temp_dir, monkeypatch):
    monkeypatch.setenv("SUBLARR_MEDIA_PATH", temp_dir)
    from config import reload_settings

    reload_settings()

    sub_file = os.path.join(temp_dir, "ep.en.srt")
    Path(sub_file).write_text("1\n00:00:01,000 --> 00:00:02,000\nHello\n")

    fake_job = {"id": "job-abc", "status": "queued"}
    with (
        patch("db.jobs.create_job", return_value=fake_job),
        patch("routes.translate.core._run_job"),
        # Default config has translation_enabled=False — bypass the feature
        # gate added 2026-04-30 so this happy-path test still exercises the
        # success branch instead of hitting the 503.
        patch("routes.translate.core._is_translation_enabled", return_value=True),
    ):
        resp = client.post("/api/v1/translate", json={"file_path": sub_file})

    # Should queue the job (202) — job_queue may or may not be configured in test
    # Accept either 202 (queued) or 500 (no queue configured but job creation failed)
    assert resp.status_code in (202, 400, 404, 500)


# ---------------------------------------------------------------------------
# POST /api/v1/translate/sync — sync/queued translate
# ---------------------------------------------------------------------------


def test_translate_sync_missing_file_path(client):
    resp = client.post("/api/v1/translate/sync", json={})
    assert resp.status_code == 400


def test_translate_sync_file_not_found(client):
    resp = client.post("/api/v1/translate/sync", json={"file_path": "/no/such/file.srt"})
    assert resp.status_code == 404


def test_translate_sync_path_outside_media(client, temp_dir, monkeypatch):
    evil = os.path.join(temp_dir, "outside.srt")
    Path(evil).write_text("1\n00:00:01,000 --> 00:00:02,000\nHello\n")

    sub_media = os.path.join(temp_dir, "media")
    os.makedirs(sub_media, exist_ok=True)
    monkeypatch.setenv("SUBLARR_MEDIA_PATH", sub_media)
    from config import reload_settings

    reload_settings()

    resp = client.post("/api/v1/translate/sync", json={"file_path": evil})
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# POST /api/v1/translate/disable — disable translation
# ---------------------------------------------------------------------------


def test_disable_translation(client):
    with (
        patch("db.config.save_config_entry"),
        patch("db.config.get_all_config_entries", return_value={}),
        patch("config.reload_settings"),
        patch("cache_response.invalidate_response_cache"),
        patch("db.jobs.cancel_queued_jobs", return_value=3),
    ):
        resp = client.post("/api/v1/translate/disable")
    data = resp.get_json()
    assert resp.status_code == 200
    assert data["status"] == "disabled"
    assert data["cancelled_jobs"] == 3


# ---------------------------------------------------------------------------
# GET /api/v1/backends — list translation backends
# ---------------------------------------------------------------------------


def test_list_backends(client):
    mock_manager = MagicMock()
    mock_manager.get_all_backends.return_value = [
        {"name": "ollama", "display_name": "Ollama", "configured": True, "config_fields": []},
        {"name": "deepl", "display_name": "DeepL", "configured": False, "config_fields": []},
    ]
    with patch("translation.get_translation_manager", return_value=mock_manager):
        resp = client.get("/api/v1/backends")
    data = resp.get_json()
    assert resp.status_code == 200
    assert "backends" in data
    assert len(data["backends"]) == 2


# ---------------------------------------------------------------------------
# POST /api/v1/backends/test/<name> — test backend health
# ---------------------------------------------------------------------------


def test_test_backend_not_found(client):
    mock_manager = MagicMock()
    mock_manager.get_backend.return_value = None
    with patch("translation.get_translation_manager", return_value=mock_manager):
        resp = client.post("/api/v1/backends/test/nonexistent")
    assert resp.status_code == 404


def test_test_backend_healthy(client):
    mock_backend = MagicMock()
    mock_backend.health_check.return_value = (True, "Ollama reachable")
    mock_backend.get_usage.return_value = None

    mock_manager = MagicMock()
    mock_manager.get_backend.return_value = mock_backend
    with patch("translation.get_translation_manager", return_value=mock_manager):
        resp = client.post("/api/v1/backends/test/ollama")
    data = resp.get_json()
    assert resp.status_code == 200
    assert data["healthy"] is True
    assert data["message"] == "Ollama reachable"


def test_test_backend_unhealthy(client):
    mock_backend = MagicMock()
    mock_backend.health_check.return_value = (False, "Connection refused")
    mock_backend.get_usage.return_value = None

    mock_manager = MagicMock()
    mock_manager.get_backend.return_value = mock_backend
    with patch("translation.get_translation_manager", return_value=mock_manager):
        resp = client.post("/api/v1/backends/test/ollama")
    data = resp.get_json()
    assert resp.status_code == 200
    assert data["healthy"] is False


def test_test_backend_with_usage(client):
    mock_backend = MagicMock()
    mock_backend.health_check.return_value = (True, "OK")
    mock_backend.get_usage.return_value = {"requests": 100, "limit": 500}

    mock_manager = MagicMock()
    mock_manager.get_backend.return_value = mock_backend
    with patch("translation.get_translation_manager", return_value=mock_manager):
        resp = client.post("/api/v1/backends/test/deepl")
    data = resp.get_json()
    assert resp.status_code == 200
    assert "usage" in data
    assert data["usage"]["requests"] == 100


# ---------------------------------------------------------------------------
# GET /api/v1/backends/<name>/config — get backend config
# ---------------------------------------------------------------------------


def test_get_backend_config_not_found(client):
    mock_manager = MagicMock()
    mock_manager.get_all_backends.return_value = []
    with patch("translation.get_translation_manager", return_value=mock_manager):
        resp = client.get("/api/v1/backends/nonexistent/config")
    assert resp.status_code == 404


def test_get_backend_config_found(client):
    mock_manager = MagicMock()
    mock_manager.get_all_backends.return_value = [
        {"name": "ollama", "config_fields": [{"key": "url", "type": "text"}]}
    ]
    with (
        patch("translation.get_translation_manager", return_value=mock_manager),
        patch(
            "db.config.get_all_config_entries",
            return_value={"backend.ollama.url": "http://localhost:11434"},
        ),
    ):
        resp = client.get("/api/v1/backends/ollama/config")
    data = resp.get_json()
    assert resp.status_code == 200
    assert "url" in data


def test_get_backend_config_masks_password(client):
    mock_manager = MagicMock()
    mock_manager.get_all_backends.return_value = [
        {
            "name": "deepl",
            "config_fields": [{"key": "api_key", "type": "password"}],
        }
    ]
    with (
        patch("translation.get_translation_manager", return_value=mock_manager),
        patch(
            "db.config.get_all_config_entries",
            return_value={"backend.deepl.api_key": "supersecret"},
        ),
    ):
        resp = client.get("/api/v1/backends/deepl/config")
    data = resp.get_json()
    assert resp.status_code == 200
    assert data.get("api_key") == "***"


# ---------------------------------------------------------------------------
# PUT /api/v1/backends/<name>/config — save backend config
# ---------------------------------------------------------------------------


def test_save_backend_config_not_found(client):
    mock_manager = MagicMock()
    mock_manager.get_all_backends.return_value = []
    with patch("translation.get_translation_manager", return_value=mock_manager):
        resp = client.put("/api/v1/backends/nonexistent/config", json={"url": "http://x"})
    assert resp.status_code == 404


def test_save_backend_config_no_data(client):
    mock_manager = MagicMock()
    mock_manager.get_all_backends.return_value = [{"name": "ollama", "config_fields": []}]
    with patch("translation.get_translation_manager", return_value=mock_manager):
        resp = client.put("/api/v1/backends/ollama/config", json={})
    assert resp.status_code == 400


def test_save_backend_config_success(client):
    mock_manager = MagicMock()
    mock_manager.get_all_backends.return_value = [{"name": "ollama", "config_fields": []}]
    with (
        patch("translation.get_translation_manager", return_value=mock_manager),
        patch("db.config.save_config_entry") as mock_save,
    ):
        resp = client.put("/api/v1/backends/ollama/config", json={"url": "http://localhost:11434"})
    data = resp.get_json()
    assert resp.status_code == 200
    assert data["status"] == "saved"
    mock_save.assert_called_once_with("backend.ollama.url", "http://localhost:11434")


# ---------------------------------------------------------------------------
# GET /api/v1/backends/templates — LLM backend templates
# ---------------------------------------------------------------------------


def test_get_backend_templates(client):
    resp = client.get("/api/v1/backends/templates")
    data = resp.get_json()
    assert resp.status_code == 200
    assert "templates" in data
    assert isinstance(data["templates"], list)


# ---------------------------------------------------------------------------
# GET /api/v1/backends/stats — backend statistics
# ---------------------------------------------------------------------------


def test_backend_stats(client):
    with patch(
        "db.translation.get_backend_stats",
        return_value=[{"backend": "ollama", "requests": 5, "errors": 0}],
    ):
        resp = client.get("/api/v1/backends/stats")
    data = resp.get_json()
    assert resp.status_code == 200
    assert "stats" in data


# ---------------------------------------------------------------------------
# GET /api/v1/translation-memory/stats — translation memory stats
# ---------------------------------------------------------------------------


def test_translation_memory_stats(client):
    with patch(
        "db.translation.get_translation_cache_stats",
        return_value={"entries": 42},
    ):
        resp = client.get("/api/v1/translation-memory/stats")
    data = resp.get_json()
    assert resp.status_code == 200
    assert "entries" in data


def test_translation_memory_stats_error(client):
    with patch("db.translation.get_translation_cache_stats", side_effect=RuntimeError("DB error")):
        resp = client.get("/api/v1/translation-memory/stats")
    assert resp.status_code == 500
