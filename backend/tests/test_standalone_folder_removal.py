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


def test_titles_a_remaining_folder_reaches_through_a_symlink_stay(api, media):
    storage = _folder(media / "A")
    library = media / "New"
    _folder(library)
    sid = _series(media / "A" / "Show")
    mid = _movie(media / "A" / "film.mkv")
    (library / "Show").symlink_to(media / "A" / "Show")
    (library / "film.mkv").symlink_to(media / "A" / "film.mkv")

    assert api.delete(f"/api/v1/standalone/folders/{storage}").status_code == 200

    assert _ids("standalone_series") == {sid}
    assert _ids("standalone_movies") == {mid}


def test_symlink_chains_and_a_symlinked_root_keep_coverage(api, media):
    storage = _folder(media / "A")
    sid = _series(media / "A" / "Show")
    bridge = media / "AB"
    (bridge / "show").symlink_to(media / "A" / "Show")
    library = media / "New"
    (library / "bridge").symlink_to(bridge)
    _folder(library)
    linked_root = media / "Linked"
    linked_root.symlink_to(media / "A")
    _folder(linked_root)
    mid = _movie(media / "A" / "film.mkv")

    assert api.delete(f"/api/v1/standalone/folders/{storage}").status_code == 200

    assert _ids("standalone_series") == {sid}
    assert _ids("standalone_movies") == {mid}


def test_symlink_loops_end(api, media):
    storage = _folder(media / "A")
    _series(media / "A" / "Show")
    loop = media / "New"
    (loop / "self").symlink_to(loop)
    _folder(loop)

    assert api.delete(f"/api/v1/standalone/folders/{storage}").status_code == 200

    assert _ids("standalone_series") == set()


def test_titles_stored_through_an_aliased_root_stay(api, media):
    _folder(media / "A")
    alias = media / "Alias"
    alias.symlink_to(media / "A")
    gone = _folder(alias)
    sid = _series(alias / "Show")
    mid = _movie(alias / "film.mkv")

    assert api.delete(f"/api/v1/standalone/folders/{gone}").status_code == 200

    assert _ids("standalone_series") == {sid}
    assert _ids("standalone_movies") == {mid}


def test_an_unreadable_remaining_folder_keeps_the_titles(api, media):
    gone = _folder(media / "A")
    _folder(media / "Missing")  # configured, but the mount is gone
    sid = _series(media / "A" / "Show")

    assert api.delete(f"/api/v1/standalone/folders/{gone}").status_code == 200

    assert _ids("standalone_series") == {sid}


def test_an_unreadable_symlink_target_keeps_the_titles(api, media, monkeypatch):
    import os

    gone = _folder(media / "A")
    sid = _series(media / "A" / "Show")
    private = media / "AB"
    (media / "New" / "bridge").symlink_to(private)
    _folder(media / "New")
    real_stat = os.stat

    def stat(path, *a, **kw):
        if os.fspath(path) == str(private):
            raise PermissionError(13, "denied")
        return real_stat(path, *a, **kw)

    monkeypatch.setattr("services.standalone_manager.os.stat", stat)

    assert api.delete(f"/api/v1/standalone/folders/{gone}").status_code == 200

    assert _ids("standalone_series") == {sid}


def test_a_title_kept_through_a_symlink_goes_with_the_last_folder_reaching_it(api, media):
    # A goes first; New still reaches the show through its symlink. When New
    # goes as well nothing covers the show any more, although it never lay
    # under New's path.
    storage = _folder(media / "A")
    library = media / "New"
    linking = _folder(library)
    _folder(media / "AB")
    _series(media / "A" / "Show")
    _movie(media / "A" / "film.mkv")
    keep = _series(media / "AB" / "Other")
    (library / "Show").symlink_to(media / "A" / "Show")
    (library / "film.mkv").symlink_to(media / "A" / "film.mkv")

    assert api.delete(f"/api/v1/standalone/folders/{storage}").status_code == 200
    assert len(_ids("standalone_series")) == 2
    assert len(_ids("standalone_movies")) == 1

    assert api.delete(f"/api/v1/standalone/folders/{linking}").status_code == 200

    assert _ids("standalone_series") == {keep}
    assert _ids("standalone_movies") == set()
    assert _wanted_owners() == {(keep, None)}


def test_an_unreadable_removed_folder_only_takes_titles_under_its_path(api, media):
    library = media / "New"
    gone = _folder(library)
    outside = _series(media / "A" / "Show")
    (library / "Show").symlink_to(media / "A" / "Show")
    inside = _series(library / "Local")
    library.rename(media / "Unmounted")  # the removed folder cannot be walked

    assert api.delete(f"/api/v1/standalone/folders/{gone}").status_code == 200

    assert _ids("standalone_series") == {outside}
    assert inside not in _ids("standalone_series")


def test_titles_committed_before_the_folder_row_is_deleted_go_too(api, media, monkeypatch):
    # A running scan can commit a title after the route's first cleanup but
    # before the folder row is gone; the scan still sees the folder then.
    import db.standalone as dbs

    gone = _folder(media / "A")
    real_delete = dbs.delete_watched_folder

    def delete_after_a_late_title(folder_id):
        _series(media / "A" / "Late")
        return real_delete(folder_id)

    monkeypatch.setattr(dbs, "delete_watched_folder", delete_after_a_late_title)

    assert api.delete(f"/api/v1/standalone/folders/{gone}").status_code == 200

    assert _ids("standalone_series") == set()
    assert _wanted_owners() == set()


def test_removing_a_series_drops_its_episode_health_findings(api, media):
    from db.models.core import SubtitleHealthFinding
    from db.models.standalone import StandaloneEpisode
    from extensions import db

    gone = _folder(media / "A")
    _folder(media / "AB")
    kept_finding = None
    for folder in (media / "A" / "Show", media / "AB" / "Other"):
        ep = StandaloneEpisode(
            standalone_series_id=_series(folder),
            file_path=str(folder / "ep.mkv"),
            season=1,
            episode=1,
            created_at=_NOW,
            updated_at=_NOW,
        )
        db.session.add(ep)
        db.session.commit()
        db.session.add(
            SubtitleHealthFinding(
                episode_id=-ep.id,
                target_kind="sidecar",
                target_path=str(folder / "ep.en.srt"),
                issue_type="encoding",
                severity="low",
                detected_at=_NOW,
            )
        )
        db.session.commit()
        kept_finding = -ep.id

    assert api.delete(f"/api/v1/standalone/folders/{gone}").status_code == 200

    rows = db.session.execute(sa.text("SELECT episode_id FROM subtitle_health_findings"))
    assert {r[0] for r in rows} == {kept_finding}
