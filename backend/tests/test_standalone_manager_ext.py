"""Extended tests for services/standalone_manager.py — series/movie business logic."""

import os
import threading
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# validate_folder_input
# ---------------------------------------------------------------------------


def test_validate_folder_input_whitespace_only():
    """Whitespace-only path is rejected."""
    from services.standalone_manager import validate_folder_input

    error = validate_folder_input({"path": "   ", "media_type": "auto"})
    assert error is not None
    assert "path" in error.lower()


def test_validate_folder_input_default_media_type(tmp_path):
    """Missing media_type defaults to 'auto' and is valid."""
    from services.standalone_manager import validate_folder_input

    error = validate_folder_input({"path": str(tmp_path)})
    assert error is None


def test_validate_folder_input_movie_type(tmp_path):
    """media_type='movie' is valid."""
    from services.standalone_manager import validate_folder_input

    error = validate_folder_input({"path": str(tmp_path), "media_type": "movie"})
    assert error is None


# ---------------------------------------------------------------------------
# validate_folder_exists_for_scan
# ---------------------------------------------------------------------------


def test_validate_folder_exists_found(monkeypatch):
    """Returns folder dict when found."""
    from services.standalone_manager import validate_folder_exists_for_scan

    folder = {"id": 1, "path": "/media/anime"}
    monkeypatch.setattr("services.standalone_manager.get_watched_folder", lambda fid: folder)
    result = validate_folder_exists_for_scan(1)
    assert result == folder


# ---------------------------------------------------------------------------
# enrich_series_list
# ---------------------------------------------------------------------------


def test_enrich_series_list_adds_wanted_count(app_ctx):
    """Each series gets a wanted_count field."""
    from services.standalone_manager import enrich_series_list

    series_list = [{"id": 1, "title": "A"}, {"id": 2, "title": "B"}]
    result = enrich_series_list(series_list)
    assert all("wanted_count" in s for s in result)
    # Fresh DB has no wanted items
    assert all(s["wanted_count"] == 0 for s in result)


def test_enrich_series_list_empty(app_ctx):
    """Empty list returns empty list."""
    from services.standalone_manager import enrich_series_list

    assert enrich_series_list([]) == []


# ---------------------------------------------------------------------------
# enrich_series_detail
# ---------------------------------------------------------------------------


def test_enrich_series_detail_adds_wanted_items(app_ctx):
    """Series detail gets wanted_items list."""
    from services.standalone_manager import enrich_series_detail

    series = {"id": 1, "title": "Test"}
    result = enrich_series_detail(series, 1)
    assert "wanted_items" in result
    assert isinstance(result["wanted_items"], list)


# ---------------------------------------------------------------------------
# enrich_movie_list
# ---------------------------------------------------------------------------


def test_enrich_movie_list_adds_wanted_count(app_ctx):
    """Each movie gets a wanted_count field."""
    from services.standalone_manager import enrich_movie_list

    movies = [{"id": 1, "title": "A"}, {"id": 2, "title": "B"}]
    result = enrich_movie_list(movies)
    assert all("wanted_count" in m for m in result)


# ---------------------------------------------------------------------------
# enrich_movie_detail
# ---------------------------------------------------------------------------


def test_enrich_movie_detail_adds_wanted_count(app_ctx):
    """Movie detail gets wanted_count."""
    from services.standalone_manager import enrich_movie_detail

    movie = {"id": 1, "title": "Test Movie"}
    result = enrich_movie_detail(movie, 1)
    assert "wanted_count" in result
    assert result["wanted_count"] == 0


# ---------------------------------------------------------------------------
# get_radarr_movie_fallback
# ---------------------------------------------------------------------------


def test_radarr_movie_fallback_no_client():
    """Returns None when radarr client is not available."""
    from services.standalone_manager import get_radarr_movie_fallback

    with patch("radarr_client.get_radarr_client", return_value=None):
        result = get_radarr_movie_fallback(1)
    assert result is None


def test_radarr_movie_fallback_success():
    """Returns normalised movie dict from radarr."""
    from services.standalone_manager import get_radarr_movie_fallback

    radarr_movie = {
        "id": 42,
        "title": "Test Movie",
        "year": 2025,
        "images": [{"coverType": "poster", "remoteUrl": "https://img/poster.jpg"}],
        "path": "/movies/test",
    }
    mock_radarr = MagicMock()
    mock_radarr.get_movie_by_id.return_value = radarr_movie
    with patch("radarr_client.get_radarr_client", return_value=mock_radarr):
        result = get_radarr_movie_fallback(42)
    assert result is not None
    assert result["title"] == "Test Movie"
    assert result["poster_url"] == "https://img/poster.jpg"
    assert result["source"] == "radarr"


def test_radarr_movie_fallback_no_poster():
    """Returns empty poster_url when no poster image."""
    from services.standalone_manager import get_radarr_movie_fallback

    radarr_movie = {
        "id": 42,
        "title": "No Poster",
        "year": 2025,
        "images": [],
        "path": "/movies/test",
    }
    mock_radarr = MagicMock()
    mock_radarr.get_movie_by_id.return_value = radarr_movie
    with patch("radarr_client.get_radarr_client", return_value=mock_radarr):
        result = get_radarr_movie_fallback(42)
    assert result["poster_url"] == ""


def test_radarr_movie_fallback_exception():
    """Returns None on exception."""
    from services.standalone_manager import get_radarr_movie_fallback

    with patch("radarr_client.get_radarr_client", side_effect=RuntimeError("connection failed")):
        result = get_radarr_movie_fallback(1)
    assert result is None


def test_radarr_movie_fallback_movie_not_found():
    """Returns None when radarr movie not found."""
    from services.standalone_manager import get_radarr_movie_fallback

    mock_radarr = MagicMock()
    mock_radarr.get_movie_by_id.return_value = None
    with patch("radarr_client.get_radarr_client", return_value=mock_radarr):
        result = get_radarr_movie_fallback(999)
    assert result is None


# ---------------------------------------------------------------------------
# resolve_poster_path
# ---------------------------------------------------------------------------


def test_resolve_poster_no_poster():
    """Returns error when no poster_url."""
    from services.standalone_manager import resolve_poster_path

    path, error, status = resolve_poster_path({"poster_url": ""})
    assert path is None
    assert status == 404


def test_resolve_poster_remote_url():
    """Returns the URL for remote poster."""
    from services.standalone_manager import resolve_poster_path

    path, error, status = resolve_poster_path({"poster_url": "https://img/poster.jpg"})
    assert path == "https://img/poster.jpg"
    assert error is None
    assert status is None


def test_resolve_poster_local_file_not_found():
    """Returns 404 when local poster file does not exist."""
    from services.standalone_manager import resolve_poster_path

    path, error, status = resolve_poster_path({"poster_url": "/nonexistent/poster.jpg"})
    assert path is None
    assert status == 404


def test_resolve_poster_local_file_safe(tmp_path):
    """Returns local poster path when safe."""
    from services.standalone_manager import resolve_poster_path

    poster = tmp_path / "poster.jpg"
    poster.write_bytes(b"\xff\xd8\xff")

    entity = {"poster_url": str(poster), "folder_path": str(tmp_path)}
    with patch("security_utils.is_safe_path", return_value=True):
        path, error, status = resolve_poster_path(entity)
    assert path == str(poster)
    assert error is None


def test_resolve_poster_path_traversal(tmp_path):
    """Returns 403 when path is not safe."""
    from services.standalone_manager import resolve_poster_path

    poster = tmp_path / "poster.jpg"
    poster.write_bytes(b"\xff\xd8\xff")

    entity = {"poster_url": str(poster), "folder_path": str(tmp_path / "subfolder")}
    with patch("security_utils.is_safe_path", return_value=False):
        path, error, status = resolve_poster_path(entity)
    assert path is None
    assert status == 403


# ---------------------------------------------------------------------------
# launch_full_scan / launch_folder_scan
# ---------------------------------------------------------------------------


def test_launch_full_scan_thread(monkeypatch):
    """Starts a daemon thread."""
    from services.standalone_manager import launch_full_scan

    threads = []

    class FakeThread:
        def __init__(self, target, daemon=False):
            threads.append(self)
            self.daemon = daemon

        def start(self):
            pass

    monkeypatch.setattr("services.standalone_manager.threading.Thread", FakeThread)
    launch_full_scan(MagicMock())
    assert len(threads) == 1
    assert threads[0].daemon is True


def test_launch_folder_scan_thread(monkeypatch):
    """Starts a daemon thread for folder scan."""
    from services.standalone_manager import launch_folder_scan

    threads = []

    class FakeThread:
        def __init__(self, target, daemon=False):
            threads.append(self)

        def start(self):
            pass

    monkeypatch.setattr("services.standalone_manager.threading.Thread", FakeThread)
    launch_folder_scan(MagicMock(), 1, "/media/anime")
    assert len(threads) == 1


# ---------------------------------------------------------------------------
# get_standalone_status
# ---------------------------------------------------------------------------


def test_get_standalone_status_success():
    """Returns status dict from manager."""
    from services.standalone_manager import get_standalone_status

    mock_manager = MagicMock()
    mock_manager.get_status.return_value = {"active": True}
    with patch("standalone.get_standalone_manager", return_value=mock_manager):
        status = get_standalone_status()
    assert status["active"] is True


# ---------------------------------------------------------------------------
# scan_series_or_fallback
# ---------------------------------------------------------------------------


def test_scan_series_or_fallback_uses_scanner(app_ctx):
    """Calls StandaloneScanner.scan_series and returns its summary."""
    from services.standalone_manager import scan_series_or_fallback

    expected = {"series_id": 1, "wanted_added": 3, "series_found": 1, "movies_found": 0}
    mock_scanner = MagicMock()
    mock_scanner.scan_series.return_value = expected
    with patch("standalone.scanner.StandaloneScanner", return_value=mock_scanner):
        result = scan_series_or_fallback(1)
    mock_scanner.scan_series.assert_called_once_with(1)
    assert result == expected


def test_scan_series_or_fallback_db_fallback(app_ctx):
    """When standalone scanner module unavailable, falls back to DB update."""
    import sys

    from services.standalone_manager import scan_series_or_fallback

    # Hide standalone.scanner from the import system to force the ImportError
    # branch. Restore on cleanup.
    saved = sys.modules.pop("standalone.scanner", None)
    try:
        with patch.dict(sys.modules, {"standalone.scanner": None}):
            # Should not raise — falls back to DB update; returns None.
            result = scan_series_or_fallback(1)
        assert result is None
    finally:
        if saved is not None:
            sys.modules["standalone.scanner"] = saved


# ---------------------------------------------------------------------------
# refresh_series_metadata_sync
# ---------------------------------------------------------------------------


def test_refresh_metadata_sync_series_not_found():
    """Returns None when series does not exist."""
    from services.standalone_manager import refresh_series_metadata_sync

    with patch("db.standalone.get_standalone_series", return_value=None):
        result = refresh_series_metadata_sync(999)
    assert result is None


def test_refresh_metadata_sync_no_result():
    """Returns None when resolver finds nothing."""
    from services.standalone_manager import refresh_series_metadata_sync

    series = {
        "id": 1,
        "title": "Test",
        "folder_path": "/media",
        "year": None,
        "is_anime": False,
    }
    mock_resolver = MagicMock()
    mock_resolver.resolve_series.return_value = None
    with (
        patch("db.standalone.get_standalone_series", return_value=series),
        patch("metadata.MetadataResolver", return_value=mock_resolver),
    ):
        result = refresh_series_metadata_sync(1)
    assert result is None


def test_refresh_metadata_sync_success():
    """Returns updated series on successful resolution."""
    from services.standalone_manager import refresh_series_metadata_sync

    series = {
        "id": 1,
        "title": "Test",
        "folder_path": "/media",
        "year": 2024,
        "is_anime": True,
        "episode_count": 12,
        "season_count": 1,
    }
    updated_series = {**series, "title": "Updated Title"}

    call_count = [0]

    def fake_get_series(sid):
        call_count[0] += 1
        return series if call_count[0] == 1 else updated_series

    mock_resolver = MagicMock()
    mock_resolver.resolve_series.return_value = {
        "title": "Updated Title",
        "year": 2024,
        "tmdb_id": 12345,
        "tvdb_id": 67890,
        "anilist_id": 111,
        "imdb_id": "tt1234",
        "poster_url": "https://poster.jpg",
        "metadata_source": "tmdb",
    }
    with (
        patch("db.standalone.get_standalone_series", side_effect=fake_get_series),
        patch("metadata.MetadataResolver", return_value=mock_resolver),
        patch("db.standalone.upsert_standalone_series"),
    ):
        result = refresh_series_metadata_sync(1)
    assert result is not None


# ---------------------------------------------------------------------------
# delete_series_cascade / delete_movie_cascade
# ---------------------------------------------------------------------------


def test_delete_series_cascade(app_ctx):
    """Deletes wanted items and then the series."""
    from services.standalone_manager import delete_series_cascade

    with patch("db.standalone.delete_standalone_series") as mock_delete:
        delete_series_cascade(1)
    mock_delete.assert_called_once_with(1)


def test_delete_movie_cascade(app_ctx):
    """Deletes wanted items and then the movie."""
    from services.standalone_manager import delete_movie_cascade

    with patch("db.standalone.delete_standalone_movie") as mock_delete:
        delete_movie_cascade(1)
    mock_delete.assert_called_once_with(1)
