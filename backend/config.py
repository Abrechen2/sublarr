"""Centralized configuration using Pydantic Settings.

Sublarr is **UI-first** since v0.88.0-beta — only a small bootstrap set of
settings (DB URL, mount paths, port, log level, …) is loaded from
``SUBLARR_*`` environment variables. Everything else is configured through
the Settings UI and persisted in the ``config_entries`` table.

Boot fields live on ``BootSettings`` (env-loadable). UI fields live on
``UISettings`` (no env loading — Pydantic ``BaseModel``). The ``Settings``
class is a composite that forwards attribute access to either side.
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

# Settings classes — re-exported via this module for backwards compatibility.
from config_settings import (  # noqa: E402, F401
    BootSettings,
    Settings,
    UISettings,
    warn_on_ignored_env_vars,
)

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
