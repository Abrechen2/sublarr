"""Sublarr scheduler service — APScheduler facade + JobSpec registry.

This file will grow across Phase 1 tasks; at this point it only
contains JobSpec + compute_default_misfire_grace_time.
"""

from __future__ import annotations

import logging
import traceback
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Callable

from apscheduler.triggers.base import BaseTrigger
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
        started_at = datetime.now(UTC)
        status = "ok"
        error_type: str | None = None
        error_msg: str | None = None
        finished_at: datetime | None = None

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
                _write_job_run(
                    job_id=spec.id,
                    started_at=started_at,
                    finished_at=finished_at,
                    status=status,
                    triggered_by=triggered_by,
                    error_type=error_type,
                    error_msg=error_msg,
                )

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
