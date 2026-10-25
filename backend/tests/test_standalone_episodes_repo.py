"""standalone_episodes gives every standalone episode file a stable id.

The id is what the API hands out (negated) for a standalone episode, so it
must survive rescans and subtitle downloads, never be handed to another file,
and follow a file that moves to another series.
"""

from __future__ import annotations

from datetime import UTC, datetime


def _series(title: str, folder: str) -> int:
    from db.models.standalone import StandaloneSeries
    from extensions import db

    now = datetime.now(UTC)
    row = StandaloneSeries(title=title, folder_path=folder, created_at=now, updated_at=now)
    db.session.add(row)
    db.session.commit()
    return row.id


def test_upsert_returns_the_same_id_for_the_same_file(app_ctx):
    from db.repositories.standalone_episodes import StandaloneEpisodeRepository

    sid = _series("Show", "/media/Show")
    repo = StandaloneEpisodeRepository()
    first = repo.upsert_episode(sid, "/media/Show/S01E01.mkv", 1, 1)
    again = repo.upsert_episode(sid, "/media/Show/S01E01.mkv", 1, 1)
    other = repo.upsert_episode(sid, "/media/Show/S01E02.mkv", 1, 2)

    assert first["id"] == again["id"]
    assert other["id"] != first["id"]
    assert repo.get_episode(first["id"])["file_path"] == "/media/Show/S01E01.mkv"


def test_a_file_that_moves_series_keeps_its_id(app_ctx):
    from db.repositories.standalone_episodes import StandaloneEpisodeRepository

    a = _series("A", "/media/A")
    b = _series("B", "/media/B")
    repo = StandaloneEpisodeRepository()
    ep = repo.upsert_episode(a, "/media/x.mkv", 1, 3)
    moved = repo.upsert_episode(b, "/media/x.mkv", 1, 3)

    assert moved["id"] == ep["id"]
    assert moved["standalone_series_id"] == b


def test_ids_of_deleted_episodes_are_not_reused(app_ctx):
    from db.repositories.standalone_episodes import StandaloneEpisodeRepository

    sid = _series("Show", "/media/Show")
    repo = StandaloneEpisodeRepository()
    last = repo.upsert_episode(sid, "/media/Show/S01E09.mkv", 1, 9)
    repo.delete_episodes_by_ids([last["id"]])
    fresh = repo.upsert_episode(sid, "/media/Show/S01E10.mkv", 1, 10)

    assert fresh["id"] > last["id"]


def test_episodes_for_series_and_delete_for_series(app_ctx):
    from db.repositories.standalone_episodes import StandaloneEpisodeRepository

    a = _series("A", "/media/A")
    b = _series("B", "/media/B")
    repo = StandaloneEpisodeRepository()
    repo.upsert_episode(a, "/media/A/1.mkv", 1, 1)
    repo.upsert_episode(a, "/media/A/2.mkv", 1, 2)
    repo.upsert_episode(b, "/media/B/1.mkv", 1, 1)

    assert [e["file_path"] for e in repo.get_episodes_for_series(a)] == [
        "/media/A/1.mkv",
        "/media/A/2.mkv",
    ]
    assert repo.delete_episodes_for_series(a) == 2
    assert repo.get_episodes_for_series(a) == []
    assert len(repo.get_episodes_for_series(b)) == 1


def test_a_lost_insert_race_returns_the_winner(app_ctx, monkeypatch):
    """Two writers for one new path: the loser re-reads the row the winner made."""
    from db.models.standalone import StandaloneEpisode
    from db.repositories.standalone_episodes import StandaloneEpisodeRepository
    from extensions import db

    sid = _series("Show", "/media/Show")
    repo = StandaloneEpisodeRepository()
    real_find = repo._find_by_path
    calls = {"n": 0}

    def _find_misses_once(path):
        calls["n"] += 1
        if calls["n"] == 1:
            # The concurrent writer commits between our lookup and our insert.
            now = datetime.now(UTC)
            db.session.add(
                StandaloneEpisode(
                    standalone_series_id=sid,
                    file_path=path,
                    season=1,
                    episode=1,
                    created_at=now,
                    updated_at=now,
                )
            )
            db.session.commit()
            return None
        return real_find(path)

    monkeypatch.setattr(repo, "_find_by_path", _find_misses_once)
    got = repo.upsert_episode(sid, "/media/Show/S01E01.mkv", 1, 1)

    rows = db.session.query(StandaloneEpisode).all()
    assert len(rows) == 1
    assert got["id"] == rows[0].id
