"""A restart must not reset the wanted jobs' interval anchor.

Prod finding 2026-08-01: `wanted_search` is configured at 4h but fired at
01:52 → 08:23 → 12:23, with the next run at 20:07 — gaps of 6.5h and 7.7h,
each exactly 4h after a container start. Every redeploy silently stretched
the search cadence.

Cause: `_apply_intervals_to_apscheduler` runs on startup as well as on
settings-save, and on startup it called `modify_trigger` unconditionally.
The trigger handed over is a freshly constructed `IntervalTrigger`, and
APScheduler defaults such a trigger's `start_date` to *now + interval* — so
rescheduling re-anchors the job to boot time. Jobs outside this adapter kept
their original anchor (`subtitle_automation` still carried its April one),
which is what made the difference visible.

The interval can only actually change on the settings-save path, so on
startup an already-correct trigger must be left alone.
"""

import os
import sys
from datetime import timedelta
from unittest.mock import MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.wanted_scanner_scheduler import (  # noqa: E402
    _apply_intervals_to_apscheduler,
)


def _app_with_interval(hours, next_run_time="2026-08-02T00:00:00+00:00"):
    """Flask-ish stub whose jobs carry a real IntervalTrigger-like interval."""
    aps_job = MagicMock()
    aps_job.next_run_time = next_run_time
    aps_job.trigger.interval = timedelta(hours=hours)

    scheduler = MagicMock()
    scheduler._scheduler.get_job.return_value = aps_job

    app = MagicMock()
    app.extensions = {"scheduler": scheduler}
    return app, scheduler


class TestStartupPreservesTheAnchor:
    def test_startup_leaves_an_already_correct_interval_alone(self):
        """Rescheduling with the same interval only moves the anchor."""
        app, scheduler = _app_with_interval(6)
        _apply_intervals_to_apscheduler(app, 6, 6, on_startup=True)
        scheduler.modify_trigger.assert_not_called()

    def test_startup_still_applies_a_changed_interval(self):
        """A config change made while the app was down must still land."""
        app, scheduler = _app_with_interval(6)
        _apply_intervals_to_apscheduler(app, 6, 12, on_startup=True)
        modified = {c.args[0] for c in scheduler.modify_trigger.call_args_list}
        assert modified == {"wanted_search"}

    def test_unreadable_trigger_falls_back_to_applying(self):
        """Never skip on uncertainty — a missing job must still get its trigger."""
        app, scheduler = _app_with_interval(6)
        scheduler._scheduler.get_job.return_value = None
        _apply_intervals_to_apscheduler(app, 6, 6, on_startup=True)
        modified = {c.args[0] for c in scheduler.modify_trigger.call_args_list}
        assert modified == {"wanted_scanner", "wanted_search"}

    def test_settings_save_always_applies(self):
        """An explicit save stays an explicit "use this now" instruction."""
        app, scheduler = _app_with_interval(6)
        _apply_intervals_to_apscheduler(app, 6, 6, on_startup=False)
        modified = {c.args[0] for c in scheduler.modify_trigger.call_args_list}
        assert modified == {"wanted_scanner", "wanted_search"}
