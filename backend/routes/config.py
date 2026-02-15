"""Config routes — /config, /settings/*, /onboarding/*, /config/export, /config/import."""

import os
import logging
from flask import Blueprint, request, jsonify

from events import emit_event

bp = Blueprint("config", __name__, url_prefix="/api/v1")
logger = logging.getLogger(__name__)


@bp.route("/config", methods=["GET"])
def get_config():
    """Get current configuration (without secrets)."""
    from config import get_settings
    s = get_settings()
    return jsonify(s.get_safe_config())


@bp.route("/settings/path-mapping/test", methods=["POST"])
def test_path_mapping():
    """Test path mapping by mapping a Sonarr/Radarr path to local path."""
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
    """Update configuration values and reload settings."""
    from config import Settings, get_settings, reload_settings
    from db.config import save_config_entry, get_all_config_entries
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
        # Only save known config keys (or all if we can't determine valid keys)
        if not valid_keys or key in valid_keys:
            # Sanitize credentials: strip whitespace from API keys and passwords
            sanitized_value = str(value).strip() if isinstance(value, str) or 'api_key' in key.lower() or 'password' in key.lower() else str(value)
            save_config_entry(key, sanitized_value)
            saved_keys.append(key)

    # Reload settings with ALL DB overrides applied
    all_overrides = get_all_config_entries()
    settings = reload_settings(all_overrides)

    # Invalidate singleton clients so they pick up new URLs/keys
    from sonarr_client import invalidate_client as _inv_sonarr
    from radarr_client import invalidate_client as _inv_radarr
    from mediaserver import invalidate_media_server_manager as _inv_media
    from providers import invalidate_manager as _inv_providers
    from notifier import invalidate_notifier as _inv_notifier
    _inv_sonarr()
    _inv_radarr()
    _inv_media()
    _inv_providers()
    _inv_notifier()
    invalidate_scanner()

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
    """Check if onboarding has been completed."""
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
    """Mark onboarding as completed."""
    from db.config import save_config_entry
    save_config_entry("onboarding_completed", "true")
    return jsonify({"status": "completed"})


@bp.route("/config/export", methods=["GET"])
def export_config():
    """Export current configuration as JSON (without secrets)."""
    from config import get_settings
    s = get_settings()
    return jsonify(s.get_safe_config())


@bp.route("/config/import", methods=["POST"])
def import_config():
    """Import configuration from JSON. Secrets are skipped for safety."""
    from config import Settings, reload_settings
    from db.config import save_config_entry, get_all_config_entries
    from wanted_scanner import invalidate_scanner

    data = request.get_json() or {}
    if not data:
        return jsonify({"error": "No config data provided"}), 400

    valid_keys = set(Settings.model_fields.keys()) if hasattr(Settings, 'model_fields') else set()
    secret_keys = {"api_key", "sonarr_api_key", "radarr_api_key", "jellyfin_api_key",
                   "opensubtitles_api_key", "opensubtitles_password",
                   "jimaku_api_key", "subdl_api_key"}

    imported = []
    skipped_secrets = []

    for key, value in data.items():
        if key in secret_keys:
            skipped_secrets.append(key)
            continue
        if str(value) == '***configured***':
            continue
        if not valid_keys or key in valid_keys:
            save_config_entry(key, str(value))
            imported.append(key)

    # Reload settings
    all_overrides = get_all_config_entries()
    settings = reload_settings(all_overrides)

    # Invalidate caches
    from sonarr_client import invalidate_client as _inv_sonarr
    from radarr_client import invalidate_client as _inv_radarr
    from mediaserver import invalidate_media_server_manager as _inv_media
    from providers import invalidate_manager as _inv_providers
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
