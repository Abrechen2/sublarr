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
