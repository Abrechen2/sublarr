"""Integration tests for webhook endpoints."""

import pytest
import json
from tests.fixtures.test_data import SONARR_WEBHOOK_PAYLOAD, RADARR_WEBHOOK_PAYLOAD


class TestSonarrWebhooks:
    """Tests for Sonarr webhook integration."""

    def test_sonarr_download_webhook(self, client):
        """Test Sonarr download webhook."""
        payload = SONARR_WEBHOOK_PAYLOAD.copy()
        response = client.post(
            "/api/v1/webhook/sonarr",
            data=json.dumps(payload),
            content_type="application/json",
        )
        # Webhook may process asynchronously
        assert response.status_code in [200, 202, 204]

    def test_sonarr_webhook_invalid_payload(self, client):
        """Test Sonarr webhook with invalid payload."""
        response = client.post(
            "/api/v1/webhook/sonarr",
            data=json.dumps({"invalid": "data"}),
            content_type="application/json",
        )
        # Should handle gracefully
        assert response.status_code in [200, 400, 422]


class TestRadarrWebhooks:
    """Tests for Radarr webhook integration."""

    def test_radarr_download_webhook(self, client):
        """Test Radarr download webhook."""
        payload = RADARR_WEBHOOK_PAYLOAD.copy()
        response = client.post(
            "/api/v1/webhook/radarr",
            data=json.dumps(payload),
            content_type="application/json",
        )
        # Webhook may process asynchronously
        assert response.status_code in [200, 202, 204]

    def test_radarr_webhook_invalid_payload(self, client):
        """Test Radarr webhook with invalid payload."""
        response = client.post(
            "/api/v1/webhook/radarr",
            data=json.dumps({"invalid": "data"}),
            content_type="application/json",
        )
        # Should handle gracefully
        assert response.status_code in [200, 400, 422]
