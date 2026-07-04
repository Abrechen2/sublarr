"""Idempotent creation of stats_daily_rollup on top of a create_all() schema (V1.6 #9)."""

from __future__ import annotations

import os

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text

_PRE_MIGRATION_REV = "a3c1e5b7d9f0"


def _make_minimal_app(db_path: str):
    from flask import Flask

    from extensions import db as sa_db
    from extensions import migrate as sa_migrate

    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{db_path}"
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {"connect_args": {"check_same_thread": False}}
    sa_db.init_app(app)
    sa_migrate.init_app(app, sa_db, directory="db/migrations", render_as_batch=True)
    with app.app_context():
        import db.models  # noqa: F401
    return app


def _cfg(db_path: str) -> Config:
    cfg = Config(os.path.join(os.path.dirname(__file__), "..", "db", "migrations", "alembic.ini"))
    cfg.set_main_option(
        "script_location", os.path.join(os.path.dirname(__file__), "..", "db", "migrations")
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
        cfg = _cfg(db_path)
        command.upgrade(cfg, "head")
        yield engine, cfg


def test_stats_daily_rollup_table_exists(migrated_db):
    engine, _ = migrated_db
    with engine.connect() as conn:
        insp = inspect(conn)
        assert "stats_daily_rollup" in insp.get_table_names()
        cols = {c["name"] for c in insp.get_columns("stats_daily_rollup")}
    expected = {
        "date",
        "downloads",
        "translations",
        "syncs",
        "translation_chars",
        "translation_cost_micro_usd",
        "by_source_json",
        "by_provider_json",
        "by_language_json",
        "updated_at",
    }
    assert expected.issubset(cols), f"missing: {expected - cols}"


def test_stats_rollup_migration_idempotent(migrated_db):
    _, cfg = migrated_db
    command.upgrade(cfg, "head")  # second run must not raise
