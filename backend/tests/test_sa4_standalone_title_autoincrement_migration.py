"""sa4_standalone_title_autoincrement: existing SQLite tables stop reusing ids.

``standalone_series`` / ``standalone_movies`` were created without
AUTOINCREMENT, so SQLite handed a deleted title's id to the next new one and
the new title read the rows still stored under the old owner key (1.18.0-rc.2
end-to-end test). The migration rebuilds both tables with AUTOINCREMENT and
seeds ``sqlite_sequence`` past every id still referenced by an owner-keyed
row. Tracked databases get it from Alembic, untracked ones from the registered
repair; both must keep every row and index, and a second run changes nothing.
"""

from __future__ import annotations

from datetime import UTC, datetime

import sqlalchemy as sa

_NOW = datetime(2026, 10, 1, tzinfo=UTC).isoformat()

_OLD_DDL = (
    "CREATE TABLE standalone_series (id INTEGER NOT NULL, title TEXT NOT NULL, year INTEGER, "
    "folder_path TEXT NOT NULL, tmdb_id INTEGER, tvdb_id INTEGER, anilist_id INTEGER, "
    "imdb_id TEXT, poster_url TEXT, is_anime INTEGER, episode_count INTEGER, "
    "season_count INTEGER, metadata_source TEXT, created_at DATETIME NOT NULL, "
    "updated_at DATETIME NOT NULL, PRIMARY KEY (id), UNIQUE (folder_path))",
    "CREATE INDEX idx_standalone_series_tmdb ON standalone_series (tmdb_id)",
    "CREATE INDEX idx_standalone_series_anilist ON standalone_series (anilist_id)",
    "CREATE TABLE standalone_movies (id INTEGER NOT NULL, title TEXT NOT NULL, year INTEGER, "
    "file_path TEXT NOT NULL, tmdb_id INTEGER, imdb_id TEXT, poster_url TEXT, "
    "metadata_source TEXT, created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL, "
    "PRIMARY KEY (id), UNIQUE (file_path))",
    "CREATE INDEX idx_standalone_movies_tmdb ON standalone_movies (tmdb_id)",
)


def _engine(path):
    return sa.create_engine(f"sqlite:///{path}")


def _create_pre_sa4_schema(path) -> None:
    """Every table as create_all() makes it, the two title tables as 1.17/RC had them."""
    import db.models  # noqa: F401 — registers every model on the metadata
    from extensions import db

    engine = _engine(path)
    skip = {"standalone_series", "standalone_movies"}
    db.metadata.create_all(
        engine, tables=[t for t in db.metadata.sorted_tables if t.name not in skip]
    )
    with engine.begin() as conn:
        for stmt in _OLD_DDL:
            conn.execute(sa.text(stmt))
    engine.dispose()


def _seed(path) -> None:
    engine = _engine(path)
    with engine.begin() as conn:
        conn.execute(
            sa.text(
                "INSERT INTO standalone_series (id, title, folder_path, tmdb_id, created_at, "
                "updated_at) VALUES (2, 'Show', '/m/Show', 77, :t, :t), "
                "(3, 'Other', '/m/Other', NULL, :t, :t)"
            ),
            {"t": _NOW},
        )
        conn.execute(
            sa.text(
                "INSERT INTO standalone_movies (id, title, file_path, created_at, updated_at) "
                "VALUES (1, 'Film', '/m/Film.mkv', :t, :t)"
            ),
            {"t": _NOW},
        )
        # Rows of deleted titles: series 9 (glossary), movie 6 (settings).
        conn.execute(
            sa.text(
                "INSERT INTO glossary_entries (series_id, source_term, target_term, notes, "
                "term_type, approved, created_at, updated_at) "
                "VALUES (-9, 'OldTerm', 'AltBegriff', '', 'other', 1, :t, :t)"
            ),
            {"t": _NOW},
        )
        conn.execute(
            sa.text(
                "INSERT INTO movie_settings (radarr_movie_id, min_attempts_per_day, "
                "cleanup_foreign_tracks, updated_at) VALUES (-6, 0, 1, :t)"
            ),
            {"t": _NOW},
        )
        # A Sonarr key far above: positive keys are not standalone ids.
        conn.execute(
            sa.text(
                "INSERT INTO series_settings (sonarr_series_id, absolute_order, "
                "min_attempts_per_day, cleanup_foreign_tracks, updated_at) "
                "VALUES (1500, 0, 0, 0, :t)"
            ),
            {"t": _NOW},
        )
    engine.dispose()


def _state(path) -> dict:
    engine = _engine(path)
    try:
        with engine.connect() as conn:
            ddl = dict(
                conn.execute(
                    sa.text(
                        "SELECT name, sql FROM sqlite_master WHERE type='table' "
                        "AND name IN ('standalone_series', 'standalone_movies')"
                    )
                ).fetchall()
            )
            indexes = {
                r[0]
                for r in conn.execute(
                    sa.text(
                        "SELECT name FROM sqlite_master WHERE type='index' "
                        "AND tbl_name IN ('standalone_series', 'standalone_movies') "
                        "AND name NOT LIKE 'sqlite_autoindex%'"
                    )
                )
            }
            series = conn.execute(
                sa.text("SELECT id, title, folder_path, tmdb_id FROM standalone_series ORDER BY id")
            ).fetchall()
            movies = conn.execute(
                sa.text("SELECT id, title FROM standalone_movies ORDER BY id")
            ).fetchall()
            seq = dict(conn.execute(sa.text("SELECT name, seq FROM sqlite_sequence")).fetchall())
            tables = {
                r[0]
                for r in conn.execute(sa.text("SELECT name FROM sqlite_master WHERE type='table'"))
            }
        return {
            "ddl": ddl,
            "indexes": indexes,
            "series": [tuple(r) for r in series],
            "movies": [tuple(r) for r in movies],
            "seq": seq,
            "tables": tables,
        }
    finally:
        engine.dispose()


def _assert_rebuilt(path) -> None:
    state = _state(path)
    for table in ("standalone_series", "standalone_movies"):
        assert "AUTOINCREMENT" in state["ddl"][table].upper(), table
    assert state["indexes"] == {
        "idx_standalone_series_tmdb",
        "idx_standalone_series_anilist",
        "idx_standalone_movies_tmdb",
    }
    assert state["series"] == [(2, "Show", "/m/Show", 77), (3, "Other", "/m/Other", None)]
    assert state["movies"] == [(1, "Film")]
    # Past the highest live id and every owner key of a deleted title.
    assert state["seq"]["standalone_series"] == 9
    assert state["seq"]["standalone_movies"] == 6
    assert not [t for t in state["tables"] if "sa4" in t]


def _next_ids(path) -> tuple[int, int]:
    engine = _engine(path)
    try:
        with engine.begin() as conn:
            conn.execute(
                sa.text(
                    "INSERT INTO standalone_series (title, folder_path, created_at, updated_at) "
                    "VALUES ('New', '/m/New', :t, :t)"
                ),
                {"t": _NOW},
            )
            conn.execute(
                sa.text(
                    "INSERT INTO standalone_movies (title, file_path, created_at, updated_at) "
                    "VALUES ('New', '/m/New.mkv', :t, :t)"
                ),
                {"t": _NOW},
            )
            return (
                conn.execute(sa.text("SELECT MAX(id) FROM standalone_series")).scalar(),
                conn.execute(sa.text("SELECT MAX(id) FROM standalone_movies")).scalar(),
            )
    finally:
        engine.dispose()


def _boot(db_path, monkeypatch):
    from config import reload_settings
    from db import close_db

    monkeypatch.setenv("SUBLARR_DB_PATH", str(db_path))
    monkeypatch.setenv("SUBLARR_LOG_LEVEL", "ERROR")
    reload_settings()
    try:
        from app import create_app

        create_app(testing=True)
    finally:
        close_db()


def test_rebuild_is_idempotent_and_keeps_rows(tmp_path):
    from db.migrations.versions.sa4_standalone_title_autoincrement import (
        ensure_title_autoincrement,
    )

    path = tmp_path / "direct.db"
    _create_pre_sa4_schema(path)
    _seed(path)

    engine = _engine(path)
    with engine.begin() as conn:
        assert ensure_title_autoincrement(conn) == 2
    with engine.begin() as conn:
        assert ensure_title_autoincrement(conn) == 0
    engine.dispose()
    _assert_rebuilt(path)
    assert _next_ids(path) == (10, 7)


def test_seed_never_lowers_an_existing_sequence(tmp_path):
    import db.models  # noqa: F401
    from db.migrations.versions.sa4_standalone_title_autoincrement import (
        ensure_title_autoincrement,
    )
    from extensions import db

    path = tmp_path / "fresh.db"
    engine = _engine(path)
    db.metadata.create_all(engine)
    with engine.begin() as conn:
        conn.execute(
            sa.text(
                "INSERT INTO standalone_series (id, title, folder_path, created_at, updated_at) "
                "VALUES (40, 'Gone', '/m/Gone', :t, :t)"
            ),
            {"t": _NOW},
        )
        conn.execute(sa.text("DELETE FROM standalone_series"))
        assert ensure_title_autoincrement(conn) == 0
        seq = conn.execute(
            sa.text("SELECT seq FROM sqlite_sequence WHERE name = 'standalone_series'")
        ).scalar()
    engine.dispose()
    assert seq == 40


def test_postgresql_is_a_no_op():
    from db.migrations.versions.sa4_standalone_title_autoincrement import (
        ensure_title_autoincrement,
    )

    class _Dialect:
        name = "postgresql"

    class _Conn:
        dialect = _Dialect()

        def execute(self, *_a, **_kw):
            raise AssertionError("PostgreSQL must not be touched")

    assert ensure_title_autoincrement(_Conn()) == 0


def test_tracked_database_upgrades(tmp_path, monkeypatch):
    path = tmp_path / "tracked.db"
    _create_pre_sa4_schema(path)
    _seed(path)
    engine = _engine(path)
    with engine.begin() as conn:
        conn.execute(
            sa.text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL PRIMARY KEY)")
        )
        conn.execute(
            sa.text("INSERT INTO alembic_version VALUES ('sa3_automation_queue_series_key')")
        )
    engine.dispose()

    _boot(path, monkeypatch)
    _assert_rebuilt(path)
    engine = _engine(path)
    with engine.connect() as conn:
        version = conn.execute(sa.text("SELECT version_num FROM alembic_version")).scalar()
    engine.dispose()
    assert version == "sa4_standalone_title_autoincrement"

    _boot(path, monkeypatch)
    _assert_rebuilt(path)
    assert _next_ids(path) == (10, 7)


def test_untracked_database_gets_the_rebuild(tmp_path, monkeypatch):
    path = tmp_path / "untracked.db"
    _create_pre_sa4_schema(path)
    _seed(path)

    _boot(path, monkeypatch)
    _assert_rebuilt(path)
    _boot(path, monkeypatch)
    _assert_rebuilt(path)
    assert _next_ids(path) == (10, 7)
