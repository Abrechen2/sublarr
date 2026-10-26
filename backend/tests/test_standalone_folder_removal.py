"""Removing or moving a watched folder takes its titles with it.

Found by the 1.18 end-to-end test: DELETE /standalone/folders/<id> removed
only the folder row. Its series, movies, episode ids and wanted rows stayed,
and a rescan could not prune them because the scanner skips every cleanup
when no watched folder is left.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
import sqlalchemy as sa

_NOW = datetime(2026, 10, 1, tzinfo=UTC)


@pytest.fixture
def api(app_ctx, monkeypatch):
    monkeypatch.setattr("routes.standalone.folders._hot_reload_standalone", lambda: None)
    monkeypatch.setattr("routes.standalone.folders._media_path", lambda: "")
    monkeypatch.setattr("sonarr_client.get_sonarr_client", lambda *a, **kw: None)
    monkeypatch.setattr("radarr_client.get_radarr_client", lambda *a, **kw: None)
    return app_ctx.test_client()


@pytest.fixture
def media(tmp_path):
    root = tmp_path / "media"
    for name in ("A", "AB", "New"):
        (root / name).mkdir(parents=True)
    return root


def _folder(path) -> int:
    from db.standalone import upsert_watched_folder

    return upsert_watched_folder(path=str(path))


def _series(folder) -> int:
    from db.models.standalone import StandaloneSeries
    from extensions import db

    folder.mkdir(parents=True, exist_ok=True)
    row = StandaloneSeries(
        title=folder.name, folder_path=str(folder), created_at=_NOW, updated_at=_NOW
    )
    db.session.add(row)
    db.session.commit()
    _wanted("series", str(folder / "ep.mkv"), standalone_series_id=row.id)
    return row.id


def _movie(path) -> int:
    from db.models.standalone import StandaloneMovie
    from extensions import db

    path.write_bytes(b"\x00")
    row = StandaloneMovie(title=path.stem, file_path=str(path), created_at=_NOW, updated_at=_NOW)
    db.session.add(row)
    db.session.commit()
    _wanted("movie", str(path), standalone_movie_id=row.id)
    return row.id


def _wanted(item_type: str, file_path: str, **owner) -> None:
    from db.models.core import WantedItem
    from extensions import db

    db.session.add(
        WantedItem(
            item_type=item_type,
            file_path=file_path,
            instance_name="standalone",
            added_at=_NOW,
            updated_at=_NOW,
            **owner,
        )
    )
    db.session.commit()


def _ids(table: str) -> set[int]:
    from extensions import db

    return {r[0] for r in db.session.execute(sa.text(f"SELECT id FROM {table}"))}


def _wanted_owners() -> set[tuple]:
    from extensions import db

    rows = db.session.execute(
        sa.text("SELECT standalone_series_id, standalone_movie_id FROM wanted_items")
    )
    return {tuple(r) for r in rows}


def test_deleting_a_folder_removes_its_titles_but_not_a_prefix_sibling(api, media):
    gone = _folder(media / "A")
    _folder(media / "AB")
    s_gone = _series(media / "A" / "Show")
    s_keep = _series(media / "AB" / "Other")
    m_gone = _movie(media / "A" / "film.mkv")
    m_keep = _movie(media / "AB" / "film.mkv")

    resp = api.delete(f"/api/v1/standalone/folders/{gone}")

    assert resp.status_code == 200
    assert _ids("standalone_series") == {s_keep}
    assert _ids("standalone_movies") == {m_keep}
    assert _wanted_owners() == {(s_keep, None), (None, m_keep)}
    assert s_gone not in _ids("standalone_series") and m_gone not in _ids("standalone_movies")
    # Files on disk are never touched.
    assert (media / "A" / "film.mkv").exists()
    assert (media / "A" / "Show").is_dir()


def test_deleting_a_folder_removes_the_titles_owner_key_rows(api, media):
    from extensions import db

    gone = _folder(media / "A")
    sid = _series(media / "A" / "Show")
    mid = _movie(media / "A" / "film.mkv")
    db.session.execute(
        sa.text(
            "INSERT INTO series_settings (sonarr_series_id, absolute_order, "
            "min_attempts_per_day, cleanup_foreign_tracks, updated_at) "
            "VALUES (:k, 1, 0, 1, :t)"
        ),
        {"k": -sid, "t": _NOW},
    )
    db.session.execute(
        sa.text(
            "INSERT INTO movie_settings (radarr_movie_id, min_attempts_per_day, "
            "cleanup_foreign_tracks, updated_at) VALUES (:k, 0, 1, :t)"
        ),
        {"k": -mid, "t": _NOW},
    )
    db.session.commit()

    assert api.delete(f"/api/v1/standalone/folders/{gone}").status_code == 200

    def count(sql: str, k: int) -> int:
        return db.session.execute(sa.text(sql), {"k": k}).scalar()

    assert count("SELECT COUNT(*) FROM series_settings WHERE sonarr_series_id=:k", -sid) == 0
    assert count("SELECT COUNT(*) FROM movie_settings WHERE radarr_movie_id=:k", -mid) == 0
    assert count("SELECT COUNT(*) FROM standalone_episodes WHERE standalone_series_id=:k", sid) == 0


def test_titles_also_under_another_folder_stay(api, media):
    _folder(media)
    inner = _folder(media / "A")
    sid = _series(media / "A" / "Show")
    mid = _movie(media / "A" / "film.mkv")

    assert api.delete(f"/api/v1/standalone/folders/{inner}").status_code == 200

    assert _ids("standalone_series") == {sid}
    assert _ids("standalone_movies") == {mid}


def test_series_kept_when_a_remaining_folder_lies_inside_it(api, media):
    # The scanner stores a series at its show folder even when the watched
    # folder is one of its season folders, so a remaining season folder
    # still covers the series after the outer folder goes.
    outer = _folder(media / "A")
    _folder(media / "A" / "Show" / "Season 1")
    sid = _series(media / "A" / "Show")

    assert api.delete(f"/api/v1/standalone/folders/{outer}").status_code == 200

    assert _ids("standalone_series") == {sid}


def test_deleting_the_only_season_folder_removes_its_series(api, media):
    season = _folder(media / "A" / "Show" / "Season 1")
    _series(media / "A" / "Show")

    assert api.delete(f"/api/v1/standalone/folders/{season}").status_code == 200

    assert _ids("standalone_series") == set()
