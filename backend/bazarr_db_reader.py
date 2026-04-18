"""Read-only access to a Bazarr SQLite database.

Extracted from bazarr_migrator.py. Provides:

- migrate_bazarr_db(path)      — extract profiles/blacklist/settings/history/shows/movies
- generate_mapping_report(path) — per-table inventory for UI preview (secrets masked)

All connections are opened in SQLite read-only URI mode; caller-facing
functions never mutate the source DB. Warnings (missing tables, schema
drift) are collected into the returned dict rather than raised.
"""

import json
import re
import sqlite3

_VALID_TABLE_NAME = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")

# Fields that may contain sensitive data and should be masked in reports
_SENSITIVE_FIELDS = {"apikey", "api_key", "password", "token", "secret"}


def _validate_table_name(name: str) -> None:
    """Raise ValueError if name is not a valid SQL identifier."""
    if not _VALID_TABLE_NAME.match(name):
        raise ValueError(f"Invalid table name: {name!r}")


def _get_table_info(conn: sqlite3.Connection, table_name: str) -> list:
    """Get column names for a table via PRAGMA table_info.

    Returns:
        List of column name strings, or empty list if table does not exist.
    """
    try:
        _validate_table_name(table_name)
        cursor = conn.execute(f"PRAGMA table_info({table_name})")
        return [row[1] for row in cursor]
    except ValueError:
        return []
    except sqlite3.OperationalError:
        return []


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
                            profile["languages"].append(
                                {
                                    "language": item.get("language", ""),
                                    "hi": item.get("hi", "False"),
                                    "forced": item.get("forced", "False"),
                                }
                            )
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
            blacklist.append(
                {
                    "provider": row_dict.get("provider", ""),
                    "subtitle_id": row_dict.get("subs_id", ""),
                    "timestamp": row_dict.get("timestamp", ""),
                    "language": row_dict.get("language", ""),
                }
            )
    except sqlite3.OperationalError as exc:
        warnings.append(f"table_blacklist not found: {exc}")

    return blacklist


def _read_settings_table(conn: sqlite3.Connection, table_name: str, warnings: list) -> dict:
    """Read a Bazarr settings table (Sonarr or Radarr)."""
    try:
        _validate_table_name(table_name)
        cursor = conn.execute(f"SELECT * FROM {table_name} LIMIT 1")
        row = cursor.fetchone()
        if row:
            return dict(row)
    except ValueError as exc:
        warnings.append(str(exc))
    except sqlite3.OperationalError as exc:
        warnings.append(f"{table_name} not found: {exc}")
    return {}


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
        result["sonarr_config"] = _read_settings_table(
            conn, "table_settings_sonarr", result["warnings"]
        )

        # Read Radarr settings
        result["radarr_config"] = _read_settings_table(
            conn, "table_settings_radarr", result["warnings"]
        )

        # Read history, shows, movies
        result["history"] = _read_history(conn, result["warnings"])
        result["shows"] = _read_shows(conn, result["warnings"])
        result["movies"] = _read_movies(conn, result["warnings"])
    finally:
        conn.close()

    return result


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

            try:
                _validate_table_name(table_name)
            except ValueError:
                report["warnings"].append(f"Skipped table with invalid name: {table_name!r}")
                continue

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
                        row_dict = dict(sample_row)
                        masked = {}
                        for col_name in columns:
                            val = row_dict.get(col_name)
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
                    report["compatibility"]["bazarr_version"] = str(
                        gen_dict.get("bazarr_version", "")
                    )
                    report["compatibility"]["schema_version"] = str(
                        gen_dict.get("db_version", gen_dict.get("schema_version", ""))
                    )
        except sqlite3.OperationalError:
            pass

    finally:
        conn.close()

    return report
