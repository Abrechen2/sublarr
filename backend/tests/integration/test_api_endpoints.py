"""Integration tests for API endpoints."""

import pytest
import json
from tests.fixtures.test_data import (
    SAMPLE_VIDEO_QUERY,
    SAMPLE_SERIES,
    SAMPLE_EPISODE,
    SAMPLE_LANGUAGE_PROFILE,
)


class TestHealthEndpoints:
    """Tests for health and status endpoints."""

    def test_health_endpoint(self, client):
        """Test /api/v1/health endpoint."""
        response = client.get("/api/v1/health")
        assert response.status_code == 200
        data = json.loads(response.data)
        assert "status" in data
        assert data["status"] in ("ok", "healthy")

    def test_stats_endpoint(self, client):
        """Test /api/v1/stats endpoint."""
        response = client.get("/api/v1/stats")
        assert response.status_code == 200
        data = json.loads(response.data)
        assert "stats" in data


class TestWantedEndpoints:
    """Tests for wanted items endpoints."""

    def test_list_wanted(self, client):
        """Test GET /api/v1/wanted endpoint."""
        response = client.get("/api/v1/wanted")
        assert response.status_code == 200
        data = json.loads(response.data)
        assert "items" in data
        assert "total" in data
        assert isinstance(data["items"], list)

    def test_wanted_summary(self, client):
        """Test GET /api/v1/wanted/summary endpoint."""
        response = client.get("/api/v1/wanted/summary")
        assert response.status_code == 200
        data = json.loads(response.data)
        assert "total" in data
        assert "by_status" in data

    def test_refresh_wanted(self, client):
        """Test POST /api/v1/wanted/refresh endpoint."""
        response = client.post("/api/v1/wanted/refresh")
        assert response.status_code in [200, 202]  # Can be async
        data = json.loads(response.data)
        assert "status" in data or "message" in data


class TestProviderEndpoints:
    """Tests for provider endpoints."""

    def test_list_providers(self, client):
        """Test GET /api/v1/providers endpoint."""
        response = client.get("/api/v1/providers")
        assert response.status_code == 200
        data = json.loads(response.data)
        assert "providers" in data
        assert isinstance(data["providers"], list)

    def test_provider_cache_stats(self, client):
        """Test GET /api/v1/providers/cache/stats endpoint."""
        response = client.get("/api/v1/providers/cache/stats")
        assert response.status_code == 200
        data = json.loads(response.data)
        assert "stats" in data or isinstance(data, dict)


class TestLibraryEndpoints:
    """Tests for library endpoints."""

    def test_list_series(self, client):
        """Test GET /api/v1/library/series endpoint."""
        response = client.get("/api/v1/library/series")
        assert response.status_code == 200
        data = json.loads(response.data)
        assert "series" in data or "items" in data
        assert isinstance(data.get("series", data.get("items", [])), list)

    def test_list_movies(self, client):
        """Test GET /api/v1/library/movies endpoint."""
        response = client.get("/api/v1/library/movies")
        assert response.status_code == 200
        data = json.loads(response.data)
        assert "movies" in data or "items" in data
        assert isinstance(data.get("movies", data.get("items", [])), list)


class TestHistoryEndpoints:
    """Tests for history endpoints."""

    def test_list_history(self, client):
        """Test GET /api/v1/history endpoint."""
        response = client.get("/api/v1/history")
        assert response.status_code == 200
        data = json.loads(response.data)
        assert "history" in data or "items" in data
        assert isinstance(data.get("history", data.get("items", [])), list)

    def test_history_stats(self, client):
        """Test GET /api/v1/history/stats endpoint."""
        response = client.get("/api/v1/history/stats")
        assert response.status_code == 200
        data = json.loads(response.data)
        assert isinstance(data, dict)


class TestBlacklistEndpoints:
    """Tests for blacklist endpoints."""

    def test_list_blacklist(self, client):
        """Test GET /api/v1/blacklist endpoint."""
        response = client.get("/api/v1/blacklist")
        assert response.status_code == 200
        data = json.loads(response.data)
        assert "blacklist" in data or "items" in data
        assert isinstance(data.get("blacklist", data.get("items", [])), list)

    def test_blacklist_count(self, client):
        """Test GET /api/v1/blacklist/count endpoint."""
        response = client.get("/api/v1/blacklist/count")
        assert response.status_code == 200
        data = json.loads(response.data)
        assert "count" in data
        assert isinstance(data["count"], int)


class TestLanguageProfileEndpoints:
    """Tests for language profile endpoints."""

    def test_list_language_profiles(self, client):
        """Test GET /api/v1/language-profiles endpoint."""
        response = client.get("/api/v1/language-profiles")
        assert response.status_code == 200
        data = json.loads(response.data)
        assert "profiles" in data
        assert isinstance(data["profiles"], list)

    def test_create_language_profile(self, client):
        """Test POST /api/v1/language-profiles endpoint."""
        profile_data = {
            "name": "Test Profile",
            "languages": ["de"],
            "min_score": 200,
            "prefer_ass": True,
        }
        response = client.post(
            "/api/v1/language-profiles",
            data=json.dumps(profile_data),
            content_type="application/json",
        )
        assert response.status_code in [200, 201]
        data = json.loads(response.data)
        assert "id" in data or "profile" in data


class TestConfigEndpoints:
    """Tests for configuration endpoints."""

    def test_list_config(self, client):
        """Test GET /api/v1/config endpoint."""
        response = client.get("/api/v1/config")
        assert response.status_code == 200
        data = json.loads(response.data)
        assert isinstance(data, dict)

    def test_get_config_entry(self, client):
        """Test GET /api/v1/config/<key> endpoint."""
        # Test with a non-existent key (should return 404 or default)
        response = client.get("/api/v1/config/non_existent_key")
        assert response.status_code in [200, 404]
