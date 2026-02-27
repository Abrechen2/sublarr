"""Blacklist and history routes — /blacklist/*, /history/*."""

import logging

from flask import Blueprint, jsonify, request

bp = Blueprint("blacklist", __name__, url_prefix="/api/v1")
logger = logging.getLogger(__name__)


@bp.route("/blacklist", methods=["GET"])
def list_blacklist():
    """Get paginated blacklist entries.
    ---
    get:
      tags:
        - Blacklist
      summary: List blacklist entries
      description: Returns paginated subtitle blacklist entries. Blacklisted subtitles are excluded from future downloads.
      parameters:
        - in: query
          name: page
          schema:
            type: integer
            default: 1
        - in: query
          name: per_page
          schema:
            type: integer
            default: 50
            maximum: 200
      responses:
        200:
          description: Paginated blacklist
          content:
            application/json:
              schema:
                type: object
                properties:
                  data:
                    type: array
                    items:
                      type: object
                  page:
                    type: integer
                  per_page:
                    type: integer
                  total:
                    type: integer
                  total_pages:
                    type: integer
    """
    from db.blacklist import get_blacklist_entries

    page = request.args.get("page", 1, type=int)
    per_page = min(request.args.get("per_page", 50, type=int), 200)
    result = get_blacklist_entries(page=page, per_page=per_page)
    return jsonify(result)


@bp.route("/blacklist", methods=["POST"])
def add_to_blacklist():
    """Add a subtitle to the blacklist.
    ---
    post:
      tags:
        - Blacklist
      summary: Add subtitle to blacklist
      description: Blacklists a subtitle so it will not be downloaded again.
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required:
                - provider_name
                - subtitle_id
              properties:
                provider_name:
                  type: string
                subtitle_id:
                  type: string
                language:
                  type: string
                file_path:
                  type: string
                title:
                  type: string
                reason:
                  type: string
      responses:
        201:
          description: Entry added
          content:
            application/json:
              schema:
                type: object
                properties:
                  status:
                    type: string
                  id:
                    type: integer
        400:
          description: Missing provider_name or subtitle_id
    """
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
    """Remove a single blacklist entry.
    ---
    delete:
      tags:
        - Blacklist
      summary: Remove blacklist entry
      description: Removes a single entry from the subtitle blacklist by ID.
      parameters:
        - in: path
          name: entry_id
          required: true
          schema:
            type: integer
      responses:
        200:
          description: Entry removed
          content:
            application/json:
              schema:
                type: object
                properties:
                  status:
                    type: string
                  id:
                    type: integer
        404:
          description: Entry not found
    """
    from db.blacklist import remove_blacklist_entry

    deleted = remove_blacklist_entry(entry_id)
    if not deleted:
        return jsonify({"error": "Entry not found"}), 404
    return jsonify({"status": "deleted", "id": entry_id})


@bp.route("/blacklist", methods=["DELETE"])
def clear_all_blacklist():
    """Clear all blacklist entries. Requires ?confirm=true.
    ---
    delete:
      tags:
        - Blacklist
      summary: Clear all blacklist entries
      description: Removes all entries from the blacklist. Requires confirm=true query parameter as a safety measure.
      parameters:
        - in: query
          name: confirm
          required: true
          schema:
            type: string
            enum: ["true"]
          description: Must be "true" to confirm clearing
      responses:
        200:
          description: All entries cleared
          content:
            application/json:
              schema:
                type: object
                properties:
                  status:
                    type: string
                  count:
                    type: integer
        400:
          description: Missing confirm=true parameter
    """
    from db.blacklist import clear_blacklist

    confirm = request.args.get("confirm", "").lower()
    if confirm != "true":
        return jsonify({"error": "Add ?confirm=true to clear all entries"}), 400

    count = clear_blacklist()
    return jsonify({"status": "cleared", "count": count})


@bp.route("/blacklist/count", methods=["GET"])
def blacklist_count():
    """Get blacklist entry count.
    ---
    get:
      tags:
        - Blacklist
      summary: Get blacklist count
      description: Returns the total number of blacklisted subtitles.
      responses:
        200:
          description: Blacklist count
          content:
            application/json:
              schema:
                type: object
                properties:
                  count:
                    type: integer
    """
    from db.blacklist import get_blacklist_count

    return jsonify({"count": get_blacklist_count()})


# ─── History Endpoints ───────────────────────────────────────────────────────


@bp.route("/history", methods=["GET"])
def list_history():
    """Get paginated download history.
    ---
    get:
      tags:
        - Blacklist
      summary: List download history
      description: Returns paginated subtitle download history with optional provider and language filters.
      parameters:
        - in: query
          name: page
          schema:
            type: integer
            default: 1
        - in: query
          name: per_page
          schema:
            type: integer
            default: 50
            maximum: 200
        - in: query
          name: provider
          schema:
            type: string
          description: Filter by provider name
        - in: query
          name: language
          schema:
            type: string
          description: Filter by language code
        - in: query
          name: format
          schema:
            type: string
            enum: [ass, srt]
          description: Filter by subtitle format
        - in: query
          name: score_min
          schema:
            type: integer
          description: Minimum score filter
        - in: query
          name: score_max
          schema:
            type: integer
          description: Maximum score filter
        - in: query
          name: search
          schema:
            type: string
          description: Text search in file_path and provider_name
        - in: query
          name: sort_by
          schema:
            type: string
            default: downloaded_at
            enum: [downloaded_at, score, provider_name, language]
          description: Sort field
        - in: query
          name: sort_dir
          schema:
            type: string
            default: desc
            enum: [asc, desc]
          description: Sort direction
      responses:
        200:
          description: Paginated history
          content:
            application/json:
              schema:
                type: object
                properties:
                  data:
                    type: array
                    items:
                      type: object
                  page:
                    type: integer
                  per_page:
                    type: integer
                  total:
                    type: integer
                  total_pages:
                    type: integer
    """
    from db.library import get_download_history

    page = request.args.get("page", 1, type=int)
    per_page = min(request.args.get("per_page", 50, type=int), 200)
    provider = request.args.get("provider")
    language = request.args.get("language")
    format_filter = request.args.get("format") or None
    score_min = request.args.get("score_min", type=int)
    score_max = request.args.get("score_max", type=int)
    search = request.args.get("search") or None
    sort_by = request.args.get("sort_by", "downloaded_at")
    sort_dir = request.args.get("sort_dir", "desc")

    result = get_download_history(
        page=page,
        per_page=per_page,
        provider=provider,
        language=language,
        format=format_filter,
        score_min=score_min,
        score_max=score_max,
        search=search,
        sort_by=sort_by,
        sort_dir=sort_dir,
    )
    return jsonify(result)


@bp.route("/history/stats", methods=["GET"])
def history_stats():
    """Get aggregated download statistics.
    ---
    get:
      tags:
        - Blacklist
      summary: Get download statistics
      description: Returns aggregated download statistics including totals by provider, format, and language.
      responses:
        200:
          description: Download statistics
          content:
            application/json:
              schema:
                type: object
                properties:
                  total_downloads:
                    type: integer
                  by_provider:
                    type: object
                    additionalProperties:
                      type: integer
                  by_format:
                    type: object
                    additionalProperties:
                      type: integer
                  by_language:
                    type: object
                    additionalProperties:
                      type: integer
    """
    from db.library import get_download_stats

    return jsonify(get_download_stats())
