"""Plan B7 — sync engines API.

Exposes:
    GET /api/v1/sync/engines  — configured engine chain + availability + sanity threshold
    GET /api/v1/sync/runs     — recent sync_job_runs audit rows
"""

from __future__ import annotations

from flask import Blueprint, jsonify, request

bp = Blueprint("sync_engines", __name__, url_prefix="/api/v1/sync")


@bp.route("/engines", methods=["GET"])
def list_engines():
    from services.sync_engines.orchestrator import get_default_orchestrator

    orch = get_default_orchestrator()
    return jsonify(
        {
            "engines": [
                {
                    "name": e.name,
                    "available": e.is_available(),
                    "timeout_s": e.timeout_s,
                }
                for e in orch.engines
            ],
            "sanity_threshold_ms": orch.sanity_threshold_ms,
        }
    )


@bp.route("/runs", methods=["GET"])
def list_runs():
    from db.models.core import SyncJobRun

    try:
        limit = int(request.args.get("limit", 50))
    except (TypeError, ValueError):
        limit = 50
    limit = max(1, min(limit, 500))

    rows = SyncJobRun.query.order_by(SyncJobRun.id.desc()).limit(limit).all()
    return jsonify(
        {
            "runs": [
                {
                    "id": r.id,
                    "engine": r.engine,
                    "status": r.status,
                    "offset_ms": r.offset_ms,
                    "duration_ms": r.duration_ms,
                    "subtitle_path": r.subtitle_path,
                    "video_path": r.video_path,
                    "reason": r.reason,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                }
                for r in rows
            ]
        }
    )
