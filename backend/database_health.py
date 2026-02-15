"""Database health checks and maintenance utilities.

Provides integrity verification, size reporting, and VACUUM
for the Sublarr SQLite database.
"""

import os
import logging
import sqlite3
from typing import Optional

from error_handler import DatabaseIntegrityError

logger = logging.getLogger(__name__)


def check_integrity(db: sqlite3.Connection) -> tuple[bool, str]:
    """Run ``PRAGMA integrity_check`` on the database.

    Returns:
        (is_ok, message) — ``True, "ok"`` when healthy.

    Raises:
        DatabaseIntegrityError: If the check reports corruption.
    """
    try:
        rows = db.execute("PRAGMA integrity_check").fetchall()
        # SQLite returns a single row with "ok" when healthy
        result = rows[0][0] if rows else "unknown"
        is_ok = result == "ok"
        if not is_ok:
            details = "; ".join(r[0] for r in rows[:10])
            logger.error("Integrity check failed: %s", details)
            raise DatabaseIntegrityError(
                f"Integrity check failed: {details}",
                context={"details": details},
            )
        return True, "ok"
    except DatabaseIntegrityError:
        raise
    except Exception as exc:
        logger.error("Integrity check error: %s", exc)
        return False, str(exc)


def get_database_stats(db: sqlite3.Connection, db_path: str) -> dict:
    """Gather useful statistics about the database.

    Returns a dict with keys: ``size_bytes``, ``wal_mode``, ``tables``,
    ``page_size``, ``page_count``, ``freelist_count``.
    """
    stats: dict = {}

    # File size
    try:
        stats["size_bytes"] = os.path.getsize(db_path)
    except OSError:
        stats["size_bytes"] = 0

    # WAL file size
    wal_path = db_path + "-wal"
    try:
        stats["wal_size_bytes"] = os.path.getsize(wal_path) if os.path.exists(wal_path) else 0
    except OSError:
        stats["wal_size_bytes"] = 0

    # PRAGMAs
    for pragma in ("journal_mode", "page_size", "page_count", "freelist_count"):
        try:
            row = db.execute(f"PRAGMA {pragma}").fetchone()
            stats[pragma] = row[0] if row else None
        except Exception:
            stats[pragma] = None

    stats["wal_mode"] = stats.get("journal_mode") == "wal"

    # Row counts per table
    tables: dict[str, int] = {}
    try:
        rows = db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
        for (name,) in rows:
            try:
                count = db.execute(f"SELECT COUNT(*) FROM [{name}]").fetchone()[0]  # noqa: S608
                tables[name] = count
            except Exception:
                tables[name] = -1
    except Exception as exc:
        logger.debug("Could not enumerate tables: %s", exc)

    stats["tables"] = tables
    return stats


def vacuum(db: sqlite3.Connection, db_path: str) -> dict:
    """Run VACUUM and report space savings.

    Returns:
        Dict with ``before_bytes``, ``after_bytes``, ``saved_bytes``.
    """
    before = 0
    try:
        before = os.path.getsize(db_path)
    except OSError:
        pass

    db.execute("VACUUM")

    after = 0
    try:
        after = os.path.getsize(db_path)
    except OSError:
        pass

    saved = before - after
    logger.info("VACUUM complete: %d → %d bytes (saved %d)", before, after, saved)
    return {"before_bytes": before, "after_bytes": after, "saved_bytes": saved}
