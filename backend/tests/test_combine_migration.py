"""Tests that the combined-subtitle migration is idempotent and adds the
expected columns on top of a create_all()-seeded schema (V1.6 Feature #1, C1)."""

from __future__ import annotations

import os

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text

# The revision immediately before the combined-subtitle migration
# (add_mt_provisional_fields). The fixture stamps here after create_all(),
# then upgrades to head, applying only the combine migration.
_PRE_MIGRATION_REV = "9882235dacf6"

_COMBINE_COLUMNS = (
    "combine_enabled",
    "combine_format",
    "combine_languages_json",
    "combine_position_json",
)


def _make_minimal_app(db_path: str):
    from flask import Flask

    from extensions import db as sa_db
    from extensions import migrate as sa_migrate

    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{db_path}"
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
        "connect_args": {"check_same_thread": False},
    }
    sa_db.init_app(app)
    sa_migrate.init_app(app, sa_db, directory="db/migrations", render_as_batch=True)

    with app.app_context():
        import db.models  # noqa: F401 — populate metadata

    return app


def _make_alembic_cfg(db_path: str) -> Config:
    cfg = Config(os.path.join(os.path.dirname(__file__), "..", "db", "migrations", "alembic.ini"))
    cfg.set_main_option(
        "script_location",
        os.path.join(os.path.dirname(__file__), "..", "db", "migrations"),
    )
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    return cfg


@pytest.fixture()
def migrated_db(tmp_path):
    db_path = str(tmp_path / "test.db")
    app = _make_minimal_app(db_path)

    with app.app_context():
        db = app.extensions["migrate"].db
        engine = db.engine

        db.create_all()

        with engine.begin() as conn:
            conn.execute(
                text(
                    "CREATE TABLE IF NOT EXISTS alembic_version "
                    "(version_num VARCHAR(32) NOT NULL PRIMARY KEY)"
                )
            )
            conn.execute(
                text("INSERT OR REPLACE INTO alembic_version (version_num) VALUES (:rev)"),
                {"rev": _PRE_MIGRATION_REV},
            )

        cfg = _make_alembic_cfg(db_path)
        command.upgrade(cfg, "head")

        yield engine, cfg


def test_language_profiles_has_combine_columns(migrated_db):
    engine, _ = migrated_db
    with engine.connect() as conn:
        cols = {c["name"] for c in inspect(conn).get_columns("language_profiles")}
    for col in _COMBINE_COLUMNS:
        assert col in cols, f"missing column {col}"


def test_combine_migration_runs_idempotently(migrated_db):
    """Re-running upgrade head must not raise (coexists with create_all schema)."""
    _, cfg = migrated_db
    command.upgrade(cfg, "head")
