"""Migration regression tests for translation_events.

Follows the same isolation pattern as test_scheduler_migration.py: stamp a
fresh DB at the previous head, apply a single ``upgrade +1``, then assert
the resulting schema matches the explicit migration.
"""

from __future__ import annotations

import os

import pytest
import sqlalchemy as sa

# Revisions under test — keep in sync with the migration file.
PREVIOUS_HEAD = "dc8da0c509a8"
TRANSLATION_EVENTS_REVISION = "7e085763f714"


def _alembic_config(sqlalchemy_url: str):
    """Build an Alembic Config pointing at backend/db/migrations."""
    from alembic.config import Config

    backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    script_location = os.path.join(backend_dir, "db", "migrations")

    cfg = Config()
    cfg.set_main_option("script_location", script_location)
    cfg.set_main_option("sqlalchemy.url", sqlalchemy_url)
    return cfg


@pytest.fixture
def migrated_db_engine(tmp_path, monkeypatch):
    """Fresh SQLite DB stamped at the previous head, then upgraded to head."""
    from alembic import command

    db_path = tmp_path / "test.db"
    url = f"sqlite:///{db_path}"

    monkeypatch.setenv("SUBLARR_DB_PATH", str(db_path))
    monkeypatch.setenv("SUBLARR_API_KEY", "")
    monkeypatch.setenv("SUBLARR_LOG_LEVEL", "ERROR")

    from app import create_app
    from config import reload_settings

    reload_settings()
    app = create_app(testing=True)

    with app.app_context():
        from extensions import db as sa_db

        # Clear anything create_all() may have seeded for our new table + the
        # extra column on translation_memory, so upgrade() runs cleanly.
        with sa_db.engine.begin() as conn:
            conn.execute(sa.text("DROP TABLE IF EXISTS translation_events"))
            conn.execute(sa.text("DROP TABLE IF EXISTS alembic_version"))
            # SQLite can't drop columns before 3.35; easiest is to drop the
            # whole table and let upgrade recreate just the column we need.
            # translation_memory lives in main DB, and we re-stamp from
            # dc8da0c509a8 which already includes it, so simply drop the
            # preseeded column by recreating the table without it.
            insp = sa.inspect(sa_db.engine)
            tm_cols = {c["name"] for c in insp.get_columns("translation_memory")}
            if "backend" in tm_cols:
                conn.execute(sa.text("ALTER TABLE translation_memory DROP COLUMN backend"))

        cfg = _alembic_config(url)
        command.stamp(cfg, PREVIOUS_HEAD)
        command.upgrade(cfg, "head")

        engine = sa.create_engine(url)
        try:
            yield engine
        finally:
            engine.dispose()
            sa_db.engine.dispose()

    reload_settings()


def test_upgrade_creates_table_and_indexes(migrated_db_engine):
    insp = sa.inspect(migrated_db_engine)
    assert "translation_events" in insp.get_table_names()

    cols = {c["name"] for c in insp.get_columns("translation_events")}
    assert cols == {
        "id",
        "backend",
        "source_lang",
        "target_lang",
        "lines_count",
        "chars_in",
        "chars_out",
        "tokens_in",
        "tokens_out",
        "cost_estimate_micro_usd",
        "cache_hit",
        "latency_ms",
        "status",
        "error_type",
        "error_msg",
        "job_id",
        "started_at",
        "finished_at",
    }

    ix = {i["name"] for i in insp.get_indexes("translation_events")}
    assert "ix_translation_events_backend_started_at" in ix
    assert "ix_translation_events_started_at" in ix
    assert "ix_translation_events_status" in ix
    assert "ix_translation_events_job_id" in ix


def test_translation_memory_gains_backend_column(migrated_db_engine):
    insp = sa.inspect(migrated_db_engine)
    cols = {c["name"] for c in insp.get_columns("translation_memory")}
    assert "backend" in cols


def test_cost_column_is_bigint(migrated_db_engine):
    """BigInt required — regular Int32 overflows at ~$2.1k cumulative cost."""
    insp = sa.inspect(migrated_db_engine)
    for col in insp.get_columns("translation_events"):
        if col["name"] == "cost_estimate_micro_usd":
            type_str = str(col["type"]).upper()
            assert "BIG" in type_str or type_str == "BIGINT", (
                f"cost column must be BigInteger, got {type_str}"
            )
            return
    raise AssertionError("cost_estimate_micro_usd column not found")
