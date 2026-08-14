"""The startup search must use the same bounded execution path as a tick.

Production 2026-08-13: the startup search called the job body directly in a
bare thread, so it had no timeout and no cancellation source. It took 100
sidecar items at ~14.5 minutes each and held the search lock for a day. A
scheduled tick doing the identical work would have been asked to stop after
1800s. The guarantee cannot depend on which door the work came through.

``bootstrap_scheduler`` runs before this adapter (``app_schedulers.py``
calls it first and only then ``scanner.start_scheduler(on_startup=True)``),
so ``run_now`` is the load-bearing path here — the fallback branches only
cover a failed bootstrap.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


def _settings(**over):
    base = dict(
        wanted_scan_interval_hours=0,
        wanted_search_interval_hours=4,
        wanted_scan_on_startup=False,
        wanted_search_on_startup=True,
    )
    base.update(over)
    return SimpleNamespace(**base)


def _scanner():
    from services.wanted_scanner import WantedScanner

    return WantedScanner()


class TestStartupSearchUsesScheduler:
    def test_startup_search_goes_through_run_now(self, app_ctx):
        from services import wanted_scanner_scheduler as mod

        scheduler = MagicMock()
        scheduler.run_now.return_value = "wanted_search_oneshot_abc"

        with (
            patch.object(mod, "get_settings", return_value=_settings()),
            patch.object(mod, "_job_is_paused", return_value=False),
            patch.object(mod, "_get_scheduler", return_value=scheduler),
            patch.object(mod.threading, "Thread") as thread_cls,
        ):
            _scanner().start_scheduler(app=app_ctx, on_startup=True)

        scheduler.run_now.assert_called_once_with("wanted_search")
        assert not thread_cls.called, "must not spawn an unmanaged thread"

    def test_paused_job_is_not_revived(self, app_ctx):
        from services import wanted_scanner_scheduler as mod

        scheduler = MagicMock()
        with (
            patch.object(mod, "get_settings", return_value=_settings()),
            patch.object(mod, "_job_is_paused", return_value=True),
            patch.object(mod, "_get_scheduler", return_value=scheduler),
        ):
            _scanner().start_scheduler(app=app_ctx, on_startup=True)

        scheduler.run_now.assert_not_called()

    def test_flag_off_means_no_run_now(self, app_ctx):
        from services import wanted_scanner_scheduler as mod

        scheduler = MagicMock()
        with (
            patch.object(
                mod, "get_settings", return_value=_settings(wanted_search_on_startup=False)
            ),
            patch.object(mod, "_job_is_paused", return_value=False),
            patch.object(mod, "_get_scheduler", return_value=scheduler),
        ):
            _scanner().start_scheduler(app=app_ctx, on_startup=True)

        scheduler.run_now.assert_not_called()

    def test_settings_save_does_not_trigger_a_search(self, app_ctx):
        """on_startup=False is the settings-save path and must stay inert."""
        from services import wanted_scanner_scheduler as mod

        scheduler = MagicMock()
        with (
            patch.object(mod, "get_settings", return_value=_settings()),
            patch.object(mod, "_job_is_paused", return_value=False),
            patch.object(mod, "_get_scheduler", return_value=scheduler),
        ):
            _scanner().start_scheduler(app=app_ctx, on_startup=False)

        scheduler.run_now.assert_not_called()


class TestStartupSearchSurvivesSchedulerTrouble:
    @pytest.mark.parametrize("exc_name", ["OneshotAlreadyPendingError", "JobNotRegisteredError"])
    def test_scheduler_errors_do_not_break_boot(self, app_ctx, exc_name):
        """A restart while a one-shot is queued, or a failed bootstrap, must
        not stop the rest of ``start_scheduler`` from running."""
        from services import wanted_scanner_scheduler as mod
        from services.scheduler import errors

        scheduler = MagicMock()
        scheduler.run_now.side_effect = getattr(errors, exc_name)("wanted_search")

        with (
            patch.object(mod, "get_settings", return_value=_settings()),
            patch.object(mod, "_job_is_paused", return_value=False),
            patch.object(mod, "_get_scheduler", return_value=scheduler),
        ):
            _scanner().start_scheduler(app=app_ctx, on_startup=True)
        # no exception propagates

    def test_missing_scheduler_does_not_break_boot(self, app_ctx):
        from services import wanted_scanner_scheduler as mod

        with (
            patch.object(mod, "get_settings", return_value=_settings()),
            patch.object(mod, "_job_is_paused", return_value=False),
            patch.object(mod, "_get_scheduler", return_value=None),
            patch.object(mod.threading, "Thread") as thread_cls,
        ):
            _scanner().start_scheduler(app=app_ctx, on_startup=True)

        assert not thread_cls.called, "no scheduler is not a licence to run unmanaged"
