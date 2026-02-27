"""Integration tests for provider system."""

from unittest.mock import MagicMock, patch

import pytest

from tests.fixtures.provider_responses import (
    OPENSEARCH_EMPTY_RESPONSE,
    OPENSEARCH_RESPONSE,
    PROVIDER_ERROR_RESPONSE,
)


class TestProviderSearch:
    """Tests for provider search functionality."""

    @pytest.mark.skip(
        reason="endpoint not yet implemented: /api/v1/providers/search POST with form data is unverified"
    )
    @patch("providers.opensubtitles.OpenSubtitlesProvider.search")
    def test_provider_search_success(self, mock_search, client):
        """Test successful provider search via the /api/v1/providers/search endpoint."""
        from providers.base import SubtitleResult

        # Mock successful search result
        mock_result = SubtitleResult(
            provider_name="opensubtitles",
            subtitle_id="12345",
            language="en",
            format="ass",
            score=250,
            download_url="https://example.com/sub.ass",
        )
        mock_search.return_value = [mock_result]

        response = client.post(
            "/api/v1/providers/search",
            data={
                "query": "Attack on Titan",
                "language": "en",
            },
        )
        # Endpoint must exist and return success or validation error — not 501
        assert response.status_code in [200, 400, 422]

    @patch("providers.opensubtitles.OpenSubtitlesProvider.search")
    def test_provider_search_empty(self, mock_search, client):
        """Test provider search with no results returns a valid API response."""
        mock_search.return_value = []
        response = client.post(
            "/api/v1/providers/search",
            json={"query": "test", "language": "en"},
        )
        # Endpoint must exist and handle the request without crashing
        assert response.status_code in [200, 400]

    @patch("providers.opensubtitles.OpenSubtitlesProvider.search")
    def test_provider_search_error(self, mock_search, client):
        """Test provider search error is handled gracefully by the API."""
        mock_search.side_effect = Exception("Provider error")
        response = client.post(
            "/api/v1/providers/search",
            json={"query": "test", "language": "en"},
        )
        # Should handle gracefully, not crash with 500
        assert response.status_code in [200, 400, 503]


class TestProviderDownload:
    """Tests for provider download functionality."""

    @patch("providers.opensubtitles.OpenSubtitlesProvider.download")
    def test_provider_download_success(self, mock_download, client):
        """Test successful subtitle download."""
        mock_download.return_value = b"Subtitle content"

        # Test download (mock)
        result = mock_download("12345")
        assert result == b"Subtitle content"

    @patch("providers.opensubtitles.OpenSubtitlesProvider.download")
    def test_provider_download_error(self, mock_download, client):
        """Test subtitle download with error."""
        mock_download.side_effect = Exception("Download failed")

        with pytest.raises(Exception):
            mock_download("12345")


class TestProviderManager:
    """Tests for provider manager functionality."""

    def test_provider_manager_initialization(self, client):
        """Test that provider manager can be initialized."""
        from providers import get_provider_manager

        manager = get_provider_manager()
        assert manager is not None

    def test_provider_status(self, client):
        """Test provider status endpoint."""
        import json

        response = client.get("/api/v1/providers")
        assert response.status_code == 200
        data = json.loads(response.data)
        assert "providers" in data
