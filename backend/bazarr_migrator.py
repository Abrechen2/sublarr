"""Bazarr configuration and database migration tool.

Parses Bazarr config files (YAML or INI format) and reads Bazarr SQLite databases
to extract language profiles, blacklist entries, and connection settings for import
into Sublarr.
"""

import json
import logging
import sqlite3

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
        "history": [],
        "shows": [],
        "movies": [],
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

        # Read history, shows, movies
        result["history"] = _read_history(conn, result["warnings"])
        result["shows"] = _read_shows(conn, result["warnings"])
        result["movies"] = _read_movies(conn, result["warnings"])
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


def _get_table_info(conn: sqlite3.Connection, table_name: str) -> list:
    """Get column names for a table via PRAGMA table_info.

    Returns:
        List of column name strings, or empty list if table does not exist.
    """
    try:
        cursor = conn.execute(f"PRAGMA table_info({table_name})")
        return [row[1] for row in cursor]
    except sqlite3.OperationalError:
        return []


def _read_history(conn: sqlite3.Connection, warnings: list) -> list:
    """Read download history from Bazarr database.

    Reads the most recent 1000 entries from table_history.
    Uses column discovery to handle schema differences across Bazarr versions.

    Returns:
        List of history entry dicts.
    """
    history = []
    columns = _get_table_info(conn, "table_history")
    if not columns:
        warnings.append("table_history not found or has no columns")
        return history

    target_fields = ["provider", "score", "subs_id", "video_path", "language", "timestamp"]
    select_fields = [f for f in target_fields if f in columns]
    if not select_fields:
        warnings.append("table_history has none of the expected columns")
        return history

    order_col = "timestamp" if "timestamp" in columns else select_fields[0]

    try:
        query = f"SELECT {', '.join(select_fields)} FROM table_history ORDER BY {order_col} DESC LIMIT 1000"
        cursor = conn.execute(query)
        for row in cursor:
            row_dict = dict(zip(select_fields, row))
            history.append({f: row_dict.get(f, "") for f in target_fields})
    except sqlite3.OperationalError as exc:
        warnings.append(f"Failed to read table_history: {exc}")

    return history


def _read_shows(conn: sqlite3.Connection, warnings: list) -> list:
    """Read show entries from Bazarr database.

    Extracts title, path, profileId, audio_language, and sonarrSeriesId
    from table_shows. Uses column discovery for version tolerance.

    Returns:
        List of show dicts.
    """
    shows = []
    columns = _get_table_info(conn, "table_shows")
    if not columns:
        warnings.append("table_shows not found or has no columns")
        return shows

    target_fields = ["title", "path", "profileId", "audio_language", "sonarrSeriesId"]
    select_fields = [f for f in target_fields if f in columns]
    if not select_fields:
        warnings.append("table_shows has none of the expected columns")
        return shows

    try:
        query = f"SELECT {', '.join(select_fields)} FROM table_shows"
        cursor = conn.execute(query)
        for row in cursor:
            row_dict = dict(zip(select_fields, row))
            shows.append({f: row_dict.get(f, "") for f in target_fields})
    except sqlite3.OperationalError as exc:
        warnings.append(f"Failed to read table_shows: {exc}")

    return shows


def _read_movies(conn: sqlite3.Connection, warnings: list) -> list:
    """Read movie entries from Bazarr database.

    Extracts title, path, profileId, audio_language, radarrId, and tmdbId
    from table_movies. Uses column discovery for version tolerance.

    Returns:
        List of movie dicts.
    """
    movies = []
    columns = _get_table_info(conn, "table_movies")
    if not columns:
        warnings.append("table_movies not found or has no columns")
        return movies

    target_fields = ["title", "path", "profileId", "audio_language", "radarrId", "tmdbId"]
    select_fields = [f for f in target_fields if f in columns]
    if not select_fields:
        warnings.append("table_movies has none of the expected columns")
        return movies

    try:
        query = f"SELECT {', '.join(select_fields)} FROM table_movies"
        cursor = conn.execute(query)
        for row in cursor:
            row_dict = dict(zip(select_fields, row))
            movies.append({f: row_dict.get(f, "") for f in target_fields})
    except sqlite3.OperationalError as exc:
        warnings.append(f"Failed to read table_movies: {exc}")

    return movies


# ---------------------------------------------------------------------------
# Mapping Report
# ---------------------------------------------------------------------------

# Fields that may contain sensitive data and should be masked in reports
_SENSITIVE_FIELDS = {"apikey", "api_key", "password", "token", "secret"}


def generate_mapping_report(db_path: str) -> dict:
    """Generate a detailed mapping report of a Bazarr database.

    Opens the database read-only and inventories all tables, providing
    per-table row counts, column lists, and a sample row (with secrets masked).
    Also generates a migration summary and compatibility information.

    Args:
        db_path: Path to the Bazarr SQLite database file.

    Returns:
        Dict with tables_found, table_details, migration_summary,
        compatibility, and warnings.
    """
    report = {
        "tables_found": [],
        "table_details": {},
        "migration_summary": {
            "profiles_count": 0,
            "blacklist_count": 0,
            "shows_count": 0,
            "movies_count": 0,
            "history_count": 0,
            "has_sonarr_config": False,
            "has_radarr_config": False,
        },
        "compatibility": {
            "bazarr_version": "",
            "schema_version": "",
        },
        "warnings": [],
    }

    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
    except sqlite3.Error as exc:
        report["warnings"].append(f"Cannot open database: {exc}")
        return report

    try:
        # Discover all tables
        try:
            cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
            report["tables_found"] = [row[0] for row in cursor]
        except sqlite3.OperationalError as exc:
            report["warnings"].append(f"Cannot read table list: {exc}")
            return report

        # Per-table details
        for table_name in report["tables_found"]:
            detail = {"row_count": 0, "columns": [], "sample_row": None}

            columns = _get_table_info(conn, table_name)
            detail["columns"] = columns

            try:
                count_cursor = conn.execute(f"SELECT COUNT(*) FROM [{table_name}]")
                detail["row_count"] = count_cursor.fetchone()[0]
            except sqlite3.OperationalError:
                pass

            # Get a sample row with secrets masked
            if detail["row_count"] > 0 and columns:
                try:
                    sample_cursor = conn.execute(f"SELECT * FROM [{table_name}] LIMIT 1")
                    sample_row = sample_cursor.fetchone()
                    if sample_row:
                        masked = {}
                        for col_name in columns:
                            val = sample_row.get(col_name, None)
                            if col_name.lower() in _SENSITIVE_FIELDS and val:
                                masked[col_name] = "***"
                            else:
                                masked[col_name] = val
                        detail["sample_row"] = masked
                except sqlite3.OperationalError:
                    pass

            report["table_details"][table_name] = detail

        # Migration summary counts
        profiles_detail = report["table_details"].get("table_languages_profiles", {})
        report["migration_summary"]["profiles_count"] = profiles_detail.get("row_count", 0)

        blacklist_detail = report["table_details"].get("table_blacklist", {})
        report["migration_summary"]["blacklist_count"] = blacklist_detail.get("row_count", 0)

        shows_detail = report["table_details"].get("table_shows", {})
        report["migration_summary"]["shows_count"] = shows_detail.get("row_count", 0)

        movies_detail = report["table_details"].get("table_movies", {})
        report["migration_summary"]["movies_count"] = movies_detail.get("row_count", 0)

        history_detail = report["table_details"].get("table_history", {})
        report["migration_summary"]["history_count"] = history_detail.get("row_count", 0)

        sonarr_detail = report["table_details"].get("table_settings_sonarr", {})
        report["migration_summary"]["has_sonarr_config"] = sonarr_detail.get("row_count", 0) > 0

        radarr_detail = report["table_details"].get("table_settings_radarr", {})
        report["migration_summary"]["has_radarr_config"] = radarr_detail.get("row_count", 0) > 0

        # Compatibility: try to read Bazarr version info
        try:
            general_detail = report["table_details"].get("table_settings_general", {})
            if general_detail.get("row_count", 0) > 0:
                gen_cursor = conn.execute("SELECT * FROM table_settings_general LIMIT 1")
                gen_row = gen_cursor.fetchone()
                if gen_row:
                    gen_dict = dict(gen_row)
                    report["compatibility"]["bazarr_version"] = str(gen_dict.get("bazarr_version", ""))
                    report["compatibility"]["schema_version"] = str(gen_dict.get("db_version", gen_dict.get("schema_version", "")))
        except sqlite3.OperationalError:
            pass

    finally:
        conn.close()

    return report


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

    # Bazarr provider name -> Sublarr provider name mapping
    provider_map = {
        "opensubtitles": "OpenSubtitles",
        "addic7ed": "Addic7ed",
        "subscene": "Subscene",
        "podnapisi": "Podnapisi",
        "legendasdivx": "LegendasDivx",
        "subscenter": "SubsCenter",
        "thesubdb": "TheSubDB",
        "tvsubtitles": "TVSubtitles",
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
    for bazarr_name, sublarr_name in provider_map.items():
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


def batch_migrate_bazarr_instances(instances: list[dict]) -> dict:
    """Batch migrate multiple Bazarr instances.

    Args:
        instances: List of dicts with "config_path" and/or "db_path" keys

    Returns:
        Dict with migration results for each instance
    """
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
