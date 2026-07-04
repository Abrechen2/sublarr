"""Config entries repository using SQLAlchemy ORM.

Replaces the raw sqlite3 queries in db/config.py with SQLAlchemy ORM
operations. Return types match the existing functions exactly.
"""

import logging

from sqlalchemy import select

from config_crypto import decrypt, encrypt
from db.models.core import ConfigEntry
from db.repositories.base import BaseRepository
from sensitive_keys import is_sensitive_key

logger = logging.getLogger(__name__)


class ConfigRepository(BaseRepository):
    """Repository for config_entries table operations."""

    def save_config_entry(self, key: str, value: str):
        """Save a config entry (INSERT OR REPLACE). Sensitive keys are
        encrypted at rest transparently."""
        stored = encrypt(value) if is_sensitive_key(key) else value
        now = self._now()
        entry = ConfigEntry(key=key, value=stored, updated_at=now)
        self.session.merge(entry)
        self._commit()

    def get_config_entry(self, key: str) -> str | None:
        """Get a config entry value by key (decrypted if encrypted)."""
        entry = self.session.get(ConfigEntry, key)
        return decrypt(entry.value) if entry else None

    def get_all_config_entries(self) -> dict:
        """Get all config entries as a {key: value} dict (values decrypted)."""
        stmt = select(ConfigEntry)
        entries = self.session.execute(stmt).scalars().all()
        return {e.key: decrypt(e.value) for e in entries}
