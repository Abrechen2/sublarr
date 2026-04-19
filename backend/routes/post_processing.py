"""Plan B6 — post-processing API endpoints.

Exposes:
  GET /api/v1/post-processing/ops       — registered ops with metadata
  GET /api/v1/post-processing/config    — per-trigger op list
  PUT /api/v1/post-processing/config/<trigger> — update trigger's op list
  GET /api/v1/post-processing/runs      — recent audit rows
"""

from __future__ import annotations

from flask import Blueprint, jsonify, request

bp = Blueprint("post_processing", __name__, url_prefix="/api/v1/post-processing")


@bp.route("/ops", methods=["GET"])
def list_ops():
    """Return all registered ops with metadata."""
    # Import triggers decorator registration for every curated op
    import post_processing.ops  # noqa: F401
    from post_processing.base_op import _OP_REGISTRY

    return jsonify(
        {
            "ops": [
                {
                    "op_id": cls.op_id,
                    "label": cls.label,
                    "description": cls.description,
                }
                for cls in _OP_REGISTRY
            ]
        }
    )


@bp.route("/config", methods=["GET"])
def get_config():
    """Return per-trigger op config."""
    from post_processing.config_store import get_trigger_ops

    return jsonify(
        {
            "after_download": get_trigger_ops("after_download"),
            "after_translate": get_trigger_ops("after_translate"),
            "after_sync": get_trigger_ops("after_sync"),
        }
    )


@bp.route("/config/<trigger>", methods=["PUT"])
def update_config(trigger):
    """Update op list for a trigger. Body: ``{"op_ids": ["strip_html", ...]}``."""
    from post_processing.config_store import is_valid_trigger, set_trigger_ops

    if not is_valid_trigger(trigger):
        return jsonify({"error": "unknown trigger"}), 400

    data = request.get_json(silent=True) or {}
    op_ids = data.get("op_ids", [])
    if not isinstance(op_ids, list):
        return jsonify({"error": "op_ids must be a list"}), 400

    set_trigger_ops(trigger, [str(x) for x in op_ids])
    return jsonify({"trigger": trigger, "op_ids": op_ids})


@bp.route("/runs", methods=["GET"])
def list_runs():
    """Return recent post-processing audit rows."""
    from db.models.core import PostProcessingRun

    try:
        limit = min(int(request.args.get("limit", 50)), 500)
    except (TypeError, ValueError):
        limit = 50
    rows = PostProcessingRun.query.order_by(PostProcessingRun.id.desc()).limit(limit).all()
    return jsonify(
        {
            "runs": [
                {
                    "id": r.id,
                    "trigger": r.trigger,
                    "ops_executed": r.ops_executed,
                    "duration_ms": r.duration_ms,
                    "outcome": r.outcome,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                }
                for r in rows
            ]
        }
    )
