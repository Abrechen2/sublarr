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


def test_put_config_rejects_empty_body(client):
    resp = client.put(
        "/api/v1/config",
        json={},
        content_type="application/json",
    )
    assert resp.status_code == 400
    data = resp.get_json()
    assert "error" in data


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
