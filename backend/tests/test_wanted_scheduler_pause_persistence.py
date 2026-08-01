"""A paused wanted job must stay paused across a restart.

Regression cover for a bug found on the RC instance on 2026-08-01: pausing
``wanted_search`` in Settings → System → Scheduler held until the container
restarted, then the job silently came back and started firing again — on an
instance holding real DeepL credentials, that meant billed work nobody asked
for.

Two independent paths revived it, and both are covered here:

1. ``_apply_intervals_to_apscheduler`` resumed every job with a non-zero
   interval. It runs on settings-save *and* on startup, so a restart always
   resumed the job.
2. The ``wanted_search_on_startup`` one-shot spawned its run thread without
   consulting the pause state at all.
"""

import os
import sys
from unittest.mock import MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.wanted_scanner_scheduler import (  # noqa: E402
    _apply_intervals_to_apscheduler,
    _job_is_paused,
)


def _app_with_job(next_run_time):
    """Flask-ish stub whose scheduler holds one job with the given next_run_time."""
    aps_job = MagicMock()
    aps_job.next_run_time = next_run_time

    scheduler = MagicMock()
    scheduler._scheduler.get_job.return_value = aps_job

    app = MagicMock()
    app.extensions = {"scheduler": scheduler}
    return app, scheduler


class TestJobIsPaused:
    def test_no_next_run_time_means_paused(self):
        app, _ = _app_with_job(None)
        assert _job_is_paused(app, "wanted_search") is True

    def test_scheduled_job_is_not_paused(self):
        app, _ = _app_with_job("2026-08-02T00:00:00+00:00")
        assert _job_is_paused(app, "wanted_search") is False

    def test_missing_job_is_not_reported_as_paused(self):
        """A job that doesn't exist yet must not block a legitimate startup run."""
        app, scheduler = _app_with_job(None)
        scheduler._scheduler.get_job.return_value = None
        assert _job_is_paused(app, "wanted_search") is False

    def test_no_scheduler_attached_is_not_paused(self):
        app = MagicMock()
        app.extensions = {}
        assert _job_is_paused(app, "wanted_search") is False

    def test_app_none_is_not_paused(self):
        assert _job_is_paused(None, "wanted_search") is False


class TestIntervalApplication:
    def test_startup_does_not_resume_a_paused_job(self):
        """The whole point: a restart must not revive what the user paused."""
        app, scheduler = _app_with_job(None)
        _apply_intervals_to_apscheduler(app, 6, 24, on_startup=True)
        scheduler.resume_job.assert_not_called()

    def test_settings_save_still_resumes(self):
        """Changing the interval in Settings is an explicit "run it" instruction."""
        app, scheduler = _app_with_job(None)
        _apply_intervals_to_apscheduler(app, 6, 24, on_startup=False)
        resumed = {c.args[0] for c in scheduler.resume_job.call_args_list}
        assert resumed == {"wanted_scanner", "wanted_search"}

    def test_trigger_is_still_applied_on_startup(self):
        """Skipping the resume must not skip picking up an interval change."""
        app, scheduler = _app_with_job(None)
        _apply_intervals_to_apscheduler(app, 6, 24, on_startup=True)
        modified = {c.args[0] for c in scheduler.modify_trigger.call_args_list}
        assert modified == {"wanted_scanner", "wanted_search"}

    def test_zero_interval_still_pauses_on_startup(self):
        app, scheduler = _app_with_job("2026-08-02T00:00:00+00:00")
        _apply_intervals_to_apscheduler(app, 0, 0, on_startup=True)
        paused = {c.args[0] for c in scheduler.pause_job.call_args_list}
        assert paused == {"wanted_scanner", "wanted_search"}
