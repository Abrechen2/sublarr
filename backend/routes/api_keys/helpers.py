"""Static registry + generic helpers for the API-keys module."""

from __future__ import annotations

API_KEY_REGISTRY: dict[str, dict] = {
    "sublarr": {
        "keys": ["api_key"],
        "test_fn": None,
        "label": "Sublarr",
    },
    "sonarr": {
        "keys": ["sonarr_api_key"],
        "test_fn": "_test_sonarr",
        "label": "Sonarr",
    },
    "radarr": {
        "keys": ["radarr_api_key"],
        "test_fn": "_test_radarr",
        "label": "Radarr",
    },
    "opensubtitles": {
        "keys": ["opensubtitles_api_key", "opensubtitles_username", "opensubtitles_password"],
        "test_fn": "_test_provider",
        "label": "OpenSubtitles",
    },
    "jimaku": {
        "keys": ["jimaku_api_key"],
        "test_fn": "_test_provider",
        "label": "Jimaku",
    },
    "subdl": {
        "keys": ["subdl_api_key"],
        "test_fn": "_test_provider",
        "label": "SubDL",
    },
    "tmdb": {
        "keys": ["tmdb_api_key"],
        "test_fn": None,
        "label": "TMDB",
    },
    "tvdb": {
        "keys": ["tvdb_api_key"],
        "test_fn": None,
        "label": "TVDB",
    },
    "deepl": {
        "keys": ["deepl_api_key"],
        "test_fn": "_test_deepl",
        "label": "DeepL",
    },
    "apprise": {
        "keys": ["notification_urls_json"],
        "test_fn": "_test_apprise",
        "label": "Apprise Notifications",
    },
}


def _mask_value(val: str) -> str:
    """Mask a secret value, showing first 4 + '***' + last 4 chars.

    Returns all '***' if the value is 8 chars or fewer.
    """
    if not val:
        return ""
    if len(val) <= 8:
        return "***"
    return val[:4] + "***" + val[-4:]


def _get_service_info(service_name: str) -> dict | None:
    """Build a status dict for a single registered service."""
    from db.config import get_config_entry

    entry = API_KEY_REGISTRY.get(service_name)
    if entry is None:
        return None

    keys_list = []
    for key_name in entry["keys"]:
        raw = get_config_entry(key_name) or ""
        keys_list.append(
            {
                "name": key_name,
                "status": "configured" if raw else "missing",
                "masked_value": _mask_value(raw) if raw else "(not set)",
            }
        )

    all_configured = all(k["status"] == "configured" for k in keys_list)
    any_configured = any(k["status"] == "configured" for k in keys_list)

    return {
        "service": service_name,
        "label": entry["label"],
        "keys": keys_list,
        "status": "configured" if all_configured else ("partial" if any_configured else "missing"),
        "testable": entry["test_fn"] is not None,
    }
