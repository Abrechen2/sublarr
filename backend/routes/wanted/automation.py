"""Subtitle automation status + run-now API (0.71.0 Phase 7).

Exposes two endpoints under `/api/v1/wanted/automation/`:

- `GET /status` — queue counts + last-run state for the dashboard.
- `POST /run-now` — triggers an immediate drain tick (synchronous for
  small queues, accepts while drain is already running).
"""

from __future__ import annotations

import logging

from flask import jsonify

from config import get_settings
from routes.wanted import bp

logger = logging.getLogger(__name__)


def _is_master_toggle_on() -> bool:
    try:
        return bool(get_settings().subtitle_automation_enabled)
    except Exception:
        logger.debug("automation.status: settings unavailable", exc_info=True)
        return False


@bp.route("/wanted/automation/status", methods=["GET"])
def automation_status():
    """Read-only snapshot for the Subtitle Automation settings page."""
    from db.repositories.subtitle_automation_queue import (
        SubtitleAutomationQueueRepository,
    )

    repo = SubtitleAutomationQueueRepository()
    counts = repo.get_counts()
    queue_size = sum(counts[k] for k in ("pending", "running", "failed"))

    # Last-run fields derive from the most-recent non-pending entry. We keep
    # this a sparse, best-effort view — the scheduler_job_runs table already
    # owns the authoritative execution log, this endpoint exists for the UI.
    last_run_at = None
    last_run_status = None
    last_error = None
    try:
        from db.models.core import SubtitleAutomationQueueEntry
        from extensions import db

        last_row = (
            db.session.query(SubtitleAutomationQueueEntry)
            .filter(
                SubtitleAutomationQueueEntry.last_finished_at.isnot(None)
            )
            .order_by(SubtitleAutomationQueueEntry.last_finished_at.desc())
            .limit(1)
            .one_or_none()
        )
        if last_row is not None:
            last_run_at = (
                last_row.last_finished_at.isoformat()
                if last_row.last_finished_at
                else None
            )
            last_run_status = last_row.state
            last_error = last_row.last_error
    except Exception:
        logger.debug("automation.status: last-run lookup failed", exc_info=True)

    return jsonify(
        {
            "enabled": _is_master_toggle_on(),
            "queue_size": queue_size,
            "queue": counts,
            "last_run_at": last_run_at,
            "last_run_status": last_run_status,
            "last_error": last_error,
        }
    )


@bp.route("/wanted/automation/run-now", methods=["POST"])
def automation_run_now():
    """Kick the drain synchronously. No-op when master toggle is off."""
    if not _is_master_toggle_on():
        return jsonify({"status": "disabled"}), 200

    from services.subtitle_automation_runner import SubtitleAutomationRunner

    runner = SubtitleAutomationRunner()
    processed = 0
    try:
        processed = runner.drain(max_items=25)
    except Exception as exc:
        logger.warning("automation.run_now: drain raised: %s", exc)

    return (
        jsonify({"status": "queued", "processed": processed}),
        202 if processed == 0 else 200,
    )
