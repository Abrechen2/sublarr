"""Startup Alembic upgrade and the resulting schema state for health checks.

``create_app`` runs ``alembic upgrade head`` on every start of an
Alembic-tracked database. A failing migration is rolled back and the app
keeps serving on the old schema, which used to leave /api/v1/health
reporting "healthy". The outcome is now captured as a ``MigrationState``
and stored in ``app.extensions[EXTENSION_KEY]``; the health routes read it
and report unhealthy (HTTP 503) whenever the database is not at head.

Only the exception *type* is kept: driver messages can contain connection
strings or credentials, so the full error goes to the log only.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import sqlalchemy as sa

logger = logging.getLogger(__name__)

EXTENSION_KEY = "sublarr_migration_state"
_UNKNOWN = "unknown"


@dataclass(frozen=True)
class MigrationState:
    ok: bool
    current: str
    head: str
    error: str | None = None
    reason: str | None = None


def _alembic_config(script_location: str, url: str | None = None):
    from alembic.config import Config

    cfg = Config()
    cfg.set_main_option("script_location", script_location)
    if url is not None:
        cfg.set_main_option("sqlalchemy.url", url)
    return cfg


def _head_revisions(script_location: str) -> str:
    from alembic.script import ScriptDirectory

    heads = ScriptDirectory.from_config(_alembic_config(script_location)).get_heads()
    return ",".join(sorted(heads)) or _UNKNOWN


def _current_revisions(engine) -> str:
    with engine.connect() as conn:
        rows = conn.execute(sa.text("SELECT version_num FROM alembic_version")).fetchall()
    return ",".join(sorted(str(r[0]) for r in rows)) or _UNKNOWN


def evaluate(engine, script_location: str, error: BaseException | None = None) -> MigrationState:
    """Compare the database revision with the script head(s)."""
    try:
        head = _head_revisions(script_location)
    except Exception:
        logger.warning("Could not read Alembic head revisions", exc_info=True)
        head = _UNKNOWN
    try:
        current = _current_revisions(engine)
    except Exception:
        logger.warning("Could not read the database's Alembic revision", exc_info=True)
        current = _UNKNOWN

    if error is not None:
        error_type = type(error).__name__
        reason = f"database migration failed: at {current}, expected {head} ({error_type})"
        return MigrationState(False, current, head, error_type, reason)
    if current == _UNKNOWN or head == _UNKNOWN or current != head:
        reason = f"database schema not at head: at {current}, expected {head}"
        return MigrationState(False, current, head, None, reason)
    return MigrationState(True, current, head)


def run_startup_migrations(engine, script_location: str) -> MigrationState:
    """Run ``alembic upgrade head`` and return the resulting schema state."""
    from alembic import command

    error: BaseException | None = None
    try:
        # Online mode in env.py uses the Flask-SQLAlchemy engine; the URL here
        # (password masked by str()) is informational only.
        command.upgrade(_alembic_config(script_location, str(engine.url)), "head")
        logger.info("Alembic migrations applied (upgrade head)")
    except Exception as exc:
        # exc_info=True keeps the full traceback in the log: an empty reason
        # once hid a migration chain pinned one revision behind head for weeks.
        logger.error("Alembic auto-upgrade failed: %s", exc, exc_info=True)
        error = exc
    state = evaluate(engine, script_location, error=error)
    if not state.ok:
        logger.error("Database schema problem: %s", state.reason)
    return state


def get_problem(app) -> MigrationState | None:
    """The recorded migration state of ``app`` when it is not at head, else None."""
    state = app.extensions.get(EXTENSION_KEY)
    if isinstance(state, MigrationState) and not state.ok:
        return state
    return None
