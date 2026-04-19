"""Translation concurrency admin endpoints."""

from __future__ import annotations

import logging

from flask import Blueprint, jsonify, request

from routes.translation.events import _audit_log
from translation.concurrency import get_concurrency

logger = logging.getLogger(__name__)

bp = Blueprint(
    "translation_concurrency_admin",
    __name__,
    url_prefix="/api/v1/translation",
)


@bp.route("/concurrency", methods=["GET"])
def list_concurrency():
    c = get_concurrency()
    backends = [{"backend": name, "limit": c.get_limit(name)} for name in sorted(c._limits.keys())]
    return jsonify({"backends": backends}), 200


@bp.route("/concurrency/<backend>", methods=["PATCH"])
def set_concurrency(backend: str):
    body = request.get_json(silent=True) or {}
    limit = body.get("limit")
    if not isinstance(limit, int) or limit < 1 or limit > 50:
        return (
            jsonify(
                {
                    "error": "limit must be int in [1, 50]",
                    "error_type": "ValidationError",
                }
            ),
            400,
        )

    c = get_concurrency()
    if c.get_limit(backend) == 0:  # not registered
        return (
            jsonify(
                {
                    "error": f"backend {backend!r} not registered",
                    "error_type": "NotFoundError",
                }
            ),
            404,
        )

    c.set_limit(backend, limit)

    # Persist to config_entries so it survives restart
    try:
        from db.config import save_config_entry

        save_config_entry(f"translation_concurrency_{backend}", str(limit))
    except Exception:
        logger.warning("failed to persist concurrency limit for %s", backend, exc_info=True)

    _audit_log("set-concurrency", backend=backend, limit=limit)
    return jsonify({"backend": backend, "limit": limit}), 200
