"""Audit-row writer for post_processing_runs (Plan B6)."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

logger = logging.getLogger(__name__)


def write_post_processing_run(
    trigger: str,
    op_results: list,
    duration_ms: int,
) -> None:
    """Insert one audit row. Never raises — falls back to WARN on DB failure."""
    try:
        from db.models.core import PostProcessingRun
        from extensions import db

        if not op_results or all(r.ok for r in op_results):
            outcome = "ok"
        elif not any(r.ok for r in op_results):
            outcome = "failure"
        else:
            outcome = "partial_failure"

        row = PostProcessingRun(
            trigger=trigger,
            ops_executed={
                "ops": [
                    {
                        "op_id": r.op_id,
                        "ok": r.ok,
                        "duration_ms": r.duration_ms,
                        "message": r.message,
                    }
                    for r in op_results
                ],
            },
            duration_ms=duration_ms,
            outcome=outcome,
            created_at=datetime.now(UTC),
        )
        db.session.add(row)
        db.session.commit()
    except Exception as exc:  # pragma: no cover — defensive
        logger.warning("post_processing audit write failed: %s", exc)
        try:
            from extensions import db

            db.session.rollback()
        except Exception:
            pass
