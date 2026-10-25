"""``/api/v1/standalone/*`` returns the row as before plus ``standalone_id``.

docs/specs/standalone-ids.md, "API compatibility": the standalone-only
namespace keeps its pre-1.18 row shape (positive ``id``) and adds the
positive ``standalone_id`` and ``source``. The movie detail is the exception
the movie page relies on: it answers with the negative wire id. The
1.18.0-rc.2 end-to-end test found the series list/detail and the movie list
without ``standalone_id`` (F7).
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest


@pytest.fixture
def no_arr(monkeypatch):
    monkeypatch.setattr("sonarr_client.get_sonarr_client", lambda *a, **kw: None)
    monkeypatch.setattr("radarr_client.get_radarr_client", lambda *a, **kw: None)


def _rows(client, tmp_path) -> tuple[int, int]:
    from db.models.standalone import StandaloneMovie, StandaloneSeries
    from extensions import db

    now = datetime.now(UTC)
    with client.application.app_context():
        series = StandaloneSeries(
            title="Show", folder_path=str(tmp_path / "Show"), created_at=now, updated_at=now
        )
        movie = StandaloneMovie(
            title="Film", file_path=str(tmp_path / "Film.mkv"), created_at=now, updated_at=now
        )
        db.session.add_all([series, movie])
        db.session.commit()
        return series.id, movie.id


def test_series_list_and_detail_carry_standalone_id(client, no_arr, tmp_path):
    sid, _mid = _rows(client, tmp_path)

    listed = client.get("/api/v1/standalone/series").get_json()
    assert [(s["id"], s["standalone_id"], s["source"]) for s in listed] == [
        (sid, sid, "standalone")
    ]
    for series_id in (sid, -sid):
        detail = client.get(f"/api/v1/standalone/series/{series_id}").get_json()
        assert (detail["id"], detail["standalone_id"], detail["source"]) == (
            sid,
            sid,
            "standalone",
        )
        assert "wanted_items" in detail


def test_movie_list_carries_standalone_id(client, no_arr, tmp_path):
    _sid, mid = _rows(client, tmp_path)

    listed = client.get("/api/v1/standalone/movies").get_json()
    assert [(m["id"], m["standalone_id"], m["source"]) for m in listed] == [
        (mid, mid, "standalone")
    ]


def test_movie_detail_keeps_the_negative_wire_id(client, no_arr, tmp_path):
    _sid, mid = _rows(client, tmp_path)

    detail = client.get(f"/api/v1/standalone/movies/{-mid}").get_json()
    assert (detail["id"], detail["standalone_id"], detail["source"]) == (
        -mid,
        mid,
        "standalone",
    )
