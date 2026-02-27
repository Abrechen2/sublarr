"""Plugin config repository using SQLAlchemy ORM.

Replaces the raw sqlite3 queries in db/plugins.py with SQLAlchemy ORM
operations. Plugin configs are stored in the config_entries table using
namespaced keys: plugin.<provider_name>.<key>

Return types match the existing functions exactly.
"""

import logging

from sqlalchemy import delete, select

from db.models.core import ConfigEntry
from db.repositories.base import BaseRepository

logger = logging.getLogger(__name__)

_PLUGIN_PREFIX = "plugin."


class PluginRepository(BaseRepository):
    """Repository for plugin configuration stored in config_entries table."""

    def get_plugin_config(self, provider_name: str) -> dict:
        """Read all config entries for a plugin provider.

        Reads from config_entries where key starts with 'plugin.<provider_name>.'.
        Returns a dict with the prefix stripped.

        Returns:
            Dict of {key: value} with the namespace prefix stripped.
        """
        prefix = f"{_PLUGIN_PREFIX}{provider_name}."
        stmt = select(ConfigEntry).where(ConfigEntry.key.like(f"{prefix}%"))
        entries = self.session.execute(stmt).scalars().all()

        config = {}
        for entry in entries:
            bare_key = entry.key[len(prefix):]
            config[bare_key] = entry.value
        return config

    def set_plugin_config(self, provider_name: str, key: str, value: str) -> None:
        """Write a single config entry for a plugin provider.

        Stores in config_entries with key 'plugin.<provider_name>.<key>'.
        """
        full_key = f"{_PLUGIN_PREFIX}{provider_name}.{key}"
        now = self._now()
        entry = ConfigEntry(key=full_key, value=value, updated_at=now)
        self.session.merge(entry)
        self._commit()

    def get_all_plugin_configs(self) -> dict:
        """Get all plugin config entries grouped by provider name.

        Returns:
            Dict of {provider_name: {key: value}} for all plugins.
        """
        stmt = select(ConfigEntry).where(ConfigEntry.key.like(f"{_PLUGIN_PREFIX}%"))
        entries = self.session.execute(stmt).scalars().all()

        configs: dict[str, dict] = {}
        for entry in entries:
            remainder = entry.key[len(_PLUGIN_PREFIX):]
            parts = remainder.split(".", 1)
            if len(parts) != 2:
                continue
            provider_name, config_key = parts
            if provider_name not in configs:
                configs[provider_name] = {}
            configs[provider_name][config_key] = entry.value
        return configs

    def delete_plugin_config(self, provider_name: str) -> int:
        """Delete all config entries for a plugin provider.

        Returns:
            Number of deleted entries.
        """
        prefix = f"{_PLUGIN_PREFIX}{provider_name}."
        result = self.session.execute(
            delete(ConfigEntry).where(ConfigEntry.key.like(f"{prefix}%"))
        )
        self._commit()
        return result.rowcount
