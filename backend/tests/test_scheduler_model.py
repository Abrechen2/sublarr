"""Unit tests for JobRun ORM model."""

import os
from datetime import UTC, datetime

import pytest

from app import create_app
from db.models.scheduler import JobRun
from extensions import db as sa_db


@pytest.fixture()
def app(tmp_path):
    """Create a Flask app with an isolated SQLite DB for testing."""
    db_path = str(tmp_path / "test.db")
    os.environ["SUBLARR_DB_PATH"] = db_path
    os.environ["SUBLARR_API_KEY"] = ""
    os.environ["SUBLARR_LOG_LEVEL"] = "ERROR"

    from config import reload_settings

    reload_settings()

    application = create_app(testing=True)
    application.config["TESTING"] = True

    with application.app_context():
        sa_db.create_all()
        yield application

    os.environ.pop("SUBLARR_DB_PATH", None)
    os.environ.pop("SUBLARR_API_KEY", None)
    os.environ.pop("SUBLARR_LOG_LEVEL", None)


def test_jobrun_tablename_and_columns():
    assert JobRun.__tablename__ == "scheduler_job_runs"
    cols = {c.name for c in JobRun.__table__.columns}
    assert cols == {
        "id",
        "job_id",
        "started_at",
        "finished_at",
        "duration_ms",
        "status",
        "triggered_by",
        "error_type",
        "error_msg",
    }


def test_jobrun_indexes():
    index_names = {ix.name for ix in JobRun.__table__.indexes}
    assert "ix_scheduler_job_runs_job_id_started_at" in index_names
    assert "ix_scheduler_job_runs_started_at" in index_names
    assert "ix_scheduler_job_runs_status" in index_names


def test_jobrun_default_triggered_by(app):
    with app.app_context():
        from extensions import db

        row = JobRun(
            job_id="x",
            started_at=datetime.now(UTC),
            status="ok",
        )
        db.session.add(row)
        db.session.flush()
        assert row.triggered_by == "schedule"
        db.session.rollback()


def test_jobrun_status_accepts_valid_values(app):
    with app.app_context():
        from extensions import db

        for status in ("ok", "error", "timeout", "missed", "skipped_overlap"):
            row = JobRun(
                job_id="x",
                started_at=datetime.now(UTC),
                status=status,
            )
            db.session.add(row)
        db.session.flush()
        db.session.rollback()
