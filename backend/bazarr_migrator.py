"""Bazarr configuration and database migration tool.

Parses Bazarr config files (YAML or INI format) and reads Bazarr SQLite databases
to extract language profiles, blacklist entries, and connection settings for import
into Sublarr.
"""

import json
import logging
import sqlite3
from typing import Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Config Parsing
# ---------------------------------------------------------------------------

def parse_bazarr_config(file_content: str, filename: str) -> dict:
    """Parse a Bazarr config file into a normalized dict.

    Supports both YAML (.yaml/.yml) and INI (.ini/.cfg) formats.
    If format cannot be determined from filename, tries YAML first, then INI.

    Args:
        file_content: The raw text content of the config file.
        filename: The original filename (used for format detection).

    Returns:
        Normalized dict with keys: sonarr, radarr, general, raw, warnings.
    """
    if not file_content or not file_content.strip():
        return {"sonarr": {}, "radarr": {}, "general": {}, "raw": {}, "warnings": ["Empty config file"]}

    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

    if ext in ("yaml", "yml"):
        return _parse_yaml(file_content)
    elif ext in ("ini", "cfg"):
        return _parse_ini(file_content)
    else:
        # Try YAML first, then INI
        result = _parse_yaml(file_content)
        if result.get("raw"):
            return result
        return _parse_ini(file_content)


def _parse_yaml(content: str) -> dict:
    """Parse YAML format Bazarr config."""
    warnings = []
    try:
        import yaml
        data = yaml.safe_load(content)
    except ImportError:
        warnings.append("PyYAML not installed -- cannot parse YAML config")
        return {"sonarr": {}, "radarr": {}, "general": {}, "raw": {}, "warnings": warnings}
    except Exception as exc:
        warnings.append(f"YAML parse error: {exc}")
        return {"sonarr": {}, "radarr": {}, "general": {}, "raw": {}, "warnings": warnings}

    if not isinstance(data, dict):
        warnings.append("YAML content is not a mapping")
        return {"sonarr": {}, "radarr": {}, "general": {}, "raw": {}, "warnings": warnings}

    return _normalize_config(data, warnings)


def _parse_ini(content: str) -> dict:
    """Parse INI format Bazarr config."""
    import configparser
    import io

    warnings = []
    parser = configparser.ConfigParser()
    try:
        parser.read_string(content)
    except configparser.Error as exc:
        warnings.append(f"INI parse error: {exc}")
        return {"sonarr": {}, "radarr": {}, "general": {}, "raw": {}, "warnings": warnings}

    # Convert sections to nested dict
    data = {}
    for section in parser.sections():
        data[section] = dict(parser[section])

    return _normalize_config(data, warnings)


def _normalize_config(data: dict, warnings: list) -> dict:
    """Normalize parsed config data into a standard structure.

    Extracts Sonarr, Radarr, and general settings from Bazarr config
    regardless of the original format.
    """
    result = {
        "sonarr": {},
        "radarr": {},
        "general": {},
        "raw": data,
        "warnings": warnings,
    }

    # Extract Sonarr settings (Bazarr uses 'sonarr' section)
    sonarr = data.get("sonarr", data.get("Sonarr", {}))
    if isinstance(sonarr, dict):
        result["sonarr"] = {
            "url": sonarr.get("ip", sonarr.get("base_url", "")),
            "port": sonarr.get("port", ""),
            "api_key": sonarr.get("apikey", sonarr.get("api_key", "")),
            "base_url": sonarr.get("base_url", ""),
        }

    # Extract Radarr settings
    radarr = data.get("radarr", data.get("Radarr", {}))
    if isinstance(radarr, dict):
        result["radarr"] = {
            "url": radarr.get("ip", radarr.get("base_url", "")),
            "port": radarr.get("port", ""),
            "api_key": radarr.get("apikey", radarr.get("api_key", "")),
            "base_url": radarr.get("base_url", ""),
        }

    # Extract general settings
    general = data.get("general", data.get("General", {}))
    if isinstance(general, dict):
        result["general"] = {
            "source_language": general.get("serie_default_language", general.get("default_language", "")),
            "target_language": general.get("serie_default_hi", ""),
            "use_embedded": general.get("use_embedded_subs", general.get("embedded_subs_show_desired", "")),
            "branch": general.get("branch", ""),
        }

    # Extract subtitle provider settings
    providers_section = data.get("opensubtitles", data.get("OpenSubtitles", data.get("opensubtitlescom", {})))
    if isinstance(providers_section, dict):
        result["general"]["opensubtitles_username"] = providers_section.get("username", "")
        result["general"]["opensubtitles_password"] = providers_section.get("password", "")
        result["general"]["opensubtitles_api_key"] = providers_section.get("apikey", "")

    return result


# ---------------------------------------------------------------------------
# Database Migration
# ---------------------------------------------------------------------------

def migrate_bazarr_db(db_path: str) -> dict:
    """Read a Bazarr SQLite database and extract relevant data.

    Opens the database read-only. Extracts:
    - Language profiles from table_languages_profiles
    - Blacklist entries from table_blacklist
    - Sonarr connection settings from table_settings_sonarr
    - Radarr connection settings from table_settings_radarr

    Args:
        db_path: Path to the Bazarr SQLite database file.

    Returns:
        Dict with profiles, blacklist, sonarr_config, radarr_config, and warnings.
    """
    result = {
        "profiles": [],
        "blacklist": [],
        "sonarr_config": {},
        "radarr_config": {},
        "warnings": [],
    }

    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
    except sqlite3.Error as exc:
        result["warnings"].append(f"Cannot open database: {exc}")
        return result

    try:
        # Read language profiles
        result["profiles"] = _read_language_profiles(conn, result["warnings"])

        # Read blacklist
        result["blacklist"] = _read_blacklist(conn, result["warnings"])

        # Read Sonarr settings
        result["sonarr_config"] = _read_settings_table(conn, "table_settings_sonarr", result["warnings"])

        # Read Radarr settings
        result["radarr_config"] = _read_settings_table(conn, "table_settings_radarr", result["warnings"])
    finally:
        conn.close()

    return result


def _read_language_profiles(conn: sqlite3.Connection, warnings: list) -> list:
    """Read language profiles from Bazarr database."""
    profiles = []
    try:
        cursor = conn.execute("SELECT * FROM table_languages_profiles")
        for row in cursor:
            row_dict = dict(row)
            profile = {
                "name": row_dict.get("name", "Unnamed"),
                "languages": [],
            }

            # Bazarr stores languages as JSON array in 'items' column
            items_raw = row_dict.get("items", "[]")
            try:
                items = json.loads(items_raw) if isinstance(items_raw, str) else items_raw
                if isinstance(items, list):
                    for item in items:
                        if isinstance(item, dict):
                            profile["languages"].append({
                                "language": item.get("language", ""),
                                "hi": item.get("hi", "False"),
                                "forced": item.get("forced", "False"),
                            })
            except (json.JSONDecodeError, TypeError):
                warnings.append(f"Could not parse languages for profile '{profile['name']}'")

            # Include cutoff and original profile_id for reference
            profile["cutoff"] = row_dict.get("cutoff")
            profile["profile_id"] = row_dict.get("profileId", row_dict.get("id"))
            profiles.append(profile)
    except sqlite3.OperationalError as exc:
        warnings.append(f"table_languages_profiles not found: {exc}")

    return profiles


def _read_blacklist(conn: sqlite3.Connection, warnings: list) -> list:
    """Read blacklist entries from Bazarr database."""
    blacklist = []
    try:
        cursor = conn.execute("SELECT * FROM table_blacklist")
        for row in cursor:
            row_dict = dict(row)
            blacklist.append({
                "provider": row_dict.get("provider", ""),
                "subtitle_id": row_dict.get("subs_id", ""),
                "timestamp": row_dict.get("timestamp", ""),
                "language": row_dict.get("language", ""),
            })
    except sqlite3.OperationalError as exc:
        warnings.append(f"table_blacklist not found: {exc}")

    return blacklist


def _read_settings_table(conn: sqlite3.Connection, table_name: str, warnings: list) -> dict:
    """Read a Bazarr settings table (Sonarr or Radarr)."""
    try:
        cursor = conn.execute(f"SELECT * FROM {table_name} LIMIT 1")
        row = cursor.fetchone()
        if row:
            return dict(row)
    except sqlite3.OperationalError as exc:
        warnings.append(f"{table_name} not found: {exc}")
    return {}


# ---------------------------------------------------------------------------
# Preview & Apply
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
        preview["config_entries"].append({
            "key": "sonarr_url",
            "value": url,
            "source": "Bazarr config (sonarr)",
        })
        preview["config_entries"].append({
            "key": "sonarr_api_key",
            "value": _mask_preview(sonarr["api_key"]),
            "source": "Bazarr config (sonarr)",
        })

    radarr = config_data.get("radarr", {})
    if radarr.get("url") and radarr.get("api_key"):
        url = radarr["url"]
        port = radarr.get("port", "")
        if port:
            url = f"{url}:{port}"
        preview["config_entries"].append({
            "key": "radarr_url",
            "value": url,
            "source": "Bazarr config (radarr)",
        })
        preview["config_entries"].append({
            "key": "radarr_api_key",
            "value": _mask_preview(radarr["api_key"]),
            "source": "Bazarr config (radarr)",
        })

    general = config_data.get("general", {})
    if general.get("opensubtitles_api_key"):
        preview["config_entries"].append({
            "key": "opensubtitles_api_key",
            "value": _mask_preview(general["opensubtitles_api_key"]),
            "source": "Bazarr config (opensubtitles)",
        })
    if general.get("opensubtitles_username"):
        preview["config_entries"].append({
            "key": "opensubtitles_username",
            "value": general["opensubtitles_username"],
            "source": "Bazarr config (opensubtitles)",
        })

    # Profiles from DB
    for p in db_data.get("profiles", []):
        lang_list = [lang.get("language", "?") for lang in p.get("languages", [])]
        preview["profiles"].append({
            "name": p.get("name", "Unnamed"),
            "languages": lang_list,
        })

    # Blacklist count
    preview["blacklist_count"] = len(db_data.get("blacklist", []))

    return preview


def _mask_preview(val: str) -> str:
    """Mask a value for preview display."""
    if not val or len(val) <= 4:
        return "***"
    return val[:4] + "***"


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
