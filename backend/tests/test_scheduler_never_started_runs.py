"""A tick that never started must not be recorded as abandoned.

`timeout_abandoned` means "asked to stop and kept working" — an operator reads
it as runaway work and goes looking for it. But the timeout bounds the wait on
the future, not the work, and the tick executor has 16 workers shared by 17
jobs: a submitted tick can still be *queued* when its timeout expires. Setting
the cancel event then reaches nobody, the grace expires too, and a job that
never ran a single line is filed as one that refused to stop.

Prod 2026-08-21 12:07:52 shows the shape: a `wanted_search` run recorded
`timeout_abandoned` at 2700s with not one line of its own in the log for the
whole window.
"""

import threading
import time
from unittest.mock import MagicMock, patch

from apscheduler.triggers.interval import IntervalTrigger


class TestQueuedTickIsNotAbandoned:
    def test_a_tick_still_queued_at_timeout_is_not_called_abandoned(self):
        """The executor is saturated, so the tick never starts. That is an
        executor problem, not a runaway job, and must not read as one."""
        from services.scheduler import ticks

        started = threading.Event()

        def _never_runs():
            started.set()

        # A pool with no free worker: the blocker holds the only slot.
        blocker_release = threading.Event()
        pool = ticks.ThreadPoolExecutor(max_workers=1)
        pool.submit(blocker_release.wait)
        try:
            with patch.object(ticks, "_get_tick_executor", return_value=pool):
                status = _run_and_capture_status(_never_runs, timeout_s=1, cancel_grace_s=1)
            assert not started.is_set(), "the probe should never have started"
            assert status != "timeout_abandoned", (
                "a tick that never started must not be filed as one that refused to stop"
            )
            assert status == "timeout_not_started", status
        finally:
            blocker_release.set()
            pool.shutdown(wait=False)


class TestRunningTickStillReportsAbandoned:
    def test_a_tick_that_ran_and_ignored_the_stop_is_still_abandoned(self):
        """The existing verdict must survive: this is the case it exists for."""
        started = threading.Event()

        def _ignores_the_stop():
            started.set()
            time.sleep(3)

        status = _run_and_capture_status(_ignores_the_stop, timeout_s=1, cancel_grace_s=1)
        assert started.is_set()
        assert status == "timeout_abandoned", status

    def test_a_cooperative_tick_is_still_plain_timeout(self):
        from services.scheduler import cancellation

        def _stops_when_asked():
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                if cancellation.abort_requested():
                    return
                time.sleep(0.05)

        status = _run_and_capture_status(_stops_when_asked, timeout_s=1, cancel_grace_s=5)
        assert status == "timeout", status


class TestEveryStatusFitsItsColumn:
    def test_timeout_not_started_fits(self):
        from db.models.scheduler import JobRun

        width = JobRun.__table__.c.status.type.length
        assert len("timeout_not_started") <= width, (
            f"status column is VARCHAR({width}); this is the mismatch that made "
            "timeout_abandoned unwritable on Postgres"
        )


def _run_and_capture_status(func, *, timeout_s, cancel_grace_s) -> str:
    """Drive one real tick through _tick_wrapper and read back its status."""
    import contextlib

    from services.scheduler import ticks

    spec = ticks.JobSpec(
        id="probe",
        func=func,
        default_trigger=IntervalTrigger(seconds=60),
        timeout_s=timeout_s,
        cancel_grace_s=cancel_grace_s,
        owner_module="tests",
        description="probe",
    )
    captured: dict = {}

    app = MagicMock()
    app.app_context.side_effect = lambda: contextlib.nullcontext()

    with patch.object(ticks, "_write_job_run", side_effect=lambda **kw: captured.update(kw)):
        ticks._tick_wrapper(app, spec)()
    return captured.get("status")
