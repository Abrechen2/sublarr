"""Cooperative cancellation of a running scheduled job (#183, bug 3).

The failure being fixed: `future.result(timeout=...)` bounds the wait, not the
work. A job past its ceiling was recorded as finished while its thread kept
running — sixteen hours, in the report that prompted this — and pausing the job
did not reach it either.

Every test here goes through `_tick_wrapper`, never around it. That is
deliberate: the whole mechanism hangs on the event reaching the *worker*
thread, and `ThreadPoolExecutor.submit` does not carry context across that
boundary. A test that set the ContextVar itself and then called the job
directly would pass against plumbing that never works in production.
"""

import threading
import time

from apscheduler.triggers.interval import IntervalTrigger

from services.scheduler import cancellation
from services.scheduler.ticks import JobSpec, _tick_wrapper


def _spec(job_id: str, func, timeout_s: int) -> JobSpec:
    return JobSpec(
        id=job_id,
        func=func,
        default_trigger=IntervalTrigger(hours=1),
        timeout_s=timeout_s,
    )


class TestTheSignalReachesTheJobThread:
    def test_a_job_polling_the_flag_is_asked_to_stop_on_timeout(self, app_ctx):
        """The point of the whole change: the job learns its time is up."""
        seen = threading.Event()
        released = threading.Event()

        def slow_job():
            for _ in range(200):
                if cancellation.abort_requested():
                    seen.set()
                    return
                time.sleep(0.02)
            released.set()

        _tick_wrapper(app_ctx, _spec("cancel_probe", slow_job, timeout_s=1))()

        assert seen.is_set(), (
            "the worker thread never saw the stop request — the event is not "
            "reaching it, which makes every abort_requested() call in every job "
            "a silent no-op"
        )
        assert not released.is_set(), "the job ran to completion instead of stopping"

    def test_a_job_that_finishes_normally_is_never_asked_to_stop(self, app_ctx):
        asked = []

        def quick_job():
            asked.append(cancellation.abort_requested())

        _tick_wrapper(app_ctx, _spec("cancel_quick", quick_job, timeout_s=30))()

        assert asked == [False]

    def test_abort_requested_is_false_outside_a_scheduled_run(self):
        """The same function must stay callable from a route or a script."""
        assert cancellation.abort_requested() is False

    def test_the_event_is_unregistered_once_the_run_ends(self, app_ctx):
        _tick_wrapper(app_ctx, _spec("cancel_cleanup", lambda: None, timeout_s=30))()

        assert cancellation.request_stop("cancel_cleanup", reason="test") is False, (
            "a finished run must not leave an event behind for the next one to trip over"
        )


class TestTheRunIsReportedHonestly:
    def _last_status(self, job_id: str) -> str:
        from sqlalchemy import select

        from db.models.scheduler import JobRun
        from extensions import db

        rows = (
            db.session.execute(
                select(JobRun).where(JobRun.job_id == job_id).order_by(JobRun.id.desc())
            )
            .scalars()
            .all()
        )
        assert rows, f"no run row recorded for {job_id}"
        return rows[0].status

    def test_a_job_that_stops_when_asked_is_recorded_as_timeout(self, app_ctx):
        def obedient():
            for _ in range(200):
                if cancellation.abort_requested():
                    return
                time.sleep(0.02)

        _tick_wrapper(app_ctx, _spec("cancel_obedient", obedient, timeout_s=1))()

        assert self._last_status("cancel_obedient") == "timeout"

    def test_a_job_that_ignores_the_request_is_not_reported_as_ended(self, app_ctx):
        """The lie this fixes: the run row said the work was over while it ran on.

        An operator reading `timeout` reasonably concludes the library reads
        stopped. They did not, and only a container restart ended them.
        """
        keep_going = threading.Event()

        def stubborn():
            keep_going.wait(timeout=10)

        try:
            _tick_wrapper(app_ctx, _spec("cancel_stubborn", stubborn, timeout_s=1))()

            assert self._last_status("cancel_stubborn") == "timeout_abandoned"
        finally:
            keep_going.set()


class TestPauseReachesARunningJob:
    def test_pausing_asks_the_running_job_to_stop(self, app_ctx):
        """Pause removed future fires only; the in-flight run kept going.

        In the field report a tick was still logging seven minutes after the
        pause was recorded.
        """
        started = threading.Event()
        stopped = threading.Event()

        def slow_job():
            started.set()
            for _ in range(400):
                if cancellation.abort_requested():
                    stopped.set()
                    return
                time.sleep(0.02)

        runner = _tick_wrapper(app_ctx, _spec("cancel_paused", slow_job, timeout_s=60))
        thread = threading.Thread(target=runner, daemon=True)
        thread.start()
        assert started.wait(timeout=5), "job never started"

        assert cancellation.request_stop("cancel_paused", reason="paused by user") is True
        assert stopped.wait(timeout=5), "the paused job never noticed"
        thread.join(timeout=5)

    def test_the_pause_endpoint_goes_through_the_same_signal(self, app_ctx, monkeypatch):
        """Wiring test: the mechanism above is useless if pause_job never calls it.

        Asserting on `request_stop` rather than on a running job keeps this
        test about the wiring; whether the signal reaches a worker is settled
        by the tests above, which go through the real executor.
        """
        from services.scheduler.core import SublarrScheduler

        asked: list[tuple[str, str]] = []
        monkeypatch.setattr(
            cancellation,
            "request_stop",
            lambda job_id, *, reason: asked.append((job_id, reason)) or True,
        )

        scheduler = SublarrScheduler.__new__(SublarrScheduler)
        monkeypatch.setattr(scheduler, "_require_registered", lambda job_id: None, raising=False)
        monkeypatch.setattr(
            scheduler,
            "_ensure_scheduler",
            lambda: type("_S", (), {"pause_job": staticmethod(lambda job_id: None)})(),
            raising=False,
        )

        scheduler.pause_job("wanted_search")

        assert asked == [("wanted_search", "paused by user")]
