"""Webhook routes -- /webhook/sonarr, /webhook/radarr."""

import time
import logging
import threading

from flask import Blueprint, request, jsonify

from extensions import socketio
from events import emit_event

bp = Blueprint("webhooks", __name__, url_prefix="/api/v1")
logger = logging.getLogger(__name__)


def _webhook_auto_pipeline(file_path: str, title: str, series_id: int = None, movie_id: int = None):
    """Full webhook automation pipeline: delay -> scan -> search -> translate.

    Each step is individually configurable. Emits WebSocket events at each stage.
    """
    from config import get_settings
    from wanted_scanner import get_scanner
    from db.jobs import create_job

    # Import _run_job from translate module for direct translation fallback
    from routes.translate import _run_job

    s = get_settings()
    delay = s.webhook_delay_minutes * 60

    emit_event("webhook_received", {
        "file_path": file_path,
        "title": title,
        "delay_minutes": s.webhook_delay_minutes,
    })

    # Step 1: Configurable delay
    if delay > 0:
        logger.info("Webhook pipeline: waiting %d minutes...", s.webhook_delay_minutes)
        time.sleep(delay)

    result_info = {"file_path": file_path, "title": title, "steps": []}

    # Step 2: Auto-scan
    if s.webhook_auto_scan and series_id:
        try:
            scanner = get_scanner()
            scan_result = scanner.scan_series(series_id)
            result_info["steps"].append({"scan": scan_result})
            logger.info("Webhook pipeline: scan complete for series %d", series_id)
        except Exception as e:
            logger.warning("Webhook pipeline: scan failed: %s", e)
            result_info["steps"].append({"scan": {"error": str(e)}})
    elif s.webhook_auto_scan and movie_id:
        try:
            scanner = get_scanner()
            scan_result = scanner.scan_movie(movie_id)
            result_info["steps"].append({"scan": scan_result})
            logger.info("Webhook pipeline: scan complete for movie %d", movie_id)
        except Exception as e:
            logger.warning("Webhook pipeline: scan failed: %s", e)
            result_info["steps"].append({"scan": {"error": str(e)}})

    # Step 3: Auto-search + translate via wanted system
    if s.webhook_auto_search:
        try:
            from db.wanted import get_wanted_item_by_path
            wanted_item = get_wanted_item_by_path(file_path)

            if wanted_item and s.webhook_auto_translate:
                from wanted_search import process_wanted_item
                process_result = process_wanted_item(wanted_item["id"])
                result_info["steps"].append({"process": process_result})
                logger.info("Webhook pipeline: process result: %s", process_result.get("status"))
            elif wanted_item:
                from wanted_search import search_wanted_item
                search_result = search_wanted_item(wanted_item["id"])
                result_info["steps"].append({"search": search_result})
            else:
                result_info["steps"].append({"search": "no wanted item found"})
        except Exception as e:
            logger.warning("Webhook pipeline: search/process failed: %s", e)
            result_info["steps"].append({"search": {"error": str(e)}})

    # Step 4: Fallback -- direct translate if auto_search disabled
    if not s.webhook_auto_search:
        job = create_job(file_path)
        _run_job(job)
        result_info["steps"].append({"translate": "direct"})

    socketio.emit("webhook_completed", result_info)
    logger.info("Webhook pipeline completed for: %s", file_path)

    # Send notification
    try:
        from notifier import send_notification
        send_notification(
            title=f"Sublarr: {title}",
            body=f"Subtitle pipeline completed for {title}",
            event_type="download",
        )
    except Exception:
        pass


@bp.route("/webhook/sonarr", methods=["POST"])
def webhook_sonarr():
    """Handle Sonarr webhook (OnDownload event).
    ---
    post:
      tags:
        - Webhooks
      summary: Sonarr webhook endpoint
      description: |
        Receives webhook notifications from Sonarr. Supports Test and Download event types.
        On Download events, triggers the auto-pipeline (delay, scan, search, translate) in a background thread.

        Expected payload structure (Sonarr OnDownload):
        ```json
        {
          "eventType": "Download",
          "series": {"id": 1, "title": "Show Name"},
          "episodeFile": {"path": "/path/to/file.mkv"}
        }
        ```
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              properties:
                eventType:
                  type: string
                  enum: [Test, Download]
                series:
                  type: object
                  properties:
                    id:
                      type: integer
                    title:
                      type: string
                episodeFile:
                  type: object
                  properties:
                    path:
                      type: string
      responses:
        200:
          description: Test webhook acknowledged or event ignored
        202:
          description: Download pipeline queued
          content:
            application/json:
              schema:
                type: object
                properties:
                  status:
                    type: string
                  file_path:
                    type: string
                  delay_minutes:
                    type: integer
                  auto_pipeline:
                    type: boolean
        400:
          description: Missing file path in payload
    """
    from config import get_settings, map_path

    data = request.get_json() or {}
    event_type = data.get("eventType", "")

    if event_type == "Test":
        return jsonify({"status": "ok", "message": "Test received"}), 200

    if event_type != "Download":
        return jsonify({"status": "ignored", "event": event_type}), 200

    episode_file = data.get("episodeFile", {})
    file_path = episode_file.get("path", "")
    series = data.get("series", {})

    if not file_path:
        return jsonify({"error": "No file path in webhook payload"}), 400

    file_path = map_path(file_path)
    title = f"{series.get('title', 'Unknown')} — {file_path}"
    series_id = series.get("id")

    logger.info("Sonarr webhook: %s", title)

    thread = threading.Thread(
        target=_webhook_auto_pipeline,
        args=(file_path, title, series_id),
        daemon=True,
    )
    thread.start()

    s = get_settings()
    return jsonify({
        "status": "queued",
        "file_path": file_path,
        "delay_minutes": s.webhook_delay_minutes,
        "auto_pipeline": s.webhook_auto_search,
    }), 202


@bp.route("/webhook/radarr", methods=["POST"])
def webhook_radarr():
    """Handle Radarr webhook (OnDownload and MovieFileDelete events).
    ---
    post:
      tags:
        - Webhooks
      summary: Radarr webhook endpoint
      description: |
        Receives webhook notifications from Radarr. Supports Test, Download, and MovieFileDelete event types.
        On Download events, triggers the auto-pipeline in a background thread.
        On MovieFileDelete events, removes associated wanted items.

        Expected payload structure (Radarr OnDownload):
        ```json
        {
          "eventType": "Download",
          "movie": {"id": 1, "title": "Movie Name"},
          "movieFile": {"path": "/path/to/file.mkv"}
        }
        ```
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              properties:
                eventType:
                  type: string
                  enum: [Test, Download, MovieFileDelete]
                movie:
                  type: object
                  properties:
                    id:
                      type: integer
                    title:
                      type: string
                movieFile:
                  type: object
                  properties:
                    path:
                      type: string
      responses:
        200:
          description: Test acknowledged, event ignored, or file delete processed
        202:
          description: Download pipeline queued
          content:
            application/json:
              schema:
                type: object
                properties:
                  status:
                    type: string
                  file_path:
                    type: string
                  delay_minutes:
                    type: integer
                  auto_pipeline:
                    type: boolean
        400:
          description: Missing file path in payload
    """
    from config import get_settings, map_path

    data = request.get_json() or {}
    event_type = data.get("eventType", "")

    if event_type == "Test":
        return jsonify({"status": "ok", "message": "Test received"}), 200

    # Handle MovieFileDelete event
    if event_type == "MovieFileDelete":
        movie_file = data.get("movieFile", {})
        file_path = movie_file.get("path", "")
        movie = data.get("movie", {})
        title = movie.get("title", "Unknown")

        if file_path:
            file_path = map_path(file_path)
            logger.info("Radarr webhook MovieFileDelete: %s - %s", title, file_path)

            # Delete wanted items for this file path
            from db.wanted import delete_wanted_items
            deleted_count = delete_wanted_items([file_path])
            logger.info("Deleted %d wanted items for deleted movie file: %s", deleted_count, file_path)

            return jsonify({
                "status": "deleted",
                "file_path": file_path,
                "wanted_items_removed": deleted_count,
            }), 200
        else:
            return jsonify({"status": "ignored", "reason": "No file path in webhook payload"}), 200

    # Handle Download event
    if event_type != "Download":
        return jsonify({"status": "ignored", "event": event_type}), 200

    movie_file = data.get("movieFile", {})
    file_path = movie_file.get("path", "")
    movie = data.get("movie", {})

    if not file_path:
        return jsonify({"error": "No file path in webhook payload"}), 400

    file_path = map_path(file_path)
    title = movie.get("title", "Unknown")
    movie_id = movie.get("id")

    logger.info("Radarr webhook: %s - %s (movie_id=%s)", title, file_path, movie_id)

    thread = threading.Thread(
        target=_webhook_auto_pipeline,
        args=(file_path, title, None, movie_id),
        daemon=True,
    )
    thread.start()

    s = get_settings()
    return jsonify({
        "status": "queued",
        "file_path": file_path,
        "delay_minutes": s.webhook_delay_minutes,
        "auto_pipeline": s.webhook_auto_search,
    }), 202
