"""Tests for database_health.py — dialect-aware health checks and maintenance."""

import sys
from unittest.mock import MagicMock, patch

import pytest

from error_handler import DatabaseIntegrityError

# ── _is_postgresql ───────────────────────────────────────────────────────────


class TestIsPostgresql:
    def test_returns_true_for_postgresql_dialect(self):
        from database_health import _is_postgresql

        mock_db = MagicMock()
        mock_db.engine.dialect.name = "postgresql"
        with patch.dict(sys.modules, {"extensions": MagicMock(db=mock_db)}):
            assert _is_postgresql() is True

    def test_returns_false_for_sqlite_dialect(self):
        from database_health import _is_postgresql

        mock_db = MagicMock()
        mock_db.engine.dialect.name = "sqlite"
        with patch.dict(sys.modules, {"extensions": MagicMock(db=mock_db)}):
            assert _is_postgresql() is False

    def test_returns_false_on_exception(self):
        """When extensions.db raises, fall back to False."""
        from database_health import _is_postgresql

        mock_ext = MagicMock()
        mock_ext.db.engine.dialect.name = property(lambda self: (_ for _ in ()).throw(RuntimeError))

        # Simpler: make accessing .dialect raise
        type(mock_ext.db.engine).dialect = property(
            lambda self: (_ for _ in ()).throw(RuntimeError("no dialect"))
        )

        with patch.dict(sys.modules, {"extensions": mock_ext}):
            assert _is_postgresql() is False


# ── check_integrity ──────────────────────────────────────────────────────────


class TestCheckIntegrity:
    def test_healthy_database(self):
        from database_health import check_integrity

        mock_db = MagicMock()
        mock_db.execute.return_value.fetchall.return_value = [("ok",)]

        is_ok, message = check_integrity(mock_db)

        assert is_ok is True
        assert message == "ok"

    def test_corrupted_database_raises_integrity_error(self):
        from database_health import check_integrity

        mock_db = MagicMock()
        mock_db.execute.return_value.fetchall.return_value = [
            ("row 1 missing from index idx_foo",),
            ("row 5 missing from index idx_bar",),
        ]

        with pytest.raises(DatabaseIntegrityError, match="row 1 missing"):
            check_integrity(mock_db)

    def test_unknown_result_when_empty_rows(self):
        from database_health import check_integrity

        mock_db = MagicMock()
        mock_db.execute.return_value.fetchall.return_value = []

        # "unknown" != "ok", so it should raise DatabaseIntegrityError
        with pytest.raises(DatabaseIntegrityError, match="Integrity check failed"):
            check_integrity(mock_db)

    def test_general_exception_returns_false(self):
        from database_health import check_integrity

        mock_db = MagicMock()
        mock_db.execute.side_effect = RuntimeError("disk I/O error")

        is_ok, message = check_integrity(mock_db)

        assert is_ok is False
        assert "disk I/O error" in message

    def test_database_integrity_error_re_raised(self):
        """DatabaseIntegrityError from the pragma result is re-raised, not caught."""
        from database_health import check_integrity

        mock_db = MagicMock()
        mock_db.execute.return_value.fetchall.return_value = [("corrupt page 42",)]

        with pytest.raises(DatabaseIntegrityError):
            check_integrity(mock_db)


# ── get_database_stats ───────────────────────────────────────────────────────


class TestGetDatabaseStats:
    def _make_execute(self, pragma_map=None, tables=None, table_counts=None):
        """Helper to build a mock db.execute with predictable PRAGMA/table responses."""
        if pragma_map is None:
            pragma_map = {
                "journal_mode": ("wal",),
                "page_size": (4096,),
                "page_count": (100,),
                "freelist_count": (5,),
            }
        if tables is None:
            tables = []
        if table_counts is None:
            table_counts = {}

        def execute_side_effect(stmt):
            sql = str(stmt)
            result = MagicMock()
            # PRAGMA checks
            for pragma_name, value in pragma_map.items():
                if pragma_name in sql:
                    result.fetchone.return_value = value
                    return result
            # sqlite_master
            if "sqlite_master" in sql:
                result.fetchall.return_value = [(t,) for t in tables]
                return result
            # COUNT(*) for specific tables
            for tname, count in table_counts.items():
                if tname in sql and "COUNT" in sql:
                    if isinstance(count, Exception):
                        raise count
                    result.fetchone.return_value = (count,)
                    return result
            result.fetchone.return_value = None
            result.fetchall.return_value = []
            return result

        return execute_side_effect

    def test_basic_stats_collection(self):
        from database_health import get_database_stats

        mock_db = MagicMock()
        mock_db.execute.side_effect = self._make_execute(
            tables=["subtitles", "config_entries"],
            table_counts={"subtitles": 42, "config_entries": 10},
        )

        with (
            patch("os.path.getsize", return_value=102400),
            patch("os.path.exists", return_value=False),
        ):
            stats = get_database_stats(mock_db, "/fake/db.sqlite")

        assert stats["size_bytes"] == 102400
        assert stats["wal_mode"] is True
        assert stats["page_size"] == 4096
        assert stats["page_count"] == 100
        assert stats["freelist_count"] == 5
        assert stats["tables"]["subtitles"] == 42
        assert stats["tables"]["config_entries"] == 10

    def test_wal_file_size_when_exists(self):
        from database_health import get_database_stats

        mock_db = MagicMock()
        mock_db.execute.side_effect = self._make_execute()

        def getsize_side_effect(path):
            if path.endswith("-wal"):
                return 8192
            return 51200

        with (
            patch("os.path.getsize", side_effect=getsize_side_effect),
            patch("os.path.exists", return_value=True),
        ):
            stats = get_database_stats(mock_db, "/fake/db.sqlite")

        assert stats["wal_size_bytes"] == 8192

    def test_missing_db_file_returns_zero_size(self):
        from database_health import get_database_stats

        mock_db = MagicMock()
        mock_db.execute.side_effect = self._make_execute()

        with (
            patch("os.path.getsize", side_effect=OSError("not found")),
            patch("os.path.exists", return_value=False),
        ):
            stats = get_database_stats(mock_db, "/nonexistent/db.sqlite")

        assert stats["size_bytes"] == 0
        assert stats["wal_size_bytes"] == 0

    def test_non_standard_table_name_skipped(self):
        """Tables with names like '-- drop' are skipped for safety."""
        from database_health import get_database_stats

        mock_db = MagicMock()
        mock_db.execute.side_effect = self._make_execute(
            tables=["valid_table", "-- injection"],
            table_counts={"valid_table": 7},
        )

        with (
            patch("os.path.getsize", return_value=1000),
            patch("os.path.exists", return_value=False),
        ):
            stats = get_database_stats(mock_db, "/fake/db.sqlite")

        assert "valid_table" in stats["tables"]
        assert "-- injection" not in stats["tables"]

    def test_pragma_exception_sets_none(self):
        from database_health import get_database_stats

        mock_db = MagicMock()
        mock_db.execute.side_effect = RuntimeError("pragma failed")

        with (
            patch("os.path.getsize", return_value=500),
            patch("os.path.exists", return_value=False),
        ):
            stats = get_database_stats(mock_db, "/fake/db.sqlite")

        # PRAGMAs should be None, tables should be empty
        assert stats["page_size"] is None
        assert stats["tables"] == {}

    def test_table_count_failure_returns_minus_one(self):
        """If counting rows in a table fails, record -1."""
        from database_health import get_database_stats

        mock_db = MagicMock()
        mock_db.execute.side_effect = self._make_execute(
            tables=["broken_table"],
            table_counts={"broken_table": RuntimeError("table locked")},
        )

        with (
            patch("os.path.getsize", return_value=500),
            patch("os.path.exists", return_value=False),
        ):
            stats = get_database_stats(mock_db, "/fake/db.sqlite")

        assert stats["tables"]["broken_table"] == -1

    def test_wal_size_oserror_returns_zero(self):
        """OSError reading WAL file returns 0."""
        from database_health import get_database_stats

        mock_db = MagicMock()
        mock_db.execute.side_effect = self._make_execute()

        def getsize_side_effect(path):
            if path.endswith("-wal"):
                raise OSError("wal broken")
            return 1000

        with (
            patch("os.path.getsize", side_effect=getsize_side_effect),
            patch("os.path.exists", return_value=True),
        ):
            stats = get_database_stats(mock_db, "/fake/db.sqlite")

        assert stats["wal_size_bytes"] == 0


# ── vacuum ───────────────────────────────────────────────────────────────────


class TestVacuum:
    def test_vacuum_reports_space_savings(self):
        from database_health import vacuum

        mock_db = MagicMock()
        sizes = iter([10240, 8192])

        with patch("os.path.getsize", side_effect=lambda _: next(sizes)):
            result = vacuum(mock_db, "/fake/db.sqlite")

        assert result["before_bytes"] == 10240
        assert result["after_bytes"] == 8192
        assert result["saved_bytes"] == 2048

        # Verify VACUUM was executed
        mock_db.execute.assert_called_once()

    def test_vacuum_with_missing_file(self):
        from database_health import vacuum

        mock_db = MagicMock()

        with patch("os.path.getsize", side_effect=OSError("no file")):
            result = vacuum(mock_db, "/nonexistent/db.sqlite")

        assert result["before_bytes"] == 0
        assert result["after_bytes"] == 0
        assert result["saved_bytes"] == 0

    def test_vacuum_no_savings(self):
        from database_health import vacuum

        mock_db = MagicMock()

        with patch("os.path.getsize", return_value=5000):
            result = vacuum(mock_db, "/fake/db.sqlite")

        assert result["saved_bytes"] == 0


# ── _sqlite_health_report ────────────────────────────────────────────────────


class TestSqliteHealthReport:
    def test_healthy_report(self):
        from database_health import _sqlite_health_report

        mock_db = MagicMock()
        mock_settings = MagicMock()
        mock_settings.db_path = "/fake/db.sqlite"

        # check_integrity: integrity_check PRAGMA returns "ok"
        # get_database_stats: various PRAGMAs
        def execute_side_effect(stmt):
            sql = str(stmt)
            result = MagicMock()
            if "integrity_check" in sql:
                result.fetchall.return_value = [("ok",)]
            elif "sqlite_master" in sql:
                result.fetchall.return_value = []
            else:
                result.fetchone.return_value = (0,)
            return result

        mock_db.execute.side_effect = execute_side_effect

        with (
            patch("db.get_db", return_value=mock_db),
            patch("config.get_settings", return_value=mock_settings),
            patch("os.path.getsize", return_value=1024),
            patch("os.path.exists", return_value=False),
        ):
            report = _sqlite_health_report()

        assert report["status"] == "healthy"
        assert report["backend"] == "sqlite"
        assert report["details"]["integrity"]["ok"] is True
        assert report["details"]["integrity"]["message"] == "ok"

    def test_unhealthy_report_on_generic_error(self):
        """When check_integrity hits a generic exception, report is unhealthy."""
        from database_health import _sqlite_health_report

        mock_db = MagicMock()
        mock_settings = MagicMock()
        mock_settings.db_path = "/fake/db.sqlite"

        # First call (integrity check) raises generic error -> returns (False, msg)
        # Subsequent calls (stats) also raise but that's handled
        mock_db.execute.side_effect = RuntimeError("disk error")

        with (
            patch("db.get_db", return_value=mock_db),
            patch("config.get_settings", return_value=mock_settings),
            patch("os.path.getsize", return_value=0),
            patch("os.path.exists", return_value=False),
        ):
            report = _sqlite_health_report()

        assert report["status"] == "unhealthy"
        assert report["details"]["integrity"]["ok"] is False


# ── get_health_report (dispatch) ─────────────────────────────────────────────


class TestGetHealthReport:
    def test_dispatches_to_sqlite(self):
        from database_health import get_health_report

        with (
            patch("database_health._is_postgresql", return_value=False),
            patch(
                "database_health._sqlite_health_report",
                return_value={"status": "healthy", "backend": "sqlite", "details": {}},
            ) as mock_sqlite,
        ):
            result = get_health_report()

        mock_sqlite.assert_called_once()
        assert result["backend"] == "sqlite"

    def test_dispatches_to_postgresql(self):
        from database_health import get_health_report

        with (
            patch("database_health._is_postgresql", return_value=True),
            patch(
                "database_health._pg_health_report",
                return_value={"status": "healthy", "backend": "postgresql", "details": {}},
            ) as mock_pg,
        ):
            result = get_health_report()

        mock_pg.assert_called_once()
        assert result["backend"] == "postgresql"


# ── get_pool_stats ───────────────────────────────────────────────────────────


class TestGetPoolStats:
    def test_returns_none_for_sqlite(self):
        from database_health import get_pool_stats

        with patch("database_health._is_postgresql", return_value=False):
            assert get_pool_stats() is None

    def test_returns_pool_stats_for_postgresql(self):
        from database_health import get_pool_stats

        mock_pool = MagicMock()
        mock_pool.size.return_value = 5
        mock_pool.checkedin.return_value = 3
        mock_pool.checkedout.return_value = 2
        mock_pool.overflow.return_value = 0
        mock_pool.status.return_value = "OK"

        mock_ext = MagicMock()
        mock_ext.db.engine.pool = mock_pool

        with (
            patch("database_health._is_postgresql", return_value=True),
            patch.dict(sys.modules, {"extensions": mock_ext}),
        ):
            stats = get_pool_stats()

        assert stats == {
            "size": 5,
            "checked_in": 3,
            "checked_out": 2,
            "overflow": 0,
            "status": "OK",
        }

    def test_returns_none_on_exception(self):
        from database_health import get_pool_stats

        mock_ext = MagicMock()
        mock_ext.db.engine.pool.size.side_effect = RuntimeError("pool error")

        with (
            patch("database_health._is_postgresql", return_value=True),
            patch.dict(sys.modules, {"extensions": mock_ext}),
        ):
            stats = get_pool_stats()

        assert stats is None


# ── _pg_health_report ────────────────────────────────────────────────────────


class TestPgHealthReport:
    def _make_pg_conn(self, execute_fn):
        """Create a mock connection manager from an execute function."""
        mock_conn = MagicMock()
        mock_conn.execute.side_effect = execute_fn
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        return mock_conn

    def _default_pg_execute(self, stmt):
        """Default PG execute that returns reasonable data for all queries."""
        sql = str(stmt)
        result = MagicMock()
        if "pg_database_size" in sql:
            result.fetchone.return_value = (1048576,)
        elif "pg_stat_activity" in sql:
            result.fetchone.return_value = (3,)
        elif "pg_class" in sql:
            result.fetchall.return_value = [("users", 8192), ("logs", 4096)]
        elif "pg_stat_user_tables" in sql:
            result.fetchall.return_value = [("users", 100), ("logs", 500)]
        elif "pg_stat_user_indexes" in sql:
            result.fetchall.return_value = [("idx_users_id", 200)]
        elif "SELECT 1" in sql:
            result.fetchone.return_value = (1,)
        return result

    def test_healthy_pg_report(self):
        from database_health import _pg_health_report

        mock_conn = self._make_pg_conn(self._default_pg_execute)
        mock_ext = MagicMock()
        mock_ext.db.engine.connect.return_value = mock_conn

        with (
            patch.dict(sys.modules, {"extensions": mock_ext}),
            patch("database_health.get_pool_stats", return_value=None),
        ):
            report = _pg_health_report()

        assert report["status"] == "healthy"
        assert report["backend"] == "postgresql"
        assert report["details"]["size_bytes"] == 1048576
        assert report["details"]["active_connections"] == 3
        assert report["details"]["table_sizes"] == {"users": 8192, "logs": 4096}
        assert report["details"]["tables"] == {"users": 100, "logs": 500}
        assert report["details"]["index_usage"] == {"idx_users_id": 200}
        assert report["details"]["connection_ok"] is True

    def test_pg_report_connection_failure(self):
        from database_health import _pg_health_report

        mock_ext = MagicMock()
        mock_ext.db.engine.connect.side_effect = RuntimeError("connection refused")

        with (
            patch.dict(sys.modules, {"extensions": mock_ext}),
            patch("database_health.get_pool_stats", return_value=None),
        ):
            report = _pg_health_report()

        assert report["status"] == "unhealthy"
        assert "error" in report["details"]
        assert "connection refused" in report["details"]["error"]

    def test_pg_report_with_pool_stats(self):
        from database_health import _pg_health_report

        mock_conn = self._make_pg_conn(self._default_pg_execute)
        mock_ext = MagicMock()
        mock_ext.db.engine.connect.return_value = mock_conn

        pool_info = {
            "size": 10,
            "checked_in": 8,
            "checked_out": 2,
            "overflow": 0,
            "status": "OK",
        }

        with (
            patch.dict(sys.modules, {"extensions": mock_ext}),
            patch("database_health.get_pool_stats", return_value=pool_info),
        ):
            report = _pg_health_report()

        assert report["details"]["pool"] == pool_info

    def test_pg_report_partial_query_failures(self):
        """Individual query failures are logged but don't crash the report."""
        from database_health import _pg_health_report

        def execute_side_effect(stmt):
            sql = str(stmt)
            if "SELECT 1" in sql:
                return MagicMock(fetchone=MagicMock(return_value=(1,)))
            raise RuntimeError("query failed")

        mock_conn = self._make_pg_conn(execute_side_effect)
        mock_ext = MagicMock()
        mock_ext.db.engine.connect.return_value = mock_conn

        with (
            patch.dict(sys.modules, {"extensions": mock_ext}),
            patch("database_health.get_pool_stats", return_value=None),
        ):
            report = _pg_health_report()

        # Despite query failures, the report completes
        assert report["status"] == "healthy"
        assert report["details"]["size_bytes"] == 0
        assert report["details"]["active_connections"] == -1
        assert report["details"]["table_sizes"] == {}
        assert report["details"]["index_usage"] == {}

    def test_pg_report_connection_check_failure_marks_unhealthy(self):
        """If SELECT 1 fails, status becomes unhealthy."""
        from database_health import _pg_health_report

        def execute_side_effect(stmt):
            sql = str(stmt)
            result = MagicMock()
            if "SELECT 1" in sql:
                raise RuntimeError("connection lost")
            if "pg_database_size" in sql or "pg_stat_activity" in sql:
                result.fetchone.return_value = (0,)
            else:
                result.fetchall.return_value = []
            return result

        mock_conn = self._make_pg_conn(execute_side_effect)
        mock_ext = MagicMock()
        mock_ext.db.engine.connect.return_value = mock_conn

        with (
            patch.dict(sys.modules, {"extensions": mock_ext}),
            patch("database_health.get_pool_stats", return_value=None),
        ):
            report = _pg_health_report()

        assert report["status"] == "unhealthy"
        assert report["details"]["connection_ok"] is False

    def test_pg_report_no_pool_stats_omits_pool_key(self):
        """When get_pool_stats returns None, 'pool' key is absent from details."""
        from database_health import _pg_health_report

        mock_conn = self._make_pg_conn(self._default_pg_execute)
        mock_ext = MagicMock()
        mock_ext.db.engine.connect.return_value = mock_conn

        with (
            patch.dict(sys.modules, {"extensions": mock_ext}),
            patch("database_health.get_pool_stats", return_value=None),
        ):
            report = _pg_health_report()

        assert "pool" not in report["details"]
