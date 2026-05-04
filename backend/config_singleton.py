"""Process-wide singleton accessor for Settings.

Other modules call ``get_settings()`` to retrieve the active Settings
instance and ``reload_settings(overrides=...)`` to swap it (e.g. after
the user saves config_entries via the UI).

DB ``config_entries`` overrides are applied **only** to ``UISettings``
fields. Boot fields (``BootSettings``) are read once from the environment
at process start and stay fixed for the lifetime of the process —
restart Sublarr to pick up new boot env values.

Importing rule: this module imports ``Settings``/``BootSettings``/
``UISettings`` from ``config_settings`` at top level — never the other
way round.
"""

import threading

from config_settings import BootSettings, Settings, UISettings

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

    Boot fields are re-read from ENV/.env. UI fields start from defaults and
    then have ``overrides`` (from DB ``config_entries``) overlaid on top.

    Args:
        overrides: Dict of UI field name → value (string-form coming from
                   ``config_entries.value``). Boot-field keys in the dict
                   are ignored — boot is ENV-only by design.
    """
    global _settings
    boot = BootSettings()
    ui = UISettings()

    if overrides:
        ui_fields = UISettings.model_fields
        ui_data = ui.model_dump()
        update: dict = {}
        for key, value in overrides.items():
            if key not in ui_fields:
                # Could be a boot-field key (ignored — boot is ENV-only) or
                # an obsolete field from a downgraded install. Drop silently
                # rather than fail loud — config_entries can outlive schema.
                continue
            expected_type = type(ui_data[key])
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
            ui = ui.model_copy(update=update)

    new_settings = Settings(boot=boot, ui=ui)

    with _settings_lock:
        _settings = new_settings
        return _settings


__all__ = ["get_settings", "reload_settings"]
