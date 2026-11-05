"""The run-history row is written after the job lock is released.

A history write that stalls on the database used to hold the per-job lock,
so every later fire of that job was skipped as an overlap — the shape of
#248's held scan lock.
"""

import contextlib
from unittest.mock import MagicMock, patch

from apscheduler.triggers.interval import IntervalTrigger


def test_job_lock_is_free_while_the_history_row_is_written():
    from services.scheduler import ticks

    spec = ticks.JobSpec(
        id="history_after_lock_probe",
        func=lambda: None,
        default_trigger=IntervalTrigger(seconds=60),
        timeout_s=5,
        owner_module="tests",
        description="probe",
    )
    app = MagicMock()
    app.app_context.side_effect = lambda: contextlib.nullcontext()
    seen = {}

    def write(**kw):
        lock = ticks._get_job_run_lock(spec.id)
        seen["free"] = lock.acquire(blocking=False)
        if seen["free"]:
            lock.release()
        seen["status"] = kw["status"]

    with patch.object(ticks, "_write_job_run", side_effect=write):
        ticks._tick_wrapper(app, spec)()

    assert seen == {"free": True, "status": "ok"}
