"""Scheduler tick infrastructure — JobSpec, history writes, dispatchers.

Extracted from services/scheduler.py. Holds the picklable top-level tick
dispatchers (``_scheduled_tick`` / ``_scheduled_oneshot_tick``) and the
module-level registries they resolve against. These dispatchers are
referenced textually by the SQLAlchemyJobStore as
``services.scheduler:_scheduled_tick`` — the package root re-exports them so
that path keeps resolving across process restarts (see memory
``feedback_apscheduler_pickle_closure``).
"""

from __future__ import annotations

import logging
import threading
import traceback
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Callable

from apscheduler.triggers.base import BaseTrigger
from apscheduler.triggers.interval import IntervalTrigger
from flask import Flask

from services.scheduler import cancellation

logger = logging.getLogger(__name__)

_MAX_ERROR_MSG_BYTES = 4096

# Single shared executor for tick timeouts. Sized at module level;
# resized at scheduler.start() once the JobSpec count is known.
_tick_executor: ThreadPoolExecutor | None = None


# Shared by every JobSpec. A run recorded `timeout_abandoned` keeps its worker
# for as long as the work runs on, so a job that will not wind down costs a
# slot from this pool until it does — which is why a saturated pool has to be
# distinguishable in the history from a job that ignored its stop request.
_TICK_EXECUTOR_WORKERS = 16


def _get_tick_executor() -> ThreadPoolExecutor:
    global _tick_executor
    if _tick_executor is None:
        _tick_executor = ThreadPoolExecutor(
            max_workers=_TICK_EXECUTOR_WORKERS, thread_name_prefix="scheduler-tick"
        )
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
      cancel_grace_s: how long this job is given to leave after being asked
        to stop, before the run is recorded as `timeout_abandoned`. None
        means the proportional default, `max(1, min(60, timeout_s // 10))`.
        Declare it when the job's wind-down has been *measured*: the time is
        a property of the work in flight — one item finishing its
        post-processing — not of the timeout the job happens to sit under.
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
    cancel_grace_s: int | None = None
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
        if self.cancel_grace_s is not None and (
            not isinstance(self.cancel_grace_s, int) or self.cancel_grace_s <= 0
        ):
            raise ValueError(
                f"JobSpec.cancel_grace_s must be > 0 or None (got {self.cancel_grace_s!r})"
            )

    @property
    def effective_cancel_grace_s(self) -> int:
        """Seconds this job gets to leave after being asked to stop.

        The default stays proportional-but-capped so unmeasured jobs behave
        exactly as before. A declared value overrides it outright — the cap
        is the thing that was wrong, and only evidence should lift it.
        """
        if self.cancel_grace_s is not None:
            return self.cancel_grace_s
        return max(1, min(60, self.timeout_s // 10))


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
            # Persist the skip so the user can see in /scheduler/jobs/<id>/runs
            # that their manual run-now (or a scheduled fire) collided with an
            # in-flight tick. APScheduler's MaxInstancesReachedError covers
            # scheduled-vs-scheduled overlap, but manual oneshots have a
            # distinct APS job id, so only the per-job lock catches that case.
            now = datetime.now(UTC)
            try:
                with app.app_context():
                    _write_job_run(
                        job_id=spec.id,
                        started_at=now,
                        finished_at=now,
                        status="skipped_overlap",
                        triggered_by=triggered_by,
                    )
            except Exception:
                logger.error(
                    "scheduler: failed to record skipped_overlap row for %s",
                    spec.id,
                    exc_info=True,
                )
            return

        started_at = datetime.now(UTC)
        started_perf = _time.perf_counter()
        status = "ok"
        error_type: str | None = None
        error_msg: str | None = None
        finished_at: datetime | None = None

        # One event per run. Bound to the worker thread inside the callable
        # below — ThreadPoolExecutor does not carry this thread's context
        # across, so binding it here would leave every abort_requested() in
        # every job reading the default and answering "keep going".
        cancel_event = cancellation.begin_run(spec.id)

        # Set the instant the worker picks the job up. The timeout bounds the
        # wait on the future, not the work, and this executor's 16 workers are
        # shared by every job — so a submitted tick can still be *queued* when
        # its timeout expires. Without this flag such a run was recorded
        # `timeout_abandoned`, which tells an operator to go hunting for
        # runaway work that never existed (prod 2026-08-21: a wanted_search run
        # filed abandoned at 2700s with not one line of its own in the log).
        started = threading.Event()

        def _fn_with_ctx() -> None:
            started.set()
            token = cancellation.activate(cancel_event)
            try:
                with app.app_context():
                    spec.func()
            finally:
                cancellation.deactivate(token)
                # Deregister only once the thread is genuinely leaving, not
                # when the wait below gives up: an abandoned run must stay
                # reachable, and its event must stay set, until it exits.
                cancellation.end_run(spec.id, cancel_event)

        try:
            with app.app_context():
                try:
                    future = _get_tick_executor().submit(_fn_with_ctx)
                    future.result(timeout=spec.timeout_s)
                except FutureTimeoutError:
                    # The timeout bounded the wait, never the work. Ask the job
                    # to stop and give it a bounded chance to reach its next
                    # check point, so a cooperative job gets an honest ending.
                    cancel_event.set()
                    grace_s = spec.effective_cancel_grace_s
                    error_type = "TimeoutError"
                    try:
                        future.result(timeout=grace_s)
                        status = "timeout"
                        error_msg = f"tick exceeded {spec.timeout_s}s and stopped when asked"
                        logger.error(
                            "scheduler: %s timed out after %ds and stopped",
                            spec.id,
                            spec.timeout_s,
                        )
                    except FutureTimeoutError:
                        if not started.is_set():
                            # Never picked up by a worker: nothing ran, so
                            # nothing ignored the stop request. Saying
                            # "abandoned" here sends an operator looking for
                            # runaway work that does not exist, and hides the
                            # real fault, which is a saturated tick executor.
                            status = "timeout_not_started"
                            error_msg = (
                                f"tick waited {spec.timeout_s}s + {grace_s}s without ever "
                                "starting — every scheduler worker was busy, so the job "
                                "never ran"
                            )
                            logger.error(
                                "scheduler: %s never started — all %d tick workers were "
                                "busy for %ds; the job did not run at all",
                                spec.id,
                                _TICK_EXECUTOR_WORKERS,
                                spec.timeout_s + grace_s,
                            )
                        else:
                            # Recorded distinctly because "timeout" reads as
                            # "the run ended". One user's sweep was still
                            # reading their library sixteen hours after that
                            # line was logged.
                            status = "timeout_abandoned"
                            error_msg = (
                                f"tick exceeded {spec.timeout_s}s, was asked to stop, and was "
                                f"still running {grace_s}s later — the work continues until it "
                                "reaches a check point"
                            )
                            logger.error(
                                "scheduler: %s exceeded %ds and did NOT stop when asked — "
                                "it is still running",
                                spec.id,
                                spec.timeout_s,
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
