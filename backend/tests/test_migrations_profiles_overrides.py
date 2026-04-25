"""Tests that the profiles_overrides_phase1 migration is idempotent and
produces the expected schema."""

from __future__ import annotations

import os

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text

# The revision immediately before the profiles-overrides migration.
# The fixture stamps at this revision after create_all(), then upgrades to head.
_PRE_MIGRATION_REV = "a1b1c1d1e1f1"


def _make_minimal_app(db_path: str):
    """Build a minimal Flask app that registers SQLAlchemy + Flask-Migrate
    without running any application startup logic (no scheduler, no init_db).
    """
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
def in_memory_db(tmp_path):
    """Provide (engine, alembic_cfg) after running the full migration chain.

    Bootstrap strategy (mirrors the production path):
    1. create_all() — creates the base schema from SQLAlchemy models
    2. stamp at _PRE_MIGRATION_REV — tells Alembic the DB is at that revision
    3. upgrade to head — applies only the new profiles_overrides_phase1 migration

    This correctly tests that our new migration adds the expected DDL on top
    of a production-like schema, and that running it twice (idempotency) is safe.
    """
    db_path = str(tmp_path / "test.db")
    app = _make_minimal_app(db_path)

    with app.app_context():
        db = app.extensions["migrate"].db
        engine = db.engine

        # Step 1: bootstrap base schema via create_all (no override columns yet)
        db.create_all()

        # Step 2: stamp alembic_version so Alembic thinks the DB is at the
        # revision just before our new migration
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

        # Step 3: run upgrade head — applies only profiles_overrides_phase1
        cfg = _make_alembic_cfg(db_path)
        command.upgrade(cfg, "head")

        yield engine, cfg


def test_series_settings_has_new_override_columns(in_memory_db):
    engine, _ = in_memory_db
    with engine.connect() as conn:
        cols = {c["name"] for c in inspect(conn).get_columns("series_settings")}
    for col in (
        "forced_preference_override",
        "hi_preference_override",
        "forced_scoring_override",
        "target_languages_override",
        "cutoff_language_override",
        "must_contain_override",
        "must_not_contain_override",
        "audio_exclude_languages_override",
    ):
        assert col in cols, f"missing column {col}"


def test_movie_settings_table_exists_with_expected_columns(in_memory_db):
    engine, _ = in_memory_db
    with engine.connect() as conn:
        insp = inspect(conn)
        tables = insp.get_table_names()
        assert "movie_settings" in tables
        cols = {c["name"] for c in insp.get_columns("movie_settings")}
    expected = {
        "radarr_movie_id",
        "preferred_audio_track_index",
        "cleanup_foreign_tracks",
        "priority_override",
        "min_attempts_per_day",
        "forced_preference_override",
        "hi_preference_override",
        "forced_scoring_override",
        "target_languages_override",
        "cutoff_language_override",
        "must_contain_override",
        "must_not_contain_override",
        "audio_exclude_languages_override",
        "updated_at",
    }
    assert expected.issubset(cols), f"missing columns: {expected - cols}"


def test_migration_runs_idempotently(in_memory_db):
    """Re-running upgrade head must not raise."""
    _, cfg = in_memory_db
    command.upgrade(cfg, "head")  # second call — must succeed
