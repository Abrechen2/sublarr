"""A deleted standalone title takes its settings with it; its id is never reused.

Found by the 1.18.0-rc.2 end-to-end test: SQLite handed the id of a deleted
standalone series or movie to the next new title, and the rows stored under
the old owner key (profile, settings incl. the foreign-track cleanup switch,
glossary) were still there, so the new title inherited them. Both sides are
fixed: the tables use AUTOINCREMENT, and the delete removes the owner-key rows.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest
import sqlalchemy as sa

_NOW = datetime(2026, 10, 1, tzinfo=UTC)


@pytest.fixture
def no_arr(monkeypatch):
    monkeypatch.setattr("sonarr_client.get_sonarr_client", lambda *a, **kw: None)
    monkeypatch.setattr("radarr_client.get_radarr_client", lambda *a, **kw: None)


def _profile() -> int:
    from db.models.core import LanguageProfile
    from extensions import db

    row = LanguageProfile(
        name="DE+EN e2e",
        target_languages_json=json.dumps(["de", "en"]),
        target_language_names_json=json.dumps(["German", "English"]),
        created_at=_NOW,
        updated_at=_NOW,
    )
    db.session.add(row)
    db.session.commit()
    return row.id


def _series(tmp_path, title: str) -> int:
    from db.models.standalone import StandaloneSeries
    from extensions import db

    folder = tmp_path / title
    (folder / "Season 01").mkdir(parents=True)
    (folder / "Season 01" / f"{title} - S01E01.mkv").write_bytes(b"\x00")
    row = StandaloneSeries(title=title, folder_path=str(folder), created_at=_NOW, updated_at=_NOW)
    db.session.add(row)
    db.session.commit()
    return row.id


def _movie(tmp_path, title: str) -> int:
    from db.models.standalone import StandaloneMovie
    from extensions import db

    path = tmp_path / f"{title}.mkv"
    path.write_bytes(b"\x00")
    row = StandaloneMovie(title=title, file_path=str(path), created_at=_NOW, updated_at=_NOW)
    db.session.add(row)
    db.session.commit()
    return row.id


def _count(sql: str, **params) -> int:
    from extensions import db

    return db.session.execute(sa.text(sql), params).scalar()


def test_standalone_title_tables_use_sqlite_autoincrement():
    from db.models.standalone import StandaloneMovie, StandaloneSeries

    for model in (StandaloneSeries, StandaloneMovie):
        assert model.__table__.dialect_options["sqlite"]["autoincrement"] is True


def test_deleted_highest_series_id_is_not_reused(app_ctx, tmp_path):
    from services.standalone_manager import delete_series_cascade

    _series(tmp_path, "First")
    last = _series(tmp_path, "Second")
    delete_series_cascade(last)
    assert _series(tmp_path, "Third") > last


def test_deleted_highest_movie_id_is_not_reused(app_ctx, tmp_path):
    from services.standalone_manager import delete_movie_cascade

    _movie(tmp_path, "First")
    last = _movie(tmp_path, "Second")
    delete_movie_cascade(last)
    assert _movie(tmp_path, "Third") > last


_SERIES_ROWS = (
    "INSERT INTO series_settings (sonarr_series_id, absolute_order, min_attempts_per_day, "
    "cleanup_foreign_tracks, updated_at) VALUES (:k, 1, 0, 1, :t)",
    "INSERT INTO fansub_preferences (sonarr_series_id, preferred_groups_json, "
    "excluded_groups_json, bonus, updated_at) VALUES (:k, '[\"G\"]', '[]', 20, :t)",
    "INSERT INTO glossary_entries (series_id, source_term, target_term, notes, term_type, "
    "approved, created_at, updated_at) VALUES (:k, 'OldTerm', 'AltBegriff', '', 'other', 1, :t, :t)",
)


def test_series_delete_removes_its_owner_key_rows(app_ctx, no_arr, tmp_path):
    from db.profiles import assign_series_profile
    from extensions import db
    from services.standalone_manager import delete_series_cascade

    keep = _series(tmp_path, "Keep")
    gone = _series(tmp_path, "Gone")
    pid = _profile()
    for sid in (keep, gone):
        assign_series_profile(-sid, pid)
        for sql in _SERIES_ROWS:
            db.session.execute(sa.text(sql), {"k": -sid, "t": _NOW})
        db.session.commit()

    delete_series_cascade(gone)

    for table, col in (
        ("series_language_profiles", "sonarr_series_id"),
        ("series_settings", "sonarr_series_id"),
        ("fansub_preferences", "sonarr_series_id"),
        ("glossary_entries", "series_id"),
    ):
        assert _count(f"SELECT COUNT(*) FROM {table} WHERE {col} = :k", k=-gone) == 0, table  # noqa: S608
        assert _count(f"SELECT COUNT(*) FROM {table} WHERE {col} = :k", k=-keep) == 1, table  # noqa: S608


def test_movie_delete_removes_its_owner_key_rows(app_ctx, no_arr, tmp_path):
    from db.profiles import assign_movie_profile
    from extensions import db
    from services.standalone_manager import delete_movie_cascade

    keep = _movie(tmp_path, "Keep")
    gone = _movie(tmp_path, "Gone")
    pid = _profile()
    for mid in (keep, gone):
        assign_movie_profile(-mid, pid)
        db.session.execute(
            sa.text(
                "INSERT INTO movie_settings (radarr_movie_id, min_attempts_per_day, "
                "cleanup_foreign_tracks, updated_at) VALUES (:k, 0, 1, :t)"
            ),
            {"k": -mid, "t": _NOW},
        )
        db.session.commit()

    delete_movie_cascade(gone)

    for table in ("movie_language_profiles", "movie_settings"):
        assert _count(f"SELECT COUNT(*) FROM {table} WHERE radarr_movie_id = :k", k=-gone) == 0  # noqa: S608
        assert _count(f"SELECT COUNT(*) FROM {table} WHERE radarr_movie_id = :k", k=-keep) == 1  # noqa: S608


def test_delete_keeps_sonarr_rows_with_the_same_positive_number(app_ctx, no_arr, tmp_path):
    """Only the owner key (negative) is removed; a positive key is not the title's."""
    from extensions import db
    from services.standalone_manager import delete_series_cascade

    sid = _series(tmp_path, "Gone")
    db.session.execute(
        sa.text(
            "INSERT INTO series_settings (sonarr_series_id, absolute_order, "
            "min_attempts_per_day, cleanup_foreign_tracks, updated_at) VALUES (:k, 0, 0, 1, :t)"
        ),
        {"k": sid, "t": _NOW},
    )
    db.session.commit()
    delete_series_cascade(sid)
    assert _count("SELECT COUNT(*) FROM series_settings WHERE sonarr_series_id = :k", k=sid) == 1


def test_e2e_repro_new_series_gets_a_new_id_and_no_old_settings(client, no_arr, tmp_path):
    """Exact repro of F1: profile, cleanup switch and glossary of a deleted -id."""
    with client.application.app_context():
        for title in ("A", "B", "C", "D"):
            _series(tmp_path, title)
        old = _series(tmp_path, "Breaking Test")
        pid = _profile()
    key = -old

    assert (
        client.put(
            "/api/v1/language-profiles/assign",
            json={"type": "series", "arr_id": key, "profile_id": pid},
        ).status_code
        == 200
    )
    resp = client.patch(
        f"/api/v1/profiles-overrides/series/{key}", json={"cleanup_foreign_tracks": True}
    )
    assert resp.status_code == 200, resp.get_json()
    resp = client.post(
        "/api/v1/glossary",
        json={"series_id": key, "source_term": "OldTerm", "target_term": "AltBegriff"},
    )
    assert resp.status_code == 201, resp.get_json()

    assert client.delete(f"/api/v1/standalone/series/{key}").status_code == 200

    with client.application.app_context():
        new = _series(tmp_path, "Totally Different Show")
        from db.models.core import SeriesLanguageProfile, SeriesSettings
        from services.standalone_owner_keys import get_row

        assert new != old
        assert get_row(SeriesLanguageProfile, -new) is None
        assert get_row(SeriesLanguageProfile, key) is None
        assert get_row(SeriesSettings, -new) is None
        # The old owner key holds nothing either, so no later title can read it.
        assert get_row(SeriesSettings, key) is None
        assert _count("SELECT COUNT(*) FROM glossary_entries WHERE series_id = :k", k=key) == 0
    glossary = client.get(f"/api/v1/glossary?series_id={-new}").get_json()
    entries = glossary.get("entries", glossary) if isinstance(glossary, dict) else glossary
    assert not [e for e in entries if e.get("series_id") == -new]


def test_e2e_repro_new_movie_gets_a_new_id_and_no_old_settings(client, no_arr, tmp_path):
    with client.application.app_context():
        old = _movie(tmp_path, "Test Movie")
        pid = _profile()
    key = -old

    assert (
        client.put(
            "/api/v1/language-profiles/assign",
            json={"type": "movie", "arr_id": key, "profile_id": pid},
        ).status_code
        == 200
    )
    resp = client.patch(
        f"/api/v1/profiles-overrides/movie/{key}", json={"cleanup_foreign_tracks": True}
    )
    assert resp.status_code == 200, resp.get_json()

    assert client.delete(f"/api/v1/standalone/movies/{key}").status_code == 200

    with client.application.app_context():
        new = _movie(tmp_path, "Other Movie")
        from db.models.core import MovieLanguageProfile, MovieSettings
        from services.standalone_owner_keys import get_row

        assert new != old
        assert get_row(MovieLanguageProfile, -new) is None
        assert get_row(MovieLanguageProfile, key) is None
        assert get_row(MovieSettings, -new) is None
        assert get_row(MovieSettings, key) is None
