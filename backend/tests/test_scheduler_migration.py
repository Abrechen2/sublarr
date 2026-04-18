"""Migration regression tests for scheduler_infrastructure.

The Sublarr DB install path is "create_all + stamp" (see app.py + env.py), not
"upgrade from zero" — so a clean round-trip through every alembic revision is
not possible today. These tests instead isolate the scheduler migration: they
stamp a fresh DB at the previous head, apply a single ``upgrade +1``, and
assert the schema matches our expectations.
"""

from __future__ import annotations

import os

import pytest
import sqlalchemy as sa

# Revisions under test — keep in sync with the migration file.
PREVIOUS_HEAD = "p4a_readd_wanted_sonarr_idx"
SCHEDULER_REVISION = "dc8da0c509a8"


def _alembic_config(sqlalchemy_url: str):
    """Build an Alembic Config pointing at backend/db/migrations.

    Resolves the migrations folder via the test file's location so callers
    are robust to the invocation CWD (pytest may run from backend/ or repo
    root).
    """
    from alembic.config import Config

    backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    script_location = os.path.join(backend_dir, "db", "migrations")

    cfg = Config()
    cfg.set_main_option("script_location", script_location)
    cfg.set_main_option("sqlalchemy.url", sqlalchemy_url)
    return cfg


@pytest.fixture
def migrated_db_engine(tmp_path, monkeypatch):
    """Fresh SQLite DB stamped at the previous head, then upgraded to head.

    Flow:
    1. create_app() runs create_all() for a fresh DB, which also sets up the
       Flask app context env.py requires.
    2. We stamp alembic_version at ``PREVIOUS_HEAD`` (the revision preceding
       scheduler_infrastructure). This bypasses the historical chain that
       assumes legacy schema state.
    3. command.upgrade(head) then applies only the new scheduler revision.
    """
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

        # Clear anything create_all() may have seeded for our new tables,
        # so upgrade() runs CREATE TABLE cleanly.
        with sa_db.engine.begin() as conn:
            conn.execute(sa.text("DROP TABLE IF EXISTS scheduler_job_runs"))
            conn.execute(sa.text("DROP TABLE IF EXISTS apscheduler_jobs"))
            conn.execute(sa.text("DROP TABLE IF EXISTS alembic_version"))

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


def test_upgrade_creates_both_tables(migrated_db_engine):
    """After running migrations, both tables exist with expected indexes."""
    insp = sa.inspect(migrated_db_engine)
    assert "scheduler_job_runs" in insp.get_table_names()
    assert "apscheduler_jobs" in insp.get_table_names()

    run_cols = {c["name"] for c in insp.get_columns("scheduler_job_runs")}
    assert run_cols == {
        "id",
        "job_id",
        "started_at",
        "finished_at",
        "duration_ms",
        "status",
        "triggered_by",
        "error_type",
        "error_msg",
    }
    aps_cols = {c["name"] for c in insp.get_columns("apscheduler_jobs")}
    assert aps_cols == {"id", "next_run_time", "job_state"}

    run_ix = {ix["name"] for ix in insp.get_indexes("scheduler_job_runs")}
    assert "ix_scheduler_job_runs_job_id_started_at" in run_ix
    assert "ix_scheduler_job_runs_started_at" in run_ix
    assert "ix_scheduler_job_runs_status" in run_ix

    aps_ix = {ix["name"] for ix in insp.get_indexes("apscheduler_jobs")}
    assert "ix_apscheduler_jobs_next_run_time" in aps_ix


def test_downgrade_drops_both_tables(migrated_db_engine):
    """Downgrade -1 drops the scheduler tables; upgrade head re-creates them."""
    from alembic import command

    cfg = _alembic_config(str(migrated_db_engine.url))
    command.downgrade(cfg, "-1")
    insp = sa.inspect(migrated_db_engine)
    assert "scheduler_job_runs" not in insp.get_table_names()
    assert "apscheduler_jobs" not in insp.get_table_names()

    command.upgrade(cfg, "head")
    insp = sa.inspect(migrated_db_engine)
    assert "scheduler_job_runs" in insp.get_table_names()
    assert "apscheduler_jobs" in insp.get_table_names()


def test_apscheduler_jobs_shape_matches_library_expectation():
    """apscheduler_jobs columns match what SQLAlchemyJobStore writes."""
    from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore

    store = SQLAlchemyJobStore(url="sqlite:///:memory:", tablename="apscheduler_jobs")
    expected_cols = {c.name for c in store.jobs_t.columns}
    assert expected_cols == {"id", "next_run_time", "job_state"}
