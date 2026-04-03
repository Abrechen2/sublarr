"""HTTP tests for routes/wanted/ — list, summary, status, search, extract, batch."""

import pytest
from unittest.mock import MagicMock, patch

from app import create_app
from db import get_db
from sqlalchemy import text


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _insert_wanted_item(client_app, title="Test Episode", status="wanted"):
    """Insert a minimal wanted_item row via the app's context and return its id."""
    with client_app.app_context():
        db = get_db()
        db.execute(
            text(
                "INSERT INTO wanted_items"
                " (title, file_path, item_type, target_language, status, added_at, updated_at)"
                " VALUES (:t, :fp, 'episode', 'de', :s, datetime('now'), datetime('now'))"
            ),
            {"t": title, "fp": "/media/ep.mkv", "s": status},
        )
        db.commit()
        row = db.execute(text("SELECT id FROM wanted_items ORDER BY id DESC LIMIT 1")).fetchone()
        return row[0]


@pytest.fixture
def app_and_client(temp_db):
    """Provide both Flask app and test client sharing the same DB."""
    app = create_app(testing=True)
    app.config["TESTING"] = True
    app.config["WTF_CSRF_ENABLED"] = False
    with app.test_client() as client:
        yield app, client


# ---------------------------------------------------------------------------
# GET /api/v1/wanted — list wanted items
# ---------------------------------------------------------------------------


def test_list_wanted_empty(client):
    resp = client.get("/api/v1/wanted")
    data = resp.get_json()
    assert resp.status_code == 200
    assert "data" in data or "items" in data  # Either key is valid per implementation
    assert data.get("total", 0) == 0


def test_list_wanted_populated(app_and_client):
    app, client = app_and_client
    _insert_wanted_item(app, "Episode A")
    resp = client.get("/api/v1/wanted")
    data = resp.get_json()
    assert resp.status_code == 200
    total = data.get("total", 0)
    assert total >= 1


def test_list_wanted_pagination(app_and_client):
    app, client = app_and_client
    for i in range(3):
        _insert_wanted_item(app, f"Episode {i}")
    resp = client.get("/api/v1/wanted?page=1&per_page=2")
    data = resp.get_json()
    assert resp.status_code == 200
    items = data.get("data", data.get("items", []))
    assert len(items) <= 2


def test_list_wanted_invalid_sort_by(client):
    resp = client.get("/api/v1/wanted?sort_by=bad_field")
    assert resp.status_code == 400
    data = resp.get_json()
    assert "error" in data


def test_list_wanted_invalid_sort_dir(client):
    resp = client.get("/api/v1/wanted?sort_dir=sideways")
    assert resp.status_code == 400


def test_list_wanted_filter_by_status(app_and_client):
    app, client = app_and_client
    _insert_wanted_item(app, "Ignored Ep", status="ignored")
    resp = client.get("/api/v1/wanted?status=ignored")
    data = resp.get_json()
    assert resp.status_code == 200
    items = data.get("data", data.get("items", []))
    assert all(it["status"] == "ignored" for it in items)


def test_list_wanted_filter_by_item_type(app_and_client):
    app, client = app_and_client
    _insert_wanted_item(app, "Some Episode")
    resp = client.get("/api/v1/wanted?item_type=episode")
    data = resp.get_json()
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# GET /api/v1/wanted/summary
# ---------------------------------------------------------------------------


def test_wanted_summary_empty(client):
    resp = client.get("/api/v1/wanted/summary")
    data = resp.get_json()
    assert resp.status_code == 200
    assert "total" in data
    assert "scan_running" in data


def test_wanted_summary_populated(app_and_client):
    app, client = app_and_client
    _insert_wanted_item(app, "Ep X")
    resp = client.get("/api/v1/wanted/summary")
    data = resp.get_json()
    assert resp.status_code == 200
    assert data["total"] >= 1


def test_wanted_summary_scan_running_field(client):
    resp = client.get("/api/v1/wanted/summary")
    data = resp.get_json()
    assert isinstance(data["scan_running"], bool)


# ---------------------------------------------------------------------------
# POST /api/v1/wanted/refresh — trigger scan
# ---------------------------------------------------------------------------


def test_wanted_refresh_starts_scan(client):
    resp = client.post("/api/v1/wanted/refresh", json={})
    data = resp.get_json()
    assert resp.status_code == 202
    assert data["status"] == "scan_started"


def test_wanted_refresh_conflict_when_scanning(client, monkeypatch):
    # Mock scanner to report it is already scanning
    mock_scanner = MagicMock()
    mock_scanner.is_scanning = True
    monkeypatch.setattr("services.wanted_scanner.get_scanner", lambda: mock_scanner)
    resp = client.post("/api/v1/wanted/refresh", json={})
    assert resp.status_code == 409


# ---------------------------------------------------------------------------
# PUT /api/v1/wanted/<item_id>/status
# ---------------------------------------------------------------------------


def test_update_status_item_not_found(client):
    resp = client.put("/api/v1/wanted/99999/status", json={"status": "ignored"})
    assert resp.status_code == 404


def test_update_status_invalid_status(app_and_client):
    app, client = app_and_client
    item_id = _insert_wanted_item(app, "Status Ep")
    resp = client.put(f"/api/v1/wanted/{item_id}/status", json={"status": "invalid_value"})
    assert resp.status_code == 400


def test_update_status_ignore(app_and_client):
    app, client = app_and_client
    item_id = _insert_wanted_item(app, "Ignorable Ep")
    resp = client.put(f"/api/v1/wanted/{item_id}/status", json={"status": "ignored"})
    data = resp.get_json()
    assert resp.status_code == 200
    assert data["new_status"] == "ignored"
    assert data["id"] == item_id


def test_update_status_back_to_wanted(app_and_client):
    app, client = app_and_client
    item_id = _insert_wanted_item(app, "Restore Ep", status="ignored")
    resp = client.put(f"/api/v1/wanted/{item_id}/status", json={"status": "wanted"})
    data = resp.get_json()
    assert resp.status_code == 200
    assert data["new_status"] == "wanted"


# ---------------------------------------------------------------------------
# DELETE /api/v1/wanted/<item_id>
# ---------------------------------------------------------------------------


def test_delete_wanted_not_found(client):
    resp = client.delete("/api/v1/wanted/99999")
    assert resp.status_code == 404


def test_delete_wanted_success(app_and_client):
    app, client = app_and_client
    item_id = _insert_wanted_item(app, "Delete Me")
    resp = client.delete(f"/api/v1/wanted/{item_id}")
    data = resp.get_json()
    assert resp.status_code == 200
    assert data["status"] == "deleted"
    assert data["id"] == item_id

    # Confirm it is gone
    get_resp = client.put(f"/api/v1/wanted/{item_id}/status", json={"status": "ignored"})
    assert get_resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /api/v1/wanted/<item_id>/search — async search
# ---------------------------------------------------------------------------


def test_wanted_item_search_not_found(client):
    resp = client.post("/api/v1/wanted/99999/search")
    assert resp.status_code == 404


def test_wanted_item_search_success(app_and_client):
    app, client = app_and_client
    item_id = _insert_wanted_item(app, "Searchable Ep")
    resp = client.post(f"/api/v1/wanted/{item_id}/search")
    data = resp.get_json()
    assert resp.status_code == 202
    assert data["status"] == "searching"
    assert data["wanted_id"] == item_id


# ---------------------------------------------------------------------------
# POST /api/v1/wanted/<item_id>/process — async process
# ---------------------------------------------------------------------------


def test_wanted_item_process_not_found(client):
    resp = client.post("/api/v1/wanted/99999/process")
    assert resp.status_code == 404


def test_wanted_item_process_accepted(app_and_client):
    app, client = app_and_client
    item_id = _insert_wanted_item(app, "Processable Ep")
    resp = client.post(f"/api/v1/wanted/{item_id}/process")
    data = resp.get_json()
    assert resp.status_code == 202
    assert data["status"] == "processing"


# ---------------------------------------------------------------------------
# POST /api/v1/wanted/batch-search — batch search
# ---------------------------------------------------------------------------


def test_batch_search_empty_list_rejected(client):
    resp = client.post("/api/v1/wanted/batch-search", json={"item_ids": []})
    assert resp.status_code == 400


def test_batch_search_starts(app_and_client):
    app, client = app_and_client
    item_id = _insert_wanted_item(app, "Batch Ep")
    resp = client.post("/api/v1/wanted/batch-search", json={"item_ids": [item_id]})
    data = resp.get_json()
    assert resp.status_code == 202
    assert data["status"] == "started"


def test_batch_search_conflict_when_running(client, monkeypatch):
    # Simulate batch already running
    from routes.batch_state import wanted_batch_lock, wanted_batch_state

    with wanted_batch_lock:
        wanted_batch_state["running"] = True
    try:
        resp = client.post("/api/v1/wanted/batch-search", json={"item_ids": [1]})
        assert resp.status_code == 409
    finally:
        with wanted_batch_lock:
            wanted_batch_state["running"] = False


# ---------------------------------------------------------------------------
# GET /api/v1/wanted/batch-search/status
# ---------------------------------------------------------------------------


def test_batch_search_status(client):
    resp = client.get("/api/v1/wanted/batch-search/status")
    data = resp.get_json()
    assert resp.status_code == 200
    assert "running" in data
    assert "total" in data


# ---------------------------------------------------------------------------
# POST /api/v1/wanted/batch-action
# ---------------------------------------------------------------------------


def test_batch_action_invalid_no_ids(client):
    resp = client.post("/api/v1/wanted/batch-action", json={"action": "ignore"})
    assert resp.status_code == 400


def test_batch_action_invalid_action(app_and_client):
    app, client = app_and_client
    item_id = _insert_wanted_item(app, "Batch Action Ep")
    resp = client.post(
        "/api/v1/wanted/batch-action",
        json={"item_ids": [item_id], "action": "destroy"},
    )
    assert resp.status_code == 400


def test_batch_action_too_many_ids(client):
    resp = client.post(
        "/api/v1/wanted/batch-action",
        json={"item_ids": list(range(501)), "action": "ignore"},
    )
    assert resp.status_code == 400


def test_batch_action_ignore(app_and_client):
    app, client = app_and_client
    item_id = _insert_wanted_item(app, "Ignore Target")
    resp = client.post(
        "/api/v1/wanted/batch-action",
        json={"item_ids": [item_id], "action": "ignore"},
    )
    data = resp.get_json()
    assert resp.status_code == 200
    assert data["success"] is True
    assert data["action"] == "ignore"


def test_batch_action_export(app_and_client):
    app, client = app_and_client
    item_id = _insert_wanted_item(app, "Export Target")
    resp = client.post(
        "/api/v1/wanted/batch-action",
        json={"item_ids": [item_id], "action": "export"},
    )
    data = resp.get_json()
    assert resp.status_code == 200
    assert data["action"] == "export"
    assert "data" in data


# ---------------------------------------------------------------------------
# GET /api/v1/wanted/batch-extract/status
# ---------------------------------------------------------------------------


def test_batch_extract_status(client):
    resp = client.get("/api/v1/wanted/batch-extract/status")
    data = resp.get_json()
    assert resp.status_code == 200
    assert "running" in data


# ---------------------------------------------------------------------------
# GET /api/v1/wanted/batch-probe/status
# ---------------------------------------------------------------------------


def test_batch_probe_status(client):
    resp = client.get("/api/v1/wanted/batch-probe/status")
    data = resp.get_json()
    assert resp.status_code == 200
    assert "running" in data
