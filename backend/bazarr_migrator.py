"""Bazarr configuration parser + re-exports for the wider migration toolchain.

This module keeps the config-file parsing logic (YAML/INI -> normalized
dict) and re-exports the DB-reading helpers (bazarr_db_reader) and the
data-mapping / preview / apply helpers (bazarr_data_mapper). Callers
continue to import everything from ``bazarr_migrator``:

    from bazarr_migrator import (
        parse_bazarr_config,
        migrate_bazarr_db,
        generate_mapping_report,
        preview_migration,
        apply_migration,
    )
"""

import logging

from bazarr_data_mapper import (  # noqa: F401 — re-exported for back-compat
    _mask_preview,
    apply_migration,
    batch_migrate_bazarr_instances,
    import_bazarr_history,
    map_bazarr_provider_settings,
    preview_migration,
)
from bazarr_db_reader import (  # noqa: F401 — re-exported for back-compat
    _SENSITIVE_FIELDS,
    _get_table_info,
    _read_blacklist,
    _read_history,
    _read_language_profiles,
    _read_movies,
    _read_settings_table,
    _read_shows,
    _validate_table_name,
    generate_mapping_report,
    migrate_bazarr_db,
)

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
        return {
            "sonarr": {},
            "radarr": {},
            "general": {},
            "raw": {},
            "warnings": ["Empty config file"],
        }

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
            "source_language": general.get(
                "serie_default_language", general.get("default_language", "")
            ),
            "target_language": general.get("serie_default_hi", ""),
            "use_embedded": general.get(
                "use_embedded_subs", general.get("embedded_subs_show_desired", "")
            ),
            "branch": general.get("branch", ""),
        }

    # Extract subtitle provider settings
    providers_section = data.get(
        "opensubtitles", data.get("OpenSubtitles", data.get("opensubtitlescom", {}))
    )
    if isinstance(providers_section, dict):
        result["general"]["opensubtitles_username"] = providers_section.get("username", "")
        result["general"]["opensubtitles_password"] = providers_section.get("password", "")
        result["general"]["opensubtitles_api_key"] = providers_section.get("apikey", "")

    return result
