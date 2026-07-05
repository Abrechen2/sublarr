"""HTTP tests for routes/library/ — list, series detail, episode search, history."""

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# GET /api/v1/library — library list
# ---------------------------------------------------------------------------


def test_library_no_sonarr_no_radarr_empty(client, monkeypatch):
    """Library returns empty lists when no Sonarr/Radarr configured."""
    monkeypatch.setattr("sonarr_client.get_sonarr_client", lambda *a, **kw: None)
    monkeypatch.setattr("radarr_client.get_radarr_client", lambda *a, **kw: None)
    resp = client.get("/api/v1/library")
    data = resp.get_json()
    assert resp.status_code == 200
    assert "series" in data
    assert "movies" in data


def test_library_sonarr_returns_series(client, monkeypatch):
    mock_sonarr = MagicMock()
    mock_sonarr.get_library_info.return_value = [
        {"id": 1, "title": "Test Anime", "tags": [], "images": []}
    ]
    monkeypatch.setattr("sonarr_client.get_sonarr_client", lambda *a, **kw: mock_sonarr)
    monkeypatch.setattr("radarr_client.get_radarr_client", lambda *a, **kw: None)

    resp = client.get("/api/v1/library")
    data = resp.get_json()
    assert resp.status_code == 200
    assert len(data["series"]) == 1
    assert data["series"][0]["title"] == "Test Anime"


def test_library_radarr_returns_movies(client, monkeypatch):
    mock_radarr = MagicMock()
    mock_radarr.get_library_info.return_value = [{"id": 10, "title": "Test Movie", "tags": []}]
    monkeypatch.setattr("sonarr_client.get_sonarr_client", lambda *a, **kw: None)
    monkeypatch.setattr("radarr_client.get_radarr_client", lambda *a, **kw: mock_radarr)

    resp = client.get("/api/v1/library")
    data = resp.get_json()
    assert resp.status_code == 200
    assert len(data["movies"]) == 1
    assert data["movies"][0]["title"] == "Test Movie"


def test_library_both_sonarr_and_radarr(client, monkeypatch):
    mock_sonarr = MagicMock()
    mock_sonarr.get_library_info.return_value = [{"id": 1, "title": "S1", "tags": []}]
    mock_radarr = MagicMock()
    mock_radarr.get_library_info.return_value = [{"id": 2, "title": "M1", "tags": []}]
    monkeypatch.setattr("sonarr_client.get_sonarr_client", lambda *a, **kw: mock_sonarr)
    monkeypatch.setattr("radarr_client.get_radarr_client", lambda *a, **kw: mock_radarr)

    resp = client.get("/api/v1/library")
    data = resp.get_json()
    assert resp.status_code == 200
    assert len(data["series"]) == 1
    assert len(data["movies"]) == 1


def test_library_sonarr_raises_returns_empty_series(client, monkeypatch):
    """If Sonarr client raises, series list is still empty (graceful degradation)."""

    def _bad_client():
        raise RuntimeError("Connection refused")

    monkeypatch.setattr("sonarr_client.get_sonarr_client", _bad_client)
    monkeypatch.setattr("radarr_client.get_radarr_client", lambda *a, **kw: None)

    resp = client.get("/api/v1/library")
    data = resp.get_json()
    assert resp.status_code == 200
    assert data["series"] == []


def test_library_mixed_mode_sonarr_plus_standalone_movies(client, monkeypatch):
    """Sonarr-managed series + standalone movies → both must appear.

    Regression: previously the standalone fallback only fired when BOTH
    Sonarr AND Radarr returned empty, silently dropping standalone movies
    in mixed deployments.
    """
    mock_sonarr = MagicMock()
    mock_sonarr.get_library_info.return_value = [{"id": 1, "title": "Managed Series", "tags": []}]
    monkeypatch.setattr("sonarr_client.get_sonarr_client", lambda *a, **kw: mock_sonarr)
    monkeypatch.setattr("radarr_client.get_radarr_client", lambda *a, **kw: None)
    monkeypatch.setattr("config.is_standalone_mode", lambda: True)
    monkeypatch.setattr(
        "db.standalone.get_standalone_movies",
        lambda *a, **kw: [
            {
                "id": 99,
                "title": "Standalone Movie",
                "year": 2024,
                "file_path": "/media/movies/Standalone Movie (2024)/movie.mkv",
                "poster_url": "",
            }
        ],
    )
    monkeypatch.setattr("db.standalone.get_standalone_series", lambda *a, **kw: [])

    resp = client.get("/api/v1/library")
    data = resp.get_json()
    assert resp.status_code == 200
    assert any(s["title"] == "Managed Series" for s in data["series"])
    assert any(m["title"] == "Standalone Movie" for m in data["movies"])


def test_library_standalone_movie_titled_sample_in_real_path_kept(client, monkeypatch):
    """Real movie literally titled "Sample" — path heuristic must not drop it.

    Regression: previous title-blacklist rejected real titles "Sample" /
    "Movie" / "Trailer". Path-based heuristic only excludes when the file
    actually lives under an extras folder.
    """
    monkeypatch.setattr("sonarr_client.get_sonarr_client", lambda *a, **kw: None)
    monkeypatch.setattr("radarr_client.get_radarr_client", lambda *a, **kw: None)
    monkeypatch.setattr("config.is_standalone_mode", lambda: True)
    monkeypatch.setattr("db.standalone.get_standalone_series", lambda *a, **kw: [])
    monkeypatch.setattr(
        "db.standalone.get_standalone_movies",
        lambda *a, **kw: [
            {
                "id": 1,
                "title": "Sample",
                "year": 2008,
                "file_path": "/media/movies/Sample (2008)/Sample.mkv",
                "poster_url": "",
            },
        ],
    )

    resp = client.get("/api/v1/library")
    data = resp.get_json()
    assert resp.status_code == 200
    assert any(m["title"] == "Sample" for m in data["movies"])


def test_library_standalone_movie_under_sample_dir_excluded(client, monkeypatch):
    """File path under an extras dir must be excluded even with a real-looking title."""
    monkeypatch.setattr("sonarr_client.get_sonarr_client", lambda *a, **kw: None)
    monkeypatch.setattr("radarr_client.get_radarr_client", lambda *a, **kw: None)
    monkeypatch.setattr("config.is_standalone_mode", lambda: True)
    monkeypatch.setattr("db.standalone.get_standalone_series", lambda *a, **kw: [])
    monkeypatch.setattr(
        "db.standalone.get_standalone_movies",
        lambda *a, **kw: [
            {
                "id": 1,
                "title": "Inception",
                "year": 2010,
                "file_path": "/media/movies/Inception (2010)/Sample/sample.mkv",
                "poster_url": "",
            },
        ],
    )

    resp = client.get("/api/v1/library")
    data = resp.get_json()
    assert resp.status_code == 200
    assert all(
        not m["path"].lower().replace("\\", "/").split("/").__contains__("sample")
        for m in data["movies"]
    )


# ---------------------------------------------------------------------------
# GET /api/v1/library/series/<series_id> — series detail
# ---------------------------------------------------------------------------


def test_series_detail_sonarr_not_configured(client, monkeypatch):
    monkeypatch.setattr("sonarr_client.get_sonarr_client", lambda *a, **kw: None)
    # No standalone fallback
    with patch("db.standalone.get_standalone_series", return_value=None):
        resp = client.get("/api/v1/library/series/1")
    assert resp.status_code == 503


def test_series_detail_not_found(client, monkeypatch):
    mock_sonarr = MagicMock()
    mock_sonarr.get_series_by_id.return_value = None
    monkeypatch.setattr("sonarr_client.get_sonarr_client", lambda *a, **kw: mock_sonarr)
    resp = client.get("/api/v1/library/series/999")
    assert resp.status_code == 404


def test_series_detail_found(client, monkeypatch):
    mock_sonarr = MagicMock()
    mock_sonarr.get_series_by_id.return_value = {
        "id": 1,
        "title": "My Series",
        "year": 2020,
        "path": "/media/series",
        "images": [],
        "tags": [],
        "status": "continuing",
        "overview": "",
    }
    mock_sonarr.get_episodes.return_value = []
    mock_sonarr.get_episode_files_by_series.return_value = {}
    mock_sonarr.get_tags.return_value = []
    monkeypatch.setattr("sonarr_client.get_sonarr_client", lambda *a, **kw: mock_sonarr)

    resp = client.get("/api/v1/library/series/1")
    data = resp.get_json()
    assert resp.status_code == 200
    assert data["title"] == "My Series"
    assert data["id"] == 1
    assert "episodes" in data
    assert isinstance(data["episodes"], list)


def test_standalone_series_detail_lists_episodes_from_disk_without_wanted(
    client, monkeypatch, tmp_path
):
    """Regression: a standalone series with 0 wanted_items (all subs present)
    must still list its episodes. The detail now enumerates the series folder on
    disk and uses wanted_items only for status — previously it built episodes
    straight from wanted_items, so a satisfied series rendered '0 episodes'."""
    # Sonarr unconfigured → the endpoint falls back to the standalone builder.
    monkeypatch.setattr("sonarr_client.get_sonarr_client", lambda *a, **kw: None)

    # Two episode files on disk; NO wanted_items are inserted for this series.
    sdir = tmp_path / "My Show (2020)" / "Season 1"
    sdir.mkdir(parents=True)
    (sdir / "My Show - S01E01 [1080p].mkv").write_bytes(b"\x00")
    (sdir / "My Show - S01E02 [1080p].mkv").write_bytes(b"\x00")

    series = {
        "id": 77,
        "title": "My Show",
        "year": 2020,
        "folder_path": str(tmp_path),
        "poster_url": "",
        "status": "continuing",
        "season_count": 1,
    }
    monkeypatch.setattr("db.standalone.get_standalone_series", lambda *a, **kw: series)

    resp = client.get("/api/v1/library/series/77")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["source"] == "standalone"
    assert data["episode_count"] == 2
    paths = {e["file_path"] for e in data["episodes"]}
    assert any("S01E01" in p for p in paths)
    assert any("S01E02" in p for p in paths)


def test_series_detail_with_episodes(client, monkeypatch):
    mock_sonarr = MagicMock()
    mock_sonarr.get_series_by_id.return_value = {
        "id": 5,
        "title": "Anime Show",
        "year": 2021,
        "path": "/media/anime",
        "images": [],
        "tags": [],
        "status": "ended",
        "overview": "Great show",
    }
    mock_sonarr.get_episodes.return_value = [
        {
            "id": 101,
            "seasonNumber": 1,
            "episodeNumber": 1,
            "title": "Episode 1",
            "hasFile": False,
            "monitored": True,
        }
    ]
    mock_sonarr.get_episode_files_by_series.return_value = {}
    mock_sonarr.get_tags.return_value = []
    monkeypatch.setattr("sonarr_client.get_sonarr_client", lambda *a, **kw: mock_sonarr)

    resp = client.get("/api/v1/library/series/5")
    data = resp.get_json()
    assert resp.status_code == 200
    assert len(data["episodes"]) == 1
    assert data["episodes"][0]["season"] == 1
    assert data["episodes"][0]["episode"] == 1


def test_series_detail_includes_profile_info(client, monkeypatch):
    mock_sonarr = MagicMock()
    mock_sonarr.get_series_by_id.return_value = {
        "id": 2,
        "title": "Profiled Series",
        "year": 2022,
        "path": "/media/s2",
        "images": [],
        "tags": [],
        "status": "continuing",
        "overview": "",
    }
    mock_sonarr.get_episodes.return_value = []
    mock_sonarr.get_episode_files_by_series.return_value = {}
    mock_sonarr.get_tags.return_value = []
    monkeypatch.setattr("sonarr_client.get_sonarr_client", lambda *a, **kw: mock_sonarr)

    resp = client.get("/api/v1/library/series/2")
    data = resp.get_json()
    assert resp.status_code == 200
    assert "target_languages" in data
    assert "profile_name" in data


# ---------------------------------------------------------------------------
# 0.71.1 follow-up #3 — cleanup_foreign_tracks_override / _effective response fields
# ---------------------------------------------------------------------------


def _sonarr_series_stub(sid: int):
    mock_sonarr = MagicMock()
    mock_sonarr.get_series_by_id.return_value = {
        "id": sid,
        "title": f"Series {sid}",
        "year": 2024,
        "path": f"/media/s{sid}",
        "images": [],
        "tags": [],
        "status": "continuing",
        "overview": "",
    }
    mock_sonarr.get_episodes.return_value = []
    mock_sonarr.get_episode_files_by_series.return_value = {}
    mock_sonarr.get_tags.return_value = []
    return mock_sonarr


def test_series_detail_cleanup_foreign_tracks_no_row_inherits_global_false(client, monkeypatch):
    """No SeriesSettings row, global default False → override null, effective False."""
    monkeypatch.setattr("sonarr_client.get_sonarr_client", lambda *a, **kw: _sonarr_series_stub(1))
    resp = client.get("/api/v1/library/series/1")
    data = resp.get_json()
    assert resp.status_code == 200
    assert data["cleanup_foreign_tracks_override"] is None
    assert data["cleanup_foreign_tracks_effective"] is False


def test_series_detail_cleanup_foreign_tracks_series_override_true(client, monkeypatch):
    """SeriesSettings.cleanup_foreign_tracks = True beats global False → effective True."""
    from db.models.core import SeriesSettings
    from extensions import db as _db

    with client.application.app_context():
        row = SeriesSettings(
            sonarr_series_id=7,
            cleanup_foreign_tracks=True,
            updated_at=datetime.now(UTC),
        )
        _db.session.add(row)
        _db.session.commit()

    monkeypatch.setattr("sonarr_client.get_sonarr_client", lambda *a, **kw: _sonarr_series_stub(7))
    resp = client.get("/api/v1/library/series/7")
    data = resp.get_json()
    assert resp.status_code == 200
    assert data["cleanup_foreign_tracks_override"] is True
    assert data["cleanup_foreign_tracks_effective"] is True


def test_series_detail_cleanup_foreign_tracks_series_override_false_beats_global_true(
    client, monkeypatch
):
    """SeriesSettings.cleanup_foreign_tracks = False beats global True → effective False."""
    from db.models.core import SeriesSettings
    from extensions import db as _db

    with client.application.app_context():
        row = SeriesSettings(
            sonarr_series_id=9,
            cleanup_foreign_tracks=False,
            updated_at=datetime.now(UTC),
        )
        _db.session.add(row)
        _db.session.commit()

    # Simulate global True via a fake Settings object returned by get_settings().
    class _S:
        cleanup_foreign_tracks_default = True
        target_language = "de"
        target_language_name = "German"
        source_language = "en"
        source_language_name = "English"

    monkeypatch.setattr("config.get_settings", lambda: _S())
    monkeypatch.setattr("sonarr_client.get_sonarr_client", lambda *a, **kw: _sonarr_series_stub(9))
    resp = client.get("/api/v1/library/series/9")
    data = resp.get_json()
    assert resp.status_code == 200
    assert data["cleanup_foreign_tracks_override"] is False
    assert data["cleanup_foreign_tracks_effective"] is False


def test_standalone_series_detail_cleanup_foreign_tracks_inherits_global(client, monkeypatch):
    """Standalone path has no SeriesSettings → override null, effective = global default."""
    # No Sonarr → falls through to standalone
    monkeypatch.setattr("sonarr_client.get_sonarr_client", lambda *a, **kw: None)

    fake_series = {
        "id": 42,
        "title": "Standalone Show",
        "year": 2023,
        "folder_path": "/media/standalone/show",
        "status": "continuing",
        "season_count": 1,
        "poster_url": None,
    }

    class _S:
        cleanup_foreign_tracks_default = True
        target_language = "de"
        target_language_name = "German"
        source_language = "en"
        source_language_name = "English"

    monkeypatch.setattr("config.get_settings", lambda: _S())
    with patch("db.standalone.get_standalone_series", return_value=fake_series):
        resp = client.get("/api/v1/library/series/42")

    data = resp.get_json()
    assert resp.status_code == 200
    assert data["source"] == "standalone"
    assert data["cleanup_foreign_tracks_override"] is None
    assert data["cleanup_foreign_tracks_effective"] is True


def test_standalone_series_detail_returns_subtitle_scores(client, monkeypatch):
    """Regression: the subtitle_downloads → standalone series query used `?`
    placeholders + a positional list, which SQLAlchemy 2.x rejects on every
    backend (the route's catch-all hid it as a debug log). Score and provider
    must surface on the per-episode payload now that the query uses an
    expanding bindparam.
    """
    from db.models.core import WantedItem
    from db.models.providers import SubtitleDownload
    from extensions import db as ext_db

    monkeypatch.setattr("sonarr_client.get_sonarr_client", lambda *a, **kw: None)

    fake_series = {
        "id": 99,
        "title": "Score Test",
        "year": 2024,
        "folder_path": "/media/standalone/score",
        "status": "continuing",
        "season_count": 1,
        "poster_url": None,
    }

    class _S:
        cleanup_foreign_tracks_default = False
        target_language = "de"
        target_language_name = "German"
        source_language = "en"
        source_language_name = "English"

    monkeypatch.setattr("config.get_settings", lambda: _S())

    # Seed one wanted_items + one subtitle_downloads row that the query
    # should resolve. Use a real session — the bug was specifically that the
    # f-string SQL fails on SQLAlchemy session.execute.
    with client.application.app_context():
        now = datetime.now(UTC)
        ext_db.session.add(
            WantedItem(
                item_type="episode",
                file_path="/media/standalone/score/ep1.mkv",
                target_language="de",
                standalone_series_id=99,
                season_episode="S01E01",
                title="Episode 1",
                status="wanted",
                added_at=now,
                updated_at=now,
            )
        )
        ext_db.session.add(
            SubtitleDownload(
                file_path="/media/standalone/score/ep1.mkv",
                language="de",
                format="ass",
                score=420,
                provider_name="opensubtitles",
                subtitle_id="osub-1",
                downloaded_at=datetime.now(UTC),
            )
        )
        ext_db.session.commit()

    with patch("db.standalone.get_standalone_series", return_value=fake_series):
        resp = client.get("/api/v1/library/series/99")

    assert resp.status_code == 200
    data = resp.get_json()
    assert data["source"] == "standalone"
    assert len(data["episodes"]) == 1
    ep = data["episodes"][0]
    assert ep["subtitle_scores"]["de"] == 420
    assert ep["subtitle_providers"]["de"] == "opensubtitles"


# ---------------------------------------------------------------------------
# PUT /api/v1/library/series/<series_id>/settings
# ---------------------------------------------------------------------------


def test_series_settings_missing_field(client):
    resp = client.put("/api/v1/library/series/1/settings", json={})
    assert resp.status_code == 400
    data = resp.get_json()
    assert data["success"] is False


def test_series_settings_update_absolute_order(client):
    resp = client.put("/api/v1/library/series/1/settings", json={"absolute_order": True})
    data = resp.get_json()
    assert resp.status_code == 200
    assert data["success"] is True
    assert data["absolute_order"] is True
    assert data["series_id"] == 1


def test_series_settings_disable_absolute_order(client):
    resp = client.put("/api/v1/library/series/5/settings", json={"absolute_order": False})
    data = resp.get_json()
    assert resp.status_code == 200
    assert data["absolute_order"] is False


# ---------------------------------------------------------------------------
# GET /api/v1/episodes/<episode_id>/search — episode subtitle search
# ---------------------------------------------------------------------------


def test_episode_search_sonarr_not_configured(client, monkeypatch):
    monkeypatch.setattr("sonarr_client.get_sonarr_client", lambda *a, **kw: None)
    resp = client.post("/api/v1/episodes/1/search")
    assert resp.status_code == 503


def test_episode_search_episode_not_found(client, monkeypatch):
    mock_sonarr = MagicMock()
    mock_sonarr.get_episode_by_id.return_value = None
    monkeypatch.setattr("sonarr_client.get_sonarr_client", lambda *a, **kw: mock_sonarr)
    resp = client.post("/api/v1/episodes/999/search")
    assert resp.status_code == 404


def test_episode_search_episode_has_no_file(client, monkeypatch):
    mock_sonarr = MagicMock()
    mock_sonarr.get_episode_by_id.return_value = {
        "id": 1,
        "title": "Ep 1",
        "seasonNumber": 1,
        "episodeNumber": 1,
        "seriesId": 10,
    }
    mock_sonarr.get_episode_file_path.return_value = None
    monkeypatch.setattr("sonarr_client.get_sonarr_client", lambda *a, **kw: mock_sonarr)

    # Patch find_wanted_by_episode to return None so it tries to get the file
    with patch("db.wanted.find_wanted_by_episode", return_value=None):
        resp = client.post("/api/v1/episodes/1/search")
    assert resp.status_code == 404


def test_episode_search_success(client, monkeypatch, temp_dir, mock_provider_manager):
    import os
    from pathlib import Path

    video = os.path.join(temp_dir, "ep1.mkv")
    Path(video).touch()

    mock_sonarr = MagicMock()
    mock_sonarr.get_episode_by_id.return_value = {
        "id": 1,
        "title": "Ep 1",
        "seasonNumber": 1,
        "episodeNumber": 1,
        "seriesId": 10,
    }
    mock_sonarr.get_series_by_id.return_value = {"title": "My Anime"}
    mock_sonarr.get_episode_file_path.return_value = video
    monkeypatch.setattr("sonarr_client.get_sonarr_client", lambda *a, **kw: mock_sonarr)
    monkeypatch.setattr("config.map_path", lambda p: p)

    with (
        patch("db.wanted.find_wanted_by_episode", return_value=None),
        patch("db.wanted.upsert_wanted_item", return_value=(1, False)),
        patch("wanted_search.search_wanted_item", return_value={"wanted_id": 1, "results": []}),
    ):
        resp = client.post("/api/v1/episodes/1/search")

    assert resp.status_code in (200, 202)


# ---------------------------------------------------------------------------
# GET /api/v1/episodes/<episode_id>/history
# ---------------------------------------------------------------------------


def test_episode_history_sonarr_not_configured(client, monkeypatch):
    monkeypatch.setattr("sonarr_client.get_sonarr_client", lambda *a, **kw: None)
    resp = client.get("/api/v1/episodes/1/history")
    assert resp.status_code == 503


def test_episode_history_no_file(client, monkeypatch):
    mock_sonarr = MagicMock()
    mock_sonarr.get_episode_file_path.return_value = None
    monkeypatch.setattr("sonarr_client.get_sonarr_client", lambda *a, **kw: mock_sonarr)
    resp = client.get("/api/v1/episodes/1/history")
    data = resp.get_json()
    assert resp.status_code == 200
    assert data["entries"] == []


def test_episode_history_with_entries(client, monkeypatch):
    mock_sonarr = MagicMock()
    mock_sonarr.get_episode_file_path.return_value = "/media/ep1.mkv"
    monkeypatch.setattr("sonarr_client.get_sonarr_client", lambda *a, **kw: mock_sonarr)
    monkeypatch.setattr("config.map_path", lambda p: p)

    fake_entries = [
        {
            "file_path": "/media/ep1.mkv",
            "provider_name": "animetosho",
            "language": "de",
            "downloaded_at": "2024-01-01T00:00:00",
        }
    ]
    with patch("db.cache.get_episode_history", return_value=fake_entries):
        resp = client.get("/api/v1/episodes/1/history")

    data = resp.get_json()
    assert resp.status_code == 200
    assert len(data["entries"]) == 1
    assert data["entries"][0]["provider_name"] == "animetosho"


# ---------------------------------------------------------------------------
# GET /api/v1/episodes/<episode_id>/search-providers — interactive search
# ---------------------------------------------------------------------------


def test_episode_search_providers_sonarr_not_configured(client, monkeypatch):
    monkeypatch.setattr("sonarr_client.get_sonarr_client", lambda *a, **kw: None)
    resp = client.get("/api/v1/episodes/1/search-providers")
    assert resp.status_code == 503


def test_episode_search_providers_episode_not_found(client, monkeypatch):
    mock_sonarr = MagicMock()
    mock_sonarr.get_episode_by_id.return_value = None
    monkeypatch.setattr("sonarr_client.get_sonarr_client", lambda *a, **kw: mock_sonarr)
    resp = client.get("/api/v1/episodes/999/search-providers")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /api/v1/episodes/<episode_id>/download-specific
# ---------------------------------------------------------------------------


def test_download_specific_missing_fields(client, monkeypatch):
    mock_sonarr = MagicMock()
    mock_sonarr.get_episode_by_id.return_value = {
        "id": 1,
        "title": "Ep 1",
        "seasonNumber": 1,
        "episodeNumber": 1,
        "seriesId": 10,
    }
    monkeypatch.setattr("sonarr_client.get_sonarr_client", lambda *a, **kw: mock_sonarr)
    # Missing required fields
    resp = client.post("/api/v1/episodes/1/download-specific", json={})
    assert resp.status_code == 400


def test_download_specific_sonarr_not_configured(client, monkeypatch):
    monkeypatch.setattr("sonarr_client.get_sonarr_client", lambda *a, **kw: None)
    resp = client.post(
        "/api/v1/episodes/1/download-specific",
        json={"provider_name": "animetosho", "subtitle_id": "123", "language": "de"},
    )
    assert resp.status_code == 503
