"""Base repository class with shared SQLAlchemy session helpers.

All repository classes inherit from BaseRepository to get access to
the Flask-SQLAlchemy request-scoped session and common CRUD helpers.
"""

from datetime import datetime

from extensions import db


class BaseRepository:
    """Base class for all repository classes.

    Provides access to the Flask-SQLAlchemy session and common helpers
    for commit, dict conversion, and timestamp generation.
    """

    @property
    def session(self):
        """Return the Flask-SQLAlchemy request-scoped session."""
        return db.session

    def _commit(self):
        """Commit the current session."""
        self.session.commit()

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
        return datetime.utcnow().isoformat()
