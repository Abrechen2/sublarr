"""Tests for routes/standalone.py -- watched folders, series, movies, scanner control, metadata."""

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Patch targets (modules import lazily inside route handlers)
DB_STANDALONE = "db.standalone"
SVC_STANDALONE = "services.standalone_manager"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def client(temp_db):
    from app import create_app

    app = create_app(testing=True)
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


# ---------------------------------------------------------------------------
# TestListFolders — GET /api/v1/standalone/folders
# ---------------------------------------------------------------------------


class TestListFolders:
    def test_returns_all_folders(self, client):
        folders = [
            {"id": 1, "path": "/media/anime", "label": "Anime", "media_type": "tv", "enabled": True}
        ]
        with patch(f"{DB_STANDALONE}.get_watched_folders", return_value=folders):
            resp = client.get("/api/v1/standalone/folders")
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["path"] == "/media/anime"

    def test_returns_empty_list(self, client):
        with patch(f"{DB_STANDALONE}.get_watched_folders", return_value=[]):
            resp = client.get("/api/v1/standalone/folders")
        assert resp.status_code == 200
        assert resp.get_json() == []

    def test_passes_enabled_only_false(self, client):
        with patch(f"{DB_STANDALONE}.get_watched_folders", return_value=[]) as mock_fn:
            client.get("/api/v1/standalone/folders")
        mock_fn.assert_called_once_with(enabled_only=False)

    def test_500_on_exception(self, client):
        with patch(f"{DB_STANDALONE}.get_watched_folders", side_effect=RuntimeError("db error")):
            resp = client.get("/api/v1/standalone/folders")
        assert resp.status_code == 500
        assert "error" in resp.get_json()


# ---------------------------------------------------------------------------
# TestAddFolder — POST /api/v1/standalone/folders
# ---------------------------------------------------------------------------


class TestAddFolder:
    def test_400_when_path_missing(self, client):
        resp = client.post("/api/v1/standalone/folders", json={})
        assert resp.status_code == 400
        assert "path" in resp.get_json()["error"].lower()

    def test_400_when_path_empty(self, client):
        resp = client.post("/api/v1/standalone/folders", json={"path": "   "})
        assert resp.status_code == 400
        assert "path" in resp.get_json()["error"].lower()

    def test_400_when_directory_does_not_exist(self, client):
        resp = client.post("/api/v1/standalone/folders", json={"path": "/nonexistent/dir"})
        assert resp.status_code == 400
        assert "does not exist" in resp.get_json()["error"].lower()

    def test_400_invalid_media_type(self, client, tmp_path):
        resp = client.post(
            "/api/v1/standalone/folders",
            json={"path": str(tmp_path), "media_type": "invalid"},
        )
        assert resp.status_code == 400
        assert "media_type" in resp.get_json()["error"]

    def test_201_on_success(self, client, tmp_path):
        folder_record = {
            "id": 1,
            "path": str(tmp_path),
            "label": "My Folder",
            "media_type": "tv",
            "enabled": True,
        }
        with (
            patch(f"{DB_STANDALONE}.upsert_watched_folder", return_value=1),
            patch(f"{DB_STANDALONE}.get_watched_folder", return_value=folder_record),
        ):
            resp = client.post(
                "/api/v1/standalone/folders",
                json={"path": str(tmp_path), "label": "My Folder", "media_type": "tv"},
            )
        assert resp.status_code == 201
        assert resp.get_json()["id"] == 1

    def test_201_defaults_media_type_to_auto(self, client, tmp_path):
        folder_record = {
            "id": 2,
            "path": str(tmp_path),
            "label": "",
            "media_type": "auto",
            "enabled": True,
        }
        with (
            patch(f"{DB_STANDALONE}.upsert_watched_folder", return_value=2) as mock_upsert,
            patch(f"{DB_STANDALONE}.get_watched_folder", return_value=folder_record),
        ):
            client.post("/api/v1/standalone/folders", json={"path": str(tmp_path)})
        _, kwargs = mock_upsert.call_args
        assert kwargs["media_type"] == "auto"

    def test_500_on_db_error(self, client, tmp_path):
        with patch(f"{DB_STANDALONE}.upsert_watched_folder", side_effect=RuntimeError("db boom")):
            resp = client.post("/api/v1/standalone/folders", json={"path": str(tmp_path)})
        assert resp.status_code == 500
        assert "error" in resp.get_json()


# ---------------------------------------------------------------------------
# TestUpdateFolder — PUT /api/v1/standalone/folders/<id>
# ---------------------------------------------------------------------------


class TestUpdateFolder:
    def test_404_when_folder_not_found(self, client):
        with patch(f"{DB_STANDALONE}.get_watched_folder", return_value=None):
            resp = client.put("/api/v1/standalone/folders/999", json={"label": "new"})
        assert resp.status_code == 404

    def test_400_invalid_media_type(self, client):
        existing = {"id": 1, "path": "/media/anime", "label": "", "media_type": "tv", "enabled": 1}
        with patch(f"{DB_STANDALONE}.get_watched_folder", return_value=existing):
            resp = client.put(
                "/api/v1/standalone/folders/1",
                json={"media_type": "podcast"},
            )
        assert resp.status_code == 400

    def test_400_when_new_path_does_not_exist(self, client):
        existing = {"id": 1, "path": "/media/anime", "label": "", "media_type": "tv", "enabled": 1}
        with patch(f"{DB_STANDALONE}.get_watched_folder", return_value=existing):
            resp = client.put(
                "/api/v1/standalone/folders/1",
                json={"path": "/nonexistent/new/path"},
            )
        assert resp.status_code == 400

    def test_200_on_success(self, client):
        existing = {"id": 1, "path": "/media/anime", "label": "", "media_type": "tv", "enabled": 1}
        updated = {**existing, "label": "Updated"}
        with (
            patch(f"{DB_STANDALONE}.get_watched_folder", side_effect=[existing, updated]),
            patch(f"{DB_STANDALONE}.upsert_watched_folder"),
        ):
            resp = client.put("/api/v1/standalone/folders/1", json={"label": "Updated"})
        assert resp.status_code == 200
        assert resp.get_json()["label"] == "Updated"


# ---------------------------------------------------------------------------
# TestDeleteFolder — DELETE /api/v1/standalone/folders/<id>
# ---------------------------------------------------------------------------


class TestDeleteFolder:
    def test_404_when_not_found(self, client):
        with patch(f"{DB_STANDALONE}.get_watched_folder", return_value=None):
            resp = client.delete("/api/v1/standalone/folders/999")
        assert resp.status_code == 404

    def test_200_on_success(self, client):
        existing = {"id": 1, "path": "/media/anime"}
        with (
            patch(f"{DB_STANDALONE}.get_watched_folder", return_value=existing),
            patch(f"{DB_STANDALONE}.delete_watched_folder"),
        ):
            resp = client.delete("/api/v1/standalone/folders/1")
        assert resp.status_code == 200
        assert resp.get_json()["success"] is True

    def test_500_on_db_error(self, client):
        existing = {"id": 1, "path": "/media/anime"}
        with (
            patch(f"{DB_STANDALONE}.get_watched_folder", return_value=existing),
            patch(f"{DB_STANDALONE}.delete_watched_folder", side_effect=RuntimeError("boom")),
        ):
            resp = client.delete("/api/v1/standalone/folders/1")
        assert resp.status_code == 500


# ---------------------------------------------------------------------------
# TestListSeries — GET /api/v1/standalone/series
# ---------------------------------------------------------------------------


class TestListSeries:
    def test_returns_enriched_series(self, client):
        raw = [{"id": 1, "title": "Naruto", "folder_path": "/media/naruto"}]
        enriched = [{"id": 1, "title": "Naruto", "folder_path": "/media/naruto", "wanted_count": 3}]
        with (
            patch(f"{DB_STANDALONE}.get_standalone_series", return_value=raw),
            patch(f"{SVC_STANDALONE}.enrich_series_list", return_value=enriched),
        ):
            resp = client.get("/api/v1/standalone/series")
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data) == 1
        assert data[0]["wanted_count"] == 3

    def test_500_on_error(self, client):
        with patch(f"{DB_STANDALONE}.get_standalone_series", side_effect=RuntimeError("fail")):
            resp = client.get("/api/v1/standalone/series")
        assert resp.status_code == 500


# ---------------------------------------------------------------------------
# TestGetSeries — GET /api/v1/standalone/series/<id>
# ---------------------------------------------------------------------------


class TestGetSeries:
    def test_404_when_not_found(self, client):
        with patch(f"{DB_STANDALONE}.get_standalone_series", return_value=None):
            resp = client.get("/api/v1/standalone/series/999")
        assert resp.status_code == 404

    def test_200_with_enriched_data(self, client):
        series = {"id": 1, "title": "Attack on Titan", "folder_path": "/media/aot"}
        enriched = {**series, "wanted_items": []}
        with (
            patch(f"{DB_STANDALONE}.get_standalone_series", return_value=series),
            patch(f"{SVC_STANDALONE}.enrich_series_detail", return_value=enriched),
        ):
            resp = client.get("/api/v1/standalone/series/1")
        assert resp.status_code == 200
        assert resp.get_json()["title"] == "Attack on Titan"


# ---------------------------------------------------------------------------
# TestDeleteSeries — DELETE /api/v1/standalone/series/<id>
# ---------------------------------------------------------------------------


class TestDeleteSeries:
    def test_404_when_not_found(self, client):
        with patch(f"{DB_STANDALONE}.get_standalone_series", return_value=None):
            resp = client.delete("/api/v1/standalone/series/999")
        assert resp.status_code == 404

    def test_200_on_cascade_delete(self, client):
        series = {"id": 1, "title": "Naruto"}
        with (
            patch(f"{DB_STANDALONE}.get_standalone_series", return_value=series),
            patch(f"{SVC_STANDALONE}.delete_series_cascade"),
        ):
            resp = client.delete("/api/v1/standalone/series/1")
        assert resp.status_code == 200
        assert resp.get_json()["success"] is True

    def test_500_on_cascade_error(self, client):
        series = {"id": 1, "title": "Naruto"}
        with (
            patch(f"{DB_STANDALONE}.get_standalone_series", return_value=series),
            patch(f"{SVC_STANDALONE}.delete_series_cascade", side_effect=RuntimeError("fail")),
        ):
            resp = client.delete("/api/v1/standalone/series/1")
        assert resp.status_code == 500


# ---------------------------------------------------------------------------
# TestListMovies — GET /api/v1/standalone/movies
# ---------------------------------------------------------------------------


class TestListMovies:
    def test_returns_enriched_movies(self, client):
        raw = [{"id": 1, "title": "Your Name", "file_path": "/media/your_name.mkv"}]
        enriched = [{**raw[0], "wanted_count": 0}]
        with (
            patch(f"{DB_STANDALONE}.get_standalone_movies", return_value=raw),
            patch(f"{SVC_STANDALONE}.enrich_movie_list", return_value=enriched),
        ):
            resp = client.get("/api/v1/standalone/movies")
        assert resp.status_code == 200
        assert len(resp.get_json()) == 1

    def test_500_on_error(self, client):
        with patch(f"{DB_STANDALONE}.get_standalone_movies", side_effect=RuntimeError("fail")):
            resp = client.get("/api/v1/standalone/movies")
        assert resp.status_code == 500


# ---------------------------------------------------------------------------
# TestGetMovie — GET /api/v1/standalone/movies/<id>
# ---------------------------------------------------------------------------


class TestGetMovie:
    def test_404_when_not_found(self, client):
        with (
            patch(f"{DB_STANDALONE}.get_standalone_movies", return_value=None),
            patch(f"{SVC_STANDALONE}.get_radarr_movie_fallback", return_value=None),
        ):
            resp = client.get("/api/v1/standalone/movies/999")
        assert resp.status_code == 404

    def test_200_with_enriched_data(self, client):
        movie = {"id": 1, "title": "Spirited Away", "file_path": "/media/spirited.mkv"}
        enriched = {**movie, "wanted_count": 1}
        with (
            patch(f"{DB_STANDALONE}.get_standalone_movies", return_value=movie),
            patch(f"{SVC_STANDALONE}.enrich_movie_detail", return_value=enriched),
        ):
            resp = client.get("/api/v1/standalone/movies/1")
        assert resp.status_code == 200
        assert resp.get_json()["title"] == "Spirited Away"

    def test_fallback_to_radarr(self, client):
        fallback = {"id": 1, "title": "Radarr Fallback", "source": "radarr"}
        with (
            patch(f"{DB_STANDALONE}.get_standalone_movies", return_value=None),
            patch(f"{SVC_STANDALONE}.get_radarr_movie_fallback", return_value=fallback),
        ):
            resp = client.get("/api/v1/standalone/movies/1")
        assert resp.status_code == 200
        assert resp.get_json()["source"] == "radarr"


# ---------------------------------------------------------------------------
# TestDeleteMovie — DELETE /api/v1/standalone/movies/<id>
# ---------------------------------------------------------------------------


class TestDeleteMovie:
    def test_404_when_not_found(self, client):
        with patch(f"{DB_STANDALONE}.get_standalone_movies", return_value=None):
            resp = client.delete("/api/v1/standalone/movies/999")
        assert resp.status_code == 404

    def test_200_on_cascade_delete(self, client):
        movie = {"id": 1, "title": "Film"}
        with (
            patch(f"{DB_STANDALONE}.get_standalone_movies", return_value=movie),
            patch(f"{SVC_STANDALONE}.delete_movie_cascade"),
        ):
            resp = client.delete("/api/v1/standalone/movies/1")
        assert resp.status_code == 200
        assert resp.get_json()["success"] is True


# ---------------------------------------------------------------------------
# TestScanAll — POST /api/v1/standalone/scan
# ---------------------------------------------------------------------------


class TestScanAll:
    def test_returns_202(self, client):
        with patch(f"{SVC_STANDALONE}.launch_full_scan"):
            resp = client.post("/api/v1/standalone/scan")
        assert resp.status_code == 202
        assert "scan started" in resp.get_json()["message"].lower()


# ---------------------------------------------------------------------------
# TestScanFolder — POST /api/v1/standalone/scan/<id>
# ---------------------------------------------------------------------------


class TestScanFolder:
    def test_404_when_folder_not_found(self, client):
        with patch(f"{DB_STANDALONE}.get_watched_folder", return_value=None):
            resp = client.post("/api/v1/standalone/scan/999")
        assert resp.status_code == 404

    def test_202_on_success(self, client):
        folder = {"id": 1, "path": "/media/anime"}
        with (
            patch(f"{DB_STANDALONE}.get_watched_folder", return_value=folder),
            patch(f"{SVC_STANDALONE}.launch_folder_scan"),
        ):
            resp = client.post("/api/v1/standalone/scan/1")
        assert resp.status_code == 202


# ---------------------------------------------------------------------------
# TestGetStatus — GET /api/v1/standalone/status
# ---------------------------------------------------------------------------


class TestGetStatus:
    def test_returns_status(self, client):
        status = {"enabled": True, "watched_folders": 2, "series_count": 5, "movie_count": 3}
        with patch(f"{SVC_STANDALONE}.get_standalone_status", return_value=status):
            resp = client.get("/api/v1/standalone/status")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["enabled"] is True
        assert data["series_count"] == 5

    def test_501_when_not_implemented(self, client):
        with patch(f"{SVC_STANDALONE}.get_standalone_status", side_effect=ImportError("nope")):
            resp = client.get("/api/v1/standalone/status")
        assert resp.status_code == 501

    def test_500_on_error(self, client):
        with patch(f"{SVC_STANDALONE}.get_standalone_status", side_effect=RuntimeError("fail")):
            resp = client.get("/api/v1/standalone/status")
        assert resp.status_code == 500


# ---------------------------------------------------------------------------
# TestScanSeries — POST /api/v1/standalone/series/<id>/scan
# ---------------------------------------------------------------------------


class TestScanSeries:
    def test_404_when_series_not_found(self, client):
        with patch(f"{DB_STANDALONE}.get_standalone_series", return_value=None):
            resp = client.post("/api/v1/standalone/series/999/scan")
        assert resp.status_code == 404

    def test_200_on_success(self, client):
        series = {"id": 1, "title": "Naruto"}
        with (
            patch(f"{DB_STANDALONE}.get_standalone_series", return_value=series),
            patch(f"{SVC_STANDALONE}.scan_series_or_fallback"),
        ):
            resp = client.post("/api/v1/standalone/series/1/scan")
        assert resp.status_code == 200
        assert resp.get_json()["series_id"] == 1

    def test_500_on_scan_error(self, client):
        series = {"id": 1, "title": "Naruto"}
        with (
            patch(f"{DB_STANDALONE}.get_standalone_series", return_value=series),
            patch(
                f"{SVC_STANDALONE}.scan_series_or_fallback", side_effect=RuntimeError("scan err")
            ),
        ):
            resp = client.post("/api/v1/standalone/series/1/scan")
        assert resp.status_code == 500


# ---------------------------------------------------------------------------
# TestRefreshMetadata — POST /api/v1/standalone/series/<id>/refresh-metadata
# ---------------------------------------------------------------------------


class TestRefreshMetadata:
    def test_404_when_series_not_found(self, client):
        with patch(f"{DB_STANDALONE}.get_standalone_series", return_value=None):
            resp = client.post("/api/v1/standalone/series/999/refresh-metadata")
        assert resp.status_code == 404

    def test_200_on_success(self, client):
        series = {"id": 1, "title": "Naruto"}
        updated = {**series, "tmdb_id": 12345}
        with (
            patch(f"{DB_STANDALONE}.get_standalone_series", return_value=series),
            patch(f"{SVC_STANDALONE}.refresh_series_metadata_sync", return_value=updated),
        ):
            resp = client.post("/api/v1/standalone/series/1/refresh-metadata")
        assert resp.status_code == 200
        assert resp.get_json()["success"] is True

    def test_404_when_no_metadata_found(self, client):
        series = {"id": 1, "title": "Naruto"}
        with (
            patch(f"{DB_STANDALONE}.get_standalone_series", return_value=series),
            patch(f"{SVC_STANDALONE}.refresh_series_metadata_sync", return_value=None),
        ):
            resp = client.post("/api/v1/standalone/series/1/refresh-metadata")
        assert resp.status_code == 404
        assert resp.get_json()["success"] is False

    def test_500_on_import_error(self, client):
        series = {"id": 1, "title": "Naruto"}
        with (
            patch(f"{DB_STANDALONE}.get_standalone_series", return_value=series),
            patch(
                f"{SVC_STANDALONE}.refresh_series_metadata_sync",
                side_effect=ImportError("no resolver"),
            ),
        ):
            resp = client.post("/api/v1/standalone/series/1/refresh-metadata")
        assert resp.status_code == 500
        assert "not available" in resp.get_json()["error"].lower()
