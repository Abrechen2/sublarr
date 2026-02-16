"""Config entries repository using SQLAlchemy ORM.

Replaces the raw sqlite3 queries in db/config.py with SQLAlchemy ORM
operations. Return types match the existing functions exactly.
"""

import logging
from typing import Optional

from sqlalchemy import select

from db.models.core import ConfigEntry
from db.repositories.base import BaseRepository

logger = logging.getLogger(__name__)


class ConfigRepository(BaseRepository):
    """Repository for config_entries table operations."""

    def save_config_entry(self, key: str, value: str):
        """Save a config entry to the database (INSERT OR REPLACE)."""
        now = self._now()
        entry = ConfigEntry(key=key, value=value, updated_at=now)
        self.session.merge(entry)
        self._commit()

    def get_config_entry(self, key: str) -> Optional[str]:
        """Get a config entry value by key.

        Returns:
            The value string, or None if key not found.
        """
        entry = self.session.get(ConfigEntry, key)
        return entry.value if entry else None

    def get_all_config_entries(self) -> dict:
        """Get all config entries as a {key: value} dict.

        Returns:
            Dict mapping config key to value string.
        """
        stmt = select(ConfigEntry)
        entries = self.session.execute(stmt).scalars().all()
        return {e.key: e.value for e in entries}
