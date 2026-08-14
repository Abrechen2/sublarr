"""Periodic scan/search scheduler mixin for WantedScanner.

Migrated from threading.Timer to APScheduler SublarrScheduler in Phase 5 / P4.
The actual scan + search work lives in ``wanted_scanner_tick`` and
``wanted_search_tick`` module-level functions (in this module); they are
invoked via JobSpecs registered by ``services.scheduler._build_default_jobs``.

``_WantedSchedulerMixin`` now only holds:
  - ``start_scheduler(socketio, app)`` — adapter that caches app/socketio
    on the scanner instance, optionally kicks off the ``*_on_startup``
    runs, and reschedules the APScheduler jobs with the current interval
    from settings. Idempotent. The search one goes through
    ``scheduler.run_now`` so it inherits the tick timeout and the
    cancellation event; see ``_run_startup_search``.
  - ``stop_scheduler()`` — no-op (APScheduler owns lifecycle).
  - ``_run_scan_with_context`` / ``_run_search_with_context`` — helpers
    kept because the tick functions call them.
"""

import logging
import threading
from datetime import UTC, datetime, timedelta

from config import get_settings
from services.scheduler.errors import JobNotRegisteredError, OneshotAlreadyPendingError

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
        ``wanted_scan_on_startup`` / ``wanted_search_on_startup`` flags.
        Without this guard, every settings save
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
                _run_startup_search(app)
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


def _get_scheduler(app):
    """The SublarrScheduler facade attached to ``app``, or None.

    Same accessor ``routes/system/scheduler.py`` uses, taking the app
    explicitly because this module also runs at boot, before any request
    context exists. Returns None when the scheduler has not been attached
    (bootstrap failed, replica has ``SUBLARR_SCHEDULER_ROLE=disabled``, or
    a test never bootstrapped one).
    """
    if app is None:
        return None
    return app.extensions.get("scheduler") if hasattr(app, "extensions") else None


def _run_startup_search(app) -> None:
    """Queue the ``wanted_search_on_startup`` run through the scheduler.

    Through the scheduler, not around it. This used to start a bare daemon
    thread on the job body, which meant the startup run had no timeout and no
    cancellation event: on production 2026-08-13 it took 100 local-sidecar
    items at ~14.5 minutes each and held the global search lock for about a
    day, while a scheduled tick doing byte-for-byte the same work would have
    been asked to stop after 1800s. ``run_now`` puts it through
    ``_tick_wrapper``, which is where both guarantees live.

    Every failure mode here is "the startup run does not happen", never "the
    app does not boot" — the periodic trigger still fires later.
    """
    scheduler = _get_scheduler(app)
    if scheduler is None:
        logger.warning("Startup search skipped — no scheduler on this replica")
        return
    try:
        oneshot_id = scheduler.run_now("wanted_search")
    except OneshotAlreadyPendingError:
        logger.info("Startup search skipped — a one-shot is already queued")
    except JobNotRegisteredError:
        logger.warning("Startup search skipped — wanted_search is not registered yet")
    except Exception:
        logger.error("Startup search could not be queued", exc_info=True)
    else:
        logger.info("Startup search queued as %s", oneshot_id)


def _job_is_paused(app, job_id: str) -> bool:
    """True when the persisted APScheduler job exists and is paused.

    A paused APScheduler job has ``next_run_time = None``. Returns False when
    the scheduler or the job is not available yet, so a genuinely missing job
    never blocks a legitimate startup run.
    """
    scheduler = _get_scheduler(app)
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


def _stored_interval_matches(app, job_id: str, hours: int) -> bool:
    """True when the persisted trigger already fires every ``hours`` hours.

    Used to skip a pointless reschedule on startup. Rescheduling is not free:
    the trigger handed to ``modify_trigger`` is a fresh ``IntervalTrigger``,
    and APScheduler anchors such a trigger at *now + interval*, so re-applying
    an unchanged interval silently pushes the next run out to boot time plus a
    full interval (prod 2026-08-01: a 4h search job drifting to 6.5h and 7.7h
    gaps across redeploys).

    Returns False whenever the answer cannot be established — a missing job, a
    non-interval trigger, or anything unreadable. Uncertainty must fall through
    to applying the trigger, never to skipping it.
    """
    scheduler = _get_scheduler(app)
    if scheduler is None:
        return False
    try:
        job = scheduler._scheduler.get_job(job_id)
    except Exception:
        logger.debug("%s: could not read stored trigger", job_id, exc_info=True)
        return False
    if job is None:
        return False
    interval = getattr(getattr(job, "trigger", None), "interval", None)
    if not isinstance(interval, timedelta):
        return False
    return interval == timedelta(hours=hours)


def _apply_intervals_to_apscheduler(
    app, scan_interval: int, search_interval: int, *, on_startup: bool = False
) -> None:
    """Reschedule the wanted_scanner / wanted_search jobs.

    If the scheduler has not been attached yet (e.g. during testing or
    when called before ``bootstrap_scheduler``), this is a silent no-op.
    When interval is 0 the job is paused; otherwise the trigger is
    replaced.

    Reviving a job is a *settings-save* action, never a startup one. This
    routine runs on both paths, and on startup it silently undid a
    deliberate pause in Settings → System → Scheduler: the job came back
    with a fresh next_run_time and started firing again.

    Note that ``modify_trigger`` is itself enough to do that — APScheduler's
    reschedule_job() computes a new next_run_time, which *is* the unpaused
    state. Skipping only the explicit ``resume_job`` call is therefore not
    sufficient; a paused job has to be left alone entirely on startup. The
    trigger is still applied on the settings-save path, which is the only
    place an interval can actually change.
    """
    scheduler = _get_scheduler(app)
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
            if on_startup and _job_is_paused(app, job_id):
                # Leave it completely untouched: modify_trigger would already
                # reschedule it, and rescheduling IS unpausing.
                logger.info("%s: paused by the user — leaving it paused", job_id)
                continue
            if on_startup and _stored_interval_matches(app, job_id, max(1, interval)):
                # Nothing to change, and rescheduling would re-anchor the job to
                # boot time. The interval can only actually change on the
                # settings-save path, so on startup a correct trigger is final.
                logger.debug("%s: interval unchanged — keeping the existing anchor", job_id)
                continue
            scheduler.modify_trigger(job_id, IntervalTrigger(hours=max(1, interval)))
            if on_startup:
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
