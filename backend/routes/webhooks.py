"""Webhook routes -- /webhook/sonarr, /webhook/radarr."""

import hmac
import logging
import threading
import time

from flask import Blueprint, current_app, jsonify, request

from events import emit_event
from extensions import socketio

bp = Blueprint("webhooks", __name__, url_prefix="/api/v1")
logger = logging.getLogger(__name__)


def _spawn_pipeline(
    file_path: str, title: str, series_id: int = None, movie_id: int = None
) -> None:
    """Start the auto-pipeline on a daemon thread with a Flask app context.

    The pipeline touches the DB (get_wanted_items_by_path, process_wanted_item)
    which requires a Flask-SQLAlchemy app context. A raw threading.Thread has
    none, so we capture the live app object from the request handler and push
    an explicit context inside the worker thread. Without this every DB call
    in the pipeline raises `Working outside of application context` and the
    whole auto-download flow silently fails.
    """
    app = current_app._get_current_object()

    def _run():
        with app.app_context():
            _webhook_auto_pipeline(file_path, title, series_id, movie_id)

    threading.Thread(target=_run, daemon=True).start()


def _webhook_auto_pipeline(file_path: str, title: str, series_id: int = None, movie_id: int = None):
    """Full webhook automation pipeline: delay -> scan -> search -> translate.

    Each step is individually configurable. Emits WebSocket events at each stage.
    """
    from config import get_settings
    from db.jobs import create_job

    # Import _run_job from translate module for direct translation fallback
    from routes.translate import _run_job
    from services.wanted_scanner import get_scanner

    s = get_settings()
    delay = s.webhook_delay_minutes * 60

    emit_event(
        "webhook_received",
        {
            "file_path": file_path,
            "title": title,
            "delay_minutes": s.webhook_delay_minutes,
        },
    )

    # Step 1: Configurable delay (blocking sleep is safe here — this runs in a
    # dedicated background thread, HTTP response was already returned to the caller).
    # Long-term path: replace with RQ job so delay survives server restarts and
    # is visible in the job queue UI. See app.job_queue for the existing RQ setup.
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

    # Step 3: Auto-search + download via wanted system.
    # Runs process_wanted_item for EVERY wanted item tied to this file path —
    # one per target language (e.g. separate "de" and "en" entries for the same
    # episode). process_wanted_item internally respects settings.wanted_auto_translate:
    # when translation is disabled it still downloads target-language ASS/SRT
    # directly from providers (Steps 1+3 of process.py) and simply skips the
    # source-language + translate fallback (Steps 2/4/5).
    if s.webhook_auto_search:
        try:
            from db.wanted import get_wanted_items_by_path

            wanted_items = get_wanted_items_by_path(file_path)

            if not wanted_items:
                result_info["steps"].append({"search": "no wanted item found"})
            else:
                from wanted_search import process_wanted_item

                for item in wanted_items:
                    lang = item.get("target_language", "?")
                    try:
                        process_result = process_wanted_item(item["id"])
                        result_info["steps"].append({f"process_{lang}": process_result})
                        logger.info(
                            "Webhook pipeline: process_%s result: %s",
                            lang,
                            process_result.get("status"),
                        )
                    except Exception as inner:
                        logger.warning("Webhook pipeline: process_%s failed: %s", lang, inner)
                        result_info["steps"].append({f"process_{lang}": {"error": str(inner)}})
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
    except Exception as exc:
        logger.warning("Notification send failed in webhook handler: %s", exc)


@bp.route("/webhook/sonarr", methods=["POST"])
def webhook_sonarr():
    """Handle Sonarr webhook (OnDownload event).
    ---
    post:
      security: []
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
    from security_utils import is_safe_path

    # Auth: always require API key on webhook endpoints
    _s = get_settings()
    _api_key = getattr(_s, "api_key", None) or ""
    _provided = request.headers.get("X-Api-Key", "")
    if not _api_key or not hmac.compare_digest(_provided, _api_key):
        return jsonify({"error": "Unauthorized"}), 401

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
    if not is_safe_path(file_path, _s.media_path):
        return jsonify({"error": "file_path outside configured media_path"}), 400

    title = f"{series.get('title', 'Unknown')} — {file_path}"
    series_id = series.get("id")

    logger.info("Sonarr webhook: %s", title)

    _spawn_pipeline(file_path, title, series_id=series_id)

    s = get_settings()
    return jsonify(
        {
            "status": "queued",
            "file_path": file_path,
            "delay_minutes": s.webhook_delay_minutes,
            "auto_pipeline": s.webhook_auto_search,
        }
    ), 202


@bp.route("/webhook/radarr", methods=["POST"])
def webhook_radarr():
    """Handle Radarr webhook (OnDownload and MovieFileDelete events).
    ---
    post:
      security: []
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
    from security_utils import is_safe_path

    # Auth: always require API key on webhook endpoints
    _s = get_settings()
    _api_key = getattr(_s, "api_key", None) or ""
    _provided = request.headers.get("X-Api-Key", "")
    if not _api_key or not hmac.compare_digest(_provided, _api_key):
        return jsonify({"error": "Unauthorized"}), 401

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
            if not is_safe_path(file_path, _s.media_path):
                return jsonify({"error": "file_path outside configured media_path"}), 400
            logger.info("Radarr webhook MovieFileDelete: %s - %s", title, file_path)

            # Delete wanted items for this file path
            from db.wanted import delete_wanted_items

            deleted_count = delete_wanted_items([file_path])
            logger.info(
                "Deleted %d wanted items for deleted movie file: %s", deleted_count, file_path
            )

            return jsonify(
                {
                    "status": "deleted",
                    "file_path": file_path,
                    "wanted_items_removed": deleted_count,
                }
            ), 200
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
    if not is_safe_path(file_path, _s.media_path):
        return jsonify({"error": "file_path outside configured media_path"}), 400

    title = movie.get("title", "Unknown")
    movie_id = movie.get("id")

    logger.info("Radarr webhook: %s - %s (movie_id=%s)", title, file_path, movie_id)

    _spawn_pipeline(file_path, title, movie_id=movie_id)

    s = get_settings()
    return jsonify(
        {
            "status": "queued",
            "file_path": file_path,
            "delay_minutes": s.webhook_delay_minutes,
            "auto_pipeline": s.webhook_auto_search,
        }
    ), 202


@bp.route("/webhook/jellyfin", methods=["POST"])
def webhook_jellyfin():
    """Handle Jellyfin Webhook Plugin notifications (PlaybackStart).
    ---
    post:
      security: []
      tags:
        - Webhooks
      summary: Jellyfin webhook endpoint
      description: |
        Receives webhook notifications from the Jellyfin Webhook Plugin.
        Handles PlaybackStart events: resolves the file path via the Jellyfin API,
        then triggers the auto-pipeline (search + translate) in a background thread.

        Requires jellyfin_play_translate_enabled = true in Settings.

        Expected payload (Jellyfin Webhook Plugin default template):
        ```json
        {
          "NotificationType": "PlaybackStart",
          "ItemId": "abc123def456",
          "ItemType": "Episode",
          "Name": "Episode Title",
          "SeriesName": "Show Name"
        }
        ```
      responses:
        200:
          description: Feature disabled, test event acknowledged, or event type ignored
        202:
          description: Pipeline queued
        400:
          description: Missing ItemId
        403:
          description: Resolved path is outside media_path
        404:
          description: Item path could not be resolved from any configured Jellyfin server
    """
    from config import get_settings
    from mediaserver import get_media_server_manager
    from security_utils import is_safe_path

    s = get_settings()

    # Auth: always require API key on webhook endpoints (checked before feature gate)
    _api_key = getattr(s, "api_key", None) or ""
    _provided = request.headers.get("X-Api-Key", "")
    if not _api_key or not hmac.compare_digest(_provided, _api_key):
        return jsonify({"error": "Unauthorized"}), 401

    # Feature gate — disabled by default
    if not getattr(s, "jellyfin_play_translate_enabled", False):
        return jsonify({"status": "disabled"}), 200

    data = request.get_json() or {}
    notification_type = data.get("NotificationType", "")

    if notification_type == "Test":
        return jsonify({"status": "ok", "message": "Test received"}), 200

    if notification_type != "PlaybackStart":
        return jsonify({"status": "ignored", "notification": notification_type}), 200

    item_id = data.get("ItemId", "")
    if not item_id:
        return jsonify({"error": "No ItemId in payload"}), 400

    name = data.get("Name", "Unknown")
    series_name = data.get("SeriesName", "")
    title = f"{series_name} — {name}" if series_name else name

    # Resolve file path from configured Jellyfin instances
    manager = get_media_server_manager()
    file_path = manager.get_item_path_from_jellyfin(item_id)

    if not file_path:
        logger.warning(
            "Jellyfin webhook: could not resolve path for ItemId %s (%s)",
            item_id,
            title,
        )
        return jsonify({"error": "Could not resolve file path for item", "item_id": item_id}), 404

    if not is_safe_path(file_path, s.media_path):
        return jsonify({"error": "file_path outside configured media_path"}), 403

    logger.info("Jellyfin PlaybackStart webhook: %s (%s)", title, file_path)

    _spawn_pipeline(file_path, title)

    return jsonify({"status": "queued", "file_path": file_path, "title": title}), 202
