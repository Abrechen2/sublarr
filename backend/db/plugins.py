"""Plugin config CRUD with namespaced config_entries storage.

Plugin configs are stored in the existing config_entries table using
namespaced keys: plugin.<provider_name>.<key>

This avoids adding new tables while keeping plugin config isolated
from app-level settings.
"""

import logging
from datetime import datetime

from db import get_db, _db_lock

logger = logging.getLogger(__name__)

_PLUGIN_PREFIX = "plugin."


def get_plugin_config(provider_name: str) -> dict:
    """Read all config entries for a plugin provider.

    Reads from config_entries where key starts with 'plugin.<provider_name>.'.
    Returns a dict with the prefix stripped, e.g.:
        plugin.myprovider.api_key -> {"api_key": "value"}

    Args:
        provider_name: The plugin provider name.

    Returns:
        Dict of {key: value} with the namespace prefix stripped.
    """
    prefix = f"{_PLUGIN_PREFIX}{provider_name}."
    db = get_db()
    with _db_lock:
        rows = db.execute(
            "SELECT key, value FROM config_entries WHERE key LIKE ?",
            (f"{prefix}%",),
        ).fetchall()

    config = {}
    for row in rows:
        # Strip the "plugin.<name>." prefix to get the bare key
        bare_key = row["key"][len(prefix):]
        config[bare_key] = row["value"]

    return config


def set_plugin_config(provider_name: str, key: str, value: str) -> None:
    """Write a single config entry for a plugin provider.

    Stores in config_entries with key 'plugin.<provider_name>.<key>'.

    Args:
        provider_name: The plugin provider name.
        key: The config key (without namespace prefix).
        value: The config value.
    """
    full_key = f"{_PLUGIN_PREFIX}{provider_name}.{key}"
    now = datetime.utcnow().isoformat()
    db = get_db()
    with _db_lock:
        db.execute(
            """INSERT INTO config_entries (key, value, updated_at)
               VALUES (?, ?, ?)
               ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at""",
            (full_key, value, now),
        )
        db.commit()


def get_all_plugin_configs() -> dict[str, dict]:
    """Get all plugin config entries grouped by provider name.

    Returns:
        Dict of {provider_name: {key: value}} for all plugins.
    """
    db = get_db()
    with _db_lock:
        rows = db.execute(
            "SELECT key, value FROM config_entries WHERE key LIKE ?",
            (f"{_PLUGIN_PREFIX}%",),
        ).fetchall()

    configs: dict[str, dict] = {}
    for row in rows:
        # key format: plugin.<provider_name>.<config_key>
        remainder = row["key"][len(_PLUGIN_PREFIX):]
        parts = remainder.split(".", 1)
        if len(parts) != 2:
            continue
        provider_name, config_key = parts
        if provider_name not in configs:
            configs[provider_name] = {}
        configs[provider_name][config_key] = row["value"]

    return configs


def delete_plugin_config(provider_name: str) -> int:
    """Delete all config entries for a plugin provider.

    Args:
        provider_name: The plugin provider name.

    Returns:
        Number of deleted entries.
    """
    prefix = f"{_PLUGIN_PREFIX}{provider_name}."
    db = get_db()
    with _db_lock:
        cursor = db.execute(
            "DELETE FROM config_entries WHERE key LIKE ?",
            (f"{prefix}%",),
        )
        db.commit()
        return cursor.rowcount
