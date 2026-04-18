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


def test_timeout_writes_timeout_row(flask_app, db_session):
    from db.models.scheduler import JobRun

    def slow():
        time.sleep(3)

    spec = _make_spec(slow, timeout_s=1)
    _tick_wrapper(flask_app, spec, triggered_by="schedule")()

    rows = db_session.query(JobRun).filter_by(job_id="test_job").all()
    assert len(rows) == 1
    assert rows[0].status == "timeout"
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
