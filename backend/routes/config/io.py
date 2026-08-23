"""Config import/export routes — /config/export, /config/import."""

import logging

from flask import jsonify, request

from extensions import limiter
from routes.config import bp
from sensitive_keys import is_sensitive_key

logger = logging.getLogger(__name__)

# Keys that hold a secret without carrying a sensitive suffix, so
# ``is_sensitive_key`` cannot recognise them: a PIN, and the JSON blobs that
# embed per-instance API keys.
_EXTRA_SECRET_IMPORT_KEYS: frozenset[str] = frozenset(
    {
        "tvdb_pin",
        "notification_urls_json",
        "sonarr_instances_json",
        "radarr_instances_json",
        "media_servers_json",
    }
)


def _secret_import_keys() -> set[str]:
    """Config keys an import or restore may never set.

    Derived from ``is_sensitive_key`` over the real settings models rather
    than enumerated by hand. The hand-written list this replaced had
    drifted: it named ``opensubtitles_password`` but not the ``_password``
    fields of the providers added after it, so an import could plant their
    credentials. Deriving it means a provider added tomorrow is covered on
    the day it lands.

    It reads the field names off ``BootSettings``/``UISettings`` and not off
    the caller's ``valid_keys``, which is empty in both call sites — the
    composite ``Settings`` is a plain class and has no ``model_fields``.
    Deriving from an empty set would have silently blocked nothing.

    ``API_KEY_REGISTRY`` is a second source because not every secret is a
    settings field: ``deepl_api_key`` lives only in ``config_entries`` and
    would otherwise drop out of the set the hand-written list had covered.
    """
    from config_settings import BootSettings, UISettings
    from routes.api_keys.helpers import API_KEY_REGISTRY

    candidates = set(BootSettings.model_fields) | set(UISettings.model_fields)
    for entry in API_KEY_REGISTRY.values():
        candidates.update(entry.get("keys", ()))
    return {key for key in candidates if is_sensitive_key(key)} | _EXTRA_SECRET_IMPORT_KEYS


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
    from security_utils import validate_service_url
    from services.wanted_scanner import invalidate_scanner

    data = request.get_json(silent=True) or {}
    # A JSON list/scalar would crash the .items() loop with AttributeError.
    if not isinstance(data, dict):
        return jsonify({"error": "Import payload must be a JSON object"}), 400
    if not data:
        return jsonify({"error": "No config data provided"}), 400

    valid_keys = set(Settings.model_fields.keys()) if hasattr(Settings, "model_fields") else set()
    secret_keys = _secret_import_keys()

    # Fail-closed: if valid_keys cannot be determined, reject the import entirely
    if not valid_keys:
        return jsonify(
            {"error": "Cannot determine valid config keys - import rejected for safety"}
        ), 500

    imported = []
    skipped_secrets = []
    # Mirror update_config's URL-field set so an attacker can't smuggle
    # file://, link-local IPs, or cloud-metadata endpoints in via the
    # import path.
    _url_fields = {"ollama_url", "sonarr_url", "radarr_url", "jellyfin_url"}

    for key, value in data.items():
        if key in secret_keys:
            skipped_secrets.append(key)
            continue
        if str(value) == "***configured***":
            continue
        if key in valid_keys:
            if key in _url_fields and value:
                ok, reason = validate_service_url(str(value))
                if not ok:
                    return jsonify({"error": f"Invalid URL for {key}: {reason}"}), 400
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
