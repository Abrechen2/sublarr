"""Config instance-resolution helpers.

Extracted from config.py for size management. config.py re-exports everything
from this module for backwards compatibility.

IMPORTANT: get_settings() is imported locally inside each function to prevent
a circular import (config.py imports this module; this module needs config.get_settings).
"""

import logging

logger = logging.getLogger(__name__)


def get_sonarr_instances() -> list[dict]:
    """Get Sonarr instances from config, with fallback to legacy settings.

    Returns list of instance dicts: [{"name": "...", "url": "...", "api_key": "...", "path_mapping": "..."}]
    """
    import json

    from config import get_settings  # local import — prevents circular dep

    settings = get_settings()

    # Try new multi-instance config
    if settings.sonarr_instances_json:
        try:
            instances = json.loads(settings.sonarr_instances_json)
            if isinstance(instances, list):
                valid = [i for i in instances if i.get("url") and i.get("api_key")]
                if valid:
                    return valid
        except (json.JSONDecodeError, TypeError):
            pass

    # Fallback to legacy single-instance config
    if settings.sonarr_url and settings.sonarr_api_key:
        return [
            {
                "name": "Default",
                "url": settings.sonarr_url,
                "api_key": settings.sonarr_api_key,
                "path_mapping": settings.path_mapping,
            }
        ]

    return []


def get_radarr_instances() -> list[dict]:
    """Get Radarr instances from config, with fallback to legacy settings.

    Returns list of instance dicts: [{"name": "...", "url": "...", "api_key": "...", "path_mapping": "..."}]
    """
    import json

    from config import get_settings  # local import — prevents circular dep

    settings = get_settings()

    # Try new multi-instance config
    if settings.radarr_instances_json:
        try:
            instances = json.loads(settings.radarr_instances_json)
            if isinstance(instances, list):
                valid = [i for i in instances if i.get("url") and i.get("api_key")]
                if valid:
                    return valid
        except (json.JSONDecodeError, TypeError):
            pass

    # Fallback to legacy single-instance config
    if settings.radarr_url and settings.radarr_api_key:
        return [
            {
                "name": "Default",
                "url": settings.radarr_url,
                "api_key": settings.radarr_api_key,
                "path_mapping": settings.path_mapping,
            }
        ]

    return []


def is_standalone_mode() -> bool:
    """Return True when standalone mode should be active.

    Standalone activates when:
    - ``standalone_enabled`` is explicitly True, OR
    - No Sonarr AND no Radarr instances are configured (auto-activation).
    """
    from config import get_settings  # local import — prevents circular dep

    settings = get_settings()

    if getattr(settings, "standalone_enabled", False):
        return True

    # Auto-activate when no arr instances are configured
    return len(get_sonarr_instances()) == 0 and len(get_radarr_instances()) == 0


def get_media_server_instances() -> list[dict]:
    """Get media server instances from config, with fallback to legacy Jellyfin settings.

    Checks config_entries for media_servers_json first.
    If not found, auto-migrates legacy jellyfin_url + jellyfin_api_key to the new format.

    Returns list of instance dicts:
        [{"type": "jellyfin", "name": "...", "enabled": true, "url": "...", "api_key": "..."}]
    """
    import json

    from config import get_settings  # local import — prevents circular dep
    from db.config import get_config_entry, save_config_entry

    # Try new multi-instance config from DB
    raw = get_config_entry("media_servers_json")
    if raw:
        try:
            instances = json.loads(raw)
            if isinstance(instances, list) and len(instances) > 0:
                return instances
        except (json.JSONDecodeError, TypeError):
            pass

    # Fallback to legacy single-instance Jellyfin config
    settings = get_settings()
    if settings.jellyfin_url and settings.jellyfin_api_key:
        migrated = [
            {
                "type": "jellyfin",
                "name": "Jellyfin",
                "enabled": True,
                "url": settings.jellyfin_url,
                "api_key": settings.jellyfin_api_key,
            }
        ]
        # One-time migration: store back into config_entries
        try:
            save_config_entry("media_servers_json", json.dumps(migrated))
        except Exception:
            pass  # Migration is best-effort
        return migrated

    return []


def get_shoko_config() -> dict | None:
    """Return the first enabled Shoko instance config, or None.

    Shoko is configured as a ``shoko``-typed entry in the shared
    ``media_servers_json`` blob (same store the media-server manager uses for
    the rescan role), so the enricher/library-sync code and the media-server
    rescan share a single source of truth. Returns a dict with at least
    ``url`` plus ``api_key``/``username``/``password`` when configured.
    """
    for entry in get_media_server_instances():
        if not isinstance(entry, dict):
            continue
        if entry.get("type") != "shoko":
            continue
        if not entry.get("enabled", True):
            continue
        if entry.get("url"):
            return entry
    return None
