"""SublarrScheduler facade lifecycle tests."""

import time

import pytest
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
def scheduler(app, tmp_path):
    url = f"sqlite:///{tmp_path / 'aps.db'}"
    s = SublarrScheduler(db_url=url, autostart=False)
    s.attach_app(app)
    yield s
    if s.running:
        s.shutdown(timeout_s=2)


def test_not_running_before_start(scheduler):
    assert scheduler.running is False


def test_start_makes_running(scheduler):
    scheduler.start()
    assert scheduler.running is True


def test_start_is_idempotent(scheduler):
    """Regression for feedback_scheduler_timer_leak — start() on a running
    scheduler must be a no-op, not a restart."""
    scheduler.start()
    first_instance = id(scheduler._scheduler)
    scheduler.start()
    scheduler.start()
    assert scheduler.running is True
    assert id(scheduler._scheduler) == first_instance


def test_shutdown_stops_running(scheduler):
    scheduler.start()
    scheduler.shutdown(timeout_s=5)
    assert scheduler.running is False


def test_shutdown_is_idempotent(scheduler):
    scheduler.start()
    scheduler.shutdown(timeout_s=5)
    scheduler.shutdown(timeout_s=5)  # no raise


def test_shutdown_bounded_by_timeout(scheduler):
    scheduler.start()
    t0 = time.monotonic()
    scheduler.shutdown(timeout_s=1)
    assert time.monotonic() - t0 < 3.0


def test_duplicate_job_id_raises(app, tmp_path):
    url = f"sqlite:///{tmp_path / 'aps.db'}"
    s = SublarrScheduler(db_url=url, autostart=False)
    s.attach_app(app)
    spec1 = JobSpec(id="dup", func=lambda: None, default_trigger=IntervalTrigger(seconds=60))
    spec2 = JobSpec(id="dup", func=lambda: None, default_trigger=IntervalTrigger(seconds=30))
    s.register_job(spec1)
    with pytest.raises(ValueError, match="already registered"):
        s.register_job(spec2)
    if s.running:
        s.shutdown(timeout_s=2)
