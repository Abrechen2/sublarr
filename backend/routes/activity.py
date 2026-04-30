"""Activity log route — GET /api/v1/activity."""

import logging

from flask import Blueprint, jsonify, request

from db.activity import get_activity

bp = Blueprint("activity", __name__, url_prefix="/api/v1")
logger = logging.getLogger(__name__)

_MAX_PER_PAGE = 200
# Mirror db.models.activity event constants. ``search`` was missing here
# even though wanted_search_runner.log_activity(EVENT_SEARCH, ...) writes
# rows of that type — users could see them in the unfiltered list but
# the API returned 400 on ?type=search.
VALID_EVENT_TYPES = frozenset({"download", "extract", "delete", "scan", "search"})


@bp.route("/activity", methods=["GET"])
def list_activity():
    """Return paginated unified activity log."""
    try:
        page = max(1, int(request.args.get("page", 1)))
        per_page = min(_MAX_PER_PAGE, max(1, int(request.args.get("per_page", 50))))
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid pagination parameters"}), 400

    event_type = request.args.get("type") or None
    if event_type and event_type not in VALID_EVENT_TYPES:
        return jsonify({"error": "Invalid event type"}), 400
    result = get_activity(page=page, per_page=per_page, event_type=event_type)
    return jsonify(result), 200
