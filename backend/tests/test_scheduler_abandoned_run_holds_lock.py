"""An abandoned tick must not let the next one start beside it.

Prod, 2026-09-17. ``subtitle_automation`` fires every 10 minutes with a 2400 s
timeout and a 900 s grace, so a run that overruns is declared abandoned 55
minutes in — while its worker keeps going. The per-job overlap lock was
released in the wrapper's ``finally``, which runs at that moment, so the next
fire acquired it and started a second worker on the same queue:

    7a2ec127  20:28:10 → 23:26:24  (2 h 58 m, drained its full 50-item cap)
    253d42bc  21:28:10 → 23:19:28  (1 h 51 m)
    3ff10dbc  active in the same window

Three workers competing for one Ollama, each making the others slower, each
then abandoned in turn — and the history recorded 3300 s for all of them,
because that is just ``timeout + grace``. The lock has to follow the worker,
not the wait.
"""

import threading
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


@pytest.fixture(autouse=True)
def _fresh_job_locks():
    """Each test gets its own lock table — they are process-global."""
    from services.scheduler import ticks

    saved = dict(ticks._job_run_locks)
    ticks._job_run_locks.clear()
    yield
    ticks._job_run_locks.clear()
    ticks._job_run_locks.update(saved)


def _spec(**kw) -> JobSpec:
    return JobSpec(
        id=kw.pop("id", "overlap_probe"),
        func=kw.pop("func", lambda: None),
        default_trigger=IntervalTrigger(hours=1),
        **kw,
    )


def test_second_tick_is_skipped_while_the_abandoned_worker_runs(flask_app, db_session):
    from db.models.scheduler import JobRun

    release = threading.Event()
    entered = threading.Event()

    def _runaway():
        entered.set()
        # Ignores the stop request, exactly as the real quality loop did.
        release.wait(timeout=30)

    spec = _spec(id="overlap_runaway", func=_runaway, timeout_s=1, cancel_grace_s=1)

    try:
        _tick_wrapper(flask_app, spec, triggered_by="schedule")()
        assert entered.wait(timeout=5), "the worker never started"

        # The wrapper has given up; the worker is still in _runaway.
        _tick_wrapper(flask_app, spec, triggered_by="schedule")()

        rows = (
            db_session.query(JobRun).filter_by(job_id="overlap_runaway").order_by(JobRun.id).all()
        )
        assert [r.status for r in rows] == ["timeout_abandoned", "skipped_overlap"], (
            "the second fire started a worker beside the runaway one"
        )
    finally:
        release.set()


def test_the_lock_comes_back_once_the_worker_finishes(flask_app, db_session):
    """Holding the lock must not strand the job forever."""
    from db.models.scheduler import JobRun

    release = threading.Event()
    entered = threading.Event()

    def _runaway():
        entered.set()
        release.wait(timeout=30)

    spec = _spec(id="overlap_recovers", func=_runaway, timeout_s=1, cancel_grace_s=1)

    _tick_wrapper(flask_app, spec, triggered_by="schedule")()
    assert entered.wait(timeout=5)
    release.set()

    # Give the worker a moment to leave and hand the lock back.
    deadline = time.monotonic() + 10
    from services.scheduler.ticks import _get_job_run_lock

    lock = _get_job_run_lock("overlap_recovers")
    while time.monotonic() < deadline:
        if lock.acquire(blocking=False):
            lock.release()
            break
        time.sleep(0.05)
    else:
        pytest.fail("the lock was never released after the worker finished")

    ran = _spec(id="overlap_recovers", func=lambda: None, timeout_s=5)
    _tick_wrapper(flask_app, ran, triggered_by="schedule")()

    rows = db_session.query(JobRun).filter_by(job_id="overlap_recovers").order_by(JobRun.id).all()
    assert rows[-1].status == "ok", f"the follow-up tick did not run: {rows[-1].status!r}"


def test_a_normal_run_still_releases_immediately(flask_app, db_session):
    """The common path must be untouched — no lock held past the return."""
    from db.models.scheduler import JobRun

    spec = _spec(id="overlap_normal", func=lambda: None, timeout_s=5)

    _tick_wrapper(flask_app, spec, triggered_by="schedule")()
    _tick_wrapper(flask_app, spec, triggered_by="schedule")()

    rows = db_session.query(JobRun).filter_by(job_id="overlap_normal").order_by(JobRun.id).all()
    assert [r.status for r in rows] == ["ok", "ok"]
