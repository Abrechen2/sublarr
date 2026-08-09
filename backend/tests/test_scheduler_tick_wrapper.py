"""Tests for _tick_wrapper — timeout, error capture, app_context, history write."""

import logging
import time

import pytest
from apscheduler.triggers.interval import IntervalTrigger

from services.scheduler import JobSpec, _tick_wrapper


@pytest.fixture
def flask_app(tmp_path, monkeypatch):
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
def db_session(flask_app):
    from extensions import db

    with flask_app.app_context():
        yield db.session
        db.session.rollback()


def _make_spec(fn, timeout_s=5):
    return JobSpec(
        id="test_job",
        func=fn,
        default_trigger=IntervalTrigger(seconds=60),
        timeout_s=timeout_s,
    )


def test_happy_path_writes_ok_row(flask_app, db_session):
    from db.models.scheduler import JobRun

    ran = []
    spec = _make_spec(lambda: ran.append(1))
    _tick_wrapper(flask_app, spec, triggered_by="schedule")()

    assert ran == [1]
    rows = db_session.query(JobRun).filter_by(job_id="test_job").all()
    assert len(rows) == 1
    assert rows[0].status == "ok"
    assert rows[0].triggered_by == "schedule"
    assert rows[0].finished_at is not None
    assert rows[0].duration_ms is not None
    assert rows[0].duration_ms >= 0
    assert rows[0].error_type is None


def test_exception_writes_error_row(flask_app, db_session, caplog):
    from db.models.scheduler import JobRun

    def boom():
        raise ValueError("deliberate")

    spec = _make_spec(boom)
    with caplog.at_level(logging.ERROR, logger="services.scheduler"):
        _tick_wrapper(flask_app, spec, triggered_by="schedule")()

    rows = db_session.query(JobRun).filter_by(job_id="test_job").all()
    assert len(rows) == 1
    assert rows[0].status == "error"
    assert rows[0].error_type == "ValueError"
    assert "deliberate" in (rows[0].error_msg or "")


def test_timeout_of_an_uninterruptible_job_is_recorded_as_abandoned(flask_app, db_session):
    """A `time.sleep` cannot be asked to stop, and the row now says so.

    This test asserted `status == "timeout"` until cooperative cancellation
    landed. That reading was the problem it was documenting: the scheduler
    cannot end a running thread, so "timeout" told operators the work had
    stopped when it had not — one user's sweep kept reading their library for
    sixteen hours after such a row was written.

    A job that polls `abort_requested()` and returns during the grace period
    still gets `timeout`; see test_scheduler_cancellation.py for both branches.
    """
    from db.models.scheduler import JobRun

    def slow():
        time.sleep(3)

    spec = _make_spec(slow, timeout_s=1)
    _tick_wrapper(flask_app, spec, triggered_by="schedule")()

    rows = db_session.query(JobRun).filter_by(job_id="test_job").all()
    assert len(rows) == 1
    assert rows[0].status == "timeout_abandoned"
    assert rows[0].error_type == "TimeoutError"


def test_app_context_entered_before_fn(flask_app, db_session):
    """Regression for feedback_flask_app_context_in_threads."""
    from flask import has_app_context

    observed = []

    def check_ctx():
        observed.append(has_app_context())

    spec = _make_spec(check_ctx)
    _tick_wrapper(flask_app, spec, triggered_by="schedule")()

    assert observed == [True]


def test_triggered_by_manual(flask_app, db_session):
    from db.models.scheduler import JobRun

    spec = _make_spec(lambda: None)
    _tick_wrapper(flask_app, spec, triggered_by="manual")()

    rows = db_session.query(JobRun).filter_by(job_id="test_job").all()
    assert rows[0].triggered_by == "manual"


def test_error_msg_truncated_to_4kb(flask_app, db_session):
    from db.models.scheduler import JobRun

    def boom():
        raise RuntimeError("x" * 10000)

    spec = _make_spec(boom)
    _tick_wrapper(flask_app, spec, triggered_by="schedule")()

    rows = db_session.query(JobRun).filter_by(job_id="test_job").all()
    assert len(rows[0].error_msg) <= 4096


def test_prometheus_counter_incremented_on_ok(flask_app, db_session):
    from monitoring.metrics import scheduler_job_runs_total

    before = scheduler_job_runs_total.labels(job_id="test_job", status="ok")._value.get()
    spec = _make_spec(lambda: None)
    _tick_wrapper(flask_app, spec, triggered_by="schedule")()
    after = scheduler_job_runs_total.labels(job_id="test_job", status="ok")._value.get()
    assert after == before + 1


def test_prometheus_counter_incremented_on_error(flask_app, db_session):
    from monitoring.metrics import scheduler_job_runs_total

    def boom():
        raise RuntimeError("x")

    before = scheduler_job_runs_total.labels(job_id="test_job", status="error")._value.get()
    spec = _make_spec(boom)
    _tick_wrapper(flask_app, spec, triggered_by="schedule")()
    after = scheduler_job_runs_total.labels(job_id="test_job", status="error")._value.get()
    assert after == before + 1


def test_prometheus_histogram_observed(flask_app, db_session):
    from monitoring.metrics import scheduler_job_duration_seconds

    h = scheduler_job_duration_seconds.labels(job_id="test_job")
    before_count = h._sum.get()
    spec = _make_spec(lambda: None)
    _tick_wrapper(flask_app, spec, triggered_by="schedule")()
    after_count = h._sum.get()
    assert after_count > before_count


def test_overlapping_tick_writes_skipped_row(flask_app, db_session):
    """When the per-job lock is already held, a colliding tick must persist a
    skipped_overlap row so manual run-now collisions stay visible in history.

    Regression for the silent-skip path: APScheduler's MaxInstancesReachedError
    only covers scheduled-vs-scheduled overlap; a manual oneshot has a distinct
    APScheduler job id, so only the per-job lock catches that case.
    """
    from db.models.scheduler import JobRun
    from services.scheduler import _get_job_run_lock

    spec = _make_spec(lambda: None)
    held = _get_job_run_lock(spec.id)
    assert held.acquire(blocking=False), "test setup: lock must be free"
    try:
        _tick_wrapper(flask_app, spec, triggered_by="manual")()
    finally:
        held.release()

    rows = db_session.query(JobRun).filter_by(job_id="test_job").all()
    assert len(rows) == 1
    assert rows[0].status == "skipped_overlap"
    assert rows[0].triggered_by == "manual"
    assert rows[0].finished_at is not None
