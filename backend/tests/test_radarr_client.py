"""Tests for radarr_client module — RadarrClient class and factory function."""

from unittest.mock import MagicMock, patch

import pytest
import requests

from radarr_client import RadarrClient, get_radarr_client, invalidate_client


# ─── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _reset_client_cache():
    """Ensure module-level singletons are cleared before/after each test."""
    invalidate_client()
    yield
    invalidate_client()


@pytest.fixture
def client():
    """Create a RadarrClient with a fake URL and key."""
    return RadarrClient("http://radarr.local:7878", "test-api-key")


@pytest.fixture
def mock_session(client):
    """Replace the internal requests.Session with a MagicMock."""
    mock = MagicMock(spec=requests.Session)
    client.session = mock
    return mock


def _ok_response(json_data, status_code=200, content=b"ok"):
    """Build a mock response that passes raise_for_status."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data
    resp.content = content
    resp.headers = {}
    resp.raise_for_status.return_value = None
    return resp


def _error_response(status_code, headers=None):
    """Build a mock response that raises HTTPError on raise_for_status."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.headers = headers or {}
    resp.raise_for_status.side_effect = requests.HTTPError(f"HTTP {status_code}")
    return resp


def _rate_limit_response(retry_after=None):
    """Build a 429 response with optional Retry-After header."""
    resp = MagicMock()
    resp.status_code = 429
    resp.headers = {"Retry-After": str(retry_after)} if retry_after else {}
    return resp


# ─── RadarrClient.__init__ ─────────────────────────────────────────────────────


class TestRadarrClientInit:
    def test_url_trailing_slash_stripped(self):
        c = RadarrClient("http://host:7878/", "key")
        assert c.url == "http://host:7878"

    def test_api_key_set_in_session_header(self):
        c = RadarrClient("http://host:7878", "my-key")
        assert c.session.headers["X-Api-Key"] == "my-key"


# ─── _get ──────────────────────────────────────────────────────────────────────


class TestGet:
    def test_get_success(self, client, mock_session):
        mock_session.get.return_value = _ok_response({"version": "4.0"})

        result = client._get("/system/status")

        assert result == {"version": "4.0"}
        mock_session.get.assert_called_once()
        call_args = mock_session.get.call_args
        assert "/api/v3/system/status" in call_args[0][0]

    def test_get_passes_params(self, client, mock_session):
        mock_session.get.return_value = _ok_response([])

        client._get("/movie", params={"tmdbId": 123})

        call_kwargs = mock_session.get.call_args[1]
        assert call_kwargs["params"] == {"tmdbId": 123}

    @patch("radarr_client.time.sleep")
    def test_get_retries_on_connection_error(self, mock_sleep, client, mock_session):
        mock_session.get.side_effect = [
            requests.ConnectionError("refused"),
            _ok_response({"ok": True}),
        ]

        result = client._get("/test")

        assert result == {"ok": True}
        assert mock_session.get.call_count == 2
        mock_sleep.assert_called_once()

    @patch("radarr_client.time.sleep")
    def test_get_retries_on_timeout(self, mock_sleep, client, mock_session):
        mock_session.get.side_effect = [
            requests.Timeout("timed out"),
            requests.Timeout("timed out"),
            _ok_response({"ok": True}),
        ]

        result = client._get("/test")

        assert result == {"ok": True}
        assert mock_session.get.call_count == 3

    @patch("radarr_client.time.sleep")
    def test_get_returns_none_after_max_retries_connection_error(self, mock_sleep, client, mock_session):
        mock_session.get.side_effect = requests.ConnectionError("refused")

        result = client._get("/test")

        assert result is None
        assert mock_session.get.call_count == 3  # MAX_RETRIES

    def test_get_returns_none_on_http_error(self, client, mock_session):
        mock_session.get.return_value = _error_response(500)

        result = client._get("/test")

        assert result is None

    def test_get_returns_none_on_unexpected_error(self, client, mock_session):
        mock_session.get.side_effect = ValueError("unexpected")

        result = client._get("/test")

        assert result is None

    @patch("radarr_client.time.sleep")
    def test_get_rate_limit_retries_with_retry_after(self, mock_sleep, client, mock_session):
        mock_session.get.side_effect = [
            _rate_limit_response(retry_after=5),
            _ok_response({"ok": True}),
        ]

        result = client._get("/test")

        assert result == {"ok": True}
        mock_sleep.assert_called_with(5)

    @patch("radarr_client.time.sleep")
    def test_get_rate_limit_default_wait_without_retry_after(self, mock_sleep, client, mock_session):
        mock_session.get.side_effect = [
            _rate_limit_response(),
            _ok_response({"ok": True}),
        ]

        result = client._get("/test")

        assert result == {"ok": True}
        mock_sleep.assert_called_with(60)

    @patch("radarr_client.time.sleep")
    def test_get_rate_limit_invalid_retry_after_uses_default(self, mock_sleep, client, mock_session):
        resp_429 = _rate_limit_response()
        resp_429.headers = {"Retry-After": "not-a-number"}
        mock_session.get.side_effect = [
            resp_429,
            _ok_response({"ok": True}),
        ]

        result = client._get("/test")

        assert result == {"ok": True}
        mock_sleep.assert_called_with(60)

    @patch("radarr_client.time.sleep")
    def test_get_rate_limit_exhausts_retries(self, mock_sleep, client, mock_session):
        mock_session.get.side_effect = [
            _rate_limit_response(retry_after=1),
            _rate_limit_response(retry_after=1),
            _rate_limit_response(retry_after=1),
        ]

        result = client._get("/test")

        assert result is None


# ─── _post ─────────────────────────────────────────────────────────────────────


class TestPost:
    def test_post_success_with_body(self, client, mock_session):
        mock_session.post.return_value = _ok_response({"id": 42})

        result = client._post("/command", data={"name": "RescanMovie"})

        assert result == {"id": 42}
        call_kwargs = mock_session.post.call_args[1]
        assert call_kwargs["json"] == {"name": "RescanMovie"}

    def test_post_empty_content_returns_empty_dict(self, client, mock_session):
        resp = _ok_response({}, content=b"")
        resp.content = b""
        mock_session.post.return_value = resp

        result = client._post("/command", data={})

        assert result == {}

    @patch("radarr_client.time.sleep")
    def test_post_retries_on_connection_error(self, mock_sleep, client, mock_session):
        mock_session.post.side_effect = [
            requests.ConnectionError("refused"),
            _ok_response({"id": 1}),
        ]

        result = client._post("/command")

        assert result == {"id": 1}
        assert mock_session.post.call_count == 2

    @patch("radarr_client.time.sleep")
    def test_post_retries_on_timeout(self, mock_sleep, client, mock_session):
        mock_session.post.side_effect = [
            requests.Timeout("timed out"),
            _ok_response({"id": 1}),
        ]

        result = client._post("/command")

        assert result == {"id": 1}

    @patch("radarr_client.time.sleep")
    def test_post_returns_none_after_max_retries(self, mock_sleep, client, mock_session):
        mock_session.post.side_effect = requests.ConnectionError("refused")

        result = client._post("/command")

        assert result is None
        assert mock_session.post.call_count == 3

    def test_post_returns_none_on_unexpected_error(self, client, mock_session):
        mock_session.post.side_effect = ValueError("unexpected")

        result = client._post("/command")

        assert result is None

    @patch("radarr_client.time.sleep")
    def test_post_rate_limit_retries(self, mock_sleep, client, mock_session):
        mock_session.post.side_effect = [
            _rate_limit_response(retry_after=2),
            _ok_response({"id": 1}),
        ]

        result = client._post("/command")

        assert result == {"id": 1}
        mock_sleep.assert_called_with(2)

    @patch("radarr_client.time.sleep")
    def test_post_rate_limit_exhausts_retries(self, mock_sleep, client, mock_session):
        mock_session.post.side_effect = [
            _rate_limit_response(retry_after=1),
            _rate_limit_response(retry_after=1),
            _rate_limit_response(retry_after=1),
        ]

        result = client._post("/command")

        assert result is None


# ─── health_check ──────────────────────────────────────────────────────────────


class TestHealthCheck:
    def test_healthy(self, client, mock_session):
        mock_session.get.return_value = _ok_response({"version": "4.0"})

        healthy, msg = client.health_check()

        assert healthy is True
        assert msg == "OK"

    def test_unhealthy(self, client, mock_session):
        mock_session.get.return_value = _error_response(500)

        healthy, msg = client.health_check()

        assert healthy is False
        assert "radarr.local" in msg


# ─── test_connection ───────────────────────────────────────────────────────────


class TestTestConnection:
    def test_success(self, client, mock_session):
        mock_session.get.return_value = _ok_response({"version": "4.0"})

        result = client.test_connection()

        assert result == {"success": True, "message": "OK"}

    def test_failure(self, client, mock_session):
        mock_session.get.return_value = _error_response(500)

        result = client.test_connection()

        assert result["success"] is False


# ─── get_movies ────────────────────────────────────────────────────────────────


class TestGetMovies:
    def test_returns_movies(self, client, mock_session):
        movies = [{"id": 1, "title": "Movie A"}, {"id": 2, "title": "Movie B"}]
        mock_session.get.return_value = _ok_response(movies)

        result = client.get_movies()

        assert result == movies

    def test_returns_empty_list_on_failure(self, client, mock_session):
        mock_session.get.return_value = _error_response(500)

        result = client.get_movies()

        assert result == []


# ─── get_movie_by_id ───────────────────────────────────────────────────────────


class TestGetMovieById:
    def test_returns_movie(self, client, mock_session):
        movie = {"id": 42, "title": "Test Movie"}
        mock_session.get.return_value = _ok_response(movie)

        result = client.get_movie_by_id(42)

        assert result == movie
        assert "/api/v3/movie/42" in mock_session.get.call_args[0][0]


# ─── get_movie_file ────────────────────────────────────────────────────────────


class TestGetMovieFile:
    def test_returns_file_info(self, client, mock_session):
        file_info = {"id": 10, "path": "/movies/test.mkv"}
        mock_session.get.return_value = _ok_response(file_info)

        result = client.get_movie_file(10)

        assert result == file_info
        assert "/api/v3/moviefile/10" in mock_session.get.call_args[0][0]


# ─── get_tags ──────────────────────────────────────────────────────────────────


class TestGetTags:
    def test_returns_tags(self, client, mock_session):
        tags = [{"id": 1, "label": "anime"}, {"id": 2, "label": "drama"}]
        mock_session.get.return_value = _ok_response(tags)

        result = client.get_tags()

        assert result == tags

    def test_returns_empty_list_on_failure(self, client, mock_session):
        mock_session.get.return_value = _error_response(500)

        result = client.get_tags()

        assert result == []


# ─── get_anime_movies ──────────────────────────────────────────────────────────


class TestGetAnimeMovies:
    def test_filters_by_tag(self, client, mock_session):
        tags = [{"id": 5, "label": "anime"}]
        movies = [
            {"id": 1, "title": "Anime Movie", "tags": [5], "genres": []},
            {"id": 2, "title": "Drama Movie", "tags": [9], "genres": ["Drama"]},
        ]
        mock_session.get.side_effect = [
            _ok_response(tags),   # get_tags
            _ok_response(movies),  # get_movies
        ]

        result = client.get_anime_movies()

        assert len(result) == 1
        assert result[0]["title"] == "Anime Movie"

    def test_filters_by_genre(self, client, mock_session):
        tags = []  # no anime tag
        movies = [
            {"id": 1, "title": "Anime Film", "tags": [], "genres": ["Anime", "Action"]},
            {"id": 2, "title": "Comedy", "tags": [], "genres": ["Comedy"]},
        ]
        mock_session.get.side_effect = [
            _ok_response(tags),
            _ok_response(movies),
        ]

        result = client.get_anime_movies()

        assert len(result) == 1
        assert result[0]["title"] == "Anime Film"

    def test_tag_and_genre_combined(self, client, mock_session):
        tags = [{"id": 3, "label": "anime"}]
        movies = [
            {"id": 1, "title": "Tagged", "tags": [3], "genres": []},
            {"id": 2, "title": "Genre'd", "tags": [], "genres": ["Anime"]},
            {"id": 3, "title": "Both", "tags": [3], "genres": ["Anime"]},
            {"id": 4, "title": "Neither", "tags": [], "genres": ["Comedy"]},
        ]
        mock_session.get.side_effect = [
            _ok_response(tags),
            _ok_response(movies),
        ]

        result = client.get_anime_movies()

        assert len(result) == 3
        titles = {m["title"] for m in result}
        assert titles == {"Tagged", "Genre'd", "Both"}

    def test_custom_tag_name(self, client, mock_session):
        tags = [{"id": 7, "label": "cartoons"}]
        movies = [
            {"id": 1, "title": "Cartoon Movie", "tags": [7], "genres": []},
        ]
        mock_session.get.side_effect = [
            _ok_response(tags),
            _ok_response(movies),
        ]

        result = client.get_anime_movies(anime_tag="cartoons")

        assert len(result) == 1

    def test_case_insensitive_tag_matching(self, client, mock_session):
        tags = [{"id": 1, "label": "Anime"}]
        movies = [
            {"id": 1, "title": "Movie", "tags": [1], "genres": []},
        ]
        mock_session.get.side_effect = [
            _ok_response(tags),
            _ok_response(movies),
        ]

        result = client.get_anime_movies(anime_tag="anime")

        assert len(result) == 1


# ─── rescan_movie ──────────────────────────────────────────────────────────────


class TestRescanMovie:
    def test_success(self, client, mock_session):
        mock_session.post.return_value = _ok_response({"id": 99})

        result = client.rescan_movie(42)

        assert result is True
        call_kwargs = mock_session.post.call_args[1]
        assert call_kwargs["json"]["name"] == "RescanMovie"
        assert call_kwargs["json"]["movieId"] == 42

    def test_failure(self, client, mock_session):
        mock_session.post.side_effect = requests.ConnectionError("refused")

        with patch("radarr_client.time.sleep"):
            result = client.rescan_movie(42)

        assert result is False


# ─── get_movie_metadata ────────────────────────────────────────────────────────


class TestGetMovieMetadata:
    def test_returns_metadata(self, client, mock_session):
        movie = {
            "id": 1,
            "title": "Spirited Away",
            "year": 2001,
            "imdbId": "tt0245429",
            "tmdbId": 129,
            "genres": ["Animation", "Fantasy"],
        }
        mock_session.get.return_value = _ok_response(movie)

        result = client.get_movie_metadata(1)

        assert result == {
            "title": "Spirited Away",
            "year": 2001,
            "imdb_id": "tt0245429",
            "tmdb_id": 129,
            "genres": ["Animation", "Fantasy"],
        }

    def test_returns_none_when_movie_not_found(self, client, mock_session):
        mock_session.get.return_value = _error_response(404)

        result = client.get_movie_metadata(999)

        assert result is None

    def test_handles_missing_fields_with_defaults(self, client, mock_session):
        movie = {"id": 1}  # minimal movie — no title, year, etc.
        mock_session.get.return_value = _ok_response(movie)

        result = client.get_movie_metadata(1)

        assert result["title"] == ""
        assert result["year"] is None
        assert result["imdb_id"] == ""
        assert result["tmdb_id"] is None
        assert result["genres"] == []


# ─── extended_health_check ─────────────────────────────────────────────────────


class TestExtendedHealthCheck:
    def test_full_healthy_report(self, client, mock_session):
        status = {"version": "4.0.0", "branch": "main", "appName": "Radarr"}
        movies = [{"id": 1}, {"id": 2}]
        notifications = [
            {"name": "Sublarr Webhook", "implementation": "Webhook"},
            {"name": "Email", "implementation": "Email"},
        ]
        health = [{"type": "warning", "message": "disk space low"}]

        mock_session.get.side_effect = [
            _ok_response(status),         # /system/status
            _ok_response(movies),          # /movie
            _ok_response(notifications),   # /notification
            _ok_response(health),          # /health
        ]

        report = client.extended_health_check()

        assert report["connection"]["healthy"] is True
        assert report["connection"]["message"] == "OK"
        assert report["api_version"]["version"] == "4.0.0"
        assert report["api_version"]["branch"] == "main"
        assert report["api_version"]["app_name"] == "Radarr"
        assert report["library_access"]["accessible"] is True
        assert report["library_access"]["movie_count"] == 2
        assert report["webhook_status"]["configured"] is True
        assert len(report["webhook_status"]["sublarr_webhooks"]) == 1
        assert report["webhook_status"]["sublarr_webhooks"][0]["name"] == "Sublarr Webhook"
        assert len(report["health_issues"]) == 1
        assert report["health_issues"][0]["message"] == "disk space low"

    def test_connection_failure_returns_early(self, client, mock_session):
        mock_session.get.return_value = _error_response(500)

        report = client.extended_health_check()

        assert report["connection"]["healthy"] is False
        assert "radarr.local" in report["connection"]["message"]
        # Library/webhook/health should remain at defaults
        assert report["library_access"]["accessible"] is False
        assert report["webhook_status"]["configured"] is False

    def test_partial_failures_degrade_gracefully(self, client, mock_session):
        status = {"version": "4.0.0", "branch": "main", "appName": "Radarr"}
        mock_session.get.side_effect = [
            _ok_response(status),   # /system/status — OK
            _error_response(500),   # /movie — fail (returns None from _get)
            _error_response(500),   # /notification — fail
            _error_response(500),   # /health — fail
        ]

        report = client.extended_health_check()

        assert report["connection"]["healthy"] is True
        # Failures result in default values, not exceptions
        assert report["library_access"]["accessible"] is False
        assert report["webhook_status"]["configured"] is False
        assert report["health_issues"] == []

    def test_sublarr_webhook_detected_by_implementation(self, client, mock_session):
        status = {"version": "4.0.0"}
        notifications = [
            {"name": "My Hook", "implementation": "sublarr-notifier"},
        ]
        mock_session.get.side_effect = [
            _ok_response(status),
            _ok_response([]),            # /movie
            _ok_response(notifications),  # /notification
            _ok_response([]),            # /health
        ]

        report = client.extended_health_check()

        assert len(report["webhook_status"]["sublarr_webhooks"]) == 1


# ─── get_library_info ──────────────────────────────────────────────────────────


class TestGetLibraryInfo:
    def test_anime_only_default(self, client, mock_session):
        tags = [{"id": 1, "label": "anime"}]
        movies = [
            {
                "id": 10,
                "title": "Anime Movie",
                "year": 2023,
                "hasFile": True,
                "path": "/movies/anime",
                "tags": [1],
                "genres": [],
                "images": [{"coverType": "poster", "remoteUrl": "http://img/poster.jpg"}],
                "status": "released",
            },
        ]
        mock_session.get.side_effect = [
            _ok_response(tags),    # get_tags (via get_anime_movies)
            _ok_response(movies),  # get_movies (via get_anime_movies)
        ]

        result = client.get_library_info(anime_only=True)

        assert len(result) == 1
        entry = result[0]
        assert entry["id"] == 10
        assert entry["title"] == "Anime Movie"
        assert entry["has_file"] is True
        assert entry["poster"] == "http://img/poster.jpg"
        assert entry["status"] == "released"

    def test_all_movies(self, client, mock_session):
        movies = [
            {"id": 1, "title": "M1", "year": 2020, "hasFile": False, "path": "/m1",
             "tags": [], "genres": [], "images": [], "status": "announced"},
            {"id": 2, "title": "M2", "year": 2021, "hasFile": True, "path": "/m2",
             "tags": [], "genres": [], "images": [], "status": "released"},
        ]
        mock_session.get.return_value = _ok_response(movies)

        result = client.get_library_info(anime_only=False)

        assert len(result) == 2

    def test_poster_fallback_empty_string(self, client, mock_session):
        movies = [
            {"id": 1, "title": "No Poster", "tags": [], "genres": ["Anime"],
             "images": [{"coverType": "fanart", "remoteUrl": "http://img/fan.jpg"}]},
        ]
        mock_session.get.side_effect = [
            _ok_response([]),       # get_tags
            _ok_response(movies),   # get_movies
        ]

        result = client.get_library_info(anime_only=True)

        assert result[0]["poster"] == ""


# ─── get_radarr_client factory ─────────────────────────────────────────────────


class TestGetRadarrClientFactory:
    @patch("radarr_client.get_settings")
    @patch("config.get_radarr_instances", return_value=[])
    def test_legacy_config(self, mock_instances, mock_settings):
        settings = MagicMock()
        settings.radarr_url = "http://radarr.local:7878"
        settings.radarr_api_key = "legacy-key"
        mock_settings.return_value = settings

        result = get_radarr_client()

        assert result is not None
        assert result.url == "http://radarr.local:7878"
        assert result.api_key == "legacy-key"

    @patch("radarr_client.get_settings")
    @patch("config.get_radarr_instances", return_value=[])
    def test_returns_none_when_not_configured(self, mock_instances, mock_settings):
        settings = MagicMock()
        settings.radarr_url = ""
        settings.radarr_api_key = ""
        mock_settings.return_value = settings

        result = get_radarr_client()

        assert result is None

    @patch("config.get_radarr_instances")
    def test_uses_first_instance(self, mock_instances):
        mock_instances.return_value = [
            {"name": "Main", "url": "http://radarr1:7878", "api_key": "key1"},
            {"name": "Backup", "url": "http://radarr2:7878", "api_key": "key2"},
        ]

        result = get_radarr_client()

        assert result is not None
        assert result.url == "http://radarr1:7878"

    @patch("config.get_radarr_instances")
    def test_named_instance(self, mock_instances):
        mock_instances.return_value = [
            {"name": "Main", "url": "http://radarr1:7878", "api_key": "key1"},
            {"name": "4K", "url": "http://radarr-4k:7878", "api_key": "key-4k"},
        ]

        result = get_radarr_client(instance_name="4K")

        assert result is not None
        assert result.url == "http://radarr-4k:7878"

    @patch("config.get_radarr_instances")
    def test_named_instance_cached(self, mock_instances):
        mock_instances.return_value = [
            {"name": "Main", "url": "http://radarr1:7878", "api_key": "key1"},
        ]

        first = get_radarr_client(instance_name="Main")
        second = get_radarr_client(instance_name="Main")

        assert first is second

    @patch("config.get_radarr_instances")
    def test_named_instance_not_found_falls_back(self, mock_instances):
        mock_instances.return_value = [
            {"name": "Main", "url": "http://radarr1:7878", "api_key": "key1"},
        ]

        result = get_radarr_client(instance_name="NonExistent")

        assert result is not None
        assert result.url == "http://radarr1:7878"

    @patch("config.get_radarr_instances", return_value=[])
    def test_named_instance_no_instances_returns_none(self, mock_instances):
        result = get_radarr_client(instance_name="NonExistent")

        assert result is None

    @patch("config.get_radarr_instances")
    def test_singleton_cached(self, mock_instances):
        mock_instances.return_value = [
            {"name": "Main", "url": "http://radarr1:7878", "api_key": "key1"},
        ]

        first = get_radarr_client()
        second = get_radarr_client()

        assert first is second


# ─── invalidate_client ─────────────────────────────────────────────────────────


class TestInvalidateClient:
    @patch("config.get_radarr_instances")
    def test_clears_caches(self, mock_instances):
        mock_instances.return_value = [
            {"name": "Main", "url": "http://radarr1:7878", "api_key": "key1"},
        ]

        first = get_radarr_client()
        invalidate_client()
        second = get_radarr_client()

        # After invalidation, a new instance should be created
        assert first is not second
