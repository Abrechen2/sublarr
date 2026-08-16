"""The task_type migration must survive both shapes of database it meets.

Two of them exist and they need opposite handling:

1. A real install, where `subtitle_automation_queue` was created by the old
   migration with `wanted_item_id` UNIQUE. Here the old constraint must be
   dropped and replaced by the (wanted_item_id, task_type) pair.
2. A database built by `create_all()` from current model metadata, which
   already has the composite constraint and never had the single-column one.
   Here the migration must do nothing rather than fail.

The first version of this migration handled only (1) and took down every
other migration test in the suite, because batch_alter_table defers
drop_constraint to its flush() at __exit__ — so the try/except wrapped
around the call could not see the failure.
"""

from __future__ import annotations

import os

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text

_PRE_MIGRATION_REV = "c8d9e0f1a2b3"
_TABLE = "subtitle_automation_queue"
_NEW_UQ = "uq_automation_queue_item_task"

_OLD_TABLE_DDL = """
CREATE TABLE subtitle_automation_queue (
    id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
    wanted_item_id INTEGER NOT NULL UNIQUE,
    file_path TEXT NOT NULL,
    target_language VARCHAR(8) NOT NULL,
    state VARCHAR(10) NOT NULL,
    attempt_count INTEGER NOT NULL,
    next_retry_at DATETIME,
    last_error TEXT,
    last_started_at DATETIME,
    last_finished_at DATETIME,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL
)
"""

# A real install has the drain index too; batch mode rebuilds the table, so
# whether it survives is a genuine question about the migration.
_OLD_INDEX_DDL = (
    "CREATE INDEX idx_subtitle_automation_queue_drain "
    "ON subtitle_automation_queue (state, next_retry_at)"
)

_INSERT = (
    "INSERT INTO subtitle_automation_queue "
    "(wanted_item_id, file_path, target_language, state, attempt_count, "
    " created_at, updated_at) "
    "VALUES (:wid, :path, 'de', 'pending', 0, '2026-01-01', '2026-01-01')"
)


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


def _stamp(engine, rev: str) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE IF NOT EXISTS alembic_version "
                "(version_num VARCHAR(32) NOT NULL PRIMARY KEY)"
            )
        )
        conn.execute(
            text("INSERT OR REPLACE INTO alembic_version (version_num) VALUES (:rev)"),
            {"rev": rev},
        )


@pytest.fixture()
def legacy_db(tmp_path):
    """A database carrying the pre-migration table: wanted_item_id UNIQUE."""
    db_path = str(tmp_path / "legacy.db")
    app = _make_minimal_app(db_path)
    with app.app_context():
        db = app.extensions["migrate"].db
        engine = db.engine
        db.create_all()
        with engine.begin() as conn:
            conn.execute(text(f"DROP TABLE {_TABLE}"))
            conn.execute(text(_OLD_TABLE_DDL))
            conn.execute(text(_OLD_INDEX_DDL))
            conn.execute(text(_INSERT), {"wid": 42, "path": "/media/x.mkv"})
        _stamp(engine, _PRE_MIGRATION_REV)
        cfg = _cfg(db_path)
        command.upgrade(cfg, "head")
        yield engine, cfg


@pytest.fixture()
def create_all_db(tmp_path):
    """A database built from current model metadata — already the new shape."""
    db_path = str(tmp_path / "fresh.db")
    app = _make_minimal_app(db_path)
    with app.app_context():
        db = app.extensions["migrate"].db
        engine = db.engine
        db.create_all()
        _stamp(engine, _PRE_MIGRATION_REV)
        cfg = _cfg(db_path)
        command.upgrade(cfg, "head")
        yield engine, cfg


class TestLegacyDatabase:
    def test_columns_are_added_and_backfilled(self, legacy_db):
        engine, _ = legacy_db
        with engine.connect() as conn:
            cols = {c["name"] for c in inspect(conn).get_columns(_TABLE)}
            assert {"task_type", "source_language"}.issubset(cols)
            task_type = conn.execute(
                text(f"SELECT task_type FROM {_TABLE} WHERE wanted_item_id = 42")  # noqa: S608
            ).scalar()
        assert task_type == "embedded_extract", "existing rows are extractions"

    def test_the_old_single_column_unique_is_gone(self, legacy_db):
        engine, _ = legacy_db
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO subtitle_automation_queue "
                    "(wanted_item_id, task_type, file_path, target_language, state,"
                    " attempt_count, created_at, updated_at) "
                    "VALUES (42, 'sidecar_translate', '/media/x.eng.ass', 'de',"
                    " 'pending', 0, '2026-01-01', '2026-01-01')"
                )
            )
        with engine.connect() as conn:
            n = conn.execute(
                text(f"SELECT COUNT(*) FROM {_TABLE} WHERE wanted_item_id = 42")  # noqa: S608
            ).scalar()
        assert n == 2

    def test_the_composite_unique_is_live(self, legacy_db):
        """The key is (wanted_item_id, task_type, file_path) since d5b3c8a1f742.

        It was the first two until then. `file_path` joined it because
        `wanted_item_id` is not durable for an `auto_sync` row — SQLite reuses
        the rowid of the wanted item that was deleted right after the row was
        written, and the item that inherits it would otherwise collide with a
        stranger's pending sync.
        """
        engine, _ = legacy_db
        import sqlalchemy as sa

        with pytest.raises(sa.exc.IntegrityError), engine.begin() as conn:
            conn.execute(text(_INSERT), {"wid": 42, "path": "/media/x.mkv"})

    def test_the_same_item_may_hold_two_paths(self, legacy_db):
        engine, _ = legacy_db
        with engine.begin() as conn:
            conn.execute(text(_INSERT), {"wid": 42, "path": "/media/other.mkv"})
        with engine.connect() as conn:
            n = conn.execute(
                text(  # noqa: S608 — constant table name
                    f"SELECT COUNT(*) FROM {_TABLE} "
                    "WHERE wanted_item_id = 42 AND task_type = 'embedded_extract'"
                )
            ).scalar()
        assert n == 2

    def test_the_drain_index_survives_the_table_rebuild(self, legacy_db):
        engine, _ = legacy_db
        with engine.connect() as conn:
            names = {i["name"] for i in inspect(conn).get_indexes(_TABLE)}
        assert "idx_subtitle_automation_queue_drain" in names

    def test_migration_is_idempotent(self, legacy_db):
        _, cfg = legacy_db
        command.upgrade(cfg, "head")  # second run must not raise

    def test_the_widened_key_round_trips(self, legacy_db):
        """Down and up again — the rollback path has to actually work.

        The narrower key cannot hold while rows only the wider one allowed are
        present, so the downgrade has to drop one row per group first. It picks
        by how much is still owed on the row rather than by age: keeping the
        oldest would routinely keep a `done` row and delete the `pending` one
        beside it, which is the wrong half of the pair to lose.
        """
        engine, cfg = legacy_db
        with engine.begin() as conn:
            # Two rows the old key could never have held side by side.
            conn.execute(
                text(  # noqa: S608 — constant table name
                    f"UPDATE {_TABLE} SET state = 'done' WHERE wanted_item_id = 42"
                )
            )
            conn.execute(text(_INSERT), {"wid": 42, "path": "/media/newer.mkv"})

        command.downgrade(cfg, "c7e1a9d4b6f3")

        with engine.connect() as conn:
            uniques = {
                tuple(sorted(u["column_names"]))
                for u in inspect(conn).get_unique_constraints(_TABLE)
            }
            survivors = conn.execute(
                text(  # noqa: S608 — constant table name
                    f"SELECT file_path, state FROM {_TABLE} WHERE wanted_item_id = 42"
                )
            ).fetchall()
        assert ("task_type", "wanted_item_id") in uniques
        assert ("file_path", "task_type", "wanted_item_id") not in uniques
        # The pending row survived; the done one was the expendable half.
        assert [tuple(r) for r in survivors] == [("/media/newer.mkv", "pending")]

        command.upgrade(cfg, "head")
        with engine.connect() as conn:
            uniques = {
                tuple(sorted(u["column_names"]))
                for u in inspect(conn).get_unique_constraints(_TABLE)
            }
        assert ("file_path", "task_type", "wanted_item_id") in uniques


class TestCreateAllDatabase:
    def test_migration_is_a_no_op(self, create_all_db):
        """No single-column UNIQUE to drop here. The first cut of this
        migration tried anyway and raised, which broke every other
        migration test in the suite."""
        engine, _ = create_all_db
        with engine.connect() as conn:
            insp = inspect(conn)
            cols = {c["name"] for c in insp.get_columns(_TABLE)}
            uniques = {u["name"] for u in insp.get_unique_constraints(_TABLE)}
        assert {"task_type", "source_language"}.issubset(cols)
        assert _NEW_UQ in uniques

    def test_migration_is_idempotent(self, create_all_db):
        _, cfg = create_all_db
        command.upgrade(cfg, "head")
