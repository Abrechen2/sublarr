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


def test_register_adds_to_jobstore_on_first_run(scheduler):
    spec = JobSpec(
        id="first",
        func=lambda: None,
        default_trigger=IntervalTrigger(minutes=15),
    )
    scheduler.register_job(spec)
    scheduler.start_registered_jobs()
    scheduler.start()

    job = scheduler._scheduler.get_job("first")
    assert job is not None
    assert job.trigger.interval.total_seconds() == 900


def test_register_preserves_user_override(scheduler):
    spec = JobSpec(
        id="user_edited",
        func=lambda: None,
        default_trigger=IntervalTrigger(minutes=15),
    )
    scheduler.register_job(spec)
    scheduler.start_registered_jobs()
    scheduler.start()

    scheduler._scheduler.reschedule_job(
        "user_edited",
        trigger=IntervalTrigger(minutes=5),
    )
    scheduler.shutdown(timeout_s=2)

    # Second startup: ensure user's 5-minute interval is preserved
    scheduler._scheduler = None
    scheduler._shutting_down = False
    scheduler._registered_ids.clear()
    scheduler._specs.clear()
    scheduler.register_job(spec)
    scheduler.start_registered_jobs()
    scheduler.start()
    job = scheduler._scheduler.get_job("user_edited")
    assert job.trigger.interval.total_seconds() == 300


def test_purge_orphans_deletes_missing_ids(scheduler):
    old = JobSpec(
        id="old_one",
        func=lambda: None,
        default_trigger=IntervalTrigger(minutes=5),
    )
    scheduler.register_job(old)
    scheduler.start_registered_jobs()
    scheduler.start()
    scheduler.shutdown(timeout_s=2)

    # Second boot: "old_one" is no longer in the registry
    scheduler._scheduler = None
    scheduler._shutting_down = False
    scheduler._registered_ids.clear()
    scheduler._specs.clear()

    new = JobSpec(
        id="new_one",
        func=lambda: None,
        default_trigger=IntervalTrigger(minutes=5),
    )
    scheduler.register_job(new)
    scheduler.start_registered_jobs()
    scheduler.purge_orphans()
    scheduler.start()

    assert scheduler._scheduler.get_job("old_one") is None
    assert scheduler._scheduler.get_job("new_one") is not None


def test_purge_orphans_preserves_registered(scheduler):
    spec = JobSpec(
        id="keep",
        func=lambda: None,
        default_trigger=IntervalTrigger(minutes=5),
    )
    scheduler.register_job(spec)
    scheduler.start_registered_jobs()
    scheduler.purge_orphans()
    scheduler.start()
    assert scheduler._scheduler.get_job("keep") is not None


def test_run_now_queues_oneshot(scheduler):
    spec = JobSpec(
        id="rn_job",
        func=lambda: None,
        default_trigger=IntervalTrigger(minutes=15),
    )
    scheduler.register_job(spec)
    scheduler.start_registered_jobs()
    scheduler.start()

    oneshot_id = scheduler.run_now("rn_job")
    assert oneshot_id.startswith("rn_job_oneshot_")
    # Oneshot may fire/remove very quickly; at least confirm it was accepted.
    # (We confirm by the non-raising call + id prefix.)


def test_run_now_duplicate_raises_conflict(scheduler):
    from services.scheduler import OneshotAlreadyPendingError

    spec = JobSpec(
        id="rn_dup",
        func=lambda: __import__("time").sleep(0.5),
        default_trigger=IntervalTrigger(minutes=15),
    )
    scheduler.register_job(spec)
    scheduler.start_registered_jobs()
    scheduler.start()

    # First oneshot: accepted
    scheduler.run_now("rn_dup")
    # Second immediately after: should see the first still pending/running
    with pytest.raises(OneshotAlreadyPendingError):
        scheduler.run_now("rn_dup")


def test_run_now_unknown_id_raises(scheduler):
    from services.scheduler import JobNotRegisteredError

    scheduler.start()
    with pytest.raises(JobNotRegisteredError):
        scheduler.run_now("nope")
