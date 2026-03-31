"""Integration tests for webhook endpoints."""

import json
import os
from unittest.mock import MagicMock, patch

import pytest

from tests.fixtures.test_data import RADARR_WEBHOOK_PAYLOAD, SONARR_WEBHOOK_PAYLOAD

_TEST_API_KEY = "integration-test-webhook-key"
_AUTH_HEADERS = {"X-Api-Key": _TEST_API_KEY, "Content-Type": "application/json"}


def _make_settings_mock(extra=None):
    """Return a settings mock with api_key set to the test key."""
    s = MagicMock()
    s.api_key = _TEST_API_KEY
    s.media_path = os.environ.get("SUBLARR_MEDIA_PATH", "/tmp")
    s.webhook_delay_minutes = 0
    s.webhook_auto_scan = False
    s.webhook_auto_search = False
    s.webhook_auto_translate = False
    s.allowed_ip_ranges = ""
    if extra:
        for k, v in extra.items():
            setattr(s, k, v)
    return s


class TestSonarrWebhooks:
    """Tests for Sonarr webhook integration."""

    def test_sonarr_download_webhook(self, client):
        """Test Sonarr download webhook — valid key must be accepted."""
        payload = SONARR_WEBHOOK_PAYLOAD.copy()
        with (
            patch("config.get_settings", return_value=_make_settings_mock()),
            patch("security_utils.is_safe_path", return_value=True),
        ):
            response = client.post(
                "/api/v1/webhook/sonarr",
                data=json.dumps(payload),
                content_type="application/json",
                headers={"X-Api-Key": _TEST_API_KEY},
            )
        # Webhook may process asynchronously
        assert response.status_code in [200, 202, 204]

    def test_sonarr_webhook_invalid_payload(self, client):
        """Test Sonarr webhook with invalid payload — handled gracefully."""
        with patch("config.get_settings", return_value=_make_settings_mock()):
            response = client.post(
                "/api/v1/webhook/sonarr",
                data=json.dumps({"invalid": "data"}),
                content_type="application/json",
                headers={"X-Api-Key": _TEST_API_KEY},
            )
        # Should handle gracefully
        assert response.status_code in [200, 400, 422]

    def test_sonarr_webhook_no_key_rejected(self, client):
        """Sonarr webhook must reject requests without an API key."""
        with patch("config.get_settings", return_value=_make_settings_mock()):
            response = client.post(
                "/api/v1/webhook/sonarr",
                data=json.dumps(SONARR_WEBHOOK_PAYLOAD.copy()),
                content_type="application/json",
            )
        assert response.status_code == 401

    def test_sonarr_webhook_unconfigured_key_rejected(self, client):
        """Sonarr webhook must reject when no API key is configured."""
        s = _make_settings_mock()
        s.api_key = ""
        with patch("config.get_settings", return_value=s):
            response = client.post(
                "/api/v1/webhook/sonarr",
                data=json.dumps(SONARR_WEBHOOK_PAYLOAD.copy()),
                content_type="application/json",
                headers={"X-Api-Key": "anything"},
            )
        assert response.status_code == 401


class TestRadarrWebhooks:
    """Tests for Radarr webhook integration."""

    def test_radarr_download_webhook(self, client):
        """Test Radarr download webhook — valid key must be accepted."""
        payload = RADARR_WEBHOOK_PAYLOAD.copy()
        with (
            patch("config.get_settings", return_value=_make_settings_mock()),
            patch("security_utils.is_safe_path", return_value=True),
        ):
            response = client.post(
                "/api/v1/webhook/radarr",
                data=json.dumps(payload),
                content_type="application/json",
                headers={"X-Api-Key": _TEST_API_KEY},
            )
        # Webhook may process asynchronously
        assert response.status_code in [200, 202, 204]

    def test_radarr_webhook_invalid_payload(self, client):
        """Test Radarr webhook with invalid payload — handled gracefully."""
        with patch("config.get_settings", return_value=_make_settings_mock()):
            response = client.post(
                "/api/v1/webhook/radarr",
                data=json.dumps({"invalid": "data"}),
                content_type="application/json",
                headers={"X-Api-Key": _TEST_API_KEY},
            )
        # Should handle gracefully
        assert response.status_code in [200, 400, 422]

    def test_radarr_webhook_no_key_rejected(self, client):
        """Radarr webhook must reject requests without an API key."""
        with patch("config.get_settings", return_value=_make_settings_mock()):
            response = client.post(
                "/api/v1/webhook/radarr",
                data=json.dumps(RADARR_WEBHOOK_PAYLOAD.copy()),
                content_type="application/json",
            )
        assert response.status_code == 401

    def test_radarr_webhook_unconfigured_key_rejected(self, client):
        """Radarr webhook must reject when no API key is configured."""
        s = _make_settings_mock()
        s.api_key = ""
        with patch("config.get_settings", return_value=s):
            response = client.post(
                "/api/v1/webhook/radarr",
                data=json.dumps(RADARR_WEBHOOK_PAYLOAD.copy()),
                content_type="application/json",
                headers={"X-Api-Key": "anything"},
            )
        assert response.status_code == 401
