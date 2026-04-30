"""Batch translation endpoints — /batch, /batch/status.

Re-translation endpoints (/retranslate/*) live in routes/translate/retranslate.py
(B1Tb split, 2026-04-18).
"""

import logging
import os
import threading

from flask import current_app, jsonify, request

from events import emit_event
from extensions import socketio
from routes.batch_state import batch_lock, batch_state
from routes.translate import bp
from routes.translate._helpers import (
    _is_translation_enabled,
    _send_callback,
    _update_stats,
    _validate_callback_url,
)
from security_utils import is_safe_path

logger = logging.getLogger(__name__)


# ─── Batch Endpoints ─────────────────────────────────────────────────────────


@bp.route("/batch", methods=["POST"])
def batch_start():
    """Start batch processing of a directory.
    ---
    post:
      tags:
        - Translate
      summary: Start batch translation
      description: >
        Scans a directory for media files and translates them asynchronously.
        Supports dry_run mode to preview files. Progress is emitted via WebSocket (batch_progress event).
      security:
        - apiKeyAuth: []
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required: [directory]
              properties:
                directory:
                  type: string
                  description: Directory path to scan for media files
                force:
                  type: boolean
                  default: false
                dry_run:
                  type: boolean
                  default: false
                  description: Preview files without processing
                page:
                  type: integer
                  default: 1
                  description: Page number for dry_run results
                per_page:
                  type: integer
                  default: 100
                  maximum: 500
                callback_url:
                  type: string
                  description: URL for progress callbacks (SSRF-validated)
      responses:
        202:
          description: Batch started
          content:
            application/json:
              schema:
                type: object
                properties:
                  status:
                    type: string
                  total_files:
                    type: integer
        400:
          description: Missing directory or invalid callback URL
        404:
          description: Directory not found
        409:
          description: Batch already running
    """
    from config import get_settings
    from translator import scan_directory, translate_file

    data = request.get_json() or {}
    directory = data.get("directory")
    force = data.get("force", False)
    dry_run = data.get("dry_run", False)
    page = data.get("page", 1)
    per_page = min(data.get("per_page", 100), 500)
    callback_url = data.get("callback_url")

    if not directory:
        return jsonify({"error": "directory is required"}), 400

    if callback_url:
        valid, err = _validate_callback_url(callback_url)
        if not valid:
            return jsonify({"error": f"Invalid callback_url: {err}"}), 400

    if not is_safe_path(directory, get_settings().media_path):
        return jsonify({"error": "directory must be under the configured media_path"}), 403

    if not os.path.isdir(directory):
        return jsonify({"error": f"Directory not found: {directory}"}), 404

    files = scan_directory(directory, force=force)

    if not dry_run and not files:
        return jsonify({"error": "No items provided"}), 400

    if dry_run:
        total_files = len(files)
        total_pages = max(1, (total_files + per_page - 1) // per_page)
        page = max(1, min(page, total_pages))
        start = (page - 1) * per_page
        end = start + per_page
        page_files = files[start:end]

        return jsonify(
            {
                "dry_run": True,
                "files_found": total_files,
                "page": page,
                "per_page": per_page,
                "total_pages": total_pages,
                "files": [
                    {
                        "path": f["path"],
                        "target_status": f["target_status"],
                        "size_mb": round(f["size_mb"], 1),
                    }
                    for f in page_files
                ],
            }
        )

    # Gate AFTER the dry_run branch so users can still preview what would
    # be translated even with the feature disabled, but never start a real
    # batch run that consumes provider/LLM budget.
    if not _is_translation_enabled():
        return jsonify({"error": "Translation is disabled in configuration"}), 503

    with batch_lock:
        if batch_state["running"]:
            return jsonify({"error": "Batch already running"}), 409

        batch_state.update(
            {
                "running": True,
                "total": len(files),
                "processed": 0,
                "succeeded": 0,
                "failed": 0,
                "skipped": 0,
                "current_file": None,
                "errors": [],
            }
        )

    _app = current_app._get_current_object()

    def _run_batch():
        with _app.app_context():
            try:
                for f in files:
                    with batch_lock:
                        batch_state["current_file"] = f["path"]

                    try:
                        result = translate_file(f["path"], force=force)
                        with batch_lock:
                            batch_state["processed"] += 1
                            if result["success"]:
                                if result["stats"].get("skipped"):
                                    batch_state["skipped"] += 1
                                else:
                                    batch_state["succeeded"] += 1
                            else:
                                batch_state["failed"] += 1
                                batch_state["errors"].append(
                                    {
                                        "file": f["path"],
                                        "error": result.get("error"),
                                    }
                                )

                        _update_stats(result)

                        # WebSocket notification
                        socketio.emit(
                            "batch_progress",
                            {
                                "processed": batch_state["processed"],
                                "total": batch_state["total"],
                                "current_file": f["path"],
                                "success": result["success"],
                            },
                        )

                        # Callback notification
                        if callback_url:
                            _send_callback(
                                callback_url,
                                {
                                    "event": "file_completed",
                                    "file": f["path"],
                                    "success": result["success"],
                                    "processed": batch_state["processed"],
                                    "total": batch_state["total"],
                                },
                            )

                    except Exception as e:
                        logger.exception("Batch: failed on %s", f["path"])
                        with batch_lock:
                            batch_state["processed"] += 1
                            batch_state["failed"] += 1
                            batch_state["errors"].append(
                                {
                                    "file": f["path"],
                                    "error": str(e),
                                }
                            )
            finally:
                with batch_lock:
                    batch_state["running"] = False
                    batch_state["current_file"] = None
                    snapshot = dict(batch_state)

                emit_event("batch_complete", snapshot)

                try:
                    from notifier import send_notification

                    send_notification(
                        title="Sublarr: Batch Complete",
                        body=f"Batch finished: {snapshot['succeeded']} succeeded, {snapshot['failed']} failed, {snapshot['skipped']} skipped",
                        event_type="batch_complete",
                    )
                except Exception as exc:
                    logger.warning("Notification send failed after batch translate: %s", exc)

        if callback_url:
            _send_callback(
                callback_url,
                {
                    "event": "batch_completed",
                    "total": snapshot["total"],
                    "succeeded": snapshot["succeeded"],
                    "failed": snapshot["failed"],
                    "skipped": snapshot["skipped"],
                },
            )

    thread = threading.Thread(target=_run_batch, daemon=True)
    thread.start()

    return jsonify(
        {
            "status": "started",
            "total_files": len(files),
        }
    ), 202


@bp.route("/batch/status", methods=["GET"])
def batch_status_endpoint():
    """Get batch processing status.
    ---
    get:
      tags:
        - Translate
      summary: Get batch status
      description: Returns the current batch processing progress and state.
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
                  succeeded:
                    type: integer
                  failed:
                    type: integer
                  skipped:
                    type: integer
                  current_file:
                    type: string
                    nullable: true
    """
    with batch_lock:
        return jsonify(dict(batch_state))
