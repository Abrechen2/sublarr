"""Wanted list/CRUD routes — GET /wanted, summary, refresh, status, delete."""

import logging
import threading

from flask import current_app, jsonify, request

from events import emit_event
from routes.wanted import bp

logger = logging.getLogger(__name__)


@bp.route("/wanted", methods=["GET"])
def list_wanted():
    """Get paginated wanted items.
    ---
    get:
      tags:
        - Wanted
      summary: List wanted items
      description: Returns a paginated list of wanted subtitle items with optional filters for type, status, series, and subtitle type.
      security:
        - apiKeyAuth: []
      parameters:
        - in: query
          name: page
          schema:
            type: integer
            default: 1
          description: Page number
        - in: query
          name: per_page
          schema:
            type: integer
            default: 50
            maximum: 200
          description: Items per page
        - in: query
          name: item_type
          schema:
            type: string
            enum: [episode, movie]
          description: Filter by item type
        - in: query
          name: status
          schema:
            type: string
            enum: [wanted, ignored, failed, found]
          description: Filter by item status
        - in: query
          name: series_id
          schema:
            type: integer
          description: Filter by Sonarr series ID
        - in: query
          name: subtitle_type
          schema:
            type: string
            enum: [full, forced]
          description: Filter by subtitle type
        - in: query
          name: sort_by
          schema:
            type: string
            default: added_at
            enum: [added_at, title, last_search_at, current_score, search_count]
          description: Sort field
        - in: query
          name: sort_dir
          schema:
            type: string
            default: desc
            enum: [asc, desc]
          description: Sort direction
        - in: query
          name: search
          schema:
            type: string
          description: Text search in title and file_path
      responses:
        200:
          description: Paginated wanted items
          content:
            application/json:
              schema:
                type: object
                properties:
                  items:
                    type: array
                    items:
                      type: object
                  total:
                    type: integer
                  page:
                    type: integer
                  per_page:
                    type: integer
    """
    from db.wanted import get_wanted_items

    page = request.args.get("page", 1, type=int)
    per_page = min(request.args.get("per_page", 50, type=int), 200)
    item_type = request.args.get("item_type")
    status_filter = request.args.get("status")
    series_id = request.args.get("series_id", type=int)
    subtitle_type = request.args.get("subtitle_type")
    sort_by = request.args.get("sort_by", "added_at")
    sort_dir = request.args.get("sort_dir", "desc")
    search = request.args.get("search") or None

    VALID_SORT_BY = {"added_at", "title", "last_search_at", "current_score", "search_count"}
    VALID_SORT_DIR = {"asc", "desc"}
    if sort_by and sort_by not in VALID_SORT_BY:
        return jsonify({"error": f"Invalid sort_by value: {sort_by}"}), 400
    if sort_dir and sort_dir not in VALID_SORT_DIR:
        return jsonify({"error": f"Invalid sort_dir value: {sort_dir}"}), 400

    result = get_wanted_items(
        page=page,
        per_page=per_page,
        item_type=item_type,
        status=status_filter,
        series_id=series_id,
        subtitle_type=subtitle_type,
        sort_by=sort_by,
        sort_dir=sort_dir,
        search=search,
    )
    return jsonify(result)


@bp.route("/wanted/summary", methods=["GET"])
def wanted_summary():
    """Get aggregated wanted stats.
    ---
    get:
      tags:
        - Wanted
      summary: Get wanted summary
      description: Returns aggregated wanted statistics including counts by type, status, subtitle type, and scan state.
      security:
        - apiKeyAuth: []
      responses:
        200:
          description: Wanted summary
          content:
            application/json:
              schema:
                type: object
                properties:
                  total:
                    type: integer
                  by_type:
                    type: object
                    additionalProperties:
                      type: integer
                  scan_running:
                    type: boolean
                  last_scan_at:
                    type: string
                    nullable: true
                  by_subtitle_type:
                    type: object
                    additionalProperties:
                      type: integer
    """
    from db.wanted import get_wanted_by_subtitle_type, get_wanted_summary
    from wanted_scanner import get_scanner

    scanner = get_scanner()
    summary = get_wanted_summary()
    summary["scan_running"] = scanner.is_scanning
    summary["last_scan_at"] = scanner.last_scan_at
    summary["scan_progress"] = scanner.scan_progress
    summary["by_subtitle_type"] = get_wanted_by_subtitle_type()
    return jsonify(summary)


@bp.route("/wanted/refresh", methods=["POST"])
def refresh_wanted():
    """Trigger a wanted scan.
    ---
    post:
      tags:
        - Wanted
      summary: Trigger wanted scan
      description: Starts a background wanted scan for all series or a specific series. Results emitted via WebSocket.
      security:
        - apiKeyAuth: []
      requestBody:
        content:
          application/json:
            schema:
              type: object
              properties:
                series_id:
                  type: integer
                  description: Optional Sonarr series ID to scan (omit for full scan)
      responses:
        202:
          description: Scan started
          content:
            application/json:
              schema:
                type: object
                properties:
                  status:
                    type: string
                  series_id:
                    type: integer
                    nullable: true
        409:
          description: Scan already running
    """
    from wanted_scanner import get_scanner

    scanner = get_scanner()
    if scanner.is_scanning:
        return jsonify({"error": "Scan already running"}), 409

    data = request.get_json(silent=True) or {}
    series_id = data.get("series_id")
    app = current_app._get_current_object()

    def _run_scan():
        with app.app_context():
            if series_id:
                result = scanner.scan_series(series_id)
            else:
                result = scanner.scan_all()
            emit_event("wanted_scan_complete", result)

    thread = threading.Thread(target=_run_scan, daemon=True)
    thread.start()

    return jsonify({"status": "scan_started", "series_id": series_id}), 202


@bp.route("/wanted/<int:item_id>/status", methods=["PUT"])
def update_wanted_item_status(item_id):
    """Update a wanted item's status (e.g. ignore/un-ignore).
    ---
    put:
      tags:
        - Wanted
      summary: Update wanted item status
      description: Changes the status of a wanted item (e.g. mark as ignored or re-enable).
      security:
        - apiKeyAuth: []
      parameters:
        - in: path
          name: item_id
          required: true
          schema:
            type: integer
          description: Wanted item ID
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required: [status]
              properties:
                status:
                  type: string
                  enum: [wanted, ignored, failed]
                error:
                  type: string
                  description: Optional error message when setting status to failed
      responses:
        200:
          description: Status updated
          content:
            application/json:
              schema:
                type: object
                properties:
                  status:
                    type: string
                  id:
                    type: integer
                  new_status:
                    type: string
        400:
          description: Invalid status value
        404:
          description: Item not found
    """
    from db.wanted import get_wanted_item, update_wanted_status

    data = request.get_json() or {}
    new_status = data.get("status")

    if new_status not in ("wanted", "ignored", "failed", "extracted"):
        return jsonify({"error": "Invalid status. Use: wanted, ignored, failed, extracted"}), 400

    item = get_wanted_item(item_id)
    if not item:
        return jsonify({"error": "Item not found"}), 404

    update_wanted_status(item_id, new_status, error=data.get("error", ""))
    return jsonify({"status": "updated", "id": item_id, "new_status": new_status})


@bp.route("/wanted/<int:item_id>", methods=["DELETE"])
def delete_wanted(item_id):
    """Remove a wanted item.
    ---
    delete:
      tags:
        - Wanted
      summary: Delete wanted item
      description: Permanently removes a wanted item from the database.
      security:
        - apiKeyAuth: []
      parameters:
        - in: path
          name: item_id
          required: true
          schema:
            type: integer
          description: Wanted item ID
      responses:
        200:
          description: Item deleted
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
          description: Item not found
    """
    from db.wanted import delete_wanted_item, get_wanted_item

    item = get_wanted_item(item_id)
    if not item:
        return jsonify({"error": "Item not found"}), 404

    delete_wanted_item(item_id)
    return jsonify({"status": "deleted", "id": item_id})
