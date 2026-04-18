"""Stale-run reconciliation — abandoned rows after SIGKILL / shutdown timeout."""

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


def test_abandoned_row_marked_interrupted(app, db_session):
    from db.models.scheduler import JobRun
    from services.scheduler import reconcile_stale_runs

    old = JobRun(
        job_id="x",
        started_at=datetime.now(UTC) - timedelta(hours=1),
        finished_at=None,
        status="ok",
    )
    db_session.add(old)
    db_session.commit()

    with app.app_context():
        reconcile_stale_runs(grace_minutes=10)

    db_session.expire_all()
    row = db_session.query(JobRun).filter_by(job_id="x").first()
    assert row.status == "error"
    assert row.error_type == "InterruptedByShutdown"
    assert row.finished_at is not None


def test_in_flight_row_not_touched(app, db_session):
    from db.models.scheduler import JobRun
    from services.scheduler import reconcile_stale_runs

    fresh = JobRun(
        job_id="y",
        started_at=datetime.now(UTC) - timedelta(seconds=30),
        finished_at=None,
        status="ok",
    )
    db_session.add(fresh)
    db_session.commit()

    with app.app_context():
        reconcile_stale_runs(grace_minutes=10)

    db_session.expire_all()
    row = db_session.query(JobRun).filter_by(job_id="y").first()
    assert row.status == "ok"
    assert row.finished_at is None


def test_finished_row_not_touched(app, db_session):
    from db.models.scheduler import JobRun
    from services.scheduler import reconcile_stale_runs

    done = JobRun(
        job_id="z",
        started_at=datetime.now(UTC) - timedelta(hours=2),
        finished_at=datetime.now(UTC) - timedelta(hours=2),
        status="ok",
    )
    db_session.add(done)
    db_session.commit()

    with app.app_context():
        reconcile_stale_runs(grace_minutes=10)

    db_session.expire_all()
    row = db_session.query(JobRun).filter_by(job_id="z").first()
    assert row.status == "ok"
