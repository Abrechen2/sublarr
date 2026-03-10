"""Base repository class with shared SQLAlchemy session helpers.

All repository classes inherit from BaseRepository to get access to
the Flask-SQLAlchemy request-scoped session and common CRUD helpers.
"""

import threading
from contextlib import contextmanager
from datetime import UTC, datetime

from extensions import db


class BaseRepository:
    """Base class for all repository classes.

    Provides access to the Flask-SQLAlchemy session and common helpers
    for commit, dict conversion, and timestamp generation.
    """

    def __init__(self):
        # Thread-local storage so batch mode on a singleton repo does not
        # affect concurrent threads (e.g. API requests during a scanner run).
        self._local = threading.local()

    @property
    def _batch_mode(self) -> bool:
        return getattr(self._local, "batch_mode", False)

    @_batch_mode.setter
    def _batch_mode(self, value: bool) -> None:
        self._local.batch_mode = value

    @property
    def session(self):
        """Return the Flask-SQLAlchemy request-scoped session."""
        return db.session

    def _commit(self):
        """Commit the current session (no-op in batch mode)."""
        if not self._batch_mode:
            self.session.commit()

    @contextmanager
    def batch(self):
        """Context manager for batching multiple operations in a single transaction.

        Thread-safe: each calling thread has its own batch mode flag, so a
        background scanner can batch commits without affecting API request threads.

        Usage:
            with repo.batch():
                repo.add_entry(...)
                repo.add_entry(...)
        """
        self._batch_mode = True
        try:
            yield self
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise
        finally:
            self._batch_mode = False

    def _to_dict(self, model_instance, columns=None):
        """Convert a SQLAlchemy model instance to a dict.

        Args:
            model_instance: ORM model instance to convert.
            columns: Optional list of column names. If None, uses all
                     columns from the model's __table__.

        Returns:
            Dict with column names as keys and their values.
        """
        if model_instance is None:
            return None
        if columns is None:
            columns = [c.key for c in model_instance.__table__.columns]
        return {col: getattr(model_instance, col) for col in columns}

    def _now(self) -> str:
        """Return current UTC time as ISO format string."""
        return datetime.now(UTC).isoformat()
