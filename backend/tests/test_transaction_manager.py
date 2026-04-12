"""Tests for transaction_manager module.

Covers both the SQLAlchemy and legacy sqlite3 transaction paths,
including commit, rollback on various exception types, and the
top-level dispatcher.
"""

import sqlite3
from unittest.mock import MagicMock, patch

import pytest

from error_handler import DatabaseError
from transaction_manager import _legacy_transaction, _sqlalchemy_transaction, transaction

# ---------------------------------------------------------------------------
# _legacy_transaction tests
# ---------------------------------------------------------------------------


class TestLegacyTransaction:
    """Tests for the legacy sqlite3 transaction context manager."""

    def test_commit_on_success(self):
        """Successful block commits and closes cursor."""
        conn = MagicMock(spec=sqlite3.Connection)
        cursor = MagicMock()
        conn.cursor.return_value = cursor

        with _legacy_transaction(conn) as cur:
            cur.execute("INSERT INTO t VALUES (?)", (1,))

        conn.commit.assert_called_once()
        conn.rollback.assert_not_called()
        cursor.close.assert_called_once()

    def test_rollback_on_integrity_error(self):
        """IntegrityError rolls back and raises DatabaseError with code DB_002."""
        conn = MagicMock(spec=sqlite3.Connection)
        cursor = MagicMock()
        conn.cursor.return_value = cursor

        with pytest.raises(DatabaseError) as exc_info, _legacy_transaction(conn):
            raise sqlite3.IntegrityError("UNIQUE constraint failed")

        assert exc_info.value.code == "DB_002"
        assert "UNIQUE constraint failed" in str(exc_info.value)
        conn.rollback.assert_called_once()
        conn.commit.assert_not_called()
        cursor.close.assert_called_once()

    def test_rollback_on_sqlite_error(self):
        """Generic sqlite3.Error rolls back and raises DatabaseError."""
        conn = MagicMock(spec=sqlite3.Connection)
        cursor = MagicMock()
        conn.cursor.return_value = cursor

        with pytest.raises(DatabaseError) as exc_info, _legacy_transaction(conn):
            raise sqlite3.OperationalError("database is locked")

        assert "database is locked" in str(exc_info.value)
        conn.rollback.assert_called_once()
        conn.commit.assert_not_called()
        cursor.close.assert_called_once()

    def test_rollback_on_unexpected_error(self):
        """Non-sqlite exception rolls back and re-raises the original error."""
        conn = MagicMock(spec=sqlite3.Connection)
        cursor = MagicMock()
        conn.cursor.return_value = cursor

        with pytest.raises(ValueError, match="boom"), _legacy_transaction(conn):
            raise ValueError("boom")

        conn.rollback.assert_called_once()
        conn.commit.assert_not_called()
        cursor.close.assert_called_once()

    def test_cursor_closed_even_on_error(self):
        """Cursor is closed in the finally block regardless of outcome."""
        conn = MagicMock(spec=sqlite3.Connection)
        cursor = MagicMock()
        conn.cursor.return_value = cursor

        with pytest.raises(RuntimeError), _legacy_transaction(conn):
            raise RuntimeError("fail")

        cursor.close.assert_called_once()


# ---------------------------------------------------------------------------
# _sqlalchemy_transaction tests
# ---------------------------------------------------------------------------


class TestSqlalchemyTransaction:
    """Tests for the SQLAlchemy session-based transaction context manager."""

    @patch("extensions.db")
    def test_commit_on_success(self, mock_db):
        """Successful block commits the session."""
        mock_session = MagicMock()
        mock_db.session = mock_session

        with _sqlalchemy_transaction() as session:
            session.execute("SELECT 1")

        mock_session.commit.assert_called_once()
        mock_session.rollback.assert_not_called()

    @patch("extensions.db")
    def test_rollback_on_exception(self, mock_db):
        """Exception inside the block rolls back and re-raises."""
        mock_session = MagicMock()
        mock_db.session = mock_session

        with pytest.raises(RuntimeError, match="db error"), _sqlalchemy_transaction():
            raise RuntimeError("db error")

        mock_session.rollback.assert_called_once()
        mock_session.commit.assert_not_called()

    @patch("extensions.db")
    def test_yields_db_session(self, mock_db):
        """The yielded value is db.session."""
        mock_session = MagicMock()
        mock_db.session = mock_session

        with _sqlalchemy_transaction() as session:
            assert session is mock_session


# ---------------------------------------------------------------------------
# transaction() dispatcher tests
# ---------------------------------------------------------------------------


class TestTransactionDispatcher:
    """Tests for the top-level transaction() dispatcher."""

    def test_sqlite3_connection_delegates_to_legacy(self):
        """Passing a sqlite3.Connection dispatches to _legacy_transaction."""
        conn = MagicMock(spec=sqlite3.Connection)
        cursor = MagicMock()
        conn.cursor.return_value = cursor

        with transaction(conn) as cur:
            assert cur is cursor

        conn.commit.assert_called_once()
        cursor.close.assert_called_once()

    @patch("extensions.db")
    def test_none_arg_delegates_to_sqlalchemy(self, mock_db):
        """Calling transaction() with no args uses SQLAlchemy path."""
        mock_session = MagicMock()
        mock_db.session = mock_session

        with transaction() as session:
            assert session is mock_session

        mock_session.commit.assert_called_once()

    @patch("extensions.db")
    def test_explicit_none_delegates_to_sqlalchemy(self, mock_db):
        """Calling transaction(None) uses SQLAlchemy path."""
        mock_session = MagicMock()
        mock_db.session = mock_session

        with transaction(None) as session:
            assert session is mock_session

        mock_session.commit.assert_called_once()

    @patch("extensions.db")
    def test_non_connection_arg_delegates_to_sqlalchemy(self, mock_db):
        """A non-sqlite3.Connection argument falls through to SQLAlchemy."""
        mock_session = MagicMock()
        mock_db.session = mock_session

        with transaction("not_a_connection") as session:
            assert session is mock_session

        mock_session.commit.assert_called_once()

    def test_legacy_path_integrity_error_propagates(self):
        """DatabaseError from legacy path propagates through transaction()."""
        conn = MagicMock(spec=sqlite3.Connection)
        cursor = MagicMock()
        conn.cursor.return_value = cursor

        with pytest.raises(DatabaseError) as exc_info, transaction(conn):
            raise sqlite3.IntegrityError("duplicate key")

        assert exc_info.value.code == "DB_002"
        conn.rollback.assert_called_once()

    @patch("extensions.db")
    def test_sqlalchemy_path_exception_propagates(self, mock_db):
        """Exception from SQLAlchemy path propagates through transaction()."""
        mock_session = MagicMock()
        mock_db.session = mock_session

        with pytest.raises(ValueError, match="bad data"), transaction():
            raise ValueError("bad data")

        mock_session.rollback.assert_called_once()
