"""Radarr webhook handler — /api/v1/webhook/radarr."""

import hmac

from flask import jsonify, request

from extensions import limiter
from routes.webhooks import _spawn_pipeline, bp, logger


@bp.route("/webhook/radarr", methods=["POST"])
@limiter.limit("30/minute")
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
          description: |
            Test acknowledged, file delete processed, or the event was
            ignored. A Download event carrying no file path is ignored
            rather than rejected, matching the MovieFileDelete branch.
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
          description: file_path resolved outside the configured media_path
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
        # Same reasoning as the Sonarr handler: an event with nothing to act
        # on is not a client error, and the MovieFileDelete branch above
        # already answers 200/ignored for exactly this case. Kept loud so the
        # skip stays visible.
        logger.warning(
            "Radarr webhook: %s event carried no file path — nothing to do. "
            "This usually means Radarr's own import did not produce a file. "
            "Payload keys: %s",
            event_type,
            sorted(data.keys()),
        )
        return jsonify({"status": "ignored", "reason": "No file path in webhook payload"}), 200

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
            "auto_pipeline": bool(
                s.webhook_auto_scan or s.webhook_auto_search or s.webhook_auto_translate
            ),
        }
    ), 202
