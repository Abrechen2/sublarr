"""Bazarr data mapping, preview, and import application.

Transforms parsed Bazarr config and database data into Sublarr format.
Handles migration preview generation, config/profile/blacklist/history import,
provider setting mapping, and batch migration orchestration.
"""

import logging

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Preview & Masking
# ---------------------------------------------------------------------------


def preview_migration(config_data: dict, db_data: dict) -> dict:
    """Generate a human-readable preview of what the migration will import.

    Args:
        config_data: Parsed config dict (from parse_bazarr_config).
        db_data: Parsed DB dict (from migrate_bazarr_db).

    Returns:
        Dict with sections describing each import category.
    """
    preview = {
        "config_entries": [],
        "profiles": [],
        "blacklist_count": 0,
        "warnings": [],
    }

    # Collect warnings from both sources
    preview["warnings"].extend(config_data.get("warnings", []))
    preview["warnings"].extend(db_data.get("warnings", []))

    # Config entries that would be imported
    sonarr = config_data.get("sonarr", {})
    if sonarr.get("url") and sonarr.get("api_key"):
        url = sonarr["url"]
        port = sonarr.get("port", "")
        if port:
            url = f"{url}:{port}"
        preview["config_entries"].append(
            {
                "key": "sonarr_url",
                "value": url,
                "source": "Bazarr config (sonarr)",
            }
        )
        preview["config_entries"].append(
            {
                "key": "sonarr_api_key",
                "value": _mask_preview(sonarr["api_key"]),
                "source": "Bazarr config (sonarr)",
            }
        )

    radarr = config_data.get("radarr", {})
    if radarr.get("url") and radarr.get("api_key"):
        url = radarr["url"]
        port = radarr.get("port", "")
        if port:
            url = f"{url}:{port}"
        preview["config_entries"].append(
            {
                "key": "radarr_url",
                "value": url,
                "source": "Bazarr config (radarr)",
            }
        )
        preview["config_entries"].append(
            {
                "key": "radarr_api_key",
                "value": _mask_preview(radarr["api_key"]),
                "source": "Bazarr config (radarr)",
            }
        )

    general = config_data.get("general", {})
    if general.get("opensubtitles_api_key"):
        preview["config_entries"].append(
            {
                "key": "opensubtitles_api_key",
                "value": _mask_preview(general["opensubtitles_api_key"]),
                "source": "Bazarr config (opensubtitles)",
            }
        )
    if general.get("opensubtitles_username"):
        preview["config_entries"].append(
            {
                "key": "opensubtitles_username",
                "value": general["opensubtitles_username"],
                "source": "Bazarr config (opensubtitles)",
            }
        )

    # Profiles from DB
    for p in db_data.get("profiles", []):
        lang_list = [lang.get("language", "?") for lang in p.get("languages", [])]
        preview["profiles"].append(
            {
                "name": p.get("name", "Unnamed"),
                "languages": lang_list,
            }
        )

    # Blacklist count
    preview["blacklist_count"] = len(db_data.get("blacklist", []))

    # Extended counts from deeper DB reading
    preview["shows_count"] = len(db_data.get("shows", []))
    preview["movies_count"] = len(db_data.get("movies", []))
    preview["history_count"] = len(db_data.get("history", []))

    return preview


def _mask_preview(val: str) -> str:
    """Mask a value for preview display."""
    if not val or len(val) <= 4:
        return "***"
    return val[:4] + "***"


# ---------------------------------------------------------------------------
# Apply Migration
# ---------------------------------------------------------------------------


def apply_migration(config_data: dict, db_data: dict) -> dict:
    """Apply the Bazarr migration, importing config, profiles, and blacklist.

    Uses lazy imports for database modules to avoid circular imports.

    Args:
        config_data: Parsed config dict (from parse_bazarr_config).
        db_data: Parsed DB dict (from migrate_bazarr_db).

    Returns:
        Dict with counts of imported items and any warnings.
    """
    from db.config import save_config_entry

    result = {
        "config_imported": 0,
        "profiles_imported": 0,
        "blacklist_imported": 0,
        "warnings": [],
    }

    # Import Sonarr config
    sonarr = config_data.get("sonarr", {})
    if sonarr.get("url") and sonarr.get("api_key"):
        url = sonarr["url"]
        port = sonarr.get("port", "")
        if port:
            url = f"{url}:{port}"
        save_config_entry("sonarr_url", url)
        save_config_entry("sonarr_api_key", sonarr["api_key"])
        result["config_imported"] += 2

    # Import Radarr config
    radarr = config_data.get("radarr", {})
    if radarr.get("url") and radarr.get("api_key"):
        url = radarr["url"]
        port = radarr.get("port", "")
        if port:
            url = f"{url}:{port}"
        save_config_entry("radarr_url", url)
        save_config_entry("radarr_api_key", radarr["api_key"])
        result["config_imported"] += 2

    # Import OpenSubtitles credentials
    general = config_data.get("general", {})
    if general.get("opensubtitles_api_key"):
        save_config_entry("opensubtitles_api_key", general["opensubtitles_api_key"])
        result["config_imported"] += 1
    if general.get("opensubtitles_username"):
        save_config_entry("opensubtitles_username", general["opensubtitles_username"])
        result["config_imported"] += 1
    if general.get("opensubtitles_password"):
        save_config_entry("opensubtitles_password", general["opensubtitles_password"])
        result["config_imported"] += 1

    # Import language profiles from DB
    try:
        from db.profiles import create_language_profile

        for p in db_data.get("profiles", []):
            try:
                languages = p.get("languages", [])
                if not languages:
                    result["warnings"].append(f"Skipping profile '{p.get('name')}': no languages")
                    continue

                # Map Bazarr profile to Sublarr format
                target_langs = [lang.get("language", "en") for lang in languages]
                target_names = [lang.get("language", "Unknown") for lang in languages]

                create_language_profile(
                    name=p.get("name", "Imported from Bazarr"),
                    source_lang="en",
                    source_name="English",
                    target_langs=target_langs,
                    target_names=target_names,
                )
                result["profiles_imported"] += 1
            except Exception as exc:
                result["warnings"].append(f"Failed to import profile '{p.get('name')}': {exc}")
    except ImportError as exc:
        result["warnings"].append(f"Profile import unavailable: {exc}")

    # Import blacklist entries from DB
    try:
        from db.repositories import add_blacklist_entry

        for entry in db_data.get("blacklist", []):
            try:
                add_blacklist_entry(
                    provider_name=entry.get("provider", "unknown"),
                    subtitle_id=entry.get("subtitle_id", ""),
                    language=entry.get("language", ""),
                )
                result["blacklist_imported"] += 1
            except Exception as exc:
                result["warnings"].append(f"Failed to import blacklist entry: {exc}")
    except ImportError as exc:
        result["warnings"].append(f"Blacklist import unavailable: {exc}")

    # Reload settings with new config values
    try:
        from config import reload_settings
        from db.config import get_all_config_entries

        all_overrides = get_all_config_entries()
        reload_settings(all_overrides)
    except Exception as exc:
        result["warnings"].append(f"Settings reload failed: {exc}")

    return result


# ---------------------------------------------------------------------------
# History Import
# ---------------------------------------------------------------------------


def import_bazarr_history(db_data: dict) -> dict:
    """Import Bazarr download history.

    Args:
        db_data: Parsed DB dict from migrate_bazarr_db

    Returns:
        Dict with counts of imported history entries
    """
    result = {
        "history_imported": 0,
        "warnings": [],
    }

    try:
        from db.repositories import add_history_entry

        history_entries = db_data.get("history", [])
        for entry in history_entries:
            try:
                # Map Bazarr history to Sublarr format
                add_history_entry(
                    file_path=entry.get("video_path", ""),
                    provider_name=entry.get("provider", "unknown"),
                    subtitle_id=entry.get("subs_id", ""),
                    language=entry.get("language", ""),
                    score=entry.get("score", 0),
                    downloaded_at=entry.get("timestamp", ""),
                )
                result["history_imported"] += 1
            except Exception as exc:
                result["warnings"].append(f"Failed to import history entry: {exc}")

    except ImportError as exc:
        result["warnings"].append(f"History import unavailable: {exc}")

    return result


# ---------------------------------------------------------------------------
# Provider Settings Mapping
# ---------------------------------------------------------------------------

# Bazarr provider name -> Sublarr provider name mapping
_PROVIDER_MAP = {
    "opensubtitles": "OpenSubtitles",
    "addic7ed": "Addic7ed",
    "podnapisi": "Podnapisi",
    "legendasdivx": "LegendasDivx",
    "subscenter": "SubsCenter",
    "thesubdb": "TheSubDB",
    "tvsubtitles": "TVSubtitles",
}


def map_bazarr_provider_settings(config_data: dict) -> dict:
    """Map Bazarr provider settings to Sublarr provider configuration.

    Args:
        config_data: Parsed config dict from parse_bazarr_config

    Returns:
        Dict with provider mappings and settings
    """
    result = {
        "provider_mappings": {},
        "settings_imported": 0,
        "warnings": [],
    }

    general = config_data.get("general", {})

    # Map OpenSubtitles settings
    if general.get("opensubtitles_api_key"):
        result["provider_mappings"]["OpenSubtitles"] = {
            "api_key": general["opensubtitles_api_key"],
            "username": general.get("opensubtitles_username"),
            "password": general.get("opensubtitles_password"),
        }
        result["settings_imported"] += 1

    # Map other provider settings (if available in config)
    for bazarr_name, sublarr_name in _PROVIDER_MAP.items():
        if bazarr_name == "opensubtitles":
            continue  # Already handled

        # Check for provider-specific settings in config
        provider_key = f"{bazarr_name}_api_key"
        if general.get(provider_key):
            result["provider_mappings"][sublarr_name] = {
                "api_key": general[provider_key],
            }
            result["settings_imported"] += 1

    return result


# ---------------------------------------------------------------------------
# Batch Migration
# ---------------------------------------------------------------------------


def batch_migrate_bazarr_instances(instances: list[dict]) -> dict:
    """Batch migrate multiple Bazarr instances.

    Args:
        instances: List of dicts with "config_path" and/or "db_path" keys

    Returns:
        Dict with migration results for each instance
    """
    from bazarr_migrator import migrate_bazarr_db, parse_bazarr_config

    results = {
        "total": len(instances),
        "successful": 0,
        "failed": 0,
        "instances": [],
    }

    for i, instance in enumerate(instances):
        instance_result = {
            "index": i,
            "config_path": instance.get("config_path"),
            "db_path": instance.get("db_path"),
            "status": "pending",
            "error": None,
            "imported": {},
        }

        try:
            # Parse config if provided
            config_data = {}
            if instance.get("config_path"):
                with open(instance["config_path"], encoding="utf-8") as f:
                    config_content = f.read()
                config_data = parse_bazarr_config(config_content, instance["config_path"])

            # Parse DB if provided
            db_data = {}
            if instance.get("db_path"):
                db_data = migrate_bazarr_db(instance["db_path"])

            # Apply migration
            migration_result = apply_migration(config_data, db_data)

            # Import history
            if db_data:
                history_result = import_bazarr_history(db_data)
                migration_result.update(history_result)

            # Map provider settings
            provider_result = map_bazarr_provider_settings(config_data)
            migration_result["provider_mappings"] = provider_result["provider_mappings"]

            instance_result["status"] = "success"
            instance_result["imported"] = migration_result
            results["successful"] += 1

        except Exception as e:
            instance_result["status"] = "failed"
            instance_result["error"] = str(e)
            results["failed"] += 1
            logger.exception("Batch migration failed for instance %d", i)

        results["instances"].append(instance_result)

    return results
