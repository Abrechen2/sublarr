"""Retention cleanup — delete_old_job_runs."""

from datetime import UTC, datetime, timedelta

import pytest


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("SUBLARR_DB_PATH", str(tmp_path / "app.db"))
    from config import reload_settings

    reload_settings()
    from app import create_app

    app = create_app(testing=True)
    from extensions import db as sa_db

    with app.app_context():
        sa_db.create_all()
    yield app


@pytest.fixture
def db_session(app):
    from extensions import db

    with app.app_context():
        yield db.session
        db.session.rollback()


def test_deletes_rows_older_than_retention(app, db_session):
    from db.models.scheduler import JobRun
    from utils.scheduler_retention import delete_old_job_runs

    old = JobRun(
        job_id="x",
        started_at=datetime.now(UTC) - timedelta(days=60),
        finished_at=datetime.now(UTC) - timedelta(days=60),
        status="ok",
    )
    fresh = JobRun(
        job_id="x",
        started_at=datetime.now(UTC),
        finished_at=datetime.now(UTC),
        status="ok",
    )
    db_session.add_all([old, fresh])
    db_session.commit()

    with app.app_context():
        deleted = delete_old_job_runs(retention_days=30)
    assert deleted == 1

    db_session.expire_all()
    remaining = db_session.query(JobRun).filter_by(job_id="x").all()
    assert len(remaining) == 1


def test_idempotent_on_empty(app):
    from utils.scheduler_retention import delete_old_job_runs

    with app.app_context():
        assert delete_old_job_runs(retention_days=30) == 0
        assert delete_old_job_runs(retention_days=30) == 0


def test_reads_retention_from_settings_when_none(app, monkeypatch):
    from config import get_settings
    from utils.scheduler_retention import delete_old_job_runs

    s = get_settings()
    monkeypatch.setattr(s, "scheduler_history_retention_days", 7)

    with app.app_context():
        delete_old_job_runs()  # reads from settings when arg omitted
