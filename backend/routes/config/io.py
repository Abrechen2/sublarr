"""Config import/export routes — /config/export, /config/import."""

import logging

from flask import jsonify, request

from extensions import limiter
from routes.config import bp

logger = logging.getLogger(__name__)


@bp.route("/config/export", methods=["GET"])
@limiter.limit("30 per minute")
def export_config():
    """Export current configuration as JSON (without secrets).
    ---
    get:
      tags:
        - Config
      summary: Export configuration
      description: Exports the current configuration as JSON with secret values masked. Suitable for backup or sharing.
      security:
        - apiKeyAuth: []
      responses:
        200:
          description: Configuration JSON
          content:
            application/json:
              schema:
                type: object
                additionalProperties: true
    """
    from config import get_settings

    s = get_settings()
    return jsonify(s.get_safe_config())


@bp.route("/config/import", methods=["POST"])
@limiter.limit("5 per minute")
def import_config():
    """Import configuration from JSON. Secrets are skipped for safety.
    ---
    post:
      tags:
        - Config
      summary: Import configuration
      description: >
        Imports configuration from a JSON payload. Secret keys (API keys, passwords) are
        automatically skipped for safety. Reloads settings and invalidates cached clients after import.
      security:
        - apiKeyAuth: []
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              additionalProperties: true
              description: Configuration key-value pairs to import
      responses:
        200:
          description: Configuration imported
          content:
            application/json:
              schema:
                type: object
                properties:
                  status:
                    type: string
                  imported_keys:
                    type: array
                    items:
                      type: string
                  skipped_secrets:
                    type: array
                    items:
                      type: string
                  config:
                    type: object
                    additionalProperties: true
        400:
          description: No config data provided
    """
    from config import Settings, reload_settings
    from db.config import get_all_config_entries, save_config_entry
    from services.wanted_scanner import invalidate_scanner

    data = request.get_json() or {}
    if not data:
        return jsonify({"error": "No config data provided"}), 400

    valid_keys = set(Settings.model_fields.keys()) if hasattr(Settings, "model_fields") else set()
    secret_keys = {
        "api_key",
        "sonarr_api_key",
        "radarr_api_key",
        "jellyfin_api_key",
        "opensubtitles_api_key",
        "opensubtitles_password",
        "jimaku_api_key",
        "subdl_api_key",
        "tmdb_api_key",
        "tvdb_api_key",
        "tvdb_pin",
        "deepl_api_key",
        "notification_urls_json",
        "sonarr_instances_json",
        "radarr_instances_json",
        "media_servers_json",
    }

    # Fail-closed: if valid_keys cannot be determined, reject the import entirely
    if not valid_keys:
        return jsonify(
            {"error": "Cannot determine valid config keys - import rejected for safety"}
        ), 500

    imported = []
    skipped_secrets = []

    for key, value in data.items():
        if key in secret_keys:
            skipped_secrets.append(key)
            continue
        if str(value) == "***configured***":
            continue
        if key in valid_keys:
            save_config_entry(key, str(value))
            imported.append(key)

    # Reload settings
    all_overrides = get_all_config_entries()
    settings = reload_settings(all_overrides)

    # Invalidate caches
    from mediaserver import invalidate_media_server_manager as _inv_media
    from providers import invalidate_manager as _inv_providers
    from radarr_client import invalidate_client as _inv_radarr
    from sonarr_client import invalidate_client as _inv_sonarr

    _inv_sonarr()
    _inv_radarr()
    _inv_media()
    _inv_providers()
    invalidate_scanner()

    # Restart scanner scheduler so the new scanner instance has the Flask app reference
    try:
        from flask import current_app as _capp

        from extensions import socketio as _sock
        from services.wanted_scanner import get_scanner as _get_scanner

        _get_scanner().start_scheduler(app=_capp._get_current_object(), socketio=_sock)
    except Exception as _exc:
        logger.warning("Failed to restart scanner scheduler after config import: %s", _exc)

    # Reload media server instances with new config
    try:
        from mediaserver import get_media_server_manager

        get_media_server_manager().load_instances()
    except Exception as exc:
        logger.warning("Media server reload failed after config import: %s", exc)

    logger.info("Config imported: %s (skipped secrets: %s)", imported, skipped_secrets)

    return jsonify(
        {
            "status": "imported",
            "imported_keys": imported,
            "skipped_secrets": skipped_secrets,
            "config": settings.get_safe_config(),
        }
    )
