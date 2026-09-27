"""Bazarr data mapping, preview, and import application.

Transforms parsed Bazarr config and database data into Sublarr format.
Handles migration preview generation, config/profile/blacklist/history import,
provider setting mapping, and batch migration orchestration.
"""

import logging
import re

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Preview & Masking
# ---------------------------------------------------------------------------


def preview_migration(config_data: dict, db_data: dict, current: dict | None = None) -> dict:
    """Generate a human-readable preview of what the migration will import.

    Args:
        config_data: Parsed config dict (from parse_bazarr_config).
        db_data: Parsed DB dict (from migrate_bazarr_db).
        current: The config entries stored today, so each planned entry can
            show what it would overwrite. Secrets are masked on both sides.

    Returns:
        Dict with sections describing each import category.
    """
    current = current or {}
    preview = {
        "config_entries": [],
        "profiles": [],
        "blacklist_count": 0,
        "warnings": [],
    }

    # Collect warnings from both sources
    preview["warnings"].extend(config_data.get("warnings", []))
    preview["warnings"].extend(db_data.get("warnings", []))

    for key, value, source in planned_config_entries(config_data):
        existing = str(current.get(key) or "")
        secret = _is_secret(key)
        preview["config_entries"].append(
            {
                "key": key,
                "value": _mask_preview(value) if secret else value,
                "current_value": (_mask_preview(existing) if secret else existing)
                if existing
                else "",
                "source": source,
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


def _is_secret(key: str) -> bool:
    return "api_key" in key or "password" in key


def _truthy(value) -> bool:
    return str(value).strip().lower() in ("true", "1", "yes", "on")


def arr_url(section: dict) -> str:
    """Join Bazarr's separate host/port/ssl/base_url fields into one URL.

    ``{"url": "10.0.0.5", "port": 8989, "ssl": False, "base_url": "/sonarr"}``
    becomes ``http://10.0.0.5:8989/sonarr``. A host that already carries a
    scheme is kept as given (only the port and path are added).
    """
    host = str(section.get("url") or "").strip().rstrip("/")
    if not host:
        return ""
    if "://" in host:
        scheme, host = host.split("://", 1)
    else:
        scheme = "https" if _truthy(section.get("ssl")) else "http"
    if host.count(":") > 1 and not host.startswith("["):
        host = f"[{host}]"  # a bare IPv6 literal needs brackets before a port
    port = str(section.get("port") or "").strip()
    # "sonarr:8989" or "[::1]:8989" already carry their port.
    if port and not re.search(r"(^[^:]*|\]):\d+$", host):
        host = f"{host}:{port}"
    path = str(section.get("base_url") or "").strip().strip("/")
    return f"{scheme}://{host}/{path}" if path else f"{scheme}://{host}"


def planned_config_entries(config_data: dict) -> list[tuple[str, str, str]]:
    """The (key, value, source) config entries an import would write.

    Preview and apply both read this list, so what the user confirms is what
    gets written.
    """
    entries: list[tuple[str, str, str]] = []
    for arr in ("sonarr", "radarr"):
        section = config_data.get(arr) or {}
        url = arr_url(section)
        api_key = str(section.get("api_key") or "").strip()
        if url and api_key:
            source = f"Bazarr config ({arr})"
            entries.append((f"{arr}_url", url, source))
            entries.append((f"{arr}_api_key", api_key, source))

    general = config_data.get("general") or {}
    for field in ("opensubtitles_api_key", "opensubtitles_username", "opensubtitles_password"):
        value = str(general.get(field) or "").strip()
        if value:
            entries.append((field, value, "Bazarr config (opensubtitles)"))
    return entries


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
        "saved_keys": [],
    }

    # Config entries — a URL goes through the same SSRF guard PUT /config
    # applies, and a refused URL takes its API key with it (half a connection
    # is worse than none: the key would sit next to the old URL).
    from security_utils import validate_service_url

    refused: set[str] = set()
    planned = planned_config_entries(config_data)
    for key, value, _source in planned:
        if key.endswith("_url"):
            ok, reason = validate_service_url(value)
            if not ok:
                refused.add(key[: -len("_url")])
                result["warnings"].append(
                    f"{key} not imported: {reason}. Set it under Settings instead."
                )
    for key, value, _source in planned:
        if key.split("_", 1)[0] in refused:
            continue
        save_config_entry(key, value)
        result["config_imported"] += 1
        result["saved_keys"].append(key)

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
