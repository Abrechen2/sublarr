"""Blacklist database operations."""

import logging
from datetime import datetime

from db import get_db, _db_lock

logger = logging.getLogger(__name__)


def add_blacklist_entry(provider_name: str, subtitle_id: str,
                        language: str = "", file_path: str = "",
                        title: str = "", reason: str = "") -> int:
    """Add a subtitle to the blacklist. Returns the entry ID."""
    now = datetime.utcnow().isoformat()
    db = get_db()
    with _db_lock:
        cursor = db.execute(
            """INSERT OR IGNORE INTO blacklist_entries
               (provider_name, subtitle_id, language, file_path, title, reason, added_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (provider_name, subtitle_id, language, file_path, title, reason, now),
        )
        db.commit()
        return cursor.lastrowid or 0


def remove_blacklist_entry(entry_id: int) -> bool:
    """Remove a blacklist entry by ID. Returns True if deleted."""
    db = get_db()
    with _db_lock:
        cursor = db.execute("DELETE FROM blacklist_entries WHERE id=?", (entry_id,))
        db.commit()
    return cursor.rowcount > 0


def clear_blacklist() -> int:
    """Remove all blacklist entries. Returns count deleted."""
    db = get_db()
    with _db_lock:
        cursor = db.execute("DELETE FROM blacklist_entries")
        db.commit()
    return cursor.rowcount


def is_blacklisted(provider_name: str, subtitle_id: str) -> bool:
    """Check if a subtitle is blacklisted."""
    db = get_db()
    with _db_lock:
        row = db.execute(
            "SELECT 1 FROM blacklist_entries WHERE provider_name=? AND subtitle_id=?",
            (provider_name, subtitle_id),
        ).fetchone()
    return row is not None


def get_blacklist_entries(page: int = 1, per_page: int = 50) -> dict:
    """Get paginated blacklist entries."""
    db = get_db()
    offset = (page - 1) * per_page

    with _db_lock:
        count = db.execute("SELECT COUNT(*) FROM blacklist_entries").fetchone()[0]
        rows = db.execute(
            "SELECT * FROM blacklist_entries ORDER BY added_at DESC LIMIT ? OFFSET ?",
            (per_page, offset),
        ).fetchall()

    total_pages = max(1, (count + per_page - 1) // per_page)
    return {
        "data": [dict(r) for r in rows],
        "page": page,
        "per_page": per_page,
        "total": count,
        "total_pages": total_pages,
    }


def get_blacklist_count() -> int:
    """Get total number of blacklisted subtitles."""
    db = get_db()
    with _db_lock:
        return db.execute("SELECT COUNT(*) FROM blacklist_entries").fetchone()[0]
