"""Tests for translation.google_translate — Google Cloud Translation v3 backend."""

from unittest.mock import MagicMock, patch

import pytest

from translation.base import TranslationResult


def _make_backend(**config_overrides):
    """Create a GoogleTranslateBackend instance without __init__ side effects."""
    from translation.google_translate import GoogleTranslateBackend

    backend = GoogleTranslateBackend.__new__(GoogleTranslateBackend)
    backend.config = {
        "project_id": "test-project",
        "credentials_path": "",
        "location": "global",
        **config_overrides,
    }
    return backend


class TestGoogleBackendAttributes:
    """Tests for class-level attributes and config properties."""

    def test_name_and_display_name(self):
        backend = _make_backend()
        assert backend.name == "google"
        assert backend.display_name == "Google Cloud Translation"

    def test_supports_glossary(self):
        backend = _make_backend()
        assert backend.supports_glossary is True

    def test_supports_batch(self):
        backend = _make_backend()
        assert backend.supports_batch is True
        assert backend.max_batch_size == 1024

    def test_project_id_property(self):
        backend = _make_backend(project_id="my-proj")
        assert backend._project_id == "my-proj"

    def test_location_default(self):
        backend = _make_backend()
        assert backend._location == "global"

    def test_location_custom(self):
        backend = _make_backend(location="us-central1")
        assert backend._location == "us-central1"

    def test_parent_string(self):
        backend = _make_backend(project_id="proj-123", location="eu")
        assert backend._parent == "projects/proj-123/locations/eu"

    def test_config_fields_returned(self):
        backend = _make_backend()
        fields = backend.get_config_fields()
        assert len(fields) == 3
        keys = [f["key"] for f in fields]
        assert "project_id" in keys
        assert "credentials_path" in keys
        assert "location" in keys

    def test_get_usage_returns_empty_dict(self):
        backend = _make_backend()
        assert backend.get_usage() == {}


class TestCreateClient:
    """Tests for _create_client method."""

    @patch("translation.google_translate._HAS_GOOGLE", False)
    def test_raises_when_package_not_installed(self):
        backend = _make_backend()
        with pytest.raises(RuntimeError, match="google-cloud-translate package not installed"):
            backend._create_client()

    @patch("translation.google_translate._HAS_GOOGLE", True)
    @patch("translation.google_translate.translate_v3")
    def test_creates_client_successfully(self, mock_translate_v3):
        backend = _make_backend()
        mock_translate_v3.TranslationServiceClient.return_value = MagicMock()
        client = backend._create_client()
        mock_translate_v3.TranslationServiceClient.assert_called_once()
        assert client is not None

    @patch("translation.google_translate._HAS_GOOGLE", True)
    @patch("translation.google_translate.translate_v3")
    def test_sets_credentials_env_var(self, mock_translate_v3, monkeypatch):
        backend = _make_backend(credentials_path="/path/to/creds.json")
        mock_translate_v3.TranslationServiceClient.return_value = MagicMock()

        # Clean up env after test
        monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)

        backend._create_client()
        import os

        assert os.environ.get("GOOGLE_APPLICATION_CREDENTIALS") == "/path/to/creds.json"


class TestTranslateBatch:
    """Tests for translate_batch method."""

    def test_empty_lines_returns_success(self):
        backend = _make_backend()
        result = backend.translate_batch([], "en", "de")
        assert result.success is True
        assert result.translated_lines == []

    @patch("translation.google_translate._HAS_GOOGLE", False)
    def test_returns_failure_when_package_missing(self):
        backend = _make_backend()
        result = backend.translate_batch(["Hello"], "en", "de")
        assert result.success is False
        assert "google-cloud-translate" in result.error

    @patch("translation.google_translate._HAS_GOOGLE", True)
    @patch("translation.google_translate.translate_v3")
    def test_successful_translation(self, mock_translate_v3):
        backend = _make_backend()
        mock_client = MagicMock()
        mock_translate_v3.TranslationServiceClient.return_value = mock_client

        mock_translation = MagicMock()
        mock_translation.translated_text = "Hallo"
        mock_response = MagicMock()
        mock_response.translations = [mock_translation]
        mock_client.translate_text.return_value = mock_response

        result = backend.translate_batch(["Hello"], "en", "de")

        assert result.success is True
        assert result.translated_lines == ["Hallo"]
        assert result.backend_name == "google"
        assert result.characters_used == 5
        assert result.response_time_ms >= 0

    @patch("translation.google_translate._HAS_GOOGLE", True)
    @patch("translation.google_translate.translate_v3")
    def test_multiple_lines(self, mock_translate_v3):
        backend = _make_backend()
        mock_client = MagicMock()
        mock_translate_v3.TranslationServiceClient.return_value = mock_client

        t1, t2 = MagicMock(), MagicMock()
        t1.translated_text = "Hallo"
        t2.translated_text = "Welt"
        mock_response = MagicMock()
        mock_response.translations = [t1, t2]
        mock_client.translate_text.return_value = mock_response

        result = backend.translate_batch(["Hello", "World"], "en", "de")

        assert result.translated_lines == ["Hallo", "Welt"]
        assert result.characters_used == 10

    @patch("translation.google_translate._HAS_GOOGLE", True)
    @patch("translation.google_translate.translate_v3")
    def test_api_error_returns_failure(self, mock_translate_v3):
        backend = _make_backend()
        mock_client = MagicMock()
        mock_translate_v3.TranslationServiceClient.return_value = mock_client
        mock_client.translate_text.side_effect = Exception("Permission denied")

        result = backend.translate_batch(["Hello"], "en", "de")

        assert result.success is False
        assert result.translated_lines == []
        assert "Permission denied" in result.error
        assert result.response_time_ms >= 0

    @patch("translation.google_translate._HAS_GOOGLE", True)
    @patch("translation.google_translate.translate_v3")
    def test_translate_request_params(self, mock_translate_v3):
        backend = _make_backend(project_id="proj-x", location="europe")
        mock_client = MagicMock()
        mock_translate_v3.TranslationServiceClient.return_value = mock_client

        mock_response = MagicMock()
        mock_response.translations = [MagicMock(translated_text="Hallo")]
        mock_client.translate_text.return_value = mock_response

        backend.translate_batch(["Hello"], "en", "de")

        call_kwargs = mock_client.translate_text.call_args[1]
        request = call_kwargs["request"]
        assert request["parent"] == "projects/proj-x/locations/europe"
        assert request["source_language_code"] == "en"
        assert request["target_language_code"] == "de"
        assert request["contents"] == ["Hello"]
        assert request["mime_type"] == "text/plain"


class TestHealthCheck:
    """Tests for health_check method."""

    @patch("translation.google_translate._HAS_GOOGLE", False)
    def test_unhealthy_when_package_missing(self):
        backend = _make_backend()
        healthy, msg = backend.health_check()
        assert healthy is False
        assert "google-cloud-translate" in msg

    @patch("translation.google_translate._HAS_GOOGLE", True)
    @patch("translation.google_translate.translate_v3")
    def test_healthy_with_language_count(self, mock_translate_v3):
        backend = _make_backend()
        mock_client = MagicMock()
        mock_translate_v3.TranslationServiceClient.return_value = mock_client

        mock_response = MagicMock()
        mock_response.languages = [MagicMock()] * 120
        mock_client.get_supported_languages.return_value = mock_response

        healthy, msg = backend.health_check()
        assert healthy is True
        assert "120 languages" in msg

    @patch("translation.google_translate._HAS_GOOGLE", True)
    @patch("translation.google_translate.translate_v3")
    def test_unhealthy_on_credentials_error(self, mock_translate_v3):
        backend = _make_backend()
        mock_client = MagicMock()
        mock_translate_v3.TranslationServiceClient.return_value = mock_client

        class FakeCredError(Exception):
            pass

        FakeCredError.__name__ = "DefaultCredentialsError"
        mock_client.get_supported_languages.side_effect = FakeCredError("no credentials")

        healthy, msg = backend.health_check()
        assert healthy is False
        assert "Credentials error" in msg

    @patch("translation.google_translate._HAS_GOOGLE", True)
    @patch("translation.google_translate.translate_v3")
    def test_unhealthy_on_generic_error(self, mock_translate_v3):
        backend = _make_backend()
        mock_client = MagicMock()
        mock_translate_v3.TranslationServiceClient.return_value = mock_client
        mock_client.get_supported_languages.side_effect = Exception("network failure")

        healthy, msg = backend.health_check()
        assert healthy is False
        assert "Health check failed" in msg
