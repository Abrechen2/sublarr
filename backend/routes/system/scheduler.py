"""Scheduler admin API — GET endpoints (Phase 2 read-only).

Phase 3 adds POST/PATCH write endpoints to this same blueprint.
"""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime, timedelta

import sqlalchemy as sa
from flask import Blueprint, current_app, jsonify, request
from pydantic import ValidationError

from db.models.scheduler import JobRun
from extensions import db, limiter
from routes.system.scheduler_serializers import (
    CronTriggerModel,
    IntervalTriggerModel,
    InvalidTriggerError,
    serialize_trigger,
    trigger_model_to_apscheduler,
)
from services.scheduler import OneshotAlreadyPendingError

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


def _scheduler_initialising_response():
    return (
        jsonify(
            {
                "error": "Scheduler is starting up, please retry shortly.",
                "error_type": "SchedulerInitialisingError",
            }
        ),
        503,
    )


def _scheduler_globally_paused(scheduler) -> bool:
    """True iff the underlying APScheduler is in STATE_PAUSED globally.

    During the brief startup window between start_registered_jobs(paused=True)
    and start(), every job's next_run_time is None — using that as the
    individual-pause indicator would 409 a UI pause/resume click incorrectly.
    """
    try:
        from apscheduler.schedulers.base import STATE_PAUSED
    except Exception:
        return False
    aps = getattr(scheduler, "_scheduler", None)
    return aps is not None and getattr(aps, "state", None) == STATE_PAUSED


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


def _audit_log(job_id: str, action: str) -> None:
    """Log admin action for audit trail."""
    api_key = request.headers.get("X-Api-Key", "")
    fp = api_key[:6] if api_key else "anon"
    logger.info(
        "scheduler_admin_action job_id=%s action=%s actor=%s",
        job_id,
        action,
        fp,
    )


def _parse_trigger_model(data: dict):
    t = (data or {}).get("type")
    if t == "interval":
        return IntervalTriggerModel.model_validate(data)
    if t == "cron":
        return CronTriggerModel.model_validate(data)
    raise ValueError(f"unknown trigger type: {t!r}")


@bp.route("/jobs/<job_id>/run-now", methods=["POST"])
@limiter.limit("30 per minute")
def run_now(job_id: str):
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
        oneshot_id = s.run_now(job_id)
    except OneshotAlreadyPendingError as exc:
        return (
            jsonify(
                {
                    "error": str(exc),
                    "error_type": "OneshotAlreadyPendingError",
                }
            ),
            409,
        )
    _audit_log(job_id, "run-now")
    return jsonify({"status": "queued", "oneshot_id": oneshot_id}), 202


@bp.route("/jobs/<job_id>/pause", methods=["POST"])
@limiter.limit("30 per minute")
def pause(job_id: str):
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
    if _scheduler_globally_paused(s):
        return _scheduler_initialising_response()
    job = s._scheduler.get_job(job_id)
    if job is not None and job.next_run_time is None:
        return (
            jsonify(
                {
                    "error": f"{job_id} is already paused",
                    "error_type": "ConflictError",
                }
            ),
            409,
        )
    s.pause_job(job_id)
    _audit_log(job_id, "pause")
    return jsonify({"status": "paused"}), 200


@bp.route("/jobs/<job_id>/resume", methods=["POST"])
@limiter.limit("30 per minute")
def resume(job_id: str):
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
    if _scheduler_globally_paused(s):
        return _scheduler_initialising_response()
    job = s._scheduler.get_job(job_id)
    if job is not None and job.next_run_time is not None:
        return (
            jsonify(
                {
                    "error": f"{job_id} is not paused",
                    "error_type": "ConflictError",
                }
            ),
            409,
        )
    s.resume_job(job_id)
    _audit_log(job_id, "resume")
    return jsonify({"status": "running"}), 200


@bp.route("/jobs/<job_id>", methods=["PATCH"])
@limiter.limit("10 per minute")
def modify(job_id: str):
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
    body = request.get_json(silent=True) or {}
    trigger_payload = body.get("trigger")
    if not isinstance(trigger_payload, dict):
        return (
            jsonify(
                {
                    "error": "body must include {trigger: {...}}",
                    "error_type": "ValidationError",
                }
            ),
            400,
        )
    try:
        model = _parse_trigger_model(trigger_payload)
        aps_trigger = trigger_model_to_apscheduler(model)
    except (ValidationError, ValueError, InvalidTriggerError) as exc:
        return (
            jsonify(
                {
                    "error": str(exc),
                    "error_type": "ValidationError",
                }
            ),
            400,
        )
    s.modify_trigger(job_id, aps_trigger)
    _audit_log(job_id, "patch-trigger")
    return jsonify(_job_to_dict(s, job_id)), 200


@bp.route("/jobs/<job_id>/reset-default", methods=["POST"])
@limiter.limit("10 per minute")
def reset_default(job_id: str):
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
    s.reset_to_default(job_id)
    _audit_log(job_id, "reset-default")
    return jsonify(_job_to_dict(s, job_id)), 200
