"""Wanted batch-extract route — extracts embedded subtitles for many items at once."""

import logging
import threading

from flask import current_app, jsonify, request

from events import emit_event
from extensions import socketio
from routes.batch_state import _batch_extract_lock, _batch_extract_state
from routes.wanted import bp

logger = logging.getLogger(__name__)


def _run_batch_extract(item_ids, auto_translate, app):
    """Background thread: extract embedded subs for each item, emit progress events."""
    # Function-local import so tests that patch
    # ``routes.wanted.extract._extract_embedded_sub`` are observed here too.
    from db.wanted import get_wanted_item
    from routes.wanted import extract as _extract_mod

    with _batch_extract_lock:
        _batch_extract_state.update(
            {
                "running": True,
                "total": len(item_ids),
                "processed": 0,
                "succeeded": 0,
                "failed": 0,
                "skipped": 0,
                "current_item": None,
            }
        )

    try:
        with app.app_context():
            for idx, item_id in enumerate(item_ids):
                item = get_wanted_item(item_id)
                with _batch_extract_lock:
                    _batch_extract_state["current_item"] = (item or {}).get(
                        "title", f"Item {item_id}"
                    )
                try:
                    _extract_mod._extract_embedded_sub(
                        item_id, (item or {}).get("file_path", ""), auto_translate
                    )
                    with _batch_extract_lock:
                        _batch_extract_state["succeeded"] += 1
                except (LookupError, FileNotFoundError, ValueError) as exc:
                    # Permanent failure: no subtitle stream found or file missing.
                    # Clear the embedded_sub flag so the item falls through to provider search.
                    logger.warning(
                        "[batch-extract] item %d failed (clearing embedded flag): %s", item_id, exc
                    )
                    try:
                        from db.wanted import update_existing_sub, update_wanted_status

                        update_existing_sub(item_id, "")
                        update_wanted_status(item_id, "wanted")
                    except Exception as db_exc:
                        logger.debug(
                            "[batch-extract] DB update failed for item %d: %s", item_id, db_exc
                        )
                    with _batch_extract_lock:
                        _batch_extract_state["failed"] += 1
                except Exception as exc:
                    logger.warning("[batch-extract] item %d failed: %s", item_id, exc)
                    with _batch_extract_lock:
                        _batch_extract_state["failed"] += 1
                with _batch_extract_lock:
                    _batch_extract_state["processed"] = idx + 1
                    snapshot = dict(_batch_extract_state)
                socketio.emit("batch_extract_progress", snapshot)
    finally:
        try:
            from extensions import db as _db

            _db.session.remove()
        except Exception:
            pass
        with _batch_extract_lock:
            _batch_extract_state["running"] = False
            snapshot = dict(_batch_extract_state)
        emit_event("batch_extract_completed", snapshot)


@bp.route("/wanted/batch-extract", methods=["POST"])
def batch_extract():
    """Extract embedded subtitles for multiple wanted items.
    ---
    post:
      tags:
        - Wanted
      summary: Batch extract embedded subtitles
      description: >
        Extracts embedded subtitle streams from MKV/MP4 containers for multiple
        wanted items. Per-item errors do not abort the batch.
      security:
        - apiKeyAuth: []
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required: [item_ids]
              properties:
                item_ids:
                  type: array
                  items:
                    type: integer
                  description: List of wanted item IDs
                auto_translate:
                  type: boolean
                  default: false
                  description: Trigger translation after extraction for SRT streams
      responses:
        200:
          description: Batch extraction completed (partial success possible)
          content:
            application/json:
              schema:
                type: object
                properties:
                  succeeded:
                    type: integer
                  failed:
                    type: integer
                  results:
                    type: array
                    items:
                      type: object
        400:
          description: item_ids missing or empty
    """
    from db.wanted import get_wanted_items

    data = request.get_json(force=True, silent=True) or {}
    item_ids = data.get("item_ids", [])
    series_id = data.get("series_id")
    auto_translate = bool(data.get("auto_translate", False))

    # Allow caller to pass series_id to extract all wanted items for that series
    if not item_ids and series_id:
        page = get_wanted_items(page=1, per_page=500, series_id=int(series_id))
        item_ids = [it["id"] for it in page.get("data", [])]

    # Allow empty body to extract all wanted items with missing or embedded subtitles.
    # Include items without any sub AND items probed as embedded_ass/embedded_srt.
    # Exclude items that already have a sidecar (existing_sub = 'ass' or 'srt').
    if not item_ids and not series_id:
        page = get_wanted_items(page=1, per_page=2000)
        item_ids = [
            it["id"]
            for it in page.get("data", [])
            if it.get("existing_sub") in ("embedded_ass", "embedded_srt")
            or not it.get("existing_sub")
        ]

    if not item_ids:
        return jsonify({"error": "No eligible items found", "status": "nothing_to_do"}), 200

    with _batch_extract_lock:
        if _batch_extract_state["running"]:
            return jsonify({"error": "Batch extraction already running"}), 409

    app = current_app._get_current_object()
    threading.Thread(
        target=_run_batch_extract,
        args=(item_ids, auto_translate, app),
        daemon=True,
    ).start()
    return jsonify({"status": "started", "total_items": len(item_ids)}), 202


@bp.route("/wanted/batch-extract/status", methods=["GET"])
def batch_extract_status():
    """Get current batch-extract progress.
    ---
    get:
      tags:
        - Wanted
      summary: Batch extract status
      description: Returns current state of the background batch-extract operation.
      security:
        - apiKeyAuth: []
      responses:
        200:
          description: Current batch-extract state
    """
    with _batch_extract_lock:
        return jsonify(dict(_batch_extract_state))
