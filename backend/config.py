"""Centralized configuration using Pydantic Settings.

All settings can be overridden via environment variables with the SUBLARR_ prefix,
or via a .env file. Example: SUBLARR_PORT=8080
"""

import threading

# Settings class — re-exported via this module for backwards compatibility.
from config_settings import Settings  # noqa: E402

# View classes — re-exported via this module for backwards compatibility.
from config_views import (  # noqa: E402, F401
    GeneralSettings,
    MediaServerSettings,
    ProviderSettings,
    ScanningSettings,
    TranslationSettings,
    _SettingsView,
)

# Singleton settings instance — get_settings() and reload_settings() below
_settings: Settings | None = None
_settings_lock = threading.Lock()


def get_settings() -> Settings:
    """Get or create the singleton Settings instance (thread-safe)."""
    global _settings
    if _settings is not None:
        return _settings
    with _settings_lock:
        if _settings is not None:
            return _settings
        _settings = Settings()
        return _settings


def reload_settings(overrides: dict = None) -> Settings:
    """Force reload settings from environment/file, with optional DB overrides.

    Args:
        overrides: Dict of key-value pairs (from DB config_entries) to apply
                   on top of the env/file settings.
    """
    global _settings
    base = Settings()
    new_settings = base

    if overrides:
        # Build update dict with correct types
        base_data = base.model_dump()
        update = {}
        for key, value in overrides.items():
            if key not in base_data:
                continue
            # Convert string values from DB to the correct field type
            expected_type = type(base_data[key])
            try:
                if expected_type is bool:
                    update[key] = (
                        value.lower() in ("true", "1", "yes")
                        if isinstance(value, str)
                        else bool(value)
                    )
                elif expected_type is int:
                    update[key] = int(value)
                elif expected_type is float:
                    update[key] = float(value)
                else:
                    update[key] = str(value).strip()
            except (ValueError, TypeError):
                continue  # Skip invalid values

        if update:
            new_settings = base.model_copy(update=update)

    with _settings_lock:
        _settings = new_settings

    return _settings


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
