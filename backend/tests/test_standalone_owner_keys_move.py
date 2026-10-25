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
    for path in ("/m/Show/S01E01.de.srt", "/m/Show/Extras/x.srt"):
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
        assert _finding_ids(conn) == [("/m/Show/Extras/x.srt", 11), ("/m/Show/S01E01.de.srt", -5)]

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


def _insert(conn, sql: str, **params) -> None:
    conn.execute(sa.text(sql), {"t": _NOW, **params})


def _download(conn, path: str) -> None:
    _insert(
        conn,
        "INSERT INTO subtitle_downloads (provider_name, subtitle_id, language, file_path, "
        "downloaded_at) VALUES ('p', 's', 'de', :p, :t)",
        p=path,
    )


def _config(conn, key: str, value: str) -> None:
    _insert(
        conn,
        "INSERT INTO config_entries (key, value, updated_at) VALUES (:k, :v, :t)",
        k=key,
        v=value,
    )


def _assert_untouched(conn, *, series: bool, movies: bool) -> None:
    if series:
        assert _keys(conn, "series_language_profiles", "sonarr_series_id") == [3, 8]
        assert _keys(conn, "series_settings", "sonarr_series_id") == [3]
        assert _keys(conn, "glossary_entries", "series_id") == [3, None]
        assert ("/m/Show/S01E01.de.srt", 11) in _finding_ids(conn)
    if movies:
        assert _keys(conn, "movie_language_profiles", "radarr_movie_id") == [4]


def test_drained_radarr_queue_with_download_history_moves_nothing(app_ctx, caplog):
    """Codex finding: Radarr's wanted rows drained by successful downloads,
    Radarr removed before the upgrade. Its download history is still there, so
    movie 4's settings must not go to standalone movie 4."""
    from services.standalone_owner_keys import migrate_legacy_owner_keys

    engine = _engine(app_ctx)
    _profiles()
    with engine.begin() as conn:
        _seed(conn)
        _download(conn, "/m/Show/S01E01.de.srt")  # standalone's own: no evidence
        _download(conn, "/movies/Film (2020)/Film.de.srt")  # not a standalone title

    with caplog.at_level("WARNING", logger="services.standalone_owner_keys"):
        result = migrate_legacy_owner_keys(engine, sonarr_configured=False, radarr_configured=False)
    assert result == {"series": 0, "movies": 0, "findings": 0}
    with engine.connect() as conn:
        # A path cannot be told apart between Sonarr and Radarr: both sides stay.
        _assert_untouched(conn, series=True, movies=True)
    warnings = [r for r in caplog.records if r.levelname == "WARNING"]
    assert len(warnings) == 1
    msg = warnings[0].getMessage()
    assert "subtitle_downloads" in msg and "kept" in msg


def test_old_radarr_url_keeps_movie_rows(app_ctx):
    from services.standalone_owner_keys import migrate_legacy_owner_keys

    engine = _engine(app_ctx)
    _profiles()
    with engine.begin() as conn:
        _seed(conn)
        _config(conn, "radarr_url", "http://radarr:7878")

    result = migrate_legacy_owner_keys(engine, sonarr_configured=False, radarr_configured=False)
    assert result["movies"] == 0 and result["series"] > 0
    with engine.connect() as conn:
        _assert_untouched(conn, series=False, movies=True)
        assert _keys(conn, "series_language_profiles", "sonarr_series_id") == [-3, 8]


def test_old_sonarr_instances_keep_series_rows(app_ctx):
    from services.standalone_owner_keys import migrate_legacy_owner_keys

    engine = _engine(app_ctx)
    _profiles()
    with engine.begin() as conn:
        _seed(conn)
        _config(conn, "sonarr_instances_json", '[{"name": "a", "url": "http://s"}]')
        # Cleared fields are no evidence.
        _config(conn, "radarr_url", "")
        _config(conn, "radarr_instances_json", "[]")

    result = migrate_legacy_owner_keys(engine, sonarr_configured=False, radarr_configured=False)
    assert result["series"] == 0 and result["findings"] == 0 and result["movies"] == 1
    with engine.connect() as conn:
        _assert_untouched(conn, series=True, movies=False)
        assert _keys(conn, "movie_language_profiles", "radarr_movie_id") == [-4]


def test_job_context_with_arr_ids_is_evidence(app_ctx):
    from services.standalone_owner_keys import migrate_legacy_owner_keys

    engine = _engine(app_ctx)
    _profiles()
    with engine.begin() as conn:
        _seed(conn)
        _insert(
            conn,
            "INSERT INTO jobs (id, file_path, status, bazarr_context_json, created_at) "
            "VALUES ('j1', '/m/Show/S01E01.en.srt', 'completed', :c, :t)",
            c='{"sonarr_series_id": 3, "sonarr_episode_id": 70}',
        )

    result = migrate_legacy_owner_keys(engine, sonarr_configured=False, radarr_configured=False)
    assert result["series"] == 0 and result["movies"] == 1
    with engine.connect() as conn:
        _assert_untouched(conn, series=True, movies=False)


def test_automation_queue_radarr_id_is_evidence(app_ctx):
    from services.standalone_owner_keys import migrate_legacy_owner_keys

    engine = _engine(app_ctx)
    _profiles()
    with engine.begin() as conn:
        _seed(conn)
        _insert(
            conn,
            "INSERT INTO subtitle_automation_queue (wanted_item_id, task_type, file_path, "
            "radarr_movie_id, target_language, state, attempt_count, created_at, updated_at) "
            "VALUES (1, 'foreign_track_cleanup', '/m/Film.mkv', 4, 'de', 'done', 0, :t, :t)",
        )

    result = migrate_legacy_owner_keys(engine, sonarr_configured=False, radarr_configured=False)
    assert result["movies"] == 0 and result["series"] > 0
    with engine.connect() as conn:
        _assert_untouched(conn, series=False, movies=True)


def test_health_finding_outside_standalone_titles_is_evidence(app_ctx):
    from services.standalone_owner_keys import migrate_legacy_owner_keys

    engine = _engine(app_ctx)
    _profiles()
    with engine.begin() as conn:
        _seed(conn)
        _insert(
            conn,
            "INSERT INTO subtitle_health_findings (episode_id, target_kind, target_path, lang, "
            "issue_type, severity, count, snippets_json, raw_hash, status, scanner_version, "
            "detected_at) VALUES (900, 'sidecar', '/tv/Other/S01E01.de.srt', 'de', 'mojibake', "
            "'warning', 1, '[]', 'h', 'open', 1, :t)",
        )

    result = migrate_legacy_owner_keys(engine, sonarr_configured=False, radarr_configured=False)
    assert result == {"series": 0, "movies": 0, "findings": 0}
    with engine.connect() as conn:
        _assert_untouched(conn, series=True, movies=True)


def test_standalone_only_history_moves_exactly_once(app_ctx):
    """History that only touches standalone titles is no arr evidence."""
    from services.standalone_owner_keys import migrate_legacy_owner_keys

    engine = _engine(app_ctx)
    _profiles()
    with engine.begin() as conn:
        _seed(conn)
        _download(conn, "/m/Show/S01E01.de.srt")
        _download(conn, "/m/Film.de.srt")
        _insert(
            conn,
            "INSERT INTO upgrade_history (file_path, upgraded_at) VALUES ('/m/Film.de.ass', :t)",
        )
        _insert(
            conn,
            "INSERT INTO jobs (id, file_path, status, bazarr_context_json, created_at) "
            "VALUES ('j1', '/m/Show/S01E01.en.srt', 'completed', :c, :t)",
            c='{"standalone_series_id": 3}',
        )
        _config(conn, "sonarr_url", "")

    result = migrate_legacy_owner_keys(engine, sonarr_configured=False, radarr_configured=False)
    assert result["series"] > 0 and result["movies"] == 1
    with engine.connect() as conn:
        assert _keys(conn, "series_language_profiles", "sonarr_series_id") == [-3, 8]
        assert _keys(conn, "movie_language_profiles", "radarr_movie_id") == [-4]
    assert (
        migrate_legacy_owner_keys(engine, sonarr_configured=False, radarr_configured=False) is None
    )
    with engine.connect() as conn:
        assert _keys(conn, "movie_language_profiles", "radarr_movie_id") == [-4]


def test_kept_rows_are_not_moved_on_a_later_start(app_ctx):
    """Ambiguous once means kept for good: the evidence going away later
    (history pruned, config entry deleted) must not move the rows silently."""
    from services.standalone_owner_keys import migrate_legacy_owner_keys

    engine = _engine(app_ctx)
    _profiles()
    with engine.begin() as conn:
        _seed(conn)
        _download(conn, "/movies/Film (2020)/Film.de.srt")

    migrate_legacy_owner_keys(engine, sonarr_configured=False, radarr_configured=False)
    with engine.begin() as conn:
        conn.execute(sa.text("DELETE FROM subtitle_downloads"))
    assert (
        migrate_legacy_owner_keys(engine, sonarr_configured=False, radarr_configured=False) is None
    )
    with engine.connect() as conn:
        _assert_untouched(conn, series=True, movies=True)


def _seed_overlap_1032(conn) -> None:
    """Prod-copy repro: Sonarr series 1032 has a profile and settings, and a
    standalone series got row id 1032 as well."""
    _insert(
        conn,
        "INSERT INTO standalone_series (id, title, folder_path, created_at, updated_at) "
        "VALUES (1032, 'Show', '/m/Show', :t, :t)",
    )
    _insert(
        conn, "INSERT INTO series_language_profiles (sonarr_series_id, profile_id) VALUES (1032, 2)"
    )
    _insert(
        conn,
        "INSERT INTO series_settings (sonarr_series_id, absolute_order, min_attempts_per_day, "
        "cleanup_foreign_tracks, updated_at) VALUES (1032, 1, 0, 0, :t)",
    )
    # The Sonarr period: wanted rows (later drained) and its download history.
    _insert(
        conn,
        "INSERT INTO wanted_items (item_type, file_path, title, sonarr_series_id, status, "
        "priority, error_count, added_at, updated_at) VALUES ('episode', "
        "'/tv/Sonarr Show/S01E01.mkv', 'Sonarr Show', 1032, 'wanted', 'standard', 0, :t, :t)",
    )
    _download(conn, "/tv/Sonarr Show/S01E01.de.srt")


def _drain_wanted_and_rebuild_search_index(engine) -> None:
    from db.search import init_search_tables, rebuild_search_index

    with engine.begin() as conn:
        conn.execute(sa.text("DELETE FROM wanted_items"))
    init_search_tables()
    rebuild_search_index()  # what app start does before the move


def _series_keys_1032(engine):
    with engine.connect() as conn:
        return (
            _keys(conn, "series_language_profiles", "sonarr_series_id"),
            _keys(conn, "series_settings", "sonarr_series_id"),
        )


def test_prod_repro_drained_wanted_and_rebuilt_search_index_moves_nothing(app_ctx):
    """Sonarr unconfigured, its wanted rows drained, the search index rebuilt
    from the (now empty) wanted table: only durable history remains, and it
    must keep Sonarr series 1032's rows away from standalone series 1032."""
    from services.standalone_owner_keys import migrate_legacy_owner_keys

    engine = _engine(app_ctx)
    _profiles()
    with engine.begin() as conn:
        _seed_overlap_1032(conn)
    _drain_wanted_and_rebuild_search_index(engine)

    result = migrate_legacy_owner_keys(engine, sonarr_configured=False, radarr_configured=False)
    assert result["series"] == 0
    assert _series_keys_1032(engine) == ([1032], [1032])


def test_prod_repro_stored_sonarr_url_alone_moves_nothing(app_ctx):
    """Same repro without download history: the stored Sonarr URL keeps them."""
    from services.standalone_owner_keys import migrate_legacy_owner_keys

    engine = _engine(app_ctx)
    _profiles()
    with engine.begin() as conn:
        _seed_overlap_1032(conn)
        conn.execute(sa.text("DELETE FROM subtitle_downloads"))
        _config(conn, "sonarr_url", "http://sonarr:8989")
    _drain_wanted_and_rebuild_search_index(engine)

    result = migrate_legacy_owner_keys(engine, sonarr_configured=False, radarr_configured=False)
    assert result["series"] == 0
    assert _series_keys_1032(engine) == ([1032], [1032])


def test_history_older_than_the_standalone_title_is_evidence(app_ctx):
    """Codex re-review: Sonarr removed, its config cleared, the same folder
    imported as standalone. Its download history now lies inside the
    standalone folder, but it predates the standalone title, so it was not
    the standalone title's."""
    from services.standalone_owner_keys import migrate_legacy_owner_keys

    engine = _engine(app_ctx)
    _profiles()
    with engine.begin() as conn:
        _seed(conn)  # standalone titles created at _NOW
        _insert(
            conn,
            "INSERT INTO subtitle_downloads (provider_name, subtitle_id, language, file_path, "
            "downloaded_at) VALUES ('p', 's', 'de', '/m/Show/S01E01.de.srt', :old)",
            old=datetime(2025, 1, 1, tzinfo=UTC),
        )

    result = migrate_legacy_owner_keys(engine, sonarr_configured=False, radarr_configured=False)
    assert result == {"series": 0, "movies": 0, "findings": 0}
    with engine.connect() as conn:
        _assert_untouched(conn, series=True, movies=True)


def test_no_history_scan_when_both_sides_are_decided(app_ctx, monkeypatch):
    """Both arrs configured: the history tables are not read at all."""
    from services import standalone_owner_keys as mod

    engine = _engine(app_ctx)
    _profiles()
    with engine.begin() as conn:
        _seed(conn)

    def _boom(*a, **kw):
        raise AssertionError("history scanned")

    monkeypatch.setattr(mod, "_foreign_path_evidence", _boom)
    result = mod.migrate_legacy_owner_keys(engine, sonarr_configured=True, radarr_configured=True)
    assert result == {"series": 0, "movies": 0, "findings": 0}


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
