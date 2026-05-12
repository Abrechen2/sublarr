"""Audit-row writer for sync_job_runs (Plan B7). Never raises."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

logger = logging.getLogger(__name__)


def _record_metrics(engine: str, status: str, offset_ms: int | None, duration_ms: int) -> None:
    """Bump Prometheus counters/histograms alongside the audit row. Never raises.

    Local import keeps the module loadable when ``prometheus_client`` is
    missing (rare but possible in stripped test envs).
    """
    try:
        from monitoring.metrics import (
            sync_jobs_duration_seconds,
            sync_jobs_offset_ms,
            sync_jobs_total,
        )

        sync_jobs_total.labels(engine=engine, status=status).inc()
        sync_jobs_duration_seconds.labels(engine=engine).observe(duration_ms / 1000.0)
        if status == "ok" and offset_ms is not None:
            sync_jobs_offset_ms.labels(engine=engine).observe(abs(offset_ms))
    except Exception as exc:  # pragma: no cover — defensive
        logger.debug("sync metrics record failed: %s", exc)


def write_sync_job_run(
    engine: str,
    status: str,
    offset_ms: int | None,
    duration_ms: int,
    subtitle_path: str,
    video_path: str,
    reason: str = "",
) -> None:
    """Insert one audit row into sync_job_runs + bump Prometheus metrics. Never raises."""
    _record_metrics(engine, status, offset_ms, duration_ms)
    try:
        from db.models.core import SyncJobRun
        from extensions import db

        row = SyncJobRun(
            engine=engine,
            status=status,
            offset_ms=offset_ms,
            duration_ms=duration_ms,
            subtitle_path=subtitle_path,
            video_path=video_path,
            reason=(reason[:64] if reason else None),
            created_at=datetime.now(UTC),
        )
        db.session.add(row)
        db.session.commit()
    except Exception as exc:  # pragma: no cover — defensive
        logger.warning("sync_job_runs audit write failed: %s", exc)
