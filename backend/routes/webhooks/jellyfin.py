"""Jellyfin webhook handler — /api/v1/webhook/jellyfin."""

import hmac

from flask import jsonify, request

from extensions import limiter
from routes.webhooks import _spawn_pipeline, bp, logger


@bp.route("/webhook/jellyfin", methods=["POST"])
@limiter.limit("30/minute")
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
