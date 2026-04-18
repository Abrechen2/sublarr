"""Process-wide singleton accessor for Settings.

Other modules call `get_settings()` to retrieve the active Settings
instance and `reload_settings(overrides=...)` to swap it (e.g. after the
user saves config_entries via the UI).

Importing rule: this module imports `Settings` from `config_settings` at
top level — never the other way round.
"""

import threading

from config_settings import Settings

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


def reload_settings(overrides: dict | None = None) -> Settings:
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


__all__ = ["get_settings", "reload_settings"]
