"""Event listener tests — EVENT_JOB_MISSED / EVENT_JOB_ERROR synthetic rows."""

import time
from datetime import UTC, datetime

import pytest
from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_MISSED, JobExecutionEvent
from apscheduler.triggers.interval import IntervalTrigger

from services.scheduler import JobSpec, SublarrScheduler


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


@pytest.fixture
def scheduler(app, tmp_path):
    url = f"sqlite:///{tmp_path / 'aps.db'}"
    s = SublarrScheduler(db_url=url, autostart=False)
    s.attach_app(app)
    yield s
    if s.running:
        s.shutdown(timeout_s=2)


def test_missed_event_writes_missed_row(scheduler, db_session):
    from db.models.scheduler import JobRun

    spec = JobSpec(
        id="j_missed",
        func=lambda: None,
        default_trigger=IntervalTrigger(seconds=60),
    )
    scheduler.register_job(spec)
    scheduler.start_registered_jobs()
    scheduler.attach_listeners()
    scheduler.start()

    event = JobExecutionEvent(
        code=EVENT_JOB_MISSED,
        job_id="j_missed",
        jobstore="default",
        scheduled_run_time=datetime.now(UTC),
    )
    scheduler._scheduler._dispatch_event(event)
    time.sleep(0.1)

    rows = db_session.query(JobRun).filter_by(job_id="j_missed").all()
    assert len(rows) == 1
    assert rows[0].status == "missed"
    assert rows[0].finished_at is None


def test_max_instances_overlap_writes_skipped_row(scheduler, db_session):
    from apscheduler.executors.base import MaxInstancesReachedError

    from db.models.scheduler import JobRun

    spec = JobSpec(
        id="j_overlap",
        func=lambda: None,
        default_trigger=IntervalTrigger(seconds=60),
    )
    scheduler.register_job(spec)
    scheduler.start_registered_jobs()
    scheduler.attach_listeners()
    scheduler.start()

    class _FakeJob:
        id = "j_overlap"
        max_instances = 1

    exc = MaxInstancesReachedError(_FakeJob())
    event = JobExecutionEvent(
        code=EVENT_JOB_ERROR,
        job_id="j_overlap",
        jobstore="default",
        scheduled_run_time=datetime.now(UTC),
        exception=exc,
    )
    scheduler._scheduler._dispatch_event(event)
    time.sleep(0.1)

    rows = db_session.query(JobRun).filter_by(job_id="j_overlap").all()
    assert len(rows) == 1
    assert rows[0].status == "skipped_overlap"


def test_listener_error_does_not_crash_scheduler(scheduler, caplog):
    import logging
    from unittest.mock import patch

    spec = JobSpec(
        id="j_err",
        func=lambda: None,
        default_trigger=IntervalTrigger(seconds=60),
    )
    scheduler.register_job(spec)
    scheduler.start_registered_jobs()
    scheduler.attach_listeners()
    scheduler.start()

    event = JobExecutionEvent(
        code=EVENT_JOB_MISSED,
        job_id="j_err",
        jobstore="default",
        scheduled_run_time=datetime.now(UTC),
    )
    with (
        # Patch the module-global the listener closure actually references —
        # services.scheduler.core imports _write_job_run at module top, so
        # patching the package re-export (services.scheduler._write_job_run)
        # would leave the listener on the real function.
        patch(
            "services.scheduler.core._write_job_run",
            side_effect=RuntimeError("db down"),
        ),
        caplog.at_level(logging.ERROR, logger="services.scheduler"),
    ):
        scheduler._scheduler._dispatch_event(event)
    assert scheduler.running is True
    assert any("listener failed" in r.message for r in caplog.records)
