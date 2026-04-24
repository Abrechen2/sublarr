"""Sublarr scheduler service — APScheduler facade + JobSpec registry.

This file will grow across Phase 1 tasks; at this point it only
contains JobSpec + compute_default_misfire_grace_time.
"""

from __future__ import annotations

import logging
import os
import threading
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Callable

from apscheduler.triggers.base import BaseTrigger
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from flask import Flask

logger = logging.getLogger(__name__)

_MAX_ERROR_MSG_BYTES = 4096

# Single shared executor for tick timeouts. Sized at module level;
# resized at scheduler.start() once the JobSpec count is known.
_tick_executor: ThreadPoolExecutor | None = None


def _get_tick_executor() -> ThreadPoolExecutor:
    global _tick_executor
    if _tick_executor is None:
        _tick_executor = ThreadPoolExecutor(max_workers=16, thread_name_prefix="scheduler-tick")
    return _tick_executor


def compute_default_misfire_grace_time(trigger: BaseTrigger) -> int:
    """Return the default misfire grace (seconds) for a trigger.

    - IntervalTrigger: half of the interval in seconds.
    - CronTrigger (and anything else): 60 seconds.
    """
    if isinstance(trigger, IntervalTrigger):
        total = int(trigger.interval.total_seconds())
        return max(1, total // 2)
    return 60


@dataclass(frozen=True)
class JobSpec:
    """Declarative spec for a recurring scheduled job.

    Fields:
      id: stable identifier; used as the JobStore row key.
      func: tick function taking no args; must be idempotent.
      default_trigger: IntervalTrigger or CronTrigger used when no
        user override exists in the JobStore.
      timeout_s: enforced by _tick_wrapper via ThreadPoolExecutor.
      max_instances: APScheduler concurrency cap (defaults to 1).
      coalesce: collapse missed fires into one on resume.
      misfire_grace_time: None means computed at registration from
        compute_default_misfire_grace_time.
      owner_module: module path shown in the UI for grouping/debug.
      description: human-readable summary shown in the UI.
    """

    id: str
    func: Callable[[], None]
    default_trigger: BaseTrigger
    timeout_s: int = 300
    max_instances: int = 1
    coalesce: bool = True
    misfire_grace_time: int | None = None
    owner_module: str = ""
    description: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.id, str) or not self.id.strip():
            raise ValueError("JobSpec.id must be non-empty string")
        if not callable(self.func):
            raise TypeError("JobSpec.func must be callable")
        if not isinstance(self.timeout_s, int) or self.timeout_s <= 0:
            raise ValueError(f"JobSpec.timeout_s must be > 0 (got {self.timeout_s!r})")
        if not isinstance(self.default_trigger, BaseTrigger):
            raise TypeError("JobSpec.default_trigger must be a BaseTrigger subclass")


def _write_job_run(
    *,
    job_id: str,
    started_at: datetime,
    finished_at: datetime | None,
    status: str,
    triggered_by: str,
    error_type: str | None = None,
    error_msg: str | None = None,
) -> None:
    """Write a scheduler_job_runs row.

    A fresh db.session (via scoped_session) is used so a corrupted
    tick session cannot destroy the error record it was just trying
    to persist.
    """
    from db.models.scheduler import JobRun
    from extensions import db

    duration_ms = None
    if finished_at is not None:
        duration_ms = int((finished_at - started_at).total_seconds() * 1000)

    if error_msg and len(error_msg) > _MAX_ERROR_MSG_BYTES:
        error_msg = error_msg[: _MAX_ERROR_MSG_BYTES - 3] + "..."

    row = JobRun(
        job_id=job_id,
        started_at=started_at,
        finished_at=finished_at,
        duration_ms=duration_ms,
        status=status,
        triggered_by=triggered_by,
        error_type=error_type,
        error_msg=error_msg,
    )
    try:
        db.session.add(row)
        db.session.commit()
    except Exception:
        logger.error(
            "scheduler: failed to write job_run for %s",
            job_id,
            exc_info=True,
        )
        db.session.rollback()


# Module-level registry used by picklable tick dispatchers (SQLAlchemyJobStore
# requires that the job callable be importable; local closures cannot be
# pickled). Entries are written by SublarrScheduler.start_registered_jobs().
_tick_registry: dict[str, tuple[Flask, JobSpec]] = {}


def _scheduled_tick(spec_id: str) -> None:
    """Top-level dispatcher used as the JobStore-persisted callable.

    Resolves (app, spec) from the module registry at fire time and delegates
    to _tick_wrapper. Stored as a textual reference
    (`services.scheduler:_scheduled_tick`) so APScheduler can reimport it
    after a process restart.
    """
    app, spec = _tick_registry[spec_id]
    _tick_wrapper(app, spec, triggered_by="schedule")()


# Separate registry for one-shot (triggered_by='manual') runs.
_oneshot_registry: dict[str, tuple[Flask, JobSpec]] = {}

# Serialises every run_now() call — check-then-add of the oneshot_id +
# presence check against get_jobs() is not atomic at the APScheduler level.
_run_now_lock = threading.Lock()

# Per-job run locks — held for the duration of a tick. Guarantees that
# scheduled ticks, manual oneshots, and queued retries for the SAME job
# never run concurrently, regardless of which APScheduler thread dispatched
# them. For different jobs the locks are independent so the scheduler pool
# still gets full parallelism.
_job_run_locks: dict[str, threading.Lock] = {}
_job_run_locks_guard = threading.Lock()


def _get_job_run_lock(job_id: str) -> threading.Lock:
    with _job_run_locks_guard:
        lock = _job_run_locks.get(job_id)
        if lock is None:
            lock = threading.Lock()
            _job_run_locks[job_id] = lock
        return lock


def _scheduled_oneshot_tick(oneshot_id: str) -> None:
    """Dispatcher for run_now one-shot jobs.

    Resolves (app, spec) from _oneshot_registry and invokes _tick_wrapper
    with triggered_by='manual'. After completion, removes the registry
    entry so it doesn't accumulate.

    If the registry is empty (e.g. the process restarted between add_job
    and fire), we fall back to deriving the parent job_id from the
    oneshot_id prefix and resolve the spec from _tick_registry. This
    keeps persisted SQLAlchemyJobStore oneshots survivable across
    restarts instead of warning-and-skipping.
    """
    app, spec = _oneshot_registry.pop(oneshot_id, (None, None))
    if app is None or spec is None:
        # Fallback: parse parent job_id from "<job_id>_oneshot_<ts>"
        if "_oneshot_" in oneshot_id:
            parent_id = oneshot_id.split("_oneshot_", 1)[0]
            registry_entry = _tick_registry.get(parent_id)
            if registry_entry is not None:
                app, spec = registry_entry
                logger.info(
                    "scheduler: oneshot %s recovered from _tick_registry (post-restart fallback)",
                    oneshot_id,
                )
        if app is None or spec is None:
            logger.warning(
                "scheduler: oneshot %s fired but registry entry missing",
                oneshot_id,
            )
            return
    _tick_wrapper(app, spec, triggered_by="manual")()


def _tick_wrapper(
    app: Flask, spec: JobSpec, *, triggered_by: str = "schedule"
) -> Callable[[], None]:
    """Wrap a JobSpec.func into a callable safe for the scheduler to invoke.

    Guarantees:
      - enters app.app_context() before calling fn
      - enforces spec.timeout_s via ThreadPoolExecutor
      - catches all exceptions, logs with exc_info, writes history row
    """

    def _fn_with_ctx() -> None:
        with app.app_context():
            spec.func()

    def _runner() -> None:
        import time as _time

        # Per-job lock: same spec.id never fires concurrently even when a
        # manual oneshot overlaps with a scheduled tick.
        job_lock = _get_job_run_lock(spec.id)
        if not job_lock.acquire(blocking=False):
            logger.info(
                "scheduler: %s skipped — previous tick still running (triggered_by=%s)",
                spec.id,
                triggered_by,
            )
            return

        started_at = datetime.now(UTC)
        started_perf = _time.perf_counter()
        status = "ok"
        error_type: str | None = None
        error_msg: str | None = None
        finished_at: datetime | None = None

        try:
            with app.app_context():
                try:
                    future = _get_tick_executor().submit(_fn_with_ctx)
                    future.result(timeout=spec.timeout_s)
                except FutureTimeoutError:
                    status = "timeout"
                    error_type = "TimeoutError"
                    error_msg = f"tick exceeded {spec.timeout_s}s"
                    logger.error(
                        "scheduler: %s timed out after %ds",
                        spec.id,
                        spec.timeout_s,
                        exc_info=True,
                    )
                except Exception as exc:
                    status = "error"
                    error_type = type(exc).__name__
                    error_msg = f"{exc}\n{traceback.format_exc()}"
                    logger.error(
                        "scheduler: %s raised %s",
                        spec.id,
                        error_type,
                        exc_info=True,
                    )
                finally:
                    finished_at = datetime.now(UTC)
                    # perf_counter() is monotonic + high-resolution, so the
                    # histogram observation survives coarse-grained wall-clock
                    # sources (Windows datetime.now ~15 ms) on short ticks.
                    duration_s = _time.perf_counter() - started_perf
                    try:
                        from monitoring.metrics import (
                            scheduler_job_duration_seconds,
                            scheduler_job_runs_total,
                        )

                        scheduler_job_runs_total.labels(job_id=spec.id, status=status).inc()
                        scheduler_job_duration_seconds.labels(job_id=spec.id).observe(duration_s)
                    except Exception:
                        logger.warning("scheduler: metrics emit failed", exc_info=True)
                    _write_job_run(
                        job_id=spec.id,
                        started_at=started_at,
                        finished_at=finished_at,
                        status=status,
                        triggered_by=triggered_by,
                        error_type=error_type,
                        error_msg=error_msg,
                    )
        finally:
            # Always release the per-job lock so subsequent ticks (scheduled
            # or manual) can fire.
            job_lock.release()

    return _runner


from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore  # noqa: E402
from apscheduler.schedulers.background import BackgroundScheduler  # noqa: E402


class SublarrScheduler:
    """Facade wrapping a BackgroundScheduler bound to a SQLAlchemyJobStore."""

    def __init__(self, db_url: str, autostart: bool = True) -> None:
        self._db_url = db_url
        self._autostart = autostart
        self._app: Flask | None = None
        self._scheduler: BackgroundScheduler | None = None
        self._shutting_down = False
        self._registered_ids: set[str] = set()
        self._specs: dict[str, JobSpec] = {}

    @property
    def running(self) -> bool:
        return self._scheduler is not None and self._scheduler.running

    def attach_app(self, app: Flask) -> None:
        self._app = app

    def _ensure_scheduler(self) -> BackgroundScheduler:
        if self._scheduler is None:
            jobstore = SQLAlchemyJobStore(
                url=self._db_url,
                tablename="apscheduler_jobs",
                engine_options={"pool_pre_ping": True},
            )
            self._scheduler = BackgroundScheduler(
                jobstores={"default": jobstore},
                timezone="UTC",
            )
        return self._scheduler

    def _spec_by_id(self, spec_id: str) -> JobSpec:
        return self._specs[spec_id]

    def start(self) -> None:
        """Idempotent start. Safe to call multiple times; no-op if running.

        If the underlying scheduler was pre-started in paused mode by
        start_registered_jobs()/purge_orphans() (so it could resolve
        jobstore rows before the registry settles), resume it instead of
        starting again.

        Fixes feedback_scheduler_timer_leak by removing the "restart on
        every settings save" behaviour of the legacy threading.Timer
        schedulers.
        """
        if self._app is None:
            raise RuntimeError("attach_app() must be called before start()")
        from apscheduler.schedulers.base import STATE_PAUSED, STATE_RUNNING

        scheduler = self._ensure_scheduler()
        if scheduler.state == STATE_RUNNING:
            return
        if scheduler.state == STATE_PAUSED:
            scheduler.resume()
        else:
            scheduler.start()
        logger.info(
            "SublarrScheduler: started (%d job(s) registered)",
            len(self._registered_ids),
        )

    def shutdown(self, timeout_s: int = 25) -> None:
        """Bounded shutdown. Safe to call multiple times."""
        if self._shutting_down:
            return
        self._shutting_down = True
        scheduler = self._scheduler
        if scheduler is None or not scheduler.running:
            return
        try:
            import threading

            done = threading.Event()

            def _do_shutdown():
                try:
                    scheduler.shutdown(wait=True)
                finally:
                    done.set()

            t = threading.Thread(target=_do_shutdown, name="scheduler-shutdown")
            t.start()
            if not done.wait(timeout=timeout_s):
                logger.warning(
                    "SublarrScheduler: shutdown exceeded %ds; forcing non-wait",
                    timeout_s,
                )
                try:
                    scheduler.shutdown(wait=False)
                except Exception:
                    logger.error("forced shutdown failed", exc_info=True)
        finally:
            logger.info("SublarrScheduler: shut down")

    def register_job(self, spec: JobSpec) -> None:
        """Add a JobSpec to the internal registry.

        Fails fast on duplicate id. Does NOT yet add to the JobStore;
        that happens in start_registered_jobs() (added in Task 7).
        """
        if spec.id in self._registered_ids:
            raise ValueError(f"JobSpec id {spec.id!r} already registered")
        self._registered_ids.add(spec.id)
        self._specs[spec.id] = spec

    def start_registered_jobs(self) -> None:
        """Walk the registry and add_job() for specs not yet in JobStore.

        Existing JobStore rows (user overrides) are left untouched.
        Must be called after register_job() for all specs and before start().

        The scheduler is started in paused mode so that `get_job()` consults
        the persistent jobstore rather than only the in-memory pending list
        (otherwise a second boot would always re-add jobs and conflict on
        the store's row).
        """
        if self._app is None:
            raise RuntimeError("attach_app() required before start_registered_jobs()")

        from apscheduler.schedulers.base import STATE_STOPPED

        scheduler = self._ensure_scheduler()
        if scheduler.state == STATE_STOPPED:
            scheduler.start(paused=True)
        for spec_id in list(self._registered_ids):
            spec = self._spec_by_id(spec_id)
            # Publish to the module registry so _scheduled_tick can resolve
            # the (app, spec) tuple at fire time. Done unconditionally so
            # process restarts rebind to the live Flask app + spec.
            _tick_registry[spec_id] = (self._app, spec)
            existing = scheduler.get_job(spec_id)
            if existing is not None:
                continue
            grace = (
                spec.misfire_grace_time
                if spec.misfire_grace_time is not None
                else compute_default_misfire_grace_time(spec.default_trigger)
            )
            scheduler.add_job(
                func="services.scheduler:_scheduled_tick",
                args=[spec.id],
                trigger=spec.default_trigger,
                id=spec.id,
                replace_existing=False,
                max_instances=spec.max_instances,
                coalesce=spec.coalesce,
                misfire_grace_time=grace,
            )

    def attach_listeners(self) -> None:
        """Wire EVENT_JOB_MISSED + EVENT_JOB_ERROR to history writes.

        EVENT_JOB_EXECUTED is NOT wired — _tick_wrapper already writes the
        ok row synchronously. Listening twice would double-write.

        The EVENT_JOB_ERROR listener only synthesises a row for
        MaxInstancesReachedError (concurrency skip). Other errors are
        captured by _tick_wrapper directly via the function path.
        """
        from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_MISSED
        from apscheduler.executors.base import MaxInstancesReachedError

        scheduler = self._ensure_scheduler()

        def _on_missed(event) -> None:
            try:
                _write_job_run(
                    job_id=event.job_id,
                    started_at=event.scheduled_run_time,
                    finished_at=None,
                    status="missed",
                    triggered_by="schedule",
                )
            except Exception:
                logger.error("scheduler: missed-listener failed", exc_info=True)

        def _on_error(event) -> None:
            try:
                exc = event.exception
                if isinstance(exc, MaxInstancesReachedError):
                    _write_job_run(
                        job_id=event.job_id,
                        started_at=event.scheduled_run_time,
                        finished_at=event.scheduled_run_time,
                        status="skipped_overlap",
                        triggered_by="schedule",
                    )
            except Exception:
                logger.error("scheduler: error-listener failed", exc_info=True)

        scheduler.add_listener(_on_missed, EVENT_JOB_MISSED)
        scheduler.add_listener(_on_error, EVENT_JOB_ERROR)

    def purge_orphans(self) -> None:
        """Remove JobStore rows whose id is not in the current registry.

        Also sweeps stale one-shot rows whose next_run_time is in the past
        (they come from crashed run-now invocations; the scheduler would
        otherwise fire them all at startup).

        Starts the underlying scheduler in paused mode if needed so
        `get_jobs()` returns rows persisted in the SQLAlchemyJobStore
        (rather than only the in-memory pending list).
        """
        from apscheduler.schedulers.base import STATE_STOPPED

        scheduler = self._ensure_scheduler()
        if scheduler.state == STATE_STOPPED:
            scheduler.start(paused=True)
        for job in list(scheduler.get_jobs()):
            base_id = job.id.split("_oneshot_")[0]
            if base_id not in self._registered_ids:
                scheduler.remove_job(job.id)
                logger.info("purge_orphans: removed %s", job.id)
                continue
            if "_oneshot_" in job.id:
                if job.next_run_time is None or job.next_run_time < datetime.now(UTC):
                    scheduler.remove_job(job.id)
                    logger.info("purge_orphans: removed stale oneshot %s", job.id)

    def run_now(self, job_id: str) -> str:
        """Queue a one-shot immediate fire. Returns the one-shot job id.

        Raises:
          JobNotRegisteredError: job_id not in registry
          OneshotAlreadyPendingError: another one-shot is pending/running

        Thread-safe: the entire check-then-add is serialised via
        ``_run_now_lock`` so two concurrent callers cannot both observe
        the "no pending oneshot" state and race to register colliding
        entries. The oneshot id uses a uuid4 suffix to avoid collisions
        from second-granularity timestamps.
        """
        from apscheduler.triggers.date import DateTrigger

        if job_id not in self._registered_ids:
            raise JobNotRegisteredError(job_id)

        scheduler = self._ensure_scheduler()
        prefix = f"{job_id}_oneshot_"

        # Ensure persistent store is visible so we can detect existing oneshots
        # after a process restart. Pattern from Task 7 (see memory
        # feedback_apscheduler_pickle_closure).
        if not scheduler.running:
            scheduler.start(paused=True)

        with _run_now_lock:
            for j in scheduler.get_jobs():
                if j.id.startswith(prefix):
                    raise OneshotAlreadyPendingError(
                        f"{job_id} already has a pending one-shot: {j.id}"
                    )

            # uuid4 → 32 hex chars; collision-free under realistic load.
            oneshot_id = f"{prefix}{uuid.uuid4().hex}"

            # Use textual reference to the top-level dispatcher (picklable),
            # same pattern as start_registered_jobs. Spec lookup happens at
            # fire time via _tick_registry — also need to register this
            # oneshot binding so the dispatcher can resolve it with
            # triggered_by='manual'.
            _oneshot_registry[oneshot_id] = (self._app, self._spec_by_id(job_id))

            scheduler.add_job(
                func="services.scheduler:_scheduled_oneshot_tick",
                args=[oneshot_id],
                trigger=DateTrigger(run_date=datetime.now(UTC)),
                id=oneshot_id,
                replace_existing=False,
                max_instances=1,
            )
        return oneshot_id

    def _require_registered(self, job_id: str) -> None:
        if job_id not in self._registered_ids:
            raise JobNotRegisteredError(job_id)

    def reset_to_default(self, job_id: str) -> None:
        """Remove the JobStore row and re-register from code default."""
        self._require_registered(job_id)
        spec = self._spec_by_id(job_id)
        scheduler = self._ensure_scheduler()
        try:
            scheduler.remove_job(job_id)
        except Exception:
            logger.warning("reset_to_default: remove_job miss for %s", job_id)
        grace = (
            spec.misfire_grace_time
            if spec.misfire_grace_time is not None
            else compute_default_misfire_grace_time(spec.default_trigger)
        )
        # Refresh registry binding in case app reference changed.
        _tick_registry[spec.id] = (self._app, spec)
        scheduler.add_job(
            func="services.scheduler:_scheduled_tick",
            args=[spec.id],
            trigger=spec.default_trigger,
            id=spec.id,
            replace_existing=False,
            max_instances=spec.max_instances,
            coalesce=spec.coalesce,
            misfire_grace_time=grace,
        )

    def pause_job(self, job_id: str) -> None:
        self._require_registered(job_id)
        self._ensure_scheduler().pause_job(job_id)

    def resume_job(self, job_id: str) -> None:
        self._require_registered(job_id)
        self._ensure_scheduler().resume_job(job_id)

    def modify_trigger(self, job_id: str, trigger: BaseTrigger) -> None:
        self._require_registered(job_id)
        self._ensure_scheduler().reschedule_job(job_id, trigger=trigger)

    def trigger_is_default(self, job_id: str) -> bool:
        """Return True iff the current trigger matches spec default.

        Comparison uses repr() — APScheduler's BaseTrigger subclasses
        define __getstate__ but not __eq__, so repr is the stable
        surrogate.
        """
        self._require_registered(job_id)
        job = self._ensure_scheduler().get_job(job_id)
        if job is None:
            return False
        default = self._spec_by_id(job_id).default_trigger
        return repr(job.trigger) == repr(default)


class JobNotRegisteredError(KeyError):
    """Raised when operating on an unknown JobSpec id."""


class OneshotAlreadyPendingError(RuntimeError):
    """Raised by run_now when a prior one-shot for the same job is still pending."""


def reconcile_stale_runs(grace_minutes: int = 10) -> int:
    """Mark abandoned rows (no finished_at, started_at older than grace) as interrupted.

    Called once at scheduler startup. Returns the number of rows updated.
    """
    from datetime import timedelta

    from db.models.scheduler import JobRun
    from extensions import db

    cutoff = datetime.now(UTC) - timedelta(minutes=grace_minutes)
    now = datetime.now(UTC)

    with db.session.begin():
        stale = (
            db.session.query(JobRun)
            .filter(JobRun.finished_at.is_(None))
            .filter(JobRun.started_at < cutoff)
            .all()
        )
        for row in stale:
            row.status = "error"
            row.error_type = "InterruptedByShutdown"
            row.error_msg = (
                f"Row abandoned without finished_at after {grace_minutes}m grace; "
                "likely SIGKILL or shutdown-timeout."
            )
            row.finished_at = now
            # SQLite stores datetimes as naive; normalise to UTC-aware so the
            # subtraction below does not blow up on mixed tz-awareness.
            started = row.started_at
            if started.tzinfo is None:
                started = started.replace(tzinfo=UTC)
            row.duration_ms = int((now - started).total_seconds() * 1000)

    if stale:
        logger.warning("scheduler: reconciled %d abandoned job_run rows", len(stale))
        try:
            from monitoring.metrics import scheduler_interrupted_runs_total

            scheduler_interrupted_runs_total.inc(len(stale))
        except Exception:
            pass
    return len(stale)


_VALID_ROLES = {"primary", "disabled"}

# Phase-1 placeholder. In later phases, each retiring Timer site will
# register its own JobSpec here. scheduler_history_cleanup is the only
# real job this phase registers.
SCHEDULED_JOBS: list[JobSpec] = []


def _build_default_jobs() -> list[JobSpec]:
    """Build the canonical JobSpec list. Imports are lazy to avoid
    import-time cycles against modules that themselves import scheduler.

    Phase 5 / P4: also registers the four migrated sites (5 JobSpecs) that
    used to be driven by threading.Timer chains. Default intervals are read
    lazily from config so subsequent settings-save calls can adjust them
    via the per-site adapter (``start_cleanup_scheduler``, etc.).
    """
    from anidb_sync import anidb_sync_tick
    from cleanup_scheduler import DEFAULT_INTERVAL_HOURS as CLEANUP_DEFAULT
    from cleanup_scheduler import cleanup_tick
    from services.subtitle_automation_runner import subtitle_automation_tick
    from services.wanted_scanner_scheduler import (
        wanted_scanner_tick,
        wanted_search_tick,
    )
    from upgrade_scheduler import upgrade_tick
    from utils.scheduler_retention import delete_old_job_runs
    from utils.scheduler_retention_translation import delete_old_translation_events

    # Read wanted scan/search intervals at build time, falling back to
    # conservative defaults. _build_default_jobs runs once per process so
    # later settings saves flow through the adapter's modify_trigger path.
    scan_interval_hours = 6
    search_interval_hours = 24
    upgrade_interval_hours = 168  # trigger floor; adapter pauses when 0
    automation_drain_minutes = 2
    try:
        from config import get_settings

        settings = get_settings()
        scan_interval_hours = max(1, int(settings.wanted_scan_interval_hours or 6))
        search_interval_hours = max(1, int(settings.wanted_search_interval_hours or 24))
        upgrade_cfg = int(getattr(settings, "upgrade_scan_interval_hours", 0) or 0)
        if upgrade_cfg > 0:
            upgrade_interval_hours = upgrade_cfg
        automation_drain_minutes = max(
            1, int(getattr(settings, "subtitle_automation_drain_interval_minutes", 2) or 2)
        )
    except Exception:
        logger.debug("scheduler: settings unavailable during _build_default_jobs", exc_info=True)

    cleanup_interval_hours = CLEANUP_DEFAULT
    try:
        from db.repositories.config import ConfigRepository

        val = ConfigRepository().get_config_entry("cleanup_schedule_interval_hours")
        if val is not None:
            cleanup_interval_hours = max(1, int(val))
    except Exception:
        logger.debug(
            "scheduler: cleanup interval unavailable during _build_default_jobs",
            exc_info=True,
        )

    return [
        JobSpec(
            id="scheduler_history_cleanup",
            func=delete_old_job_runs,
            default_trigger=CronTrigger(hour=3, minute=15),
            timeout_s=60,
            owner_module="services.scheduler",
            description="Delete old scheduler_job_runs rows per retention policy.",
        ),
        JobSpec(
            id="translation_events_cleanup",
            func=delete_old_translation_events,
            default_trigger=CronTrigger(hour=3, minute=30),
            timeout_s=120,
            owner_module="utils.scheduler_retention_translation",
            description="Delete old translation_events rows per retention policy.",
        ),
        JobSpec(
            id="cleanup",
            func=cleanup_tick,
            default_trigger=IntervalTrigger(hours=max(1, cleanup_interval_hours)),
            timeout_s=3600,
            owner_module="cleanup_scheduler",
            description=("Run enabled cleanup rules (dedup, orphan files, format upgrade, ...)."),
        ),
        JobSpec(
            id="upgrade_scan",
            func=upgrade_tick,
            default_trigger=IntervalTrigger(hours=max(1, upgrade_interval_hours)),
            timeout_s=3600,
            owner_module="upgrade_scheduler",
            description="Scan subtitle_downloads for re-queue eligible upgrade candidates.",
        ),
        JobSpec(
            id="anidb_sync",
            func=anidb_sync_tick,
            default_trigger=IntervalTrigger(hours=168),
            timeout_s=1800,
            owner_module="anidb_sync",
            description="Weekly sync of AniDB absolute-episode mappings.",
        ),
        JobSpec(
            id="wanted_scanner",
            func=wanted_scanner_tick,
            default_trigger=IntervalTrigger(hours=scan_interval_hours),
            # Full-scan can exceed 10 min on large libraries (2979 items → 37 min observed
            # on prod 2026-04-24). Raised to 1 h to avoid false-positive timeout alarms.
            timeout_s=3600,
            owner_module="services.wanted_scanner",
            description="Scan Sonarr/Radarr/standalone for episodes missing subtitles.",
        ),
        JobSpec(
            id="wanted_search",
            func=wanted_search_tick,
            default_trigger=IntervalTrigger(hours=search_interval_hours),
            timeout_s=900,
            owner_module="services.wanted_scanner",
            description="Search providers for all wanted items.",
        ),
        JobSpec(
            id="subtitle_automation",
            func=subtitle_automation_tick,
            default_trigger=IntervalTrigger(minutes=automation_drain_minutes),
            timeout_s=600,
            owner_module="services.subtitle_automation_runner",
            description=(
                "Drain the subtitle_automation_queue: extract pending embedded "
                "subtitles into sidecars. No-op when the master toggle "
                "(subtitle_automation_enabled) is off."
            ),
        ),
    ]


def bootstrap_scheduler(app: Flask) -> SublarrScheduler | None:
    """Full startup: honour SUBLARR_SCHEDULER_ROLE env, reconcile,
    register jobs, start.

    Returns the scheduler instance or None if this replica is disabled.
    """
    role = os.environ.get("SUBLARR_SCHEDULER_ROLE", "primary").strip().lower()
    if role not in _VALID_ROLES:
        raise ValueError(
            f"SUBLARR_SCHEDULER_ROLE={role!r} is invalid; expected one of {sorted(_VALID_ROLES)}"
        )
    if role == "disabled":
        logger.info("SUBLARR_SCHEDULER_ROLE=disabled — skipping scheduler on this replica")
        return None

    db_url = app.config["SQLALCHEMY_DATABASE_URI"]
    s = SublarrScheduler(db_url=db_url, autostart=False)
    s.attach_app(app)

    with app.app_context():
        reconcile_stale_runs(grace_minutes=10)

    global SCHEDULED_JOBS
    if not SCHEDULED_JOBS:
        SCHEDULED_JOBS = _build_default_jobs()
    for spec in SCHEDULED_JOBS:
        s.register_job(spec)

    s.start_registered_jobs()
    s.purge_orphans()
    s.attach_listeners()
    s.start()
    app.extensions["scheduler"] = s
    return s
