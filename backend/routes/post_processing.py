"""Plan B6 — post-processing API endpoints.

Exposes:
  GET /api/v1/post-processing/ops       — registered ops with metadata
  GET /api/v1/post-processing/config    — per-trigger op list
  PUT /api/v1/post-processing/config/<trigger> — update trigger's op list
  GET /api/v1/post-processing/ops/<op_id>/config — per-op config schema + values
  PUT /api/v1/post-processing/ops/<op_id>/config — upsert per-op config
  GET /api/v1/post-processing/runs      — recent audit rows
"""

from __future__ import annotations

from flask import Blueprint, jsonify, request

bp = Blueprint("post_processing", __name__, url_prefix="/api/v1/post-processing")

# Sentinel returned for password fields on GET. The PUT endpoint
# treats this exact value as "keep existing" so a round-trip GET-edit-PUT
# doesn't overwrite a real secret with the mask.
_PASSWORD_MASK = "***"


def _find_op_class(op_id: str):
    """Return the registered op class for ``op_id`` or None."""
    import post_processing.ops  # noqa: F401 — triggers @register_op
    from post_processing.base_op import _OP_REGISTRY

    return next((cls for cls in _OP_REGISTRY if cls.op_id == op_id), None)


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


@bp.route("/ops/<op_id>/config", methods=["GET"])
def get_op_config_route(op_id: str):
    """Return schema + stored values for one op.

    Password fields are masked (``"***"``) in ``values`` to avoid leaking
    stored secrets to anyone with UI access; the PUT endpoint preserves
    existing values when the caller sends the mask back unchanged.
    """
    from post_processing.config_store import get_op_config

    cls = _find_op_class(op_id)
    if cls is None:
        return jsonify({"error": "unknown op"}), 404

    schema = cls.config_schema
    stored = get_op_config(op_id)

    values: dict[str, str] = {}
    for entry in schema:
        field = entry["key"]
        raw = stored.get(field, entry.get("default", ""))
        if entry.get("type") == "password" and raw:
            values[field] = _PASSWORD_MASK
        else:
            values[field] = raw

    return jsonify(
        {
            "op_id": op_id,
            "schema": schema,
            "values": values,
        }
    )


@bp.route("/ops/<op_id>/config", methods=["PUT"])
def update_op_config_route(op_id: str):
    """Upsert per-op config.

    Body: ``{"values": {"field": "value", ...}}``. Validates each field
    against the op's ``config_schema``:
      - only keys declared in the schema are accepted
      - ``required=True`` fields must be non-empty strings
      - ``type=number`` fields must parse as int
    Password fields submitted as ``"***"`` are silently dropped so a
    GET-edit-PUT round-trip does not overwrite an existing secret.
    """
    from post_processing.config_store import set_op_config

    cls = _find_op_class(op_id)
    if cls is None:
        return jsonify({"error": "unknown op"}), 404

    data = request.get_json(silent=True) or {}
    values_in = data.get("values")
    if not isinstance(values_in, dict):
        return jsonify({"error": "values must be an object"}), 400

    schema = cls.config_schema
    schema_by_key = {entry["key"]: entry for entry in schema}

    to_write: dict[str, str] = {}
    errors: list[str] = []

    # Reject unknown keys
    for key in values_in:
        if key not in schema_by_key:
            errors.append(f"unknown field: {key}")
    if errors:
        return jsonify({"error": "; ".join(errors)}), 400

    for field_key, entry in schema_by_key.items():
        raw = values_in.get(field_key)
        # Password-mask sentinel → keep existing stored value (don't overwrite).
        if entry.get("type") == "password" and raw == _PASSWORD_MASK:
            continue

        # Missing key on body: only fail if required AND no existing value.
        if raw is None:
            if entry.get("required", False):
                from post_processing.config_store import get_op_config

                if not get_op_config(op_id).get(field_key):
                    errors.append(f"{field_key} is required")
            continue

        if not isinstance(raw, (str, int, float)):
            errors.append(f"{field_key} must be a primitive")
            continue

        value_str = str(raw).strip() if isinstance(raw, str) else str(raw)

        if entry.get("required", False) and not value_str:
            errors.append(f"{field_key} is required")
            continue

        if entry.get("type") == "number" and value_str:
            try:
                int(value_str)
            except ValueError:
                errors.append(f"{field_key} must be a number")
                continue

        to_write[field_key] = value_str

    if errors:
        return jsonify({"error": "; ".join(errors)}), 400

    if to_write:
        set_op_config(op_id, to_write)

    return jsonify({"op_id": op_id, "saved": sorted(to_write.keys())})


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
