"""Tests for translation.libretranslate — LibreTranslate translation backend."""

from unittest.mock import MagicMock, patch

import pytest
import requests

from translation.base import TranslationResult


def _make_backend(**config_overrides):
    """Create a LibreTranslateBackend instance without __init__ side effects."""
    from translation.libretranslate import LibreTranslateBackend

    backend = LibreTranslateBackend.__new__(LibreTranslateBackend)
    backend.config = {
        "url": "http://libretranslate:5000",
        "api_key": "",
        "request_timeout": "30",
        **config_overrides,
    }
    return backend


class TestLibreTranslateAttributes:
    """Tests for class-level attributes and config."""

    def test_name_and_display_name(self):
        backend = _make_backend()
        assert backend.name == "libretranslate"
        assert backend.display_name == "LibreTranslate (Self-Hosted)"

    def test_no_glossary_support(self):
        backend = _make_backend()
        assert backend.supports_glossary is False

    def test_no_batch_support(self):
        backend = _make_backend()
        assert backend.supports_batch is False
        assert backend.max_batch_size == 1

    def test_config_fields_returned(self):
        backend = _make_backend()
        fields = backend.get_config_fields()
        assert len(fields) == 3
        keys = [f["key"] for f in fields]
        assert "url" in keys
        assert "api_key" in keys
        assert "request_timeout" in keys

    def test_get_usage_returns_empty_dict(self):
        backend = _make_backend()
        assert backend.get_usage() == {}


class TestTranslateBatch:
    """Tests for translate_batch method (line-by-line translation)."""

    @patch("translation.libretranslate.requests.post")
    def test_single_line_translation(self, mock_post):
        backend = _make_backend()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"translatedText": "Hallo"}
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        result = backend.translate_batch(["Hello"], "en", "de")

        assert result.success is True
        assert result.translated_lines == ["Hallo"]
        assert result.backend_name == "libretranslate"
        assert result.characters_used == 5

    @patch("translation.libretranslate.requests.post")
    def test_multiple_lines_translated_individually(self, mock_post):
        backend = _make_backend()

        responses = []
        for text in ["Hallo", "Welt", "Test"]:
            resp = MagicMock()
            resp.json.return_value = {"translatedText": text}
            resp.raise_for_status = MagicMock()
            responses.append(resp)

        mock_post.side_effect = responses

        result = backend.translate_batch(["Hello", "World", "Test"], "en", "de")

        assert result.success is True
        assert result.translated_lines == ["Hallo", "Welt", "Test"]
        assert mock_post.call_count == 3
        assert result.characters_used == 14  # 5 + 5 + 4

    @patch("translation.libretranslate.requests.post")
    def test_api_key_included_in_payload(self, mock_post):
        backend = _make_backend(api_key="my-secret-key")
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"translatedText": "Hallo"}
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        backend.translate_batch(["Hello"], "en", "de")

        call_kwargs = mock_post.call_args[1]
        payload = call_kwargs["json"]
        assert payload["api_key"] == "my-secret-key"

    @patch("translation.libretranslate.requests.post")
    def test_no_api_key_not_in_payload(self, mock_post):
        backend = _make_backend(api_key="")
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"translatedText": "Hallo"}
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        backend.translate_batch(["Hello"], "en", "de")

        call_kwargs = mock_post.call_args[1]
        payload = call_kwargs["json"]
        assert "api_key" not in payload

    @patch("translation.libretranslate.requests.post")
    def test_correct_url_and_timeout(self, mock_post):
        backend = _make_backend(url="http://my-libre:9000/", request_timeout="60")
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"translatedText": "Hallo"}
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        backend.translate_batch(["Hello"], "en", "de")

        call_args = mock_post.call_args
        assert call_args[0][0] == "http://my-libre:9000/translate"
        assert call_args[1]["timeout"] == 60

    @patch("translation.libretranslate.requests.post")
    def test_trailing_slash_stripped_from_url(self, mock_post):
        backend = _make_backend(url="http://libre:5000/")
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"translatedText": "Hallo"}
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        backend.translate_batch(["Hello"], "en", "de")

        call_url = mock_post.call_args[0][0]
        assert call_url == "http://libre:5000/translate"

    @patch("translation.libretranslate.requests.post")
    def test_missing_translated_text_uses_original(self, mock_post):
        backend = _make_backend()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {}  # No "translatedText" key
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        result = backend.translate_batch(["Hello"], "en", "de")

        assert result.success is True
        assert result.translated_lines == ["Hello"]  # Falls back to original

    @patch("translation.libretranslate.requests.post")
    def test_http_error_returns_failure(self, mock_post):
        backend = _make_backend()
        mock_post.side_effect = requests.exceptions.HTTPError("500 Internal Server Error")

        result = backend.translate_batch(["Hello"], "en", "de")

        assert result.success is False
        assert result.translated_lines == []
        assert "500" in result.error

    @patch("translation.libretranslate.requests.post")
    def test_timeout_returns_failure(self, mock_post):
        backend = _make_backend()
        mock_post.side_effect = requests.exceptions.Timeout("Request timed out")

        result = backend.translate_batch(["Hello"], "en", "de")

        assert result.success is False
        assert result.translated_lines == []

    @patch("translation.libretranslate.requests.post")
    def test_connection_error_returns_failure(self, mock_post):
        backend = _make_backend()
        mock_post.side_effect = requests.exceptions.ConnectionError("Connection refused")

        result = backend.translate_batch(["Hello"], "en", "de")

        assert result.success is False
        assert "Connection refused" in result.error


class TestHealthCheck:
    """Tests for health_check method."""

    @patch("translation.libretranslate.requests.get")
    def test_healthy_with_language_count(self, mock_get):
        backend = _make_backend()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = [{"code": "en"}, {"code": "de"}, {"code": "fr"}]
        mock_get.return_value = mock_resp

        healthy, msg = backend.health_check()

        assert healthy is True
        assert "3 languages" in msg

    @patch("translation.libretranslate.requests.get")
    def test_unhealthy_on_non_200(self, mock_get):
        backend = _make_backend()
        mock_resp = MagicMock()
        mock_resp.status_code = 503
        mock_get.return_value = mock_resp

        healthy, msg = backend.health_check()

        assert healthy is False
        assert "HTTP 503" in msg

    @patch("translation.libretranslate.requests.get")
    def test_unhealthy_on_connection_error(self, mock_get):
        backend = _make_backend()
        mock_get.side_effect = requests.exceptions.ConnectionError("refused")

        healthy, msg = backend.health_check()

        assert healthy is False

    @patch("translation.libretranslate.requests.get")
    def test_health_check_url_constructed_correctly(self, mock_get):
        backend = _make_backend(url="http://my-libre:9000/")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = []
        mock_get.return_value = mock_resp

        backend.health_check()

        call_url = mock_get.call_args[0][0]
        assert call_url == "http://my-libre:9000/languages"
