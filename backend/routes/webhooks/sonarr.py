"""Sonarr webhook handler — /api/v1/webhook/sonarr."""

import hmac

from flask import jsonify, request

from extensions import limiter
from routes.webhooks import _spawn_pipeline, bp, logger


@bp.route("/webhook/sonarr", methods=["POST"])
@limiter.limit("30/minute")
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
            "auto_pipeline": bool(
                s.webhook_auto_scan or s.webhook_auto_search or s.webhook_auto_translate
            ),
        }
    ), 202
