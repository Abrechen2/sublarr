"""HTTP tests for GET /api/v1/wanted/export — CSV/JSON download."""

import csv
import io

import pytest
from sqlalchemy import text

from app import create_app
from db import get_db


def _insert_wanted_item(client_app, title="Test Episode", status="wanted", target_language="de"):
    """Insert a minimal wanted_item row via the app's context and return its id."""
    with client_app.app_context():
        db = get_db()
        db.execute(
            text(
                "INSERT INTO wanted_items"
                " (title, file_path, item_type, target_language, status, priority,"
                "  error_count, added_at, updated_at)"
                " VALUES (:t, :fp, 'episode', :tl, :s, 'standard',"
                "  0, datetime('now'), datetime('now'))"
            ),
            {"t": title, "fp": "/media/ep.mkv", "s": status, "tl": target_language},
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


def test_export_invalid_format(client):
    resp = client.get("/api/v1/wanted/export?format=xml")
    assert resp.status_code == 400
    assert "Invalid format" in resp.get_json()["error"]


def test_export_csv_empty(client):
    resp = client.get("/api/v1/wanted/export")
    assert resp.status_code == 200
    assert resp.mimetype == "text/csv"
    assert "attachment" in resp.headers["Content-Disposition"]
    rows = list(csv.reader(io.StringIO(resp.get_data(as_text=True))))
    assert rows[0][0] == "id"  # header row only
    assert len(rows) == 1


def test_export_csv_populated(app_and_client):
    app, client = app_and_client
    _insert_wanted_item(app, "Episode A")
    _insert_wanted_item(app, "Episode B", status="ignored")

    resp = client.get("/api/v1/wanted/export?format=csv")
    assert resp.status_code == 200
    rows = list(csv.DictReader(io.StringIO(resp.get_data(as_text=True))))
    assert len(rows) == 2
    titles = {r["title"] for r in rows}
    assert titles == {"Episode A", "Episode B"}
    assert all(r["file_path"] == "/media/ep.mkv" for r in rows)


def test_export_csv_respects_status_filter(app_and_client):
    app, client = app_and_client
    _insert_wanted_item(app, "Episode A")
    _insert_wanted_item(app, "Episode B", status="ignored")

    resp = client.get("/api/v1/wanted/export?format=csv&status=ignored")
    rows = list(csv.DictReader(io.StringIO(resp.get_data(as_text=True))))
    assert len(rows) == 1
    assert rows[0]["title"] == "Episode B"


def test_export_json(app_and_client):
    app, client = app_and_client
    _insert_wanted_item(app, "Episode A")

    resp = client.get("/api/v1/wanted/export?format=json")
    assert resp.status_code == 200
    assert resp.mimetype == "application/json"
    assert resp.headers["Content-Disposition"].endswith('.json"')
    payload = resp.get_json()
    assert isinstance(payload, list)
    assert len(payload) == 1
    assert payload[0]["title"] == "Episode A"
    assert payload[0]["target_language"] == "de"
