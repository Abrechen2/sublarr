"""Wanted bulk-action routes — search-all, search-upgrades, batch-action."""

import logging
import threading

from flask import jsonify, request

from extensions import socketio
from routes.wanted import bp

logger = logging.getLogger(__name__)


@bp.route("/wanted/search-all", methods=["POST"])
def wanted_search_all():
    """Trigger a search-all for wanted items (provider search for all pending items).
    ---
    post:
      tags:
        - Wanted
      summary: Search all wanted items
      description: Triggers provider search for all pending wanted items. Progress emitted via WebSocket.
      security:
        - apiKeyAuth: []
      responses:
        202:
          description: Search started
          content:
            application/json:
              schema:
                type: object
                properties:
                  status:
                    type: string
        409:
          description: Search already running
    """
    from services.wanted_scanner import get_scanner

    scanner = get_scanner()
    if scanner.is_searching:
        return jsonify({"error": "Search already running"}), 409

    def _run_search():
        scanner._run_search_with_context(socketio=socketio)

    thread = threading.Thread(target=_run_search, daemon=True)
    thread.start()

    return jsonify({"status": "search_started"}), 202


@bp.route("/wanted/search-upgrades", methods=["POST"])
def wanted_search_upgrades():
    """Trigger a one-time search for upgrade candidates (regardless of upgrade schedule setting).
    ---
    post:
      tags:
        - Wanted
      summary: One-time upgrade search
      description: >
        Searches all upgrade candidates once, even when upgrade_scan_interval_hours is 0.
        Useful for a manual upgrade run without permanently enabling the upgrade scheduler.
      security:
        - apiKeyAuth: []
      responses:
        202:
          description: Search started
        409:
          description: Search already running
    """
    from services.wanted_scanner import get_scanner

    scanner = get_scanner()
    if scanner.is_searching:
        return jsonify({"error": "Search already running"}), 409

    def _run_search():
        scanner._run_search_with_context(socketio=socketio, include_upgrades=True)

    thread = threading.Thread(target=_run_search, daemon=True)
    thread.start()

    return jsonify({"status": "search_started"}), 202


@bp.route("/wanted/batch-action", methods=["POST"])
def wanted_batch_action():
    """Perform a batch action on multiple wanted items.
    ---
    post:
      tags:
        - Wanted
      summary: Batch action on wanted items
      description: >
        Performs a bulk action (ignore, unignore, blacklist, export) on
        a list of wanted item IDs.
      security:
        - apiKeyAuth: []
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required: [item_ids, action]
              properties:
                item_ids:
                  type: array
                  items:
                    type: integer
                  description: List of wanted item IDs (max 500)
                action:
                  type: string
                  enum: [ignore, unignore, blacklist, export]
                  description: Action to perform
      responses:
        200:
          description: Action completed
          content:
            application/json:
              schema:
                type: object
                properties:
                  success:
                    type: boolean
                  action:
                    type: string
                  affected:
                    type: integer
                  item_ids:
                    type: array
                    items:
                      type: integer
        400:
          description: Invalid input
    """
    from db.repositories.wanted import WantedRepository

    ALLOWED_ACTIONS = {"ignore", "unignore", "blacklist", "export"}

    data = request.get_json() or {}
    item_ids = data.get("item_ids")
    action = data.get("action", "")

    # Validation
    if not item_ids or not isinstance(item_ids, list):
        return jsonify({"error": "item_ids must be a non-empty list of integers"}), 400
    if len(item_ids) > 500:
        return jsonify({"error": "Maximum 500 items per batch action"}), 400
    if not all(isinstance(i, int) for i in item_ids):
        return jsonify({"error": "item_ids must contain only integers"}), 400
    if action not in ALLOWED_ACTIONS:
        return jsonify(
            {"error": f"action must be one of: {', '.join(sorted(ALLOWED_ACTIONS))}"}
        ), 400

    # Export action: return item data without DB changes
    if action == "export":
        items_map = WantedRepository().get_wanted_items_by_ids(item_ids)
        items = [items_map[i] for i in item_ids if i in items_map]
        return jsonify({"success": True, "action": "export", "data": items})

    # Process each item
    affected = 0
    warning = None

    if action == "ignore":
        affected = WantedRepository().update_wanted_status_bulk(item_ids, "ignored")

    elif action == "unignore":
        wr = WantedRepository()
        items_map = wr.get_wanted_items_by_ids(item_ids)
        ignored_ids = [i for i in item_ids if items_map.get(i, {}).get("status") == "ignored"]
        affected = wr.update_wanted_status_bulk(ignored_ids, "wanted") if ignored_ids else 0

    elif action == "blacklist":
        try:
            from db.blacklist import add_blacklist_entry

            wr = WantedRepository()
            items_map = wr.get_wanted_items_by_ids(item_ids)
            for item_id, item in items_map.items():
                add_blacklist_entry(
                    provider_name="manual",
                    subtitle_id=str(item_id),
                    file_path=item.get("file_path", ""),
                    title=item.get("title", ""),
                    reason="batch_blacklist",
                )
            ids_to_ignore = list(items_map.keys())
            affected = (
                wr.update_wanted_status_bulk(ids_to_ignore, "ignored") if ids_to_ignore else 0
            )
        except ImportError:
            # Blacklist module not available -- fall back to ignore
            warning = "Blacklist module not available, items set to ignored instead"
            affected = WantedRepository().update_wanted_status_bulk(item_ids, "ignored")

    result = {
        "success": True,
        "action": action,
        "affected": affected,
        "item_ids": item_ids[:affected] if affected < len(item_ids) else item_ids,
    }
    if warning:
        result["warning"] = warning
    return jsonify(result)
