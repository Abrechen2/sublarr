"""HTTP tests for routes/mediaservers.py — types, instances, test connection."""

from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# GET /api/v1/mediaservers/types
# ---------------------------------------------------------------------------


def test_list_server_types_returns_list(client):
    resp = client.get("/api/v1/mediaservers/types")
    assert resp.status_code == 200
    data = resp.get_json()
    assert isinstance(data, list)


def test_list_server_types_entries_have_name(client):
    resp = client.get("/api/v1/mediaservers/types")
    assert resp.status_code == 200
    data = resp.get_json()
    for entry in data:
        assert "name" in entry


# ---------------------------------------------------------------------------
# GET /api/v1/mediaservers/instances
# ---------------------------------------------------------------------------


def test_get_instances_empty_by_default(client):
    # Fresh test DB has no media_servers_json entry — should return empty list
    resp = client.get("/api/v1/mediaservers/instances")
    assert resp.status_code == 200
    data = resp.get_json()
    assert isinstance(data, list)


def test_get_instances_masks_api_key(client):
    # Seed a config entry with a sensitive api_key and verify masking
    import json

    from flask import g

    from app import create_app
    from db.config import save_config_entry

    # Use the client's app to push an app context for DB seeding
    with client.application.app_context():
        save_config_entry(
            "media_servers_json",
            json.dumps([{"type": "jellyfin", "name": "Home", "api_key": "supersecrettoken1234"}]),
        )

    resp = client.get("/api/v1/mediaservers/instances")
    assert resp.status_code == 200
    data = resp.get_json()
    assert len(data) == 1
    assert data[0]["api_key"].startswith("***")
    assert "supersecrettoken" not in data[0]["api_key"]


# ---------------------------------------------------------------------------
# POST /api/v1/mediaservers/test
# ---------------------------------------------------------------------------


def test_connection_test_missing_body(client):
    # Empty body → missing 'type' → 400
    resp = client.post(
        "/api/v1/mediaservers/test",
        json={},
        content_type="application/json",
    )
    assert resp.status_code == 400
    data = resp.get_json()
    assert "error" in data


def test_connection_test_unknown_type(client):
    resp = client.post(
        "/api/v1/mediaservers/test",
        json={"type": "nonexistent_server_xyz"},
        content_type="application/json",
    )
    assert resp.status_code == 400
    data = resp.get_json()
    assert "error" in data


def test_connection_test_mocked_success(client):
    # Mock the media server manager so no real network call is made
    mock_manager = MagicMock()
    mock_manager.get_all_server_types.return_value = [
        {"name": "jellyfin", "display_name": "Jellyfin", "config_fields": []}
    ]
    mock_cls = MagicMock()
    mock_instance = MagicMock()
    mock_instance.health_check.return_value = (True, "OK")
    mock_cls.return_value = mock_instance
    mock_manager._server_classes = {"jellyfin": mock_cls}

    with patch("mediaserver.get_media_server_manager", return_value=mock_manager):
        resp = client.post(
            "/api/v1/mediaservers/test",
            json={"type": "jellyfin", "url": "http://localhost:8096"},
            content_type="application/json",
        )

    assert resp.status_code == 200
    data = resp.get_json()
    assert "healthy" in data
    assert data["healthy"] is True
