"""Standalone-mode episode search, interactive search and download (#226).

Without Sonarr the episode endpoints used to answer 503 "Sonarr not
configured". A standalone episode is a ``wanted_items`` row of a standalone
series (its id is what the series detail hands the UI); an episode whose
subtitles are already satisfied has no row and a negative synthetic id, so the
UI also sends its ``file_path``. Both must route into the same
``wanted_search`` functions the Wanted page uses.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import patch

import pytest


@pytest.fixture
def no_sonarr(monkeypatch):
    monkeypatch.setattr("sonarr_client.get_sonarr_client", lambda *a, **kw: None)


@pytest.fixture
def standalone_show(client, tmp_path):
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
            "folder": folder,
        }


def _wanted_rows_for(client, file_path: str) -> list[dict]:
    from db.models.core import WantedItem
    from extensions import db

    with client.application.app_context():
        rows = db.session.query(WantedItem).filter(WantedItem.file_path == file_path).all()
        return [
            {
                "id": r.id,
                "standalone_series_id": r.standalone_series_id,
                "season_episode": r.season_episode,
                "title": r.title,
                "target_language": r.target_language,
            }
            for r in rows
        ]


# --- episode search ---------------------------------------------------------


def test_search_standalone_wanted_episode(client, no_sonarr, standalone_show):
    wid = standalone_show["wanted_id"]
    with patch(
        "wanted_search.search_wanted_item", return_value={"wanted_id": wid, "results": []}
    ) as search:
        resp = client.post(f"/api/v1/episodes/{wid}/search")
    assert resp.status_code == 200, resp.get_json()
    search.assert_called_once_with(wid)


def test_search_satisfied_standalone_episode_by_file_path(client, no_sonarr, standalone_show):
    """No wanted row yet (negative synthetic id) -> resolved via file_path and a
    wanted row is created for the profile's first target language."""
    ep2 = standalone_show["ep2"]
    with patch(
        "wanted_search.search_wanted_item", return_value={"wanted_id": 0, "results": []}
    ) as search:
        resp = client.post("/api/v1/episodes/-2/search", query_string={"file_path": ep2})
    assert resp.status_code == 200, resp.get_json()

    rows = _wanted_rows_for(client, ep2)
    assert len(rows) == 1
    assert rows[0]["standalone_series_id"] == standalone_show["series_id"]
    assert rows[0]["season_episode"] == "S01E02"
    assert rows[0]["title"] == "My Show -- S01E02"
    search.assert_called_once_with(rows[0]["id"])


def test_search_by_file_path_reuses_existing_wanted_row(client, no_sonarr, standalone_show):
    """A stale id (rescan churn) plus the file_path finds the current row."""
    ep1 = standalone_show["ep1"]
    with patch(
        "wanted_search.search_wanted_item", return_value={"wanted_id": 0, "results": []}
    ) as search:
        resp = client.post("/api/v1/episodes/99999/search", query_string={"file_path": ep1})
    assert resp.status_code == 200, resp.get_json()
    search.assert_called_once_with(standalone_show["wanted_id"])
    assert len(_wanted_rows_for(client, ep1)) == 1


def test_search_unknown_standalone_episode_is_404_not_503(client, no_sonarr):
    resp = client.post("/api/v1/episodes/12345/search")
    assert resp.status_code == 404
    assert "Sonarr" not in resp.get_json()["error"]


def test_search_rejects_file_path_outside_standalone_folders(
    client, no_sonarr, standalone_show, tmp_path
):
    outside = tmp_path / "elsewhere.mkv"
    outside.write_bytes(b"\x00")
    with patch("wanted_search.search_wanted_item") as search:
        resp = client.post("/api/v1/episodes/-1/search", query_string={"file_path": str(outside)})
    assert resp.status_code == 404
    search.assert_not_called()
    assert _wanted_rows_for(client, str(outside)) == []


def test_search_rejects_path_traversal_out_of_series_folder(
    client, no_sonarr, standalone_show, tmp_path
):
    outside = tmp_path / "secret.mkv"
    outside.write_bytes(b"\x00")
    sneaky = str(standalone_show["folder"] / ".." / "secret.mkv")
    with patch("wanted_search.search_wanted_item") as search:
        resp = client.post("/api/v1/episodes/-1/search", query_string={"file_path": sneaky})
    assert resp.status_code == 404
    search.assert_not_called()


def test_search_ignores_non_standalone_wanted_row(client, no_sonarr, tmp_path):
    """A Sonarr-era wanted row id must not be treated as a standalone episode."""
    from db.models.core import WantedItem
    from extensions import db

    now = datetime.now(UTC)
    with client.application.app_context():
        wi = WantedItem(
            item_type="episode",
            title="Sonarr ep",
            file_path=str(tmp_path / "x.mkv"),
            sonarr_episode_id=5,
            status="wanted",
            added_at=now,
            updated_at=now,
        )
        db.session.add(wi)
        db.session.commit()
        wid = wi.id
    resp = client.post(f"/api/v1/episodes/{wid}/search")
    assert resp.status_code == 404


# --- interactive search -----------------------------------------------------


def test_interactive_search_standalone_episode(client, no_sonarr, standalone_show):
    wid = standalone_show["wanted_id"]
    payload = {"results": [], "total": 0, "item": {"id": wid}}
    with patch("wanted_search.search_providers_for_item", return_value=payload) as search:
        resp = client.get(
            f"/api/v1/episodes/{wid}/search-providers", query_string={"all_providers": "true"}
        )
    assert resp.status_code == 200, resp.get_json()
    search.assert_called_once_with(wid, all_providers=True)


def test_interactive_search_satisfied_standalone_episode(client, no_sonarr, standalone_show):
    ep2 = standalone_show["ep2"]
    with patch(
        "wanted_search.search_providers_for_item", return_value={"results": [], "total": 0}
    ) as search:
        resp = client.get("/api/v1/episodes/-2/search-providers", query_string={"file_path": ep2})
    assert resp.status_code == 200, resp.get_json()
    rows = _wanted_rows_for(client, ep2)
    assert len(rows) == 1
    search.assert_called_once_with(rows[0]["id"], all_providers=False)


def test_interactive_search_unknown_standalone_episode_is_404(client, no_sonarr):
    resp = client.get("/api/v1/episodes/12345/search-providers")
    assert resp.status_code == 404
    assert "Sonarr" not in resp.get_json()["error"]


# --- download selected ------------------------------------------------------

_PICK = {"provider_name": "animetosho", "subtitle_id": "abc", "language": "de"}


def test_download_specific_standalone_episode(client, no_sonarr, standalone_show):
    wid = standalone_show["wanted_id"]
    with (
        patch(
            "wanted_search.download_specific_for_item",
            return_value={"success": True, "path": "/x.de.ass"},
        ) as dl,
        patch("events.emit_event"),
    ):
        resp = client.post(f"/api/v1/episodes/{wid}/download-specific", json=_PICK)
    assert resp.status_code == 200, resp.get_json()
    dl.assert_called_once_with(wid, "animetosho", "abc", "de", False)


def test_download_specific_satisfied_standalone_episode(client, no_sonarr, standalone_show):
    ep2 = standalone_show["ep2"]
    with (
        patch(
            "wanted_search.download_specific_for_item",
            return_value={"success": True, "path": "/x.de.ass"},
        ) as dl,
        patch("events.emit_event"),
    ):
        resp = client.post(
            "/api/v1/episodes/-2/download-specific",
            query_string={"file_path": ep2},
            json=_PICK,
        )
    assert resp.status_code == 200, resp.get_json()
    rows = _wanted_rows_for(client, ep2)
    assert len(rows) == 1
    dl.assert_called_once_with(rows[0]["id"], "animetosho", "abc", "de", False)


def test_download_specific_unknown_standalone_episode_is_404(client, no_sonarr):
    resp = client.post("/api/v1/episodes/12345/download-specific", json=_PICK)
    assert resp.status_code == 404
    assert "Sonarr" not in resp.get_json()["error"]


def test_download_specific_validates_fields_before_resolving(client, no_sonarr):
    resp = client.post("/api/v1/episodes/12345/download-specific", json={})
    assert resp.status_code == 400


# --- history ----------------------------------------------------------------


def test_history_standalone_episode(client, no_sonarr, standalone_show):
    wid = standalone_show["wanted_id"]
    entries = [{"file_path": standalone_show["ep1"], "provider_name": "animetosho"}]
    with patch("db.cache.get_episode_history", return_value=entries) as hist:
        resp = client.get(f"/api/v1/episodes/{wid}/history")
    assert resp.status_code == 200
    assert resp.get_json()["entries"] == entries
    hist.assert_called_once_with(standalone_show["ep1"])


def test_history_satisfied_standalone_episode_by_file_path(client, no_sonarr, standalone_show):
    ep2 = standalone_show["ep2"]
    with patch("db.cache.get_episode_history", return_value=[]) as hist:
        resp = client.get("/api/v1/episodes/-2/history", query_string={"file_path": ep2})
    assert resp.status_code == 200
    hist.assert_called_once_with(ep2)
    # History is read-only: it must not create a wanted row.
    assert _wanted_rows_for(client, ep2) == []


def test_history_unknown_standalone_episode_is_empty(client, no_sonarr):
    resp = client.get("/api/v1/episodes/12345/history")
    assert resp.status_code == 200
    assert resp.get_json()["entries"] == []


def test_search_rejects_nul_in_file_path(client, no_sonarr, standalone_show):
    """A NUL in the query string must be a 404, never a 500."""
    nul = standalone_show["ep2"] + "\x00/../../etc/passwd"
    with patch("wanted_search.search_wanted_item") as search:
        resp = client.post("/api/v1/episodes/-1/search", query_string={"file_path": nul})
    assert resp.status_code == 404
    search.assert_not_called()


def test_search_rejects_non_video_file_in_series_folder(client, no_sonarr, standalone_show):
    nfo = standalone_show["folder"] / "tvshow.nfo"
    nfo.write_text("<tvshow/>")
    with patch("wanted_search.search_wanted_item") as search:
        resp = client.post("/api/v1/episodes/-1/search", query_string={"file_path": str(nfo)})
    assert resp.status_code == 404
    search.assert_not_called()
