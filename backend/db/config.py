"""Config entries database operations."""

import logging
from datetime import datetime
from typing import Optional

from db import get_db, _db_lock

logger = logging.getLogger(__name__)


def save_config_entry(key: str, value: str):
    """Save a config entry to the database."""
    now = datetime.utcnow().isoformat()
    db = get_db()
    with _db_lock:
        db.execute(
            """INSERT OR REPLACE INTO config_entries (key, value, updated_at)
               VALUES (?, ?, ?)""",
            (key, value, now),
        )
        db.commit()


def get_config_entry(key: str) -> Optional[str]:
    """Get a config entry from the database."""
    db = get_db()
    with _db_lock:
        row = db.execute("SELECT value FROM config_entries WHERE key=?", (key,)).fetchone()
    return row[0] if row else None


def get_all_config_entries() -> dict:
    """Get all config entries."""
    db = get_db()
    with _db_lock:
        rows = db.execute("SELECT key, value FROM config_entries").fetchall()
    return {row[0]: row[1] for row in rows}
