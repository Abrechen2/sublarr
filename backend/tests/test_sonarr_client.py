"""Tests for sonarr_client module — SonarrClient class and factory functions."""

import time
from unittest.mock import MagicMock, patch

import pytest
import requests

from sonarr_client import (
    BACKOFF_BASE,
    MAX_RETRIES,
    SonarrClient,
    get_sonarr_client,
    invalidate_client,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _reset_singletons():
    """Ensure no client singleton leaks between tests."""
    invalidate_client()
    yield
    invalidate_client()


@pytest.fixture
def client():
    """Create a bare SonarrClient with a fake URL/key."""
    return SonarrClient("http://sonarr.local:8989", "test-api-key")


@pytest.fixture
def mock_session(client):
    """Replace the requests.Session on the client with a MagicMock."""
    mock = MagicMock(spec=requests.Session)
    client.session = mock
    return mock


def _ok_response(json_data, status_code=200, content=b"ok"):
    """Build a MagicMock that behaves like a successful requests.Response."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data
    resp.content = content
    resp.headers = {}
    resp.raise_for_status.return_value = None
    return resp


def _error_response(status_code, headers=None):
    """Build a MagicMock that behaves like an HTTP error response."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.headers = headers or {}
    resp.content = b""
    resp.raise_for_status.side_effect = requests.HTTPError(f"HTTP {status_code}")
    return resp


def _rate_limit_response(retry_after=None):
    """Build a 429 rate-limit response."""
    headers = {}
    if retry_after is not None:
        headers["Retry-After"] = str(retry_after)
    resp = MagicMock()
    resp.status_code = 429
    resp.headers = headers
    resp.content = b""
    return resp


# ===========================================================================
# SonarrClient.__init__
# ===========================================================================

class TestSonarrClientInit:
    def test_url_trailing_slash_stripped(self):
        c = SonarrClient("http://host:8989/", "key")
        assert c.url == "http://host:8989"

    def test_api_key_set_in_session_header(self):
        c = SonarrClient("http://host:8989", "my-key")
        assert c.session.headers["X-Api-Key"] == "my-key"


# ===========================================================================
# _get — retry logic, error handling
# ===========================================================================

class TestGet:
    def test_success(self, client, mock_session):
        mock_session.get.return_value = _ok_response({"version": "3.0"})
        result = client._get("/system/status")
        assert result == {"version": "3.0"}
        mock_session.get.assert_called_once()

    def test_connection_error_retries(self, client, mock_session):
        mock_session.get.side_effect = requests.ConnectionError("refused")
        with patch("sonarr_client.time.sleep"):
            result = client._get("/series")
        assert result is None
        assert mock_session.get.call_count == MAX_RETRIES

    def test_timeout_retries(self, client, mock_session):
        mock_session.get.side_effect = requests.Timeout()
        with patch("sonarr_client.time.sleep"):
            result = client._get("/series")
        assert result is None
        assert mock_session.get.call_count == MAX_RETRIES

    def test_http_error_no_retry(self, client, mock_session):
        mock_session.get.return_value = _error_response(404)
        result = client._get("/series/999")
        assert result is None
        # HTTPError should NOT retry — single call only
        assert mock_session.get.call_count == 1

    def test_unexpected_error_no_retry(self, client, mock_session):
        mock_session.get.side_effect = ValueError("unexpected")
        result = client._get("/series")
        assert result is None
        assert mock_session.get.call_count == 1

    def test_rate_limit_429_retries_with_header(self, client, mock_session):
        ok = _ok_response({"ok": True})
        mock_session.get.side_effect = [_rate_limit_response(retry_after=1), ok]
        with patch("sonarr_client.time.sleep"):
            result = client._get("/series")
        assert result == {"ok": True}
        assert mock_session.get.call_count == 2

    def test_rate_limit_429_no_header_uses_default_wait(self, client, mock_session):
        ok = _ok_response({"ok": True})
        mock_session.get.side_effect = [_rate_limit_response(retry_after=None), ok]
        with patch("sonarr_client.time.sleep") as mock_sleep:
            result = client._get("/series")
        # Default wait is 60s when no Retry-After header
        mock_sleep.assert_any_call(60)
        assert result == {"ok": True}

    def test_rate_limit_429_non_numeric_retry_after(self, client, mock_session):
        resp_429 = _rate_limit_response()
        resp_429.headers["Retry-After"] = "not-a-number"
        ok = _ok_response({"ok": True})
        mock_session.get.side_effect = [resp_429, ok]
        with patch("sonarr_client.time.sleep") as mock_sleep:
            result = client._get("/series")
        mock_sleep.assert_any_call(60)
        assert result == {"ok": True}

    def test_rate_limit_exhausts_all_retries(self, client, mock_session):
        mock_session.get.side_effect = [_rate_limit_response(retry_after=1)] * MAX_RETRIES
        with patch("sonarr_client.time.sleep"):
            result = client._get("/series")
        assert result is None
        assert mock_session.get.call_count == MAX_RETRIES

    def test_backoff_sleep_on_connection_error(self, client, mock_session):
        mock_session.get.side_effect = requests.ConnectionError("refused")
        with patch("sonarr_client.time.sleep") as mock_sleep:
            client._get("/series")
        # Attempts 1 and 2 should sleep; attempt 3 (last) should not
        expected_calls = [((BACKOFF_BASE * i,),) for i in range(1, MAX_RETRIES)]
        for i, call in enumerate(expected_calls):
            assert mock_sleep.call_args_list[i] == call


# ===========================================================================
# _post — retry logic, error handling
# ===========================================================================

class TestPost:
    def test_success_with_body(self, client, mock_session):
        mock_session.post.return_value = _ok_response({"id": 1})
        result = client._post("/command", data={"name": "RescanSeries"})
        assert result == {"id": 1}

    def test_success_empty_body(self, client, mock_session):
        resp = MagicMock()
        resp.status_code = 200
        resp.content = b""
        resp.headers = {}
        resp.raise_for_status.return_value = None
        mock_session.post.return_value = resp
        result = client._post("/command")
        assert result == {}

    def test_connection_error_retries(self, client, mock_session):
        mock_session.post.side_effect = requests.ConnectionError("refused")
        with patch("sonarr_client.time.sleep"):
            result = client._post("/command")
        assert result is None
        assert mock_session.post.call_count == MAX_RETRIES

    def test_timeout_retries(self, client, mock_session):
        mock_session.post.side_effect = requests.Timeout()
        with patch("sonarr_client.time.sleep"):
            result = client._post("/command")
        assert result is None
        assert mock_session.post.call_count == MAX_RETRIES

    def test_unexpected_error_no_retry(self, client, mock_session):
        mock_session.post.side_effect = RuntimeError("boom")
        result = client._post("/command")
        assert result is None
        assert mock_session.post.call_count == 1

    def test_rate_limit_429_retries(self, client, mock_session):
        ok = _ok_response({"id": 1})
        mock_session.post.side_effect = [_rate_limit_response(retry_after=1), ok]
        with patch("sonarr_client.time.sleep"):
            result = client._post("/command")
        assert result == {"id": 1}

    def test_rate_limit_exhausts_all_retries(self, client, mock_session):
        mock_session.post.side_effect = [_rate_limit_response(retry_after=1)] * MAX_RETRIES
        with patch("sonarr_client.time.sleep"):
            result = client._post("/command")
        assert result is None


# ===========================================================================
# Public API methods
# ===========================================================================

class TestHealthCheck:
    def test_healthy(self, client, mock_session):
        mock_session.get.return_value = _ok_response({"version": "3.0"})
        healthy, msg = client.health_check()
        assert healthy is True
        assert msg == "OK"

    def test_unhealthy(self, client, mock_session):
        mock_session.get.side_effect = requests.ConnectionError("down")
        with patch("sonarr_client.time.sleep"):
            healthy, msg = client.health_check()
        assert healthy is False
        assert "sonarr.local" in msg


class TestTestConnection:
    def test_success(self, client, mock_session):
        mock_session.get.return_value = _ok_response({"version": "3.0"})
        result = client.test_connection()
        assert result == {"success": True, "message": "OK"}

    def test_failure(self, client, mock_session):
        mock_session.get.side_effect = requests.ConnectionError("down")
        with patch("sonarr_client.time.sleep"):
            result = client.test_connection()
        assert result["success"] is False


class TestGetSeries:
    def test_returns_list(self, client, mock_session):
        series = [{"id": 1, "title": "Naruto"}]
        mock_session.get.return_value = _ok_response(series)
        assert client.get_series() == series

    def test_returns_empty_on_error(self, client, mock_session):
        mock_session.get.side_effect = requests.ConnectionError("down")
        with patch("sonarr_client.time.sleep"):
            assert client.get_series() == []


class TestGetSeriesById:
    def test_returns_dict(self, client, mock_session):
        data = {"id": 42, "title": "One Piece"}
        mock_session.get.return_value = _ok_response(data)
        assert client.get_series_by_id(42) == data

    def test_returns_none_on_error(self, client, mock_session):
        mock_session.get.return_value = _error_response(404)
        assert client.get_series_by_id(999) is None


class TestGetEpisodes:
    def test_returns_list(self, client, mock_session):
        eps = [{"id": 1, "title": "Ep 1"}]
        mock_session.get.return_value = _ok_response(eps)
        result = client.get_episodes(42)
        assert result == eps

    def test_returns_empty_on_error(self, client, mock_session):
        mock_session.get.side_effect = requests.ConnectionError("down")
        with patch("sonarr_client.time.sleep"):
            assert client.get_episodes(42) == []


class TestGetEpisodeById:
    def test_returns_dict(self, client, mock_session):
        ep = {"id": 100, "title": "Pilot"}
        mock_session.get.return_value = _ok_response(ep)
        assert client.get_episode_by_id(100) == ep


class TestGetEpisodeFilePath:
    def test_direct_episode_file_path(self, client, mock_session):
        """episodeFile.path present in the episode response."""
        ep = {"id": 1, "episodeFile": {"path": "/media/show/ep1.mkv"}, "episodeFileId": 10}
        mock_session.get.return_value = _ok_response(ep)
        assert client.get_episode_file_path(1) == "/media/show/ep1.mkv"

    def test_fallback_to_episode_file_endpoint(self, client, mock_session):
        """episodeFile has no path — falls back to /episodefile/{id}."""
        ep = {"id": 1, "episodeFile": {}, "episodeFileId": 10}
        file_info = {"id": 10, "path": "/media/show/ep1.mkv"}
        mock_session.get.side_effect = [_ok_response(ep), _ok_response(file_info)]
        assert client.get_episode_file_path(1) == "/media/show/ep1.mkv"

    def test_no_file_id(self, client, mock_session):
        """Episode has no file (episodeFileId == 0)."""
        ep = {"id": 1, "episodeFileId": 0}
        mock_session.get.return_value = _ok_response(ep)
        assert client.get_episode_file_path(1) is None

    def test_episode_not_found(self, client, mock_session):
        mock_session.get.return_value = _error_response(404)
        assert client.get_episode_file_path(999) is None

    def test_file_endpoint_returns_none(self, client, mock_session):
        """Episode file endpoint fails — returns None."""
        ep = {"id": 1, "episodeFileId": 10}
        mock_session.get.side_effect = [_ok_response(ep), _error_response(500)]
        assert client.get_episode_file_path(1) is None


class TestGetEpisodeFile:
    def test_returns_file_info(self, client, mock_session):
        info = {"id": 10, "path": "/media/ep.mkv"}
        mock_session.get.return_value = _ok_response(info)
        assert client.get_episode_file(10) == info


class TestGetEpisodeFilesBySeries:
    def test_returns_dict_keyed_by_id(self, client, mock_session):
        files = [
            {"id": 1, "path": "/a.mkv"},
            {"id": 2, "path": "/b.mkv"},
        ]
        mock_session.get.return_value = _ok_response(files)
        result = client.get_episode_files_by_series(42)
        assert result == {1: files[0], 2: files[1]}

    def test_skips_entries_without_id(self, client, mock_session):
        files = [{"id": 1, "path": "/a.mkv"}, {"path": "/orphan.mkv"}]
        mock_session.get.return_value = _ok_response(files)
        result = client.get_episode_files_by_series(42)
        assert len(result) == 1

    def test_returns_empty_on_error(self, client, mock_session):
        mock_session.get.side_effect = requests.ConnectionError("down")
        with patch("sonarr_client.time.sleep"):
            assert client.get_episode_files_by_series(42) == {}


class TestGetTags:
    def test_returns_tags(self, client, mock_session):
        tags = [{"id": 1, "label": "anime"}]
        mock_session.get.return_value = _ok_response(tags)
        assert client.get_tags() == tags

    def test_returns_empty_on_error(self, client, mock_session):
        mock_session.get.side_effect = requests.ConnectionError("down")
        with patch("sonarr_client.time.sleep"):
            assert client.get_tags() == []


class TestGetAnimeSeries:
    def _setup_tags_and_series(self, mock_session, tags, series):
        """Helper to set up sequential _get calls for tags + series."""
        mock_session.get.side_effect = [_ok_response(tags), _ok_response(series)]

    def test_matches_by_tag(self, client, mock_session):
        tags = [{"id": 5, "label": "anime"}]
        series = [{"id": 1, "title": "Naruto", "tags": [5], "seriesType": "standard", "genres": []}]
        self._setup_tags_and_series(mock_session, tags, series)
        result = client.get_anime_series()
        assert len(result) == 1

    def test_matches_by_series_type(self, client, mock_session):
        tags = []
        series = [{"id": 1, "title": "Naruto", "tags": [], "seriesType": "anime", "genres": []}]
        self._setup_tags_and_series(mock_session, tags, series)
        result = client.get_anime_series()
        assert len(result) == 1

    def test_matches_by_genre(self, client, mock_session):
        tags = []
        series = [{"id": 1, "title": "Naruto", "tags": [], "seriesType": "standard", "genres": ["Anime", "Action"]}]
        self._setup_tags_and_series(mock_session, tags, series)
        result = client.get_anime_series()
        assert len(result) == 1

    def test_no_match(self, client, mock_session):
        tags = []
        series = [{"id": 1, "title": "Breaking Bad", "tags": [], "seriesType": "standard", "genres": ["Drama"]}]
        self._setup_tags_and_series(mock_session, tags, series)
        result = client.get_anime_series()
        assert len(result) == 0


class TestRescanSeries:
    def test_success(self, client, mock_session):
        mock_session.post.return_value = _ok_response({"id": 1})
        assert client.rescan_series(42) is True

    def test_failure(self, client, mock_session):
        mock_session.post.side_effect = requests.ConnectionError("down")
        with patch("sonarr_client.time.sleep"):
            assert client.rescan_series(42) is False


class TestGetEpisodeMetadata:
    def test_success_with_anidb(self, client, mock_session):
        series = {
            "id": 1, "title": "Naruto", "year": 2002,
            "tvdbId": 78857, "imdbId": "tt0409591",
            "customFields": {},
        }
        episode = {
            "id": 100, "seasonNumber": 1, "episodeNumber": 5, "title": "Ep 5",
        }
        mock_session.get.side_effect = [_ok_response(series), _ok_response(episode)]

        with patch("sonarr_client.get_anidb_id", return_value=123, create=True):
            with patch.dict("sys.modules", {"anidb_mapper": MagicMock(get_anidb_id=MagicMock(return_value=123))}):
                result = client.get_episode_metadata(1, 100)

        assert result is not None
        assert result["series_title"] == "Naruto"
        assert result["season"] == 1
        assert result["episode"] == 5
        assert result["tvdb_id"] == 78857
        assert result["imdb_id"] == "tt0409591"

    def test_series_not_found(self, client, mock_session):
        mock_session.get.return_value = _error_response(404)
        assert client.get_episode_metadata(999, 100) is None

    def test_episode_not_found(self, client, mock_session):
        series = {"id": 1, "title": "X", "tvdbId": 1}
        mock_session.get.side_effect = [_ok_response(series), _error_response(404)]
        assert client.get_episode_metadata(1, 999) is None

    def test_anidb_mapper_failure_graceful(self, client, mock_session):
        """AniDB mapper failure should not break the method."""
        series = {"id": 1, "title": "X", "year": 2020, "tvdbId": 1, "imdbId": "", "customFields": {}}
        episode = {"id": 100, "seasonNumber": 1, "episodeNumber": 1, "title": "Ep"}
        mock_session.get.side_effect = [_ok_response(series), _ok_response(episode)]

        broken_mapper = MagicMock()
        broken_mapper.get_anidb_id.side_effect = RuntimeError("mapper down")
        with patch.dict("sys.modules", {"anidb_mapper": broken_mapper}):
            result = client.get_episode_metadata(1, 100)

        assert result is not None
        assert result["anidb_id"] is None

    def test_anilist_id_from_custom_fields(self, client, mock_session):
        series = {
            "id": 1, "title": "X", "year": 2020,
            "tvdbId": 1, "imdbId": "",
            "customFields": {"anilist_id": "12345"},
        }
        episode = {"id": 100, "seasonNumber": 1, "episodeNumber": 1, "title": "Ep"}
        mock_session.get.side_effect = [_ok_response(series), _ok_response(episode)]

        broken_mapper = MagicMock()
        broken_mapper.get_anidb_id.side_effect = RuntimeError("mapper down")
        with patch.dict("sys.modules", {"anidb_mapper": broken_mapper}):
            result = client.get_episode_metadata(1, 100)

        assert result["anilist_id"] == 12345


# ===========================================================================
# extended_health_check
# ===========================================================================

class TestExtendedHealthCheck:
    def test_connection_failure(self, client, mock_session):
        mock_session.get.side_effect = requests.ConnectionError("down")
        with patch("sonarr_client.time.sleep"):
            report = client.extended_health_check()
        assert report["connection"]["healthy"] is False

    def test_full_success(self, client, mock_session):
        status = {"version": "3.0.10", "branch": "main", "appName": "Sonarr"}
        series = [{"id": 1}, {"id": 2}]
        notifications = [
            {"name": "Sublarr Webhook", "implementation": "Webhook"},
            {"name": "Pushover", "implementation": "Pushover"},
        ]
        health = [{"type": "warning", "message": "Missing root folder"}]

        mock_session.get.side_effect = [
            _ok_response(status),       # /system/status
            _ok_response(series),       # /series
            _ok_response(notifications),  # /notification
            _ok_response(health),       # /health
        ]
        report = client.extended_health_check()

        assert report["connection"]["healthy"] is True
        assert report["api_version"]["version"] == "3.0.10"
        assert report["library_access"]["series_count"] == 2
        assert report["library_access"]["accessible"] is True
        assert len(report["webhook_status"]["sublarr_webhooks"]) == 1
        assert report["webhook_status"]["sublarr_webhooks"][0]["name"] == "Sublarr Webhook"
        assert len(report["health_issues"]) == 1

    def test_partial_failure_graceful(self, client, mock_session):
        """Series endpoint works but notifications and health fail."""
        status = {"version": "3.0.10", "branch": "main", "appName": "Sonarr"}
        mock_session.get.side_effect = [
            _ok_response(status),
            _ok_response([{"id": 1}]),  # series ok
            _error_response(500),       # notifications fail
            _error_response(500),       # health fail
        ]
        report = client.extended_health_check()
        assert report["connection"]["healthy"] is True
        assert report["library_access"]["accessible"] is True
        # notification and health should stay at defaults (not crash)


# ===========================================================================
# get_library_info
# ===========================================================================

class TestGetLibraryInfo:
    def test_anime_only(self, client, mock_session):
        tags = [{"id": 1, "label": "anime"}]
        series = [{
            "id": 10, "title": "Naruto", "year": 2002, "tags": [1],
            "seriesType": "standard", "genres": [],
            "statistics": {"seasonCount": 5, "episodeCount": 220, "episodeFileCount": 200},
            "path": "/media/Naruto",
            "images": [{"coverType": "poster", "remoteUrl": "http://img/poster.jpg"}],
            "status": "ended",
        }]
        mock_session.get.side_effect = [_ok_response(tags), _ok_response(series)]
        result = client.get_library_info(anime_only=True)
        assert len(result) == 1
        item = result[0]
        assert item["title"] == "Naruto"
        assert item["seasons"] == 5
        assert item["episodes"] == 220
        assert item["poster"] == "http://img/poster.jpg"

    def test_all_series(self, client, mock_session):
        series = [
            {"id": 1, "title": "Show A", "year": 2020, "tags": [], "seriesType": "standard",
             "genres": [], "statistics": {}, "path": "/a", "images": [], "status": "continuing"},
        ]
        mock_session.get.return_value = _ok_response(series)
        result = client.get_library_info(anime_only=False)
        assert len(result) == 1

    def test_poster_missing(self, client, mock_session):
        series = [
            {"id": 1, "title": "No Poster", "year": 2020, "tags": [], "seriesType": "anime",
             "genres": [], "statistics": {}, "path": "/a", "images": [], "status": "continuing"},
        ]
        # anime_only=True needs tags + series
        tags = []
        mock_session.get.side_effect = [_ok_response(tags), _ok_response(series)]
        result = client.get_library_info(anime_only=True)
        assert result[0]["poster"] == ""


# ===========================================================================
# Factory function: get_sonarr_client
# ===========================================================================

class TestGetSonarrClient:
    def test_returns_none_when_not_configured(self):
        with patch("config.get_sonarr_instances", return_value=[]), \
             patch("sonarr_client.get_settings") as mock_settings:
            mock_settings.return_value.sonarr_url = ""
            mock_settings.return_value.sonarr_api_key = ""
            result = get_sonarr_client()
        assert result is None

    def test_uses_first_instance(self):
        instances = [{"name": "main", "url": "http://sonarr:8989", "api_key": "key1"}]
        with patch("config.get_sonarr_instances", return_value=instances):
            result = get_sonarr_client()
        assert result is not None
        assert result.url == "http://sonarr:8989"

    def test_named_instance(self):
        instances = [
            {"name": "main", "url": "http://sonarr1:8989", "api_key": "k1"},
            {"name": "4k", "url": "http://sonarr2:8989", "api_key": "k2"},
        ]
        with patch("config.get_sonarr_instances", return_value=instances):
            result = get_sonarr_client(instance_name="4k")
        assert result is not None
        assert result.url == "http://sonarr2:8989"

    def test_named_instance_not_found_falls_back(self):
        instances = [{"name": "main", "url": "http://sonarr1:8989", "api_key": "k1"}]
        with patch("config.get_sonarr_instances", return_value=instances):
            result = get_sonarr_client(instance_name="nonexistent")
        assert result is not None
        assert result.url == "http://sonarr1:8989"

    def test_named_instance_no_instances_configured(self):
        with patch("config.get_sonarr_instances", return_value=[]):
            result = get_sonarr_client(instance_name="anything")
        assert result is None

    def test_cached_singleton(self):
        instances = [{"name": "main", "url": "http://sonarr:8989", "api_key": "k1"}]
        with patch("config.get_sonarr_instances", return_value=instances):
            c1 = get_sonarr_client()
            c2 = get_sonarr_client()
        assert c1 is c2

    def test_cached_named_instance(self):
        instances = [{"name": "main", "url": "http://sonarr:8989", "api_key": "k1"}]
        with patch("config.get_sonarr_instances", return_value=instances):
            c1 = get_sonarr_client(instance_name="main")
            c2 = get_sonarr_client(instance_name="main")
        assert c1 is c2

    def test_legacy_fallback(self):
        with patch("config.get_sonarr_instances", return_value=[]), \
             patch("sonarr_client.get_settings") as mock_settings:
            mock_settings.return_value.sonarr_url = "http://legacy:8989"
            mock_settings.return_value.sonarr_api_key = "legacy-key"
            result = get_sonarr_client()
        assert result is not None
        assert result.url == "http://legacy:8989"


# ===========================================================================
# invalidate_client
# ===========================================================================

class TestInvalidateClient:
    def test_clears_all_caches(self):
        instances = [{"name": "main", "url": "http://sonarr:8989", "api_key": "k1"}]
        with patch("config.get_sonarr_instances", return_value=instances):
            get_sonarr_client()
            get_sonarr_client(instance_name="main")

        invalidate_client()

        # After invalidation, next call should create fresh clients
        import sonarr_client as sc
        assert sc._client is None
        assert sc._clients_cache == {}
