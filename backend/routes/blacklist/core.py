"""Blacklist CRUD routes — /blacklist (GET, POST, DELETE), /blacklist/<id>, /blacklist/count."""

import logging

from flask import jsonify, request

from routes.blacklist import bp

logger = logging.getLogger(__name__)


@bp.route("/blacklist", methods=["GET"])
def list_blacklist():
    """Get paginated blacklist entries.
    ---
    get:
      security:
        - apiKeyAuth: []
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
      security:
        - apiKeyAuth: []
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
                file_hash:
                  type: string
                  description: Optional SHA-256 or OpenSubtitles hash (max 64 chars). When set, suppresses retries for any subtitle with the same hash from this provider.
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
                  file_hash:
                    type: string
                    nullable: true
        400:
          description: Missing provider_name or subtitle_id
    """
    from db.blacklist import add_blacklist_entry

    data = request.get_json() or {}
    provider_name = data.get("provider_name", "")
    subtitle_id = data.get("subtitle_id", "")
    file_hash = data.get("file_hash") or None

    if not provider_name or not subtitle_id:
        return jsonify({"error": "provider_name and subtitle_id are required"}), 400

    entry_id = add_blacklist_entry(
        provider_name=provider_name,
        subtitle_id=subtitle_id,
        language=data.get("language", ""),
        file_path=data.get("file_path", ""),
        title=data.get("title", ""),
        reason=data.get("reason", ""),
        file_hash=file_hash,
    )

    return jsonify({"status": "added", "id": entry_id, "file_hash": file_hash}), 201


@bp.route("/blacklist/<int:entry_id>", methods=["DELETE"])
def delete_blacklist_entry(entry_id):
    """Remove a single blacklist entry.
    ---
    delete:
      security:
        - apiKeyAuth: []
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
      security:
        - apiKeyAuth: []
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
      security:
        - apiKeyAuth: []
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
