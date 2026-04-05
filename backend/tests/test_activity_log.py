import os
from datetime import datetime, timezone

import pytest


def test_activity_log_model_has_expected_columns(app_ctx):
    """ActivityLog model has the correct columns and tablename."""
    from db.models.activity import ActivityLog

    assert ActivityLog.__tablename__ == "activity_log"
    mapper = ActivityLog.__mapper__
    col_names = {c.key for c in mapper.column_attrs}
    assert col_names == {"id", "event_type", "file_path", "status", "details_json", "created_at"}


def test_activity_log_event_types(app_ctx):
    """Known event types are defined as constants."""
    from db.models.activity import EVENT_DELETE, EVENT_DOWNLOAD, EVENT_EXTRACT, EVENT_SCAN

    assert EVENT_DOWNLOAD == "download"
    assert EVENT_EXTRACT == "extract"
    assert EVENT_DELETE == "delete"
    assert EVENT_SCAN == "scan"


def test_migration_file_exists():
    """Migration file for activity_log table exists."""
    migration_path = os.path.join(
        os.path.dirname(__file__),
        "..",
        "db",
        "migrations",
        "versions",
        "e4f5a6b7c8d9_add_activity_log.py",
    )
    assert os.path.exists(migration_path), "Migration file missing"


def test_log_event_persists_record(app_ctx):
    """log_activity() creates an ActivityLog row in the DB."""
    from db.activity import log_activity
    from db.models.activity import EVENT_DOWNLOAD, ActivityLog
    from extensions import db

    log_activity(
        EVENT_DOWNLOAD,
        file_path="/media/ep1.mkv",
        status="success",
        details={"provider": "jimaku", "score": 90},
    )
    row = db.session.query(ActivityLog).filter_by(event_type=EVENT_DOWNLOAD).first()
    assert row is not None
    assert row.file_path == "/media/ep1.mkv"
    assert row.status == "success"
    assert "jimaku" in (row.details_json or "")


def test_get_activity_returns_paginated(app_ctx):
    """get_activity() returns paginated results newest-first."""
    from db.activity import get_activity, log_activity
    from db.models.activity import EVENT_DELETE, EVENT_EXTRACT

    log_activity(EVENT_EXTRACT, file_path="/media/ep2.mkv", status="success")
    log_activity(EVENT_DELETE, file_path="/media/ep3.mkv", status="success")
    result = get_activity(page=1, per_page=10)
    assert result["total"] >= 2
    assert len(result["data"]) >= 2
    assert result["data"][0]["created_at"] >= result["data"][-1]["created_at"]


def test_get_activity_filters_by_type(app_ctx):
    """get_activity() respects event_type filter."""
    from db.activity import get_activity, log_activity
    from db.models.activity import EVENT_SCAN

    log_activity(EVENT_SCAN, status="success", details={"found": 5})
    result = get_activity(page=1, per_page=10, event_type=EVENT_SCAN)
    assert all(r["event_type"] == EVENT_SCAN for r in result["data"])


def test_activity_endpoint_returns_paginated(client):
    """GET /api/v1/activity returns paginated activity log."""
    from db.activity import log_activity
    from db.models.activity import EVENT_DOWNLOAD

    with client.application.app_context():
        log_activity(EVENT_DOWNLOAD, file_path="/media/test.mkv", status="success")

    resp = client.get("/api/v1/activity?page=1&per_page=10")
    assert resp.status_code == 200
    body = resp.get_json()
    assert "data" in body
    assert "total" in body
    assert isinstance(body["data"], list)


def test_activity_endpoint_filters_by_type(client):
    """GET /api/v1/activity?type=extract filters correctly."""
    from db.activity import log_activity
    from db.models.activity import EVENT_EXTRACT

    with client.application.app_context():
        log_activity(EVENT_EXTRACT, file_path="/media/ep4.mkv", status="success")

    resp = client.get("/api/v1/activity?type=extract&per_page=50")
    assert resp.status_code == 200
    body = resp.get_json()
    for entry in body["data"]:
        assert entry["event_type"] == "extract"


def test_record_subtitle_download_also_logs_activity(app_ctx):
    """record_subtitle_download() also inserts an activity_log download entry."""
    from unittest.mock import patch

    from db.models.activity import EVENT_DOWNLOAD, ActivityLog
    from extensions import db

    # Patch the repository method to avoid needing real provider data fixtures
    with patch("db.providers._get_repo") as mock_get_repo:
        mock_repo = mock_get_repo.return_value
        mock_repo.record_subtitle_download.return_value = None

        import db.providers as prov

        prov.record_subtitle_download(
            provider_name="jimaku",
            subtitle_id="abc123",
            language="de",
            fmt="ass",
            file_path="/media/ep5.mkv",
            score=88,
        )

    row = (
        db.session.query(ActivityLog)
        .filter_by(event_type=EVENT_DOWNLOAD, file_path="/media/ep5.mkv")
        .first()
    )
    assert row is not None
    assert row.status == "success"


def test_extract_event_type_logs_correctly(app_ctx):
    """Extract events are stored with event_type='extract' and a file_path."""
    from db.activity import log_activity
    from db.models.activity import EVENT_EXTRACT, ActivityLog
    from extensions import db

    log_activity(
        EVENT_EXTRACT,
        file_path="/media/Anime/ep6.mkv",
        status="success",
        details={"format": "ass", "wanted_id": 42},
    )
    row = db.session.query(ActivityLog).filter_by(event_type=EVENT_EXTRACT).first()
    assert row is not None
    assert row.file_path == "/media/Anime/ep6.mkv"
    assert row.status == "success"


def test_delete_event_type_logs_correctly(app_ctx):
    """Delete events are stored with event_type='delete' and a file_path."""
    from db.activity import log_activity
    from db.models.activity import EVENT_DELETE, ActivityLog
    from extensions import db

    log_activity(
        EVENT_DELETE,
        file_path="/media/Anime/ep7.de.ass",
        status="success",
        details={"batch_id": "abc123"},
    )
    row = db.session.query(ActivityLog).filter_by(event_type=EVENT_DELETE).first()
    assert row is not None
    assert row.file_path == "/media/Anime/ep7.de.ass"
    assert row.status == "success"


def test_scan_event_logs_without_file_path(app_ctx):
    """Scan events have no file_path (None) and include scan summary details."""
    from db.activity import log_activity
    from db.models.activity import EVENT_SCAN, ActivityLog
    from extensions import db

    log_activity(
        EVENT_SCAN,
        file_path=None,  # scans have no specific file
        status="success",
        details={"found": 3, "processed": 10, "failed": 0},
    )
    row = db.session.query(ActivityLog).filter_by(event_type=EVENT_SCAN).first()
    assert row is not None
    assert row.file_path is None
    assert row.status == "success"
