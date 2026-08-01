"""Periodic scan/search scheduler mixin for WantedScanner.

Migrated from threading.Timer to APScheduler SublarrScheduler in Phase 5 / P4.
The actual scan + search work lives in ``wanted_scanner_tick`` and
``wanted_search_tick`` module-level functions (in this module); they are
invoked via JobSpecs registered by ``services.scheduler._build_default_jobs``.

``_WantedSchedulerMixin`` now only holds:
  - ``start_scheduler(socketio, app)`` — adapter that caches app/socketio
    on the scanner instance, optionally kicks off the ``*_on_startup``
    runs in a daemon thread, and reschedules the APScheduler jobs with
    the current interval from settings. Idempotent.
  - ``stop_scheduler()`` — no-op (APScheduler owns lifecycle).
  - ``_run_scan_with_context`` / ``_run_search_with_context`` — helpers
    kept because the tick functions call them.
"""

import logging
import threading
from datetime import UTC, datetime

from config import get_settings

logger = logging.getLogger(__name__)


class _WantedSchedulerMixin:
    """Periodic scan/search scheduler composed into WantedScanner.

    Under APScheduler the class no longer owns timer chains. It only
    keeps ``self._app`` / ``self._socketio`` so the module-level tick
    functions can pick them up via ``get_scanner()`` at fire time.
    """

    def start_scheduler(self, socketio=None, app=None, *, on_startup: bool = False):
        """Idempotent adapter.

        Called by app_schedulers._start_schedulers (with ``on_startup=True``)
        and by the settings-save / config-import paths in routes/config
        (with ``on_startup=False``, the default). Caches the app+socketio
        references on the scanner instance (so tick functions can reach
        them) and updates the APScheduler triggers for the
        ``wanted_scanner`` and ``wanted_search`` JobSpecs.

        Only when ``on_startup=True`` honours the one-shot
        ``wanted_scan_on_startup`` / ``wanted_search_on_startup`` flags by
        spawning daemon threads. Without this guard, every settings save
        re-triggered a full wanted_search (default flag is True), bypassing
        adaptive backoff, slow-mode, the backlog reserve gate, and fair
        ordering — burning provider budget invisibly.
        """
        self._socketio = socketio
        self._app = app
        self._scheduler_started_at = datetime.now(UTC)
        settings = get_settings()

        scan_interval = settings.wanted_scan_interval_hours
        if scan_interval > 0:
            if (
                on_startup
                and settings.wanted_scan_on_startup
                and not _job_is_paused(app, "wanted_scanner")
            ):
                thread = threading.Thread(target=self._run_scan_with_context, daemon=True)
                thread.start()
            logger.info("Wanted scan scheduler adapter (every %dh)", scan_interval)
        else:
            logger.info("Wanted scan scheduler disabled (interval=0)")

        search_interval = settings.wanted_search_interval_hours
        if search_interval > 0:
            # A paused job must not be revived by the startup one-shot either.
            # The on-startup flag says "run once when the app comes up"; a
            # paused job says "do not run at all". The pause is the more
            # specific, more recent instruction and wins.
            if (
                on_startup
                and settings.wanted_search_on_startup
                and not _job_is_paused(app, "wanted_search")
            ):
                thread = threading.Thread(
                    target=self._run_search_with_context,
                    args=(socketio,),
                    daemon=True,
                )
                thread.start()
            logger.info("Wanted search scheduler adapter (every %dh)", search_interval)
        else:
            logger.info("Wanted search scheduler disabled (interval=0)")

        # Push the interval change through to APScheduler (if available).
        _apply_intervals_to_apscheduler(app, scan_interval, search_interval, on_startup=on_startup)

    def stop_scheduler(self):
        """No-op — APScheduler owns lifecycle via SublarrScheduler.shutdown()."""
        return None

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


def _job_is_paused(app, job_id: str) -> bool:
    """True when the persisted APScheduler job exists and is paused.

    A paused APScheduler job has ``next_run_time = None``. Returns False when
    the scheduler or the job is not available yet, so a genuinely missing job
    never blocks a legitimate startup run.
    """
    if app is None:
        return False
    scheduler = app.extensions.get("scheduler") if hasattr(app, "extensions") else None
    if scheduler is None:
        return False
    try:
        # SublarrScheduler is a facade and exposes no get_job — go through the
        # wrapped BackgroundScheduler, the same way routes/system/scheduler.py
        # reads the flag for the admin UI.
        job = scheduler._scheduler.get_job(job_id)
    except Exception:
        logger.debug("%s: could not read pause state", job_id, exc_info=True)
        return False
    return job is not None and getattr(job, "next_run_time", None) is None


def _apply_intervals_to_apscheduler(
    app, scan_interval: int, search_interval: int, *, on_startup: bool = False
) -> None:
    """Reschedule the wanted_scanner / wanted_search jobs.

    If the scheduler has not been attached yet (e.g. during testing or
    when called before ``bootstrap_scheduler``), this is a silent no-op.
    When interval is 0 the job is paused; otherwise the trigger is
    replaced.

    Resuming a job is a *settings-save* action, never a startup one. This
    routine runs on both paths, and resuming unconditionally meant a
    deliberate pause in Settings → System → Scheduler was silently undone
    by the next container restart: the job came back with a fresh
    next_run_time and started firing again. On startup the persisted pause
    state is the user's decision and wins.
    """
    if app is None:
        return
    scheduler = app.extensions.get("scheduler") if hasattr(app, "extensions") else None
    if scheduler is None:
        return

    from apscheduler.triggers.interval import IntervalTrigger

    for job_id, interval in (
        ("wanted_scanner", scan_interval),
        ("wanted_search", search_interval),
    ):
        try:
            if interval <= 0:
                try:
                    scheduler.pause_job(job_id)
                except Exception:
                    logger.debug(
                        "%s: pause_job failed (job may not exist yet)", job_id, exc_info=True
                    )
                continue
            scheduler.modify_trigger(job_id, IntervalTrigger(hours=max(1, interval)))
            if on_startup:
                # Keep whatever the store says — do not revive a paused job.
                continue
            try:
                scheduler.resume_job(job_id)
            except Exception:
                pass
        except Exception:
            logger.error("%s: adapter failed", job_id, exc_info=True)


# ---------------------------------------------------------------------------
# Module-level tick functions (picklable; registered as JobSpec.func).
# ---------------------------------------------------------------------------


def wanted_scanner_tick() -> None:
    """Periodic scan tick — delegates to WantedScanner.scan_all().

    Picklable (module-level function, no closures). Resolves the scanner
    via the ``services.wanted_scanner:get_scanner`` factory at fire time,
    so tests can inject a mock via ``app.extensions["wanted_scanner"]``.
    """
    from services.wanted_scanner import get_scanner

    scanner = get_scanner()
    scanner.scan_all()


def wanted_search_tick() -> None:
    """Periodic search tick — delegates to WantedScanner.search_all()."""
    from services.wanted_scanner import get_scanner

    scanner = get_scanner()
    scanner.search_all(getattr(scanner, "_socketio", None))
