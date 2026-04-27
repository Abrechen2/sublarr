"""Alembic migration environment for Sublarr.

Configures Alembic to work with Flask-SQLAlchemy and supports:
- render_as_batch=True for SQLite ALTER TABLE compatibility
- Stamp-existing-db logic to avoid "Table already exists" errors
- Flask app context integration for database URL resolution
"""

import logging
from logging.config import fileConfig

from alembic import context
from flask import current_app

# Import all models so Alembic autogenerate can detect them
from db.models import *  # noqa: F401, F403

logger = logging.getLogger("alembic.env")

# Alembic Config object (access to alembic.ini values)
config = context.config

# Set up loggers from alembic.ini if not already configured.
# `disable_existing_loggers=False` is critical: the default (True) tears down
# every logger that exists at import time, which silently kills pytest's
# `caplog` handler when migrations are exercised inside the test suite.
if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

# Target metadata from Flask-SQLAlchemy for autogenerate support
target_metadata = current_app.extensions["migrate"].db.metadata


_stamp_done = False

# Revision to stamp when DB exists but has no alembic_version (one before head so
# the next run applies the latest migration, e.g. retry_after).
_STAMP_REVISION = "b3c2a1d4e5f6"


def stamp_existing_db_if_needed(connection):
    """Stamp an existing database at 'head' to prevent re-creating existing tables.

    Logic:
    - If alembic_version table does NOT exist but other tables DO exist:
      This is an existing database that predates Alembic. Stamp it at 'head'
      so future migrations only apply incremental changes.
    - If alembic_version exists: Do nothing (already managed by Alembic).
    - If neither exists: Do nothing (fresh database, upgrade will create everything).
    Uses direct SQL to avoid re-entering Alembic (command.stamp would reload env).
    """
    global _stamp_done
    if _stamp_done:
        return
    from sqlalchemy import inspect, text

    inspector = inspect(connection)
    table_names = inspector.get_table_names()

    has_alembic = "alembic_version" in table_names
    has_app_tables = "jobs" in table_names  # Use 'jobs' as sentinel for existing DB

    if not has_alembic and has_app_tables:
        _stamp_done = True
        logger.info(
            "Existing database detected without alembic_version table. "
            "Stamping at 'head' to skip initial migration."
        )
        connection.execute(
            text(
                "CREATE TABLE IF NOT EXISTS alembic_version (version_num VARCHAR(32) NOT NULL PRIMARY KEY)"
            )
        )
        connection.execute(
            text("INSERT INTO alembic_version (version_num) VALUES (:rev)"),
            {"rev": _STAMP_REVISION},
        )
        logger.info("Database stamped at 'head' successfully.")


def run_migrations_offline():
    """Run migrations in 'offline' mode (SQL script generation).

    Generates SQL script without connecting to the database.
    Uses render_as_batch=True for SQLite compatibility.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    """Run migrations in 'online' mode (direct database connection).

    Uses the Flask-SQLAlchemy engine from the current app context.
    Applies render_as_batch=True for SQLite ALTER TABLE compatibility.
    """

    def process_revision_directives(ctx, revision, directives):
        """Skip empty migrations during autogenerate."""
        if getattr(config.cmd_opts, "autogenerate", False):
            script = directives[0]
            if script.upgrade_ops.is_empty():
                directives[:] = []
                logger.info("No changes in schema detected.")

    connectable = current_app.extensions["migrate"].db.engine

    # Use engine.begin() so SQLAlchemy 2.0 auto-commits on successful exit.
    # engine.connect() uses autobegin: the outer transaction is rolled back when
    # the context manager exits unless connection.commit() is called explicitly,
    # which would undo any migration changes (including alembic_version updates).
    with connectable.begin() as connection:
        # Concurrent-safety: if two containers boot at the same time they
        # would both observe has_table=False for a fresh table and race
        # into colliding CREATE TABLE. For PostgreSQL acquire a session-
        # wide advisory lock so only one migrator runs at a time; losers
        # block until the winner commits and then see the tables already
        # exist (idempotent guards in each migration skip the DDL).
        # SQLite is single-writer so no lock is needed there.
        dialect_name = connection.dialect.name
        if dialect_name == "postgresql":
            from sqlalchemy import text

            # Fixed key ("sublarr" → CRC32 → bigint). Stable across deploys
            # so restart-loops can't leak an uncollected lock onto a
            # different key.
            _ADVISORY_KEY = 0x5FA0B4A2  # crc32("sublarr.migrations")
            logger.info("Acquiring PostgreSQL advisory lock for migrations…")
            connection.execute(text(f"SELECT pg_advisory_lock({_ADVISORY_KEY})"))

        # Stamp existing databases before running migrations
        stamp_existing_db_if_needed(connection)

        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,
            process_revision_directives=process_revision_directives,
        )

        context.run_migrations()

        # Release the advisory lock on the same connection that acquired it.
        # The ``with connectable.begin()`` block will commit immediately
        # after, closing the session and releasing any remaining locks.
        if dialect_name == "postgresql":
            from sqlalchemy import text

            connection.execute(text(f"SELECT pg_advisory_unlock({_ADVISORY_KEY})"))


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
