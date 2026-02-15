"""Blacklist and history routes — /blacklist/*, /history/*."""

import logging
from flask import Blueprint, request, jsonify

bp = Blueprint("blacklist", __name__, url_prefix="/api/v1")
logger = logging.getLogger(__name__)


@bp.route("/blacklist", methods=["GET"])
def list_blacklist():
    """Get paginated blacklist entries."""
    from db.blacklist import get_blacklist_entries

    page = request.args.get("page", 1, type=int)
    per_page = min(request.args.get("per_page", 50, type=int), 200)
    result = get_blacklist_entries(page=page, per_page=per_page)
    return jsonify(result)


@bp.route("/blacklist", methods=["POST"])
def add_to_blacklist():
    """Add a subtitle to the blacklist."""
    from db.blacklist import add_blacklist_entry

    data = request.get_json() or {}
    provider_name = data.get("provider_name", "")
    subtitle_id = data.get("subtitle_id", "")

    if not provider_name or not subtitle_id:
        return jsonify({"error": "provider_name and subtitle_id are required"}), 400

    entry_id = add_blacklist_entry(
        provider_name=provider_name,
        subtitle_id=subtitle_id,
        language=data.get("language", ""),
        file_path=data.get("file_path", ""),
        title=data.get("title", ""),
        reason=data.get("reason", ""),
    )

    return jsonify({"status": "added", "id": entry_id}), 201


@bp.route("/blacklist/<int:entry_id>", methods=["DELETE"])
def delete_blacklist_entry(entry_id):
    """Remove a single blacklist entry."""
    from db.blacklist import remove_blacklist_entry

    deleted = remove_blacklist_entry(entry_id)
    if not deleted:
        return jsonify({"error": "Entry not found"}), 404
    return jsonify({"status": "deleted", "id": entry_id})


@bp.route("/blacklist", methods=["DELETE"])
def clear_all_blacklist():
    """Clear all blacklist entries. Requires ?confirm=true."""
    from db.blacklist import clear_blacklist

    confirm = request.args.get("confirm", "").lower()
    if confirm != "true":
        return jsonify({"error": "Add ?confirm=true to clear all entries"}), 400

    count = clear_blacklist()
    return jsonify({"status": "cleared", "count": count})


@bp.route("/blacklist/count", methods=["GET"])
def blacklist_count():
    """Get blacklist entry count."""
    from db.blacklist import get_blacklist_count
    return jsonify({"count": get_blacklist_count()})


# ─── History Endpoints ───────────────────────────────────────────────────────


@bp.route("/history", methods=["GET"])
def list_history():
    """Get paginated download history."""
    from db.library import get_download_history

    page = request.args.get("page", 1, type=int)
    per_page = min(request.args.get("per_page", 50, type=int), 200)
    provider = request.args.get("provider")
    language = request.args.get("language")

    result = get_download_history(
        page=page, per_page=per_page,
        provider=provider, language=language,
    )
    return jsonify(result)


@bp.route("/history/stats", methods=["GET"])
def history_stats():
    """Get aggregated download statistics."""
    from db.library import get_download_stats
    return jsonify(get_download_stats())
