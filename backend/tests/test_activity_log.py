import pytest
from datetime import datetime, timezone
import os


def test_activity_log_model_has_expected_columns(app_ctx):
    """ActivityLog model has the correct columns and tablename."""
    from db.models.activity import ActivityLog
    assert ActivityLog.__tablename__ == "activity_log"
    mapper = ActivityLog.__mapper__
    col_names = {c.key for c in mapper.column_attrs}
    assert col_names == {"id", "event_type", "file_path", "status", "details_json", "created_at"}


def test_activity_log_event_types(app_ctx):
    """Known event types are defined as constants."""
    from db.models.activity import EVENT_DOWNLOAD, EVENT_EXTRACT, EVENT_DELETE, EVENT_SCAN
    assert EVENT_DOWNLOAD == "download"
    assert EVENT_EXTRACT == "extract"
    assert EVENT_DELETE == "delete"
    assert EVENT_SCAN == "scan"


def test_migration_file_exists():
    """Migration file for activity_log table exists."""
    migration_path = os.path.join(
        os.path.dirname(__file__), "..", "db", "migrations", "versions",
        "e4f5a6b7c8d9_add_activity_log.py"
    )
    assert os.path.exists(migration_path), "Migration file missing"
