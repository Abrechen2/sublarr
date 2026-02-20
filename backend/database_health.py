"""Dialect-aware database health checks and maintenance utilities.

Supports both SQLite and PostgreSQL backends:

- **SQLite:** PRAGMA integrity_check, page/freelist stats, VACUUM.
- **PostgreSQL:** pg_stat queries, database/table sizes, connection pool,
  active connections, index usage.

Both backends return the same top-level dict shape from ``get_health_report()``.
"""

import os
import logging
import sqlite3
from typing import Optional

from error_handler import DatabaseIntegrityError

logger = logging.getLogger(__name__)


def _is_postgresql() -> bool:
    """Detect if the current database backend is PostgreSQL."""
    try:
        from extensions import db
        return db.engine.dialect.name == "postgresql"
    except Exception:
        return False


# ── Unified entry points ─────────────────────────────────────────────────────


def get_health_report() -> dict:
    """Return a unified health report for the active database backend.

    Returns:
        Dict with ``status`` ("healthy" | "degraded" | "unhealthy"),
        ``backend`` ("sqlite" | "postgresql"), and ``details``.
    """
    if _is_postgresql():
        return _pg_health_report()
    return _sqlite_health_report()


def get_pool_stats() -> Optional[dict]:
    """Return connection pool statistics (PostgreSQL only).

    Returns None for SQLite (which uses StaticPool / NullPool).
    """
    if not _is_postgresql():
        return None

    try:
        from extensions import db
        pool = db.engine.pool
        return {
            "size": pool.size(),
            "checked_in": pool.checkedin(),
            "checked_out": pool.checkedout(),
            "overflow": pool.overflow(),
            "status": pool.status(),
        }
    except Exception as exc:
        logger.warning("Could not retrieve pool stats: %s", exc)
        return None


# ── SQLite health ─────────────────────────────────────────────────────────────


def _sqlite_health_report() -> dict:
    """Build a health report for SQLite backend."""
    from db import get_db
    from config import get_settings

    db = get_db()
    s = get_settings()

    is_ok, message = check_integrity(db)
    stats = get_database_stats(db, s.db_path)

    status = "healthy" if is_ok else "unhealthy"
    return {
        "status": status,
        "backend": "sqlite",
        "details": {
            "integrity": {"ok": is_ok, "message": message},
            "size_bytes": stats.get("size_bytes", 0),
            "wal_mode": stats.get("wal_mode", False),
            "wal_size_bytes": stats.get("wal_size_bytes", 0),
            "page_size": stats.get("page_size"),
            "page_count": stats.get("page_count"),
            "freelist_count": stats.get("freelist_count"),
            "tables": stats.get("tables", {}),
        },
    }


def check_integrity(db) -> tuple[bool, str]:
    """Run ``PRAGMA integrity_check`` on the database.

    Returns:
        (is_ok, message) -- ``True, "ok"`` when healthy.

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


def get_database_stats(db, db_path: str) -> dict:
    """Gather useful statistics about a SQLite database.

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


def vacuum(db, db_path: str) -> dict:
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
    logger.info("VACUUM complete: %d -> %d bytes (saved %d)", before, after, saved)
    return {"before_bytes": before, "after_bytes": after, "saved_bytes": saved}


# ── PostgreSQL health ─────────────────────────────────────────────────────────


def _pg_health_report() -> dict:
    """Build a health report for PostgreSQL backend."""
    from extensions import db as sa_db
    from sqlalchemy import text

    details: dict = {}
    status = "healthy"

    try:
        with sa_db.engine.connect() as conn:
            # Database size
            try:
                row = conn.execute(
                    text("SELECT pg_database_size(current_database())")
                ).fetchone()
                details["size_bytes"] = row[0] if row else 0
            except Exception as exc:
                logger.warning("Could not get database size: %s", exc)
                details["size_bytes"] = 0

            # Active connections
            try:
                row = conn.execute(
                    text("SELECT count(*) FROM pg_stat_activity WHERE datname = current_database()")
                ).fetchone()
                details["active_connections"] = row[0] if row else 0
            except Exception as exc:
                logger.warning("Could not get active connections: %s", exc)
                details["active_connections"] = -1

            # Table sizes (top 20)
            try:
                rows = conn.execute(
                    text(
                        "SELECT relname, pg_relation_size(oid) as size "
                        "FROM pg_class WHERE relkind = 'r' "
                        "AND relnamespace = (SELECT oid FROM pg_namespace WHERE nspname = 'public') "
                        "ORDER BY size DESC LIMIT 20"
                    )
                ).fetchall()
                details["table_sizes"] = {
                    row[0]: row[1] for row in rows
                }
            except Exception as exc:
                logger.warning("Could not get table sizes: %s", exc)
                details["table_sizes"] = {}

            # Row counts per table
            tables: dict[str, int] = {}
            try:
                table_rows = conn.execute(
                    text(
                        "SELECT relname, n_live_tup FROM pg_stat_user_tables "
                        "ORDER BY n_live_tup DESC"
                    )
                ).fetchall()
                for row in table_rows:
                    tables[row[0]] = row[1]
            except Exception as exc:
                logger.warning("Could not get table row counts: %s", exc)
            details["tables"] = tables

            # Index usage (top 10)
            try:
                rows = conn.execute(
                    text(
                        "SELECT indexrelname, idx_scan "
                        "FROM pg_stat_user_indexes "
                        "ORDER BY idx_scan DESC LIMIT 10"
                    )
                ).fetchall()
                details["index_usage"] = {
                    row[0]: row[1] for row in rows
                }
            except Exception as exc:
                logger.warning("Could not get index usage: %s", exc)
                details["index_usage"] = {}

            # Connection check (simple query)
            try:
                conn.execute(text("SELECT 1"))
                details["connection_ok"] = True
            except Exception:
                details["connection_ok"] = False
                status = "unhealthy"

    except Exception as exc:
        logger.error("PostgreSQL health check failed: %s", exc)
        status = "unhealthy"
        details["error"] = str(exc)

    # Connection pool stats
    pool_stats = get_pool_stats()
    if pool_stats:
        details["pool"] = pool_stats

    return {
        "status": status,
        "backend": "postgresql",
        "details": details,
    }
