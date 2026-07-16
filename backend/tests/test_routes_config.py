"""HTTP tests for routes/config.py — GET/PUT /config, path-mapping test, export."""

import pytest

# ---------------------------------------------------------------------------
# GET /api/v1/config
# ---------------------------------------------------------------------------


def test_get_config_returns_safe_fields(client):
    resp = client.get("/api/v1/config")
    assert resp.status_code == 200
    data = resp.get_json()
    assert isinstance(data, dict)
    # Safe config must not expose raw api_key value (masked or absent)
    # The key "api_key" may be present but must never be a real non-empty plaintext value
    if "api_key" in data:
        val = data["api_key"]
        # Either empty (unconfigured) or masked
        assert val == "" or val == "***configured***", f"api_key was not masked: {val!r}"


# ---------------------------------------------------------------------------
# PUT /api/v1/config
# ---------------------------------------------------------------------------


def test_put_config_updates_key(client):
    resp = client.put(
        "/api/v1/config",
        json={"log_level": "DEBUG"},
        content_type="application/json",
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data.get("status") == "saved"
    assert "log_level" in data.get("updated_keys", [])


def test_put_config_log_level_reflected_in_response(client):
    """Saving log_level must persist through the reload and come back in the
    response config (not snap back to the ENV/default INFO).

    Regression guard for the reported 'can't change log level from info to
    debug' bug — the value was written to config_entries but dropped on reload.
    """
    resp = client.put(
        "/api/v1/config",
        json={"log_level": "DEBUG"},
        content_type="application/json",
    )
    assert resp.status_code == 200
    assert resp.get_json()["config"]["log_level"] == "DEBUG"


def test_put_config_log_level_applies_live(client):
    """Changing log_level must take effect on the running logger without a
    restart (re-runs _setup_logging)."""
    import logging

    previous = logging.getLogger().level
    try:
        resp = client.put(
            "/api/v1/config",
            json={"log_level": "DEBUG"},
            content_type="application/json",
        )
        assert resp.status_code == 200
        assert logging.getLogger().level == logging.DEBUG
    finally:
        logging.getLogger().setLevel(previous)


def test_put_config_rejects_empty_body(client):
    resp = client.put(
        "/api/v1/config",
        json={},
        content_type="application/json",
    )
    assert resp.status_code == 400
    data = resp.get_json()
    assert "error" in data


def test_put_config_non_scheduler_key_skips_scheduler_restart(client, monkeypatch):
    """A bare UI-only save (e.g. items_per_page) must NOT restart the scanner
    scheduler.

    Regression guard for the ~12s settings-lag reports: the unconditional
    APScheduler jobstore trigger rewrite (~2.5s) fired on every save. The
    scanner caches no settings, so only an interval change needs a restart.
    """
    import services.wanted_scanner as ws

    calls = []

    class _RecordingScanner:
        def start_scheduler(self, *args, **kwargs):
            calls.append(True)

    monkeypatch.setattr(ws, "get_scanner", lambda: _RecordingScanner())
    resp = client.put(
        "/api/v1/config",
        json={"items_per_page": 26},
        content_type="application/json",
    )
    assert resp.status_code == 200
    assert calls == [], "items_per_page save must not restart the scanner scheduler"


def test_put_config_interval_key_restarts_scheduler(client, monkeypatch):
    """Changing a scan/search interval MUST restart the scheduler so the new
    trigger reaches APScheduler."""
    import services.wanted_scanner as ws

    calls = []

    class _RecordingScanner:
        def start_scheduler(self, *args, **kwargs):
            calls.append(True)

    monkeypatch.setattr(ws, "get_scanner", lambda: _RecordingScanner())
    resp = client.put(
        "/api/v1/config",
        json={"wanted_search_interval_hours": 12},
        content_type="application/json",
    )
    assert resp.status_code == 200
    assert calls == [True], "interval change must restart the scanner scheduler"


def test_put_config_rejects_invalid_enum(client):
    resp = client.put(
        "/api/v1/config",
        json={"log_level": "VERBOSE"},
        content_type="application/json",
    )
    # Route validates enum fields and returns 400 for invalid values
    assert resp.status_code == 400
    data = resp.get_json()
    assert "error" in data


# ---------------------------------------------------------------------------
# POST /api/v1/settings/path-mapping/test
# ---------------------------------------------------------------------------


def test_path_mapping_test_missing_param(client):
    resp = client.post(
        "/api/v1/settings/path-mapping/test",
        json={},
        content_type="application/json",
    )
    assert resp.status_code == 400
    data = resp.get_json()
    assert "error" in data


def test_path_mapping_test_valid(client):
    resp = client.post(
        "/api/v1/settings/path-mapping/test",
        json={"remote_path": "/mnt/shows/ep.mkv"},
        content_type="application/json",
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert "remote_path" in data
    assert "mapped_path" in data
    assert "exists" in data
    assert isinstance(data["exists"], bool)


# ---------------------------------------------------------------------------
# GET /api/v1/config/export
# ---------------------------------------------------------------------------


def test_config_export_returns_json_content_type(client):
    resp = client.get("/api/v1/config/export")
    if resp.status_code == 404:
        pytest.skip("Export route not available in this build")
    assert resp.status_code == 200
    assert "application/json" in resp.content_type
    data = resp.get_json()
    assert isinstance(data, dict)
