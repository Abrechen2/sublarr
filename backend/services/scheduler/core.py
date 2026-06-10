"""SublarrScheduler facade + startup reconciliation.

Extracted from services/scheduler.py. Wraps an APScheduler
``BackgroundScheduler`` bound to a ``SQLAlchemyJobStore`` and exposes the
register/start/run-now/pause/resume surface used by the routes layer.
"""

from __future__ import annotations

import logging
import threading
import uuid
from datetime import UTC, datetime

from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.base import BaseTrigger
from flask import Flask

from services.scheduler.errors import JobNotRegisteredError, OneshotAlreadyPendingError
from services.scheduler.ticks import (
    JobSpec,
    _oneshot_registry,
    _run_now_lock,
    _tick_registry,
    _write_job_run,
    compute_default_misfire_grace_time,
)

logger = logging.getLogger(__name__)


class SublarrScheduler:
    """Facade wrapping a BackgroundScheduler bound to a SQLAlchemyJobStore."""

    # WeakSet of all live instances. Used by the pytest sessionfinish
    # hook to force-stop any APScheduler daemon threads that survived a
    # test fixture's bounded shutdown — without this, leaked threads
    # query a SQLite DB whose tmp_path was already cleaned up by pytest
    # and hammer stderr with "no such table: apscheduler_jobs", which
    # in CI stretched a 2-minute pytest run to 48 minutes.
    import weakref as _weakref

    _LIVE_INSTANCES: _weakref.WeakSet = _weakref.WeakSet()

    def __init__(self, db_url: str, autostart: bool = True) -> None:
        self._db_url = db_url
        self._autostart = autostart
        self._app: Flask | None = None
        self._scheduler: BackgroundScheduler | None = None
        self._shutting_down = False
        self._registered_ids: set[str] = set()
        self._specs: dict[str, JobSpec] = {}
        SublarrScheduler._LIVE_INSTANCES.add(self)

    @classmethod
    def _force_stop_all_for_test_cleanup(cls) -> int:
        """Best-effort hard-stop of every live SublarrScheduler.

        Bypasses the ``_shutting_down`` guard so a previously
        timed-out shutdown attempt doesn't lock further cleanup.
        Returns the number of underlying APScheduler threads that
        were stopped.
        """
        stopped = 0
        for s in list(cls._LIVE_INSTANCES):
            try:
                scheduler = s._scheduler
                if scheduler is not None and scheduler.running:
                    scheduler.shutdown(wait=False)
                    stopped += 1
            except Exception:  # noqa: BLE001 — best-effort cleanup
                pass
        return stopped

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
