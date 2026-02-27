"""Config routes — /config, /settings/*, /onboarding/*, /config/export, /config/import."""

import logging
import os

from flask import Blueprint, jsonify, request

from cache_response import cached_get, invalidate_response_cache
from events import emit_event

bp = Blueprint("config", __name__, url_prefix="/api/v1")
logger = logging.getLogger(__name__)


@bp.route("/config", methods=["GET"])
@cached_get(ttl_seconds=60)
def get_config():
    """Get current configuration (without secrets).
    ---
    get:
      tags:
        - Config
      summary: Get configuration
      description: Returns the current application configuration with secret values masked.
      security:
        - apiKeyAuth: []
      responses:
        200:
          description: Configuration object
          content:
            application/json:
              schema:
                type: object
                additionalProperties: true
    """
    from config import get_settings
    from db.config import get_config_entry
    s = get_settings()
    cfg = s.get_safe_config()
    # Include namespaced extension config entries (dot-notation keys not in Pydantic Settings)
    _extension_keys = [
        'translation.context_window_size',
    ]
    for _k in _extension_keys:
        _v = get_config_entry(_k)
        if _v is not None:
            cfg[_k] = _v
    return jsonify(cfg)


@bp.route("/settings/path-mapping/test", methods=["POST"])
def test_path_mapping():
    """Test path mapping by mapping a Sonarr/Radarr path to local path.
    ---
    post:
      tags:
        - Config
      summary: Test path mapping
      description: Maps a remote Sonarr/Radarr path to the local filesystem path and checks if it exists.
      security:
        - apiKeyAuth: []
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required: [remote_path]
              properties:
                remote_path:
                  type: string
                  description: Remote path from Sonarr/Radarr
      responses:
        200:
          description: Path mapping result
          content:
            application/json:
              schema:
                type: object
                properties:
                  remote_path:
                    type: string
                  mapped_path:
                    type: string
                  exists:
                    type: boolean
        400:
          description: Missing remote_path
    """
    from config import map_path

    data = request.get_json() or {}
    remote_path = data.get("remote_path", "").strip()

    if not remote_path:
        return jsonify({"error": "remote_path is required"}), 400

    mapped = map_path(remote_path)
    return jsonify({
        "remote_path": remote_path,
        "mapped_path": mapped,
        "exists": os.path.exists(mapped),
    })


@bp.route("/config", methods=["PUT"])
def update_config():
    """Update configuration values and reload settings.
    ---
    put:
      tags:
        - Config
      summary: Update configuration
      description: >
        Saves partial configuration updates to the database and reloads settings.
        Invalidates all cached clients (Sonarr, Radarr, providers, media servers).
        Masked password values ('***configured***') are skipped.
      security:
        - apiKeyAuth: []
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              additionalProperties: true
              description: Key-value pairs of config settings to update
      responses:
        200:
          description: Configuration saved and reloaded
          content:
            application/json:
              schema:
                type: object
                properties:
                  status:
                    type: string
                  updated_keys:
                    type: array
                    items:
                      type: string
                  config:
                    type: object
                    additionalProperties: true
        400:
          description: No config values provided
    """
    from config import Settings, reload_settings
    from db.config import get_all_config_entries, save_config_entry
    from wanted_scanner import invalidate_scanner

    data = request.get_json() or {}
    if not data:
        return jsonify({"error": "No config values provided"}), 400

    # Validate that keys exist in Settings
    valid_keys = set(Settings.model_fields.keys()) if hasattr(Settings, 'model_fields') else set()
    saved_keys = []

    for key, value in data.items():
        # Skip masked password values (user didn't change them)
        if str(value) == '***configured***':
            continue
        # Allow known config keys OR namespaced extension keys (dot-notation, e.g. translation.context_window_size)
        is_extension_key = '.' in key
        if not valid_keys or key in valid_keys or is_extension_key:
            # Sanitize credentials: strip whitespace from API keys and passwords
            sanitized_value = str(value).strip() if isinstance(value, str) or 'api_key' in key.lower() or 'password' in key.lower() else str(value)
            save_config_entry(key, sanitized_value)
            saved_keys.append(key)

    # Reload settings with ALL DB overrides applied
    all_overrides = get_all_config_entries()
    settings = reload_settings(all_overrides)

    # Selectively invalidate singleton clients based on which keys changed
    from mediaserver import invalidate_media_server_manager as _inv_media
    from notifier import invalidate_notifier as _inv_notifier
    from providers import invalidate_manager as _inv_providers
    from radarr_client import invalidate_client as _inv_radarr
    from sonarr_client import invalidate_client as _inv_sonarr

    if any(k.startswith('sonarr_') for k in saved_keys):
        _inv_sonarr()
    if any(k.startswith('radarr_') for k in saved_keys):
        _inv_radarr()
    if any(k.startswith('provider_') or k.startswith('scoring_') or
           k in {'opensubtitles_api_key', 'jimaku_api_key', 'subdl_api_key',
                 'min_score', 'source_language', 'target_language'} for k in saved_keys):
        _inv_providers()
    if any(k.startswith('jellyfin_') or k.startswith('emby_') or
           k.startswith('plex_') or k.startswith('kodi_') or
           k.startswith('media_server') for k in saved_keys):
        _inv_media()
    if any(k.startswith('notification') or k.startswith('pushover') or
           k.startswith('gotify') or k.startswith('ntfy') or
           k.startswith('discord') or k.startswith('slack') for k in saved_keys):
        _inv_notifier()
    invalidate_scanner()
    invalidate_response_cache()

    # Reload media server instances with new config
    try:
        from mediaserver import get_media_server_manager
        get_media_server_manager().load_instances()
    except Exception:
        pass

    logger.info("Config updated: %s — settings reloaded", saved_keys)

    emit_event("config_updated", {"updated_keys": saved_keys})

    # Invalidate scoring cache if scoring-related keys changed
    scoring_keys_changed = any(
        k.startswith("scoring_") or k.startswith("provider_modifier_")
        for k in saved_keys
    )
    if scoring_keys_changed:
        try:
            from providers.base import invalidate_scoring_cache
            invalidate_scoring_cache()
        except Exception:
            pass

    return jsonify({
        "status": "saved",
        "updated_keys": saved_keys,
        "config": settings.get_safe_config(),
    })


@bp.route("/onboarding/status", methods=["GET"])
def onboarding_status():
    """Check if onboarding has been completed.
    ---
    get:
      tags:
        - Config
      summary: Get onboarding status
      description: Returns whether onboarding has been completed and which services are configured.
      security:
        - apiKeyAuth: []
      responses:
        200:
          description: Onboarding status
          content:
            application/json:
              schema:
                type: object
                properties:
                  completed:
                    type: boolean
                  has_sonarr:
                    type: boolean
                  has_radarr:
                    type: boolean
                  has_ollama:
                    type: boolean
                  has_providers:
                    type: boolean
    """
    from config import get_settings
    from db.config import get_config_entry

    settings = get_settings()
    completed = get_config_entry("onboarding_completed")
    return jsonify({
        "completed": completed == "true",
        "has_sonarr": bool(settings.sonarr_url and settings.sonarr_api_key),
        "has_radarr": bool(settings.radarr_url and settings.radarr_api_key),
        "has_ollama": bool(settings.ollama_url),
        "has_providers": bool(settings.opensubtitles_api_key or settings.jimaku_api_key or settings.subdl_api_key),
    })


@bp.route("/onboarding/complete", methods=["POST"])
def onboarding_complete():
    """Mark onboarding as completed.
    ---
    post:
      tags:
        - Config
      summary: Complete onboarding
      description: Marks the onboarding wizard as completed so it will not show again.
      security:
        - apiKeyAuth: []
      responses:
        200:
          description: Onboarding marked complete
          content:
            application/json:
              schema:
                type: object
                properties:
                  status:
                    type: string
    """
    from db.config import save_config_entry
    save_config_entry("onboarding_completed", "true")
    return jsonify({"status": "completed"})


@bp.route("/config/export", methods=["GET"])
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
    from wanted_scanner import invalidate_scanner

    data = request.get_json() or {}
    if not data:
        return jsonify({"error": "No config data provided"}), 400

    valid_keys = set(Settings.model_fields.keys()) if hasattr(Settings, 'model_fields') else set()
    secret_keys = {"api_key", "sonarr_api_key", "radarr_api_key", "jellyfin_api_key",
                   "opensubtitles_api_key", "opensubtitles_password",
                   "jimaku_api_key", "subdl_api_key"}

    # Fail-closed: if valid_keys cannot be determined, reject the import entirely
    if not valid_keys:
        return jsonify({"error": "Cannot determine valid config keys - import rejected for safety"}), 500

    imported = []
    skipped_secrets = []

    for key, value in data.items():
        if key in secret_keys:
            skipped_secrets.append(key)
            continue
        if str(value) == '***configured***':
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

    # Reload media server instances with new config
    try:
        from mediaserver import get_media_server_manager
        get_media_server_manager().load_instances()
    except Exception:
        pass

    logger.info("Config imported: %s (skipped secrets: %s)", imported, skipped_secrets)

    return jsonify({
        "status": "imported",
        "imported_keys": imported,
        "skipped_secrets": skipped_secrets,
        "config": settings.get_safe_config(),
    })
