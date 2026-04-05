"""Activity log route — GET /api/v1/activity."""

import logging

from flask import Blueprint, jsonify, request

from db.activity import get_activity

bp = Blueprint("activity", __name__, url_prefix="/api/v1")
logger = logging.getLogger(__name__)

_MAX_PER_PAGE = 200


@bp.route("/activity", methods=["GET"])
def list_activity():
    """Return paginated unified activity log."""
    try:
        page = max(1, int(request.args.get("page", 1)))
        per_page = min(_MAX_PER_PAGE, max(1, int(request.args.get("per_page", 50))))
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid pagination parameters"}), 400

    event_type = request.args.get("type") or None
    result = get_activity(page=page, per_page=per_page, event_type=event_type)
    return jsonify(result), 200
