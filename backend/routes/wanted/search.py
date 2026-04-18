"""Wanted per-item search + batch-search routes.

Scanner-triggered routes (search-all, search-upgrades) and bulk actions
(batch-action) live in routes/wanted/bulk_actions.py (B1Ws split, 2026-04-18).
"""

import logging
import threading

from flask import current_app, jsonify, request

from events import emit_event
from extensions import socketio
from routes.batch_state import wanted_batch_lock, wanted_batch_state
from routes.wanted import bp

logger = logging.getLogger(__name__)


@bp.route("/wanted/<int:item_id>/search", methods=["POST"])
def search_wanted(item_id):
    """Search providers for a specific wanted item.
    ---
    post:
      tags:
        - Wanted
      summary: Search for wanted item
      description: Searches all enabled subtitle providers for a specific wanted item and returns matching results.
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
          description: Search results
          content:
            application/json:
              schema:
                type: object
                additionalProperties: true
        400:
          description: Search error
        404:
          description: Item not found
    """
    from db.wanted import get_wanted_item
    from wanted_search import search_wanted_item

    item = get_wanted_item(item_id)
    if not item:
        return jsonify({"error": "Item not found"}), 404

    app = current_app._get_current_object()

    def _run():
        with app.app_context():
            try:
                result = search_wanted_item(item_id)
                emit_event("wanted_item_searched", result)
            except Exception as e:
                logger.exception("Wanted search failed for item_id=%s", item_id)
                emit_event("wanted_item_searched", {"wanted_id": item_id, "error": str(e)})

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()

    return jsonify({"status": "searching", "wanted_id": item_id}), 202


@bp.route("/wanted/<int:item_id>/process", methods=["POST"])
def process_wanted(item_id):
    """Download + translate for a single wanted item (async).
    ---
    post:
      tags:
        - Wanted
      summary: Process wanted item
      description: Downloads the best matching subtitle and translates it for the specified wanted item. Runs asynchronously.
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
        202:
          description: Processing started
          content:
            application/json:
              schema:
                type: object
                properties:
                  status:
                    type: string
                  wanted_id:
                    type: integer
        404:
          description: Item not found
    """
    from db.wanted import get_wanted_item
    from wanted_search import process_wanted_item

    item = get_wanted_item(item_id)
    if not item:
        return jsonify({"error": "Item not found"}), 404

    app = current_app._get_current_object()

    def _run():
        with app.app_context():
            try:
                result = process_wanted_item(item_id)
                emit_event("wanted_item_processed", result)
                if result.get("upgraded"):
                    emit_event(
                        "upgrade_complete",
                        {
                            "file_path": result.get("output_path"),
                            "provider": result.get("provider"),
                        },
                    )
            except Exception as e:
                logger.exception("Wanted process failed for item_id=%s", item_id)
                emit_event("wanted_item_processed", {"wanted_id": item_id, "error": str(e)})

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()

    return jsonify({"status": "processing", "wanted_id": item_id}), 202


@bp.route("/wanted/batch-search", methods=["POST"])
def wanted_batch_search():
    """Process all wanted items (async with progress tracking).
    ---
    post:
      tags:
        - Wanted
      summary: Batch search wanted items
      description: >
        Processes all wanted items (or specified IDs) asynchronously.
        Progress is emitted via WebSocket (wanted_batch_progress event).
      security:
        - apiKeyAuth: []
      requestBody:
        content:
          application/json:
            schema:
              type: object
              properties:
                item_ids:
                  type: array
                  items:
                    type: integer
                  description: Optional list of specific item IDs to process. Omit for all.
      responses:
        202:
          description: Batch search started
          content:
            application/json:
              schema:
                type: object
                properties:
                  status:
                    type: string
                  total_items:
                    type: integer
        409:
          description: Batch already running
    """
    from db.wanted import get_wanted_count
    from wanted_search import process_wanted_batch

    with wanted_batch_lock:
        if wanted_batch_state["running"]:
            return jsonify({"error": "Wanted batch already running"}), 409

        data = request.get_json(silent=True) or {}
        item_ids = data.get("item_ids")
        series_id = data.get("series_id")

        # Reject explicitly provided empty item_ids list
        if isinstance(item_ids, list) and len(item_ids) == 0:
            return jsonify({"error": "No items provided"}), 400

        # If series_id provided, resolve to item IDs for that series
        if series_id and not item_ids:
            from db.wanted import get_wanted_for_series

            series_items = get_wanted_for_series(series_id)
            item_ids = [
                item["id"] for item in series_items if item.get("status") in ("wanted", "failed")
            ]
            # No searchable items for this series — return early instead of falling
            # through to "search all wanted items globally".
            if not item_ids:
                return jsonify({"status": "no_items", "total_items": 0}), 200

        # If series_ids (plural) provided, resolve to item IDs across all listed series
        series_ids = data.get("series_ids", [])
        if isinstance(series_ids, list) and len(series_ids) == 0 and "series_ids" in data:
            return jsonify({"error": "No items provided"}), 400
        if series_ids and not item_ids:
            from db.wanted import get_wanted_for_series

            collected: list[int] = []
            for sid in series_ids:
                series_items = get_wanted_for_series(sid)
                collected.extend(
                    item["id"]
                    for item in series_items
                    if item.get("status") in ("wanted", "failed")
                )
            if not collected:
                return jsonify({"status": "no_items", "total_items": 0}), 200
            item_ids = collected

        # Determine total count upfront — inside lock to prevent TOCTOU
        if item_ids:
            total = len(item_ids)
        else:
            total = get_wanted_count(status="wanted")

        wanted_batch_state.update(
            {
                "running": True,
                "total": total,
                "processed": 0,
                "found": 0,
                "failed": 0,
                "skipped": 0,
                "current_item": None,
            }
        )

    _app = current_app._get_current_object()

    def _run_batch():
        with _app.app_context():
            try:
                for progress in process_wanted_batch(item_ids, app=_app):
                    with wanted_batch_lock:
                        wanted_batch_state["processed"] = progress["processed"]
                        wanted_batch_state["found"] = progress["found"]
                        wanted_batch_state["failed"] = progress["failed"]
                        wanted_batch_state["skipped"] = progress["skipped"]
                        wanted_batch_state["current_item"] = progress["current_item"]

                    socketio.emit(
                        "wanted_batch_progress",
                        {
                            "processed": progress["processed"],
                            "total": progress["total"],
                            "found": progress["found"],
                            "failed": progress["failed"],
                            "current_item": progress["current_item"],
                        },
                    )
            finally:
                with wanted_batch_lock:
                    snapshot = dict(wanted_batch_state)
                    wanted_batch_state["running"] = False
                    wanted_batch_state["current_item"] = None

                emit_event("batch_complete", snapshot)

                try:
                    from notifier import send_notification

                    send_notification(
                        title="Sublarr: Wanted Batch Complete",
                        body=f"Wanted batch finished: {snapshot.get('found', 0)} found, {snapshot.get('failed', 0)} failed",
                        event_type="batch_complete",
                    )
                except Exception as exc:
                    logger.warning("Notification send failed after wanted batch search: %s", exc)

    thread = threading.Thread(target=_run_batch, daemon=True)
    thread.start()

    return jsonify({"status": "started", "total_items": total}), 202


@bp.route("/wanted/batch-search/status", methods=["GET"])
def wanted_batch_status():
    """Get wanted batch search progress.
    ---
    get:
      tags:
        - Wanted
      summary: Get batch search status
      description: Returns the current wanted batch search progress and state.
      security:
        - apiKeyAuth: []
      responses:
        200:
          description: Batch state
          content:
            application/json:
              schema:
                type: object
                properties:
                  running:
                    type: boolean
                  total:
                    type: integer
                  processed:
                    type: integer
                  found:
                    type: integer
                  failed:
                    type: integer
                  skipped:
                    type: integer
                  current_item:
                    type: string
                    nullable: true
    """
    with wanted_batch_lock:
        return jsonify(dict(wanted_batch_state))
