"""Transaction context manager for safe database writes.

Wraps database operations in explicit transactions with automatic
rollback on failure. Works with the existing _db_lock pattern in database.py.
"""

import logging
import sqlite3
from contextlib import contextmanager
from typing import Generator

from error_handler import DatabaseError

logger = logging.getLogger(__name__)


@contextmanager
def transaction(db: sqlite3.Connection) -> Generator[sqlite3.Cursor, None, None]:
    """Execute database writes inside an explicit transaction.

    Usage::

        from transaction_manager import transaction

        db = get_db()
        with _db_lock:
            with transaction(db) as cursor:
                cursor.execute("INSERT INTO ...", (...))
                cursor.execute("UPDATE ...", (...))
        # commit happens automatically; rollback on any exception

    Args:
        db: An open sqlite3.Connection (usually from get_db()).

    Yields:
        A sqlite3.Cursor bound to the connection.

    Raises:
        DatabaseError: If the transaction fails and is rolled back.
    """
    cursor = db.cursor()
    try:
        yield cursor
        db.commit()
    except sqlite3.IntegrityError as exc:
        db.rollback()
        logger.warning("Transaction rolled back (integrity): %s", exc)
        raise DatabaseError(
            str(exc),
            code="DB_002",
            context={"sqlite_error": type(exc).__name__},
        ) from exc
    except sqlite3.Error as exc:
        db.rollback()
        logger.error("Transaction rolled back (sqlite): %s", exc)
        raise DatabaseError(
            str(exc),
            context={"sqlite_error": type(exc).__name__},
        ) from exc
    except Exception as exc:
        db.rollback()
        logger.error("Transaction rolled back (unexpected): %s", exc)
        raise
    finally:
        cursor.close()
