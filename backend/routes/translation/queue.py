"""Translation queue admin API — GET /queue + POST /cancel."""

from __future__ import annotations

import logging

from flask import Blueprint, jsonify, request

from translation.queue_state import get_queue_state

logger = logging.getLogger(__name__)

bp = Blueprint("translation_queue_admin", __name__, url_prefix="/api/v1/translation")


def _audit_log(action: str, **kwargs) -> None:
    api_key = request.headers.get("X-Api-Key", "")
    fp = api_key[:6] if api_key else "anon"
    extras = " ".join(f"{k}={v}" for k, v in kwargs.items())
    logger.info(
        "translation_admin_action action=%s actor=%s %s",
        action,
        fp,
        extras,
    )


@bp.route("/queue", methods=["GET"])
def queue_snapshot():
    qs = get_queue_state()
    return jsonify(
        {
            "active": qs.active_snapshot(),
            "recent": qs.recent_snapshot(),
        }
    ), 200


@bp.route("/queue/<job_id>/cancel", methods=["POST"])
def cancel_job(job_id: str):
    qs = get_queue_state()
    if qs.is_cancelled(job_id):
        return jsonify(
            {
                "error": f"job {job_id!r} is already cancelled",
                "error_type": "AlreadyCancelledError",
            }
        ), 409
    try:
        qs.cancel(job_id)
    except KeyError:
        return jsonify(
            {
                "error": f"job {job_id!r} not found",
                "error_type": "NotFoundError",
            }
        ), 404
    _audit_log("cancel-job", job_id=job_id)
    return jsonify({"status": "cancelling", "job_id": job_id}), 202
