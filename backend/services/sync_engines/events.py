"""Audit-row writer for sync_job_runs (Plan B7). Never raises."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

logger = logging.getLogger(__name__)


def write_sync_job_run(
    engine: str,
    status: str,
    offset_ms: int | None,
    duration_ms: int,
    subtitle_path: str,
    video_path: str,
    reason: str = "",
) -> None:
    """Insert one audit row into sync_job_runs. Never raises."""
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
