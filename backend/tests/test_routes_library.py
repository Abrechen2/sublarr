"""HTTP tests for routes/library/ — list, series detail, episode search, history."""

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
