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

# Set up loggers from alembic.ini if not already configured
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Target metadata from Flask-SQLAlchemy for autogenerate support
target_metadata = current_app.extensions["migrate"].db.metadata


def stamp_existing_db_if_needed(connection):
    """Stamp an existing database at 'head' to prevent re-creating existing tables.

    Logic:
    - If alembic_version table does NOT exist but other tables DO exist:
      This is an existing database that predates Alembic. Stamp it at 'head'
      so future migrations only apply incremental changes.
    - If alembic_version exists: Do nothing (already managed by Alembic).
    - If neither exists: Do nothing (fresh database, upgrade will create everything).
    """
    from sqlalchemy import inspect

    inspector = inspect(connection)
    table_names = inspector.get_table_names()

    has_alembic = "alembic_version" in table_names
    has_app_tables = "jobs" in table_names  # Use 'jobs' as sentinel for existing DB

    if not has_alembic and has_app_tables:
        # Existing DB without Alembic -- stamp at head
        logger.info(
            "Existing database detected without alembic_version table. "
            "Stamping at 'head' to skip initial migration."
        )
        context.stamp(config, "head")
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

    with connectable.connect() as connection:
        # Stamp existing databases before running migrations
        stamp_existing_db_if_needed(connection)

        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,
            process_revision_directives=process_revision_directives,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
