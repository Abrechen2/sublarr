"""Startup migration state and its effect on /health and /health/detailed."""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest
import sqlalchemy as sa

from db import migration_state as ms

_SCRIPT_LOCATION = os.path.join(os.path.dirname(os.path.dirname(__file__)), "db", "migrations")


def _head() -> str:
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    cfg = Config()
    cfg.set_main_option("script_location", _SCRIPT_LOCATION)
    return ",".join(sorted(ScriptDirectory.from_config(cfg).get_heads()))


def _engine(tmp_path, revision: str | None):
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'm.db'}")
    if revision is not None:
        with engine.begin() as conn:
            conn.execute(sa.text("CREATE TABLE alembic_version (version_num VARCHAR(32))"))
            conn.execute(sa.text("INSERT INTO alembic_version VALUES (:r)"), {"r": revision})
    return engine


# ─── evaluate / run_startup_migrations ────────────────────────────────────────


def test_state_ok_when_at_head(tmp_path):
    state = ms.evaluate(_engine(tmp_path, _head()), _SCRIPT_LOCATION)
    assert state.ok is True
    assert state.reason is None
    assert state.current == _head()
    assert state.head == _head()


def test_state_not_ok_when_behind_head(tmp_path):
    state = ms.evaluate(_engine(tmp_path, "oldrev123"), _SCRIPT_LOCATION)
    assert state.ok is False
    assert state.reason == f"database schema not at head: at oldrev123, expected {_head()}"


def test_state_reports_migration_failure(tmp_path):
    err = RuntimeError("postgresql://user:secret@db:5432/sublarr exploded")
    state = ms.evaluate(_engine(tmp_path, "oldrev123"), _SCRIPT_LOCATION, error=err)
    assert state.ok is False
    assert state.error == "RuntimeError"
    assert state.reason == (
        f"database migration failed: at oldrev123, expected {_head()} (RuntimeError)"
    )
    # The exception message (which may carry a connection string) never leaks.
    assert "secret" not in state.reason
    assert "postgresql" not in state.reason


def test_run_startup_migrations_records_forced_failure(tmp_path):
    engine = _engine(tmp_path, "oldrev123")
    with patch("alembic.command.upgrade", side_effect=ValueError("boom")):
        state = ms.run_startup_migrations(engine, _SCRIPT_LOCATION)
    assert state.ok is False
    assert state.reason.startswith("database migration failed: at oldrev123, expected ")
    assert state.error == "ValueError"


def test_run_startup_migrations_detects_mismatch_without_exception(tmp_path):
    engine = _engine(tmp_path, "oldrev123")
    with patch("alembic.command.upgrade", return_value=None):
        state = ms.run_startup_migrations(engine, _SCRIPT_LOCATION)
    assert state.ok is False
    assert state.reason.startswith("database schema not at head: at oldrev123")


def test_run_startup_migrations_ok_when_upgrade_reaches_head(tmp_path):
    engine = _engine(tmp_path, _head())
    with patch("alembic.command.upgrade", return_value=None):
        state = ms.run_startup_migrations(engine, _SCRIPT_LOCATION)
    assert state.ok is True


def test_unreadable_revision_is_reported_as_unknown(tmp_path):
    engine = _engine(tmp_path, None)  # no alembic_version table at all
    state = ms.evaluate(engine, _SCRIPT_LOCATION, error=RuntimeError("x"))
    assert state.ok is False
    assert state.current == "unknown"
    assert "at unknown" in state.reason


# ─── health routes ────────────────────────────────────────────────────────────

_FAILED = ms.MigrationState(
    ok=False,
    current="oldrev123",
    head="newrev456",
    error="ProgrammingError",
    reason="database migration failed: at oldrev123, expected newrev456 (ProgrammingError)",
)


@pytest.fixture()
def failed_migration_client(client):
    app = client.application
    app.extensions[ms.EXTENSION_KEY] = _FAILED
    yield client
    app.extensions.pop(ms.EXTENSION_KEY, None)


def test_health_unhealthy_when_migration_failed(failed_migration_client):
    resp = failed_migration_client.get("/api/v1/health")
    assert resp.status_code == 503
    body = resp.get_json()
    assert body["status"] == "unhealthy"


def test_health_reports_reason_to_authenticated_callers(failed_migration_client):
    # The test app has no api_key and no UI auth, so the caller counts as
    # authenticated and gets the detail.
    body = failed_migration_client.get("/api/v1/health").get_json()
    assert body.get("reason") == _FAILED.reason
    assert body["services"]["database_migrations"] == _FAILED.reason


def test_health_hides_reason_from_unauthenticated_callers(failed_migration_client):
    with patch("routes.system.health._caller_is_authenticated", return_value=False):
        resp = failed_migration_client.get("/api/v1/health")
    assert resp.status_code == 503
    assert resp.get_json() == {"status": "unhealthy"}


def test_health_healthy_without_migration_state(client):
    client.application.extensions.pop(ms.EXTENSION_KEY, None)
    resp = client.get("/api/v1/health")
    assert resp.get_json()["status"] == "healthy"
    assert "database_migrations" not in resp.get_json().get("services", {})


def test_health_detailed_flags_migration_failure(failed_migration_client):
    resp = failed_migration_client.get("/api/v1/health/detailed")
    assert resp.status_code == 503
    sub = resp.get_json()["subsystems"]["database_migrations"]
    assert sub["healthy"] is False
    assert sub["message"] == _FAILED.reason
    assert sub["current"] == "oldrev123"
    assert sub["head"] == "newrev456"


def test_health_detailed_status_matches_health_when_migration_failed(failed_migration_client):
    """A schema off head is a hard fault: both endpoints say "unhealthy"."""
    detailed = failed_migration_client.get("/api/v1/health/detailed").get_json()
    liveness = failed_migration_client.get("/api/v1/health").get_json()
    assert detailed["status"] == "unhealthy"
    assert liveness["status"] == "unhealthy"
