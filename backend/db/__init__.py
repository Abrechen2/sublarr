"""Database package -- SQLAlchemy ORM integration.

Provides backward-compatible shims for code importing get_db,
init_db, and close_db. All database access now goes through SQLAlchemy
sessions managed by Flask-SQLAlchemy.

Domain modules (db/config.py, db/jobs.py, etc.) are being migrated to
delegate to their repository counterparts in db/repositories/.
"""

import logging

logger = logging.getLogger(__name__)


def get_db():
    """Return the SQLAlchemy session (backward-compatible shim).

    Code that previously called get_db() to get a sqlite3.Connection
    now receives the Flask-SQLAlchemy scoped session. The session
    provides .execute(), .commit(), etc. -- similar interface.
    """
    from extensions import db

    return db.session


def init_db():
    """No-op -- SQLAlchemy initialized via app factory."""
    pass


def close_db():
    """No-op -- SQLAlchemy manages session lifecycle."""
    pass
