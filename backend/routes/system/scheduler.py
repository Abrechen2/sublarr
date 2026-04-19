"""Scheduler admin API — GET endpoints (Phase 2 read-only).

Phase 3 adds POST/PATCH write endpoints to this same blueprint.
"""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime, timedelta

import sqlalchemy as sa
from flask import Blueprint, current_app, jsonify, request

from db.models.scheduler import JobRun
from extensions import db
from routes.system.scheduler_serializers import serialize_trigger

logger = logging.getLogger(__name__)

bp = Blueprint("scheduler_admin", __name__, url_prefix="/api/v1/scheduler")

_STATS_CACHE: dict[str, tuple[float, dict]] = {}
_STATS_CACHE_TTL_S = 10.0


def _get_scheduler():
    return current_app.extensions.get("scheduler")


def _scheduler_down_response():
    return (
        jsonify(
            {
                "error": "Scheduler is not running on this replica.",
                "error_type": "SchedulerDownError",
            }
        ),
        503,
    )


def _stats_7d_all() -> dict[str, dict[str, int]]:
    now = time.monotonic()
    cached = _STATS_CACHE.get("all")
    if cached and cached[0] > now:
        return cached[1]

    cutoff = datetime.now(UTC) - timedelta(days=7)
    rows = db.session.execute(
        sa.select(JobRun.job_id, JobRun.status, sa.func.count())
        .where(JobRun.started_at >= cutoff)
        .group_by(JobRun.job_id, JobRun.status)
    ).all()

    result: dict[str, dict[str, int]] = {}
    for job_id, status, count in rows:
        result.setdefault(
            job_id,
            {"ok": 0, "error": 0, "timeout": 0, "missed": 0, "skipped_overlap": 0},
        )
        result[job_id][status] = count

    _STATS_CACHE["all"] = (now + _STATS_CACHE_TTL_S, result)
    return result


def _last_run_for(job_id: str) -> dict | None:
    row = db.session.execute(
        sa.select(JobRun).where(JobRun.job_id == job_id).order_by(JobRun.started_at.desc()).limit(1)
    ).scalar_one_or_none()
    if row is None:
        return None
    return {
        "started_at": row.started_at.isoformat() if row.started_at else None,
        "finished_at": row.finished_at.isoformat() if row.finished_at else None,
        "duration_ms": row.duration_ms,
        "status": row.status,
        "error_type": row.error_type,
        "error_msg": row.error_msg,
    }


def _job_to_dict(scheduler, spec_id: str) -> dict:
    aps_job = scheduler._scheduler.get_job(spec_id)
    spec = scheduler._spec_by_id(spec_id)
    stats = _stats_7d_all().get(
        spec_id,
        {"ok": 0, "error": 0, "timeout": 0, "missed": 0, "skipped_overlap": 0},
    )
    next_run = None
    paused = False
    if aps_job is not None:
        paused = aps_job.next_run_time is None
        next_run = aps_job.next_run_time.isoformat() if aps_job.next_run_time else None
    return {
        "id": spec.id,
        "description": spec.description,
        "owner_module": spec.owner_module,
        "trigger": serialize_trigger(aps_job.trigger if aps_job else spec.default_trigger),
        "trigger_is_default": scheduler.trigger_is_default(spec.id),
        "paused": paused,
        "next_run_time": next_run,
        "last_run": _last_run_for(spec_id),
        "stats_7d": stats,
    }


@bp.route("/jobs", methods=["GET"])
def list_jobs():
    s = _get_scheduler()
    if s is None:
        return _scheduler_down_response()
    jobs = [_job_to_dict(s, jid) for jid in sorted(s._registered_ids)]
    return jsonify({"jobs": jobs}), 200


@bp.route("/jobs/<job_id>", methods=["GET"])
def get_job(job_id: str):
    s = _get_scheduler()
    if s is None:
        return _scheduler_down_response()
    if job_id not in s._registered_ids:
        return (
            jsonify(
                {
                    "error": f"Job {job_id!r} not found",
                    "error_type": "NotFoundError",
                }
            ),
            404,
        )
    return jsonify(_job_to_dict(s, job_id)), 200


@bp.route("/jobs/<job_id>/runs", methods=["GET"])
def list_runs(job_id: str):
    s = _get_scheduler()
    if s is None:
        return _scheduler_down_response()
    if job_id not in s._registered_ids:
        return (
            jsonify(
                {
                    "error": f"Job {job_id!r} not found",
                    "error_type": "NotFoundError",
                }
            ),
            404,
        )

    try:
        limit = min(max(int(request.args.get("limit", "50")), 1), 500)
        offset = max(int(request.args.get("offset", "0")), 0)
    except ValueError:
        return (
            jsonify(
                {
                    "error": "limit/offset must be integers",
                    "error_type": "ValueError",
                }
            ),
            400,
        )

    status_filter = request.args.get("status")

    q = sa.select(JobRun).where(JobRun.job_id == job_id)
    count_q = sa.select(sa.func.count()).select_from(JobRun).where(JobRun.job_id == job_id)
    if status_filter:
        q = q.where(JobRun.status == status_filter)
        count_q = count_q.where(JobRun.status == status_filter)

    total = db.session.execute(count_q).scalar_one()
    rows = (
        db.session.execute(q.order_by(JobRun.started_at.desc()).limit(limit).offset(offset))
        .scalars()
        .all()
    )

    return (
        jsonify(
            {
                "total": total,
                "limit": limit,
                "offset": offset,
                "runs": [
                    {
                        "id": r.id,
                        "started_at": r.started_at.isoformat() if r.started_at else None,
                        "finished_at": r.finished_at.isoformat() if r.finished_at else None,
                        "duration_ms": r.duration_ms,
                        "status": r.status,
                        "triggered_by": r.triggered_by,
                        "error_type": r.error_type,
                        "error_msg": r.error_msg,
                    }
                    for r in rows
                ],
            }
        ),
        200,
    )
