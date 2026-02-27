"""Transaction context manager for safe database writes.

Wraps database operations in SQLAlchemy transactions with automatic
rollback on failure. Backward-compatible: if called with a sqlite3
connection argument, delegates to the legacy pattern.
"""

import logging
import sqlite3
from collections.abc import Generator
from contextlib import contextmanager

from error_handler import DatabaseError

logger = logging.getLogger(__name__)


@contextmanager
def _legacy_transaction(db_conn: sqlite3.Connection):
    """Legacy sqlite3 transaction (kept for backward compatibility)."""
    cursor = db_conn.cursor()
    try:
        yield cursor
        db_conn.commit()
    except sqlite3.IntegrityError as exc:
        db_conn.rollback()
        logger.warning("Transaction rolled back (integrity): %s", exc)
        raise DatabaseError(
            str(exc),
            code="DB_002",
            context={"sqlite_error": type(exc).__name__},
        ) from exc
    except sqlite3.Error as exc:
        db_conn.rollback()
        logger.error("Transaction rolled back (sqlite): %s", exc)
        raise DatabaseError(
            str(exc),
            context={"sqlite_error": type(exc).__name__},
        ) from exc
    except Exception as exc:
        db_conn.rollback()
        logger.error("Transaction rolled back (unexpected): %s", exc)
        raise
    finally:
        cursor.close()


@contextmanager
def _sqlalchemy_transaction():
    """SQLAlchemy session-based transaction."""
    from extensions import db
    try:
        yield db.session
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        logger.error("Transaction rolled back: %s", exc)
        raise


@contextmanager
def transaction(db_conn=None) -> Generator:
    """Execute database writes inside a transaction.

    If called without arguments (or with None), uses SQLAlchemy session.
    If called with a sqlite3.Connection, uses the legacy sqlite3 pattern.

    Usage (SQLAlchemy)::

        with transaction() as session:
            session.execute(...)

    Usage (Legacy sqlite3 -- backward compat)::

        with transaction(sqlite3_conn) as cursor:
            cursor.execute("INSERT INTO ...", (...))

    Yields:
        SQLAlchemy session (no args) or sqlite3.Cursor (with connection arg).

    Raises:
        DatabaseError: If the transaction fails and is rolled back.
    """
    if db_conn is not None and isinstance(db_conn, sqlite3.Connection):
        # Legacy sqlite3 path
        with _legacy_transaction(db_conn) as cursor:
            yield cursor
    else:
        # SQLAlchemy session path
        with _sqlalchemy_transaction() as session:
            yield session
