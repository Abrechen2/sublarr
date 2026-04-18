"""Periodic scan/search scheduler mixin for WantedScanner.

Extracted from services/wanted_scanner_core.py. Owns the threading.Timer
chains that drive periodic ``scan_all()`` and ``search_all()`` cycles and
the app-context wrapping needed because Timer threads have no Flask
request context by default.

Idempotent start/stop is important: the ``/api/v1/config`` save path
calls ``start_scheduler`` on every write, so the mixin cancels any
existing timers before overwriting ``self._timer`` / ``self._search_timer``
— otherwise each settings save would leak a parallel timer chain.
"""

import logging
import threading
from datetime import UTC, datetime

from config import get_settings

logger = logging.getLogger(__name__)


class _WantedSchedulerMixin:
    """Periodic scan/search scheduler composed into WantedScanner."""

    def start_scheduler(self, socketio=None, app=None):
        """Start (or restart) the periodic scan and search schedulers.

        Idempotent: cancels any previously-scheduled timers first so that
        repeated calls (e.g. after a settings save via the config UI) do
        not leak concurrent timer chains that would keep ticking until
        their original delay expired.
        """
        # Cancel any previously-scheduled timers before overwriting the
        # references. Without this, every settings save leaks a timer.
        self._cancel_timers()

        self._socketio = socketio
        self._app = app
        self._scheduler_started_at = datetime.now(UTC)
        settings = get_settings()

        scan_interval = settings.wanted_scan_interval_hours
        if scan_interval > 0:
            if settings.wanted_scan_on_startup:
                thread = threading.Thread(target=self._run_scan_with_context, daemon=True)
                thread.start()
            self._schedule_next_scan(scan_interval)
            logger.info("Wanted scan scheduler started (every %dh)", scan_interval)
        else:
            logger.info("Wanted scan scheduler disabled (interval=0)")

        search_interval = settings.wanted_search_interval_hours
        if search_interval > 0:
            if settings.wanted_search_on_startup:
                thread = threading.Thread(
                    target=self._run_search_with_context,
                    args=(socketio,),
                    daemon=True,
                )
                thread.start()
            self._schedule_next_search(search_interval)
            logger.info("Wanted search scheduler started (every %dh)", search_interval)
        else:
            logger.info("Wanted search scheduler disabled (interval=0)")

    def _cancel_timers(self) -> None:
        """Cancel scan + search timers if present. Safe to call repeatedly."""
        if self._timer:
            self._timer.cancel()
            self._timer = None
        if self._search_timer:
            self._search_timer.cancel()
            self._search_timer = None

    def stop_scheduler(self):
        """Cancel all scheduled timers."""
        self._cancel_timers()
        logger.info("Wanted schedulers stopped")

    def _schedule_next_scan(self, interval_hours):
        # Cancel any existing scan timer so a scheduled-scan -> next-scan
        # chain that was already running does not double up with a new one
        # started by start_scheduler() or a config reload.
        if self._timer:
            self._timer.cancel()
        self._timer = threading.Timer(
            interval_hours * 3600,
            self._scheduled_scan,
            args=(interval_hours,),
        )
        self._timer.daemon = True
        self._timer.start()

    def _run_scan_with_context(self):
        if self._app is not None:
            with self._app.app_context():
                self.scan_all()
        else:
            self.scan_all()

    def _run_search_with_context(self, socketio=None, include_upgrades: bool | None = None):
        if self._app is not None:
            with self._app.app_context():
                self.search_all(socketio, include_upgrades=include_upgrades)
        else:
            self.search_all(socketio, include_upgrades=include_upgrades)

    def _scheduled_scan(self, interval_hours):
        logger.info("Wanted scheduled scan starting")
        self._run_scan_with_context()
        self._schedule_next_scan(interval_hours)

    def _schedule_next_search(self, interval_hours):
        # Mirror of _schedule_next_scan — cancel any in-flight search timer
        # before swapping in a new one so reschedules do not leak.
        if self._search_timer:
            self._search_timer.cancel()
        self._search_timer = threading.Timer(
            interval_hours * 3600,
            self._scheduled_search,
            args=(interval_hours,),
        )
        self._search_timer.daemon = True
        self._search_timer.start()

    def _scheduled_search(self, interval_hours):
        logger.info("Wanted scheduled search starting")
        self._run_search_with_context(self._socketio)
        self._schedule_next_search(interval_hours)
