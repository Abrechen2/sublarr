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

# Boot fields that, although env-loadable and read at process start, are safe
# to reconfigure at runtime and are therefore ALSO overridable from the DB
# ``config_entries`` (set via the UI). Logging is fully re-applied live by
# ``_setup_logging`` on save, so a UI change to these takes effect without a
# restart and survives one (DB override wins over ENV once the user sets it).
# Everything else in ``_ALLOWED_BOOT_FIELDS`` (port, paths, database_url, …)
# stays ENV-only.
_RUNTIME_OVERRIDABLE_BOOT_FIELDS: frozenset[str] = frozenset(
    {"log_level", "log_file", "log_format"}
)


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


def peek_settings() -> Settings | None:
    """The active settings if they exist — never builds them.

    ``get_settings()`` builds the singleton on first use by merging the
    database overrides onto the defaults, which needs a Flask application
    context. A caller that runs outside one — WSGI middleware, in particular —
    would otherwise cache a Settings object with every stored setting missing,
    and every later reader would get that object.

    Callers in that position ask here instead and treat ``None`` as "too early,
    use the default". The app builds the singleton during startup, so in
    practice this returns it from the first request onwards.
    """
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
        # DB overrides for the UI fields and the runtime-reconfigurable boot
        # fields (logging), decoded by type and validated (#61 A04: model_copy
        # skipped validators, and lists arrived as their string form).
        from config_values import apply_overrides

        boot_override = {
            key: value
            for key, value in overrides.items()
            if key in _RUNTIME_OVERRIDABLE_BOOT_FIELDS and value not in (None, "")
        }
        if boot_override:
            boot = apply_overrides(boot, boot_override)
        ui = apply_overrides(ui, overrides)

    new_settings = Settings(boot=boot, ui=ui)

    with _settings_lock:
        _settings = new_settings
        return _settings


__all__ = ["get_settings", "reload_settings"]
