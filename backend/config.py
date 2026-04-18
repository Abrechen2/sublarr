"""Centralized configuration using Pydantic Settings.

All settings can be overridden via environment variables with the SUBLARR_ prefix,
or via a .env file. Example: SUBLARR_PORT=8080
"""
# ruff: noqa: I001  # Imports are ordered by dependency layer, not alphabetically.

# View classes — re-exported via this module for backwards compatibility.
from config_views import (  # noqa: E402, F401
    GeneralSettings,
    MediaServerSettings,
    ProviderSettings,
    ScanningSettings,
    TranslationSettings,
    _SettingsView,
)

# Settings class — re-exported via this module for backwards compatibility.
from config_settings import Settings  # noqa: E402, F401

# Singleton accessors — re-exported via this module for backwards compatibility.
from config_singleton import get_settings, reload_settings  # noqa: E402, F401

# ─── Re-exports for backwards compatibility ──────────────────────────────────
from config_instances import (  # noqa: E402, F401
    get_media_server_instances,
    get_radarr_instances,
    get_sonarr_instances,
    is_standalone_mode,
)
from config_language_data import (  # noqa: E402, F401
    _LANGUAGE_TAGS,
    SUPPORTED_LANGUAGES,
    _get_language_tags,
)
from config_utils import map_path  # noqa: E402, F401
