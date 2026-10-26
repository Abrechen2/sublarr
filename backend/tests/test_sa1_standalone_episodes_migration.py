"""sa1_standalone_episodes: the table arrives on both routes into a database.

An Alembic-tracked install gets it from the migration; an untracked one from
``create_all()`` plus the registered data repair. Both must backfill one row
per standalone episode file that has a wanted row, and a second run must add
nothing. Exercised through ``create_app`` like the other migration tests.
"""

from __future__ import annotations

from datetime import UTC, datetime

import sqlalchemy as sa

_NOW = datetime(2026, 10, 1, tzinfo=UTC).isoformat()


def _engine(path):
    return sa.create_engine(f"sqlite:///{path}")


def _create_schema_without_episodes(path) -> None:
    import db.models  # noqa: F401 — registers every model on the metadata
    from extensions import db

    engine = _engine(path)
    tables = [t for t in db.metadata.sorted_tables if t.name != "standalone_episodes"]
    db.metadata.create_all(engine, tables=tables)
    engine.dispose()


def _seed(path) -> None:
    engine = _engine(path)
    with engine.begin() as conn:
        conn.execute(
            sa.text(
                "INSERT INTO standalone_series (id, title, folder_path, created_at, updated_at) "
                "VALUES (3, 'Show', '/media/Show', :t, :t), (4, 'Other', '/media/Other', :t, :t)"
            ),
            {"t": _NOW},
        )
        rows = [
            # two languages of one file -> one episode
            ("/media/Show/S01E01.mkv", "S01E01", 3, "de"),
            ("/media/Show/S01E01.mkv", "S01E01", 3, "en"),
            ("/media/Show/S01E02.mkv", "S01E02", 3, "de"),
            # orphan: series 9 does not exist -> skipped
            ("/media/Gone/S01E01.mkv", "S01E01", 9, "de"),
            # Sonarr row -> skipped
            ("/tv/Sonarr/S01E01.mkv", "S01E01", None, "de"),
        ]
        for fp, se, sid, lang in rows:
            conn.execute(
                sa.text(
                    "INSERT INTO wanted_items (item_type, file_path, title, season_episode, "
                    "standalone_series_id, sonarr_series_id, target_language, status, "
                    "priority, error_count, added_at, updated_at) VALUES ('episode', :fp, 't', "
                    ":se, :sid, :sonarr, :lang, 'wanted', 'standard', 0, :t, :t)"
                ),
                {
                    "fp": fp,
                    "se": se,
                    "sid": sid,
                    "sonarr": None if sid else 12,
                    "lang": lang,
                    "t": _NOW,
                },
            )
        # A movie row of a standalone movie is not an episode.
        conn.execute(
            sa.text(
                "INSERT INTO wanted_items (item_type, file_path, title, standalone_movie_id, "
                "target_language, status, priority, error_count, added_at, updated_at) "
                "VALUES ('movie', '/media/Movie.mkv', 'm', 1, 'de', 'wanted', 'standard', 0, "
                ":t, :t)"
            ),
            {"t": _NOW},
        )
    engine.dispose()


def _episodes(path) -> list[tuple]:
    engine = _engine(path)
    try:
        with engine.connect() as conn:
            return [
                tuple(r)
                for r in conn.execute(
                    sa.text(
                        "SELECT standalone_series_id, file_path, season, episode "
                        "FROM standalone_episodes ORDER BY file_path"
                    )
                )
            ]
    finally:
        engine.dispose()


_EXPECTED = [
    (3, "/media/Show/S01E01.mkv", 1, 1),
    (3, "/media/Show/S01E02.mkv", 1, 2),
]


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


def test_backfill_is_idempotent(tmp_path):
    from db.migrations.versions.sa1_standalone_episodes import backfill_episodes

    path = tmp_path / "direct.db"
    import db.models  # noqa: F401
    from extensions import db

    engine = _engine(path)
    db.metadata.create_all(engine)
    engine.dispose()
    _seed(path)

    engine = _engine(path)
    with engine.begin() as conn:
        assert backfill_episodes(conn) == 2
    with engine.begin() as conn:
        assert backfill_episodes(conn) == 0
    engine.dispose()
    assert _episodes(path) == _EXPECTED


def test_tracked_database_upgrades_and_backfills(tmp_path, monkeypatch):
    path = tmp_path / "tracked.db"
    _create_schema_without_episodes(path)
    _seed(path)
    engine = _engine(path)
    with engine.begin() as conn:
        conn.execute(
            sa.text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL PRIMARY KEY)")
        )
        conn.execute(sa.text("INSERT INTO alembic_version VALUES ('tvp1_track_variant_policy')"))
    engine.dispose()

    _boot(path, monkeypatch)

    assert _episodes(path) == _EXPECTED
    engine = _engine(path)
    with engine.connect() as conn:
        version = conn.execute(sa.text("SELECT version_num FROM alembic_version")).scalar()
    engine.dispose()
    assert version == "sa4_standalone_autoincrement"

    # A second start changes nothing.
    _boot(path, monkeypatch)
    assert _episodes(path) == _EXPECTED


def test_untracked_database_gets_table_and_backfill(tmp_path, monkeypatch):
    path = tmp_path / "untracked.db"
    _create_schema_without_episodes(path)
    _seed(path)

    _boot(path, monkeypatch)
    assert _episodes(path) == _EXPECTED

    _boot(path, monkeypatch)
    assert _episodes(path) == _EXPECTED


def test_downgrade_drops_table_and_negative_findings(tmp_path):
    """Negative-id health findings would point at ids a later upgrade reuses."""
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    from db.migrations.versions import sa1_standalone_episodes as mig

    path = tmp_path / "down.db"
    import db.models  # noqa: F401
    from extensions import db

    engine = _engine(path)
    db.metadata.create_all(engine)
    with engine.begin() as conn:
        for ep_id in (-5, 7):
            conn.execute(
                sa.text(
                    "INSERT INTO subtitle_health_findings (episode_id, target_kind, target_path, "
                    "lang, issue_type, severity, count, snippets_json, raw_hash, status, "
                    "scanner_version, detected_at) VALUES (:e, 'sidecar', '/x.srt', 'de', "
                    "'mojibake', 'warning', 1, '[]', 'h', 'open', 1, :t)"
                ),
                {"e": ep_id, "t": _NOW},
            )
        ctx = MigrationContext.configure(conn)
        with Operations.context(ctx):
            mig.downgrade()
    with engine.connect() as conn:
        assert not sa.inspect(conn).has_table("standalone_episodes")
        left = [
            r[0] for r in conn.execute(sa.text("SELECT episode_id FROM subtitle_health_findings"))
        ]
    engine.dispose()
    assert left == [7]
