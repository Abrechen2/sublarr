"""One-shot move of pre-1.18 standalone rows to their owner key.

Before 1.18.0 a standalone title's profile assignment, settings, glossary and
fansub rows were written under its positive row id whenever no Sonarr/Radarr
client was configured. ``services.standalone_owner_keys`` moves them to the
negated id once per database — only when the install has no arr configured
and the data shows no arr history, because otherwise the positive key may
belong to the arr (Codex design review, finding 2).
"""

from __future__ import annotations

from datetime import UTC, datetime

import sqlalchemy as sa

_NOW = datetime(2026, 10, 1, tzinfo=UTC)


def _profiles() -> None:
    from db.models.core import LanguageProfile
    from extensions import db

    for pid, name in ((1, "Default"), (2, "French")):
        if db.session.get(LanguageProfile, pid) is None:
            db.session.add(
                LanguageProfile(
                    id=pid, name=name, is_default=int(pid == 1), created_at=_NOW, updated_at=_NOW
                )
            )
    db.session.commit()


def _seed(conn) -> None:
    t = {"t": _NOW}
    conn.execute(
        sa.text(
            "INSERT INTO standalone_series (id, title, folder_path, created_at, updated_at) "
            "VALUES (3, 'Show', '/m/Show', :t, :t)"
        ),
        t,
    )
    conn.execute(
        sa.text(
            "INSERT INTO standalone_movies (id, title, file_path, created_at, updated_at) "
            "VALUES (4, 'Film', '/m/Film.mkv', :t, :t)"
        ),
        t,
    )
    conn.execute(
        sa.text(
            "INSERT INTO series_language_profiles (sonarr_series_id, profile_id) "
            "VALUES (3, 2), (8, 2)"
        )
    )
    conn.execute(
        sa.text("INSERT INTO movie_language_profiles (radarr_movie_id, profile_id) VALUES (4, 2)")
    )
    conn.execute(
        sa.text(
            "INSERT INTO series_settings (sonarr_series_id, absolute_order, min_attempts_per_day, "
            "cleanup_foreign_tracks, updated_at) VALUES (3, 1, 0, 0, :t)"
        ),
        t,
    )
    conn.execute(
        sa.text(
            "INSERT INTO glossary_entries (series_id, source_term, target_term, term_type, "
            "approved, created_at, updated_at) VALUES (3, 'Titan', 'Titan', 'other', 1, :t, :t), "
            "(NULL, 'g', 'g', 'other', 1, :t, :t)"
        ),
        t,
    )
    # A standalone wanted row and a health finding keyed by its id (1.17.3).
    conn.execute(
        sa.text(
            "INSERT INTO wanted_items (id, item_type, file_path, title, standalone_series_id, "
            "status, priority, error_count, added_at, updated_at) VALUES "
            "(11, 'episode', '/m/Show/S01E01.mkv', 't', 3, 'wanted', 'standard', 0, :t, :t)"
        ),
        t,
    )
    conn.execute(
        sa.text(
            "INSERT INTO standalone_episodes (id, standalone_series_id, file_path, created_at, "
            "updated_at) VALUES (5, 3, '/m/Show/S01E01.mkv', :t, :t)"
        ),
        t,
    )
    for path in ("/m/Show/S01E01.de.srt", "/m/Other/x.srt"):
        conn.execute(
            sa.text(
                "INSERT INTO subtitle_health_findings (episode_id, target_kind, target_path, lang, "
                "issue_type, severity, count, snippets_json, raw_hash, status, scanner_version, "
                "detected_at) VALUES (11, 'sidecar', :p, 'de', 'mojibake', 'warning', 1, '[]', "
                "'h', 'open', 1, :t)"
            ),
            {"p": path, "t": _NOW},
        )


def _keys(conn, table: str, col: str) -> list:
    return sorted(
        (r[0] for r in conn.execute(sa.text(f"SELECT {col} FROM {table}"))),  # noqa: S608
        key=lambda v: (v is None, v),
    )


def _finding_ids(conn) -> list:
    return sorted(
        (r[0], r[1])
        for r in conn.execute(
            sa.text("SELECT target_path, episode_id FROM subtitle_health_findings")
        )
    )


def _engine(app_ctx):
    """The app's engine, with the marker the app start just wrote removed."""
    from extensions import db

    with db.engine.begin() as conn:
        conn.execute(
            sa.text(
                "DELETE FROM untracked_data_repairs WHERE revision = 'sa2_standalone_owner_keys'"
            )
        )
    return db.engine


def test_moves_standalone_rows_once_without_arr(app_ctx):
    from services.standalone_owner_keys import migrate_legacy_owner_keys

    engine = _engine(app_ctx)
    _profiles()
    with engine.begin() as conn:
        _seed(conn)

    result = migrate_legacy_owner_keys(engine, sonarr_configured=False, radarr_configured=False)
    assert result is not None and result["series"] > 0 and result["movies"] == 1

    with engine.connect() as conn:
        # 8 is no standalone series: stays where it is.
        assert _keys(conn, "series_language_profiles", "sonarr_series_id") == [-3, 8]
        assert _keys(conn, "movie_language_profiles", "radarr_movie_id") == [-4]
        assert _keys(conn, "series_settings", "sonarr_series_id") == [-3]
        assert _keys(conn, "glossary_entries", "series_id") == [-3, None]
        assert _finding_ids(conn) == [("/m/Other/x.srt", 11), ("/m/Show/S01E01.de.srt", -5)]

    # Second start: marker present, nothing happens even if a new row appears.
    with engine.begin() as conn:
        conn.execute(
            sa.text(
                "INSERT INTO series_language_profiles (sonarr_series_id, profile_id) VALUES (3, 1)"
            )
        )
    assert (
        migrate_legacy_owner_keys(engine, sonarr_configured=False, radarr_configured=False) is None
    )
    with engine.connect() as conn:
        assert _keys(conn, "series_language_profiles", "sonarr_series_id") == [-3, 3, 8]


def test_nothing_moves_with_sonarr_configured(app_ctx):
    from services.standalone_owner_keys import migrate_legacy_owner_keys

    engine = _engine(app_ctx)
    _profiles()
    with engine.begin() as conn:
        _seed(conn)

    migrate_legacy_owner_keys(engine, sonarr_configured=True, radarr_configured=False)
    with engine.connect() as conn:
        assert _keys(conn, "series_language_profiles", "sonarr_series_id") == [3, 8]
        assert _keys(conn, "series_settings", "sonarr_series_id") == [3]
        # The movie side has no Radarr: it moves.
        assert _keys(conn, "movie_language_profiles", "radarr_movie_id") == [-4]


def test_nothing_moves_after_a_sonarr_period(app_ctx):
    """Sonarr removed before the upgrade: its rows must not go to standalone titles."""
    from services.standalone_owner_keys import migrate_legacy_owner_keys

    engine = _engine(app_ctx)
    _profiles()
    with engine.begin() as conn:
        _seed(conn)
        conn.execute(
            sa.text(
                "INSERT INTO wanted_items (item_type, file_path, title, sonarr_series_id, status, "
                "priority, error_count, added_at, updated_at) VALUES ('episode', '/tv/x.mkv', "
                "'t', 3, 'wanted', 'standard', 0, :t, :t)"
            ),
            {"t": _NOW},
        )

    result = migrate_legacy_owner_keys(engine, sonarr_configured=False, radarr_configured=False)
    assert result["series"] == 0
    with engine.connect() as conn:
        assert _keys(conn, "series_language_profiles", "sonarr_series_id") == [3, 8]


def test_an_existing_owner_key_row_is_not_overwritten(app_ctx):
    from services.standalone_owner_keys import migrate_legacy_owner_keys

    engine = _engine(app_ctx)
    _profiles()
    with engine.begin() as conn:
        _seed(conn)
        conn.execute(
            sa.text(
                "INSERT INTO series_language_profiles (sonarr_series_id, profile_id) VALUES (-3, 1)"
            )
        )

    migrate_legacy_owner_keys(engine, sonarr_configured=False, radarr_configured=False)
    with engine.connect() as conn:
        rows = sorted(
            tuple(r)
            for r in conn.execute(
                sa.text("SELECT sonarr_series_id, profile_id FROM series_language_profiles")
            )
        )
    assert rows == [(-3, 1), (3, 2), (8, 2)]


def test_startup_runs_the_move(tmp_path, monkeypatch):
    """Wired into create_app: an untracked SQLite install without arr gets it."""
    from config import reload_settings
    from db import close_db

    db_path = tmp_path / "boot.db"
    monkeypatch.setenv("SUBLARR_DB_PATH", str(db_path))
    monkeypatch.setenv("SUBLARR_LOG_LEVEL", "ERROR")
    reload_settings()
    try:
        from app import create_app

        create_app(testing=True)
    finally:
        close_db()

    engine = sa.create_engine(f"sqlite:///{db_path}")
    with engine.connect() as conn:
        marker = conn.execute(
            sa.text(
                "SELECT revision FROM untracked_data_repairs "
                "WHERE revision = 'sa2_standalone_owner_keys'"
            )
        ).scalar()
    engine.dispose()
    assert marker == "sa2_standalone_owner_keys"
