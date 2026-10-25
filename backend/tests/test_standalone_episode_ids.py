"""Standalone episodes have stable negative ids on every per-episode route.

Before 1.18.0 a satisfied standalone episode had a list-position stand-in id
(``-(index + 1)``) that the tracks, remux, health, combine and sidecar routes
answered with 404, and an unsatisfied one the id of a wanted row that changed
on every rescan. Now the series detail hands out ``-standalone_episodes.id``
for every episode file, with or without Sonarr configured.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import patch

import pytest


class _FakeSonarr:
    """A configured Sonarr that knows nothing about standalone episodes."""

    def get_episode_file_path(self, ep_id):
        raise AssertionError(f"standalone episode {ep_id} must not be sent to Sonarr")

    def get_series_by_id(self, series_id):
        raise AssertionError(f"standalone series {series_id} must not be sent to Sonarr")

    def get_episode_files_by_series(self, series_id):
        raise AssertionError(f"standalone series {series_id} must not be sent to Sonarr")


@pytest.fixture
def no_sonarr(monkeypatch):
    monkeypatch.setattr("sonarr_client.get_sonarr_client", lambda *a, **kw: None)


@pytest.fixture
def with_sonarr(monkeypatch):
    fake = _FakeSonarr()
    monkeypatch.setattr("sonarr_client.get_sonarr_client", lambda *a, **kw: fake)
    return fake


@pytest.fixture
def show(client, tmp_path):
    """A standalone series with two episode files; only S01E01 is wanted."""
    from db.models.core import WantedItem
    from db.models.standalone import StandaloneSeries
    from extensions import db

    folder = tmp_path / "My Show (2020)"
    season = folder / "Season 1"
    season.mkdir(parents=True)
    ep1 = season / "My Show - S01E01 [1080p].mkv"
    ep2 = season / "My Show - S01E02 [1080p].mkv"
    ep1.write_bytes(b"\x00")
    ep2.write_bytes(b"\x00")
    (season / "My Show - S01E02 [1080p].de.srt").write_text("1\n00:00:01,000 --> 00:00:02,000\nHallo\n")

    now = datetime.now(UTC)
    with client.application.app_context():
        series = StandaloneSeries(
            title="My Show", folder_path=str(folder), created_at=now, updated_at=now
        )
        db.session.add(series)
        db.session.flush()
        wanted = WantedItem(
            item_type="episode",
            title="My Show -- S01E01",
            file_path=str(ep1),
            season_episode="S01E01",
            standalone_series_id=series.id,
            target_language="de",
            instance_name="standalone",
            status="wanted",
            added_at=now,
            updated_at=now,
        )
        db.session.add(wanted)
        db.session.commit()
        return {
            "series_id": series.id,
            "wanted_id": wanted.id,
            "ep1": str(ep1),
            "ep2": str(ep2),
        }


def _detail(client, series_id):
    resp = client.get(f"/api/v1/library/series/{series_id}")
    assert resp.status_code == 200, resp.get_json()
    return resp.get_json()


def _ids_by_path(detail):
    return {e["file_path"]: e["id"] for e in detail["episodes"]}


def test_detail_hands_out_stable_negative_ids(client, no_sonarr, show):
    first = _ids_by_path(_detail(client, show["series_id"]))
    again = _ids_by_path(_detail(client, show["series_id"]))

    assert first == again
    assert all(i < 0 for i in first.values())
    assert len(set(first.values())) == 2


def test_detail_episodes_carry_source_and_wanted_id(client, no_sonarr, show):
    detail = _detail(client, show["series_id"])
    by_path = {e["file_path"]: e for e in detail["episodes"]}

    ep1 = by_path[show["ep1"]]
    ep2 = by_path[show["ep2"]]
    assert ep1["source"] == "standalone" and ep2["source"] == "standalone"
    assert ep1["standalone_id"] == -ep1["id"]
    assert ep1["wanted_id"] == show["wanted_id"]
    assert ep2["wanted_id"] is None


def test_id_survives_wanted_row_churn(client, no_sonarr, show):
    """A rescan deletes and re-inserts wanted rows; the episode id must not move."""
    from db.models.core import WantedItem
    from extensions import db

    before = _ids_by_path(_detail(client, show["series_id"]))
    with client.application.app_context():
        db.session.query(WantedItem).delete()
        db.session.commit()
    after = _ids_by_path(_detail(client, show["series_id"]))
    assert after == before


def test_sidecar_list_of_a_satisfied_episode(client, no_sonarr, show):
    ep2_id = _ids_by_path(_detail(client, show["series_id"]))[show["ep2"]]
    resp = client.get(f"/api/v1/library/episodes/{ep2_id}/subtitles")
    assert resp.status_code == 200, resp.get_json()
    data = resp.get_json()
    assert data["video_path"] == show["ep2"]
    assert [s["language"] for s in data["subtitles"]] == ["de"]


def test_tracks_of_a_satisfied_episode(client, no_sonarr, show):
    ep2_id = _ids_by_path(_detail(client, show["series_id"]))[show["ep2"]]
    streams = {"streams": [{"index": 0, "codec_type": "subtitle", "codec_name": "ass"}]}
    with patch("routes.tracks.get_media_streams", return_value=streams):
        resp = client.get(f"/api/v1/library/episodes/{ep2_id}/tracks")
    assert resp.status_code == 200, resp.get_json()


def test_health_scan_keys_findings_by_the_negative_id(client, no_sonarr, show):
    ep2_id = _ids_by_path(_detail(client, show["series_id"]))[show["ep2"]]

    class _Result:
        def to_dict(self):
            return {"issues": []}

    with patch("services.subtitle_health.scan_episode", return_value=_Result()) as scan:
        resp = client.post(f"/api/v1/library/episodes/{ep2_id}/health/scan")
    assert resp.status_code == 200, resp.get_json()
    assert scan.call_args.kwargs["episode_id"] == ep2_id
    assert scan.call_args.kwargs["video_path"] == show["ep2"]


def test_series_sidecar_map_is_keyed_by_episode_id(client, no_sonarr, show):
    ids = _ids_by_path(_detail(client, show["series_id"]))
    resp = client.get(f"/api/v1/library/series/{show['series_id']}/subtitles")
    assert resp.status_code == 200
    subs = resp.get_json()["subtitles"]
    assert set(subs) == {str(ids[show["ep2"]])}


def test_negative_ids_work_with_sonarr_configured(client, with_sonarr, show):
    """Mixed mode: the sign keeps a standalone episode away from Sonarr."""
    detail = _detail(client, -show["series_id"])
    assert detail["source"] == "standalone"
    assert detail["id"] == -show["series_id"]
    ep2_id = _ids_by_path(detail)[show["ep2"]]

    resp = client.get(f"/api/v1/library/episodes/{ep2_id}/subtitles")
    assert resp.status_code == 200, resp.get_json()
    resp = client.get(f"/api/v1/library/series/{-show['series_id']}/subtitles")
    assert resp.status_code == 200, resp.get_json()
    assert set(resp.get_json()["subtitles"]) == {str(ep2_id)}


def test_unknown_negative_id_is_404(client, no_sonarr, show):
    assert client.get("/api/v1/library/episodes/-999/subtitles").status_code == 404


def test_episode_search_by_new_id_creates_the_wanted_row(client, no_sonarr, show):
    from db.models.core import WantedItem
    from extensions import db

    ep2_id = _ids_by_path(_detail(client, show["series_id"]))[show["ep2"]]
    with patch(
        "wanted_search.search_wanted_item", return_value={"wanted_id": 0, "results": []}
    ) as search:
        resp = client.post(f"/api/v1/episodes/{ep2_id}/search")
    assert resp.status_code == 200, resp.get_json()
    with client.application.app_context():
        row = db.session.query(WantedItem).filter(WantedItem.file_path == show["ep2"]).one()
        assert row.standalone_series_id == show["series_id"]
    search.assert_called_once_with(row.id)


def test_episode_path_that_left_the_series_folder_is_refused(client, no_sonarr, show, tmp_path):
    """A file swapped for a symlink pointing outside the folder is not used."""
    import os

    ep2_id = _ids_by_path(_detail(client, show["series_id"]))[show["ep2"]]
    outside = tmp_path / "outside.mkv"
    outside.write_bytes(b"\x00")
    os.remove(show["ep2"])
    os.symlink(outside, show["ep2"])

    assert client.get(f"/api/v1/library/episodes/{ep2_id}/subtitles").status_code == 404


def test_legacy_wanted_row_id_still_resolves(client, no_sonarr, show):
    resp = client.get(f"/api/v1/library/episodes/{show['wanted_id']}/subtitles")
    assert resp.status_code == 200, resp.get_json()
    assert resp.get_json()["video_path"] == show["ep1"]


def test_series_delete_drops_the_episode_rows(client, no_sonarr, show):
    from db.models.standalone import StandaloneEpisode
    from extensions import db
    from services.standalone_manager import delete_series_cascade

    _detail(client, show["series_id"])
    with client.application.app_context():
        assert db.session.query(StandaloneEpisode).count() == 2
        delete_series_cascade(show["series_id"])
        assert db.session.query(StandaloneEpisode).count() == 0
