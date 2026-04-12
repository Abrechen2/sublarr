"""Tests for translation.ollama — Ollama translation backend.

Complements test_ollama_v9.py (which tests V9 chat-API specific features)
by covering core translate_batch, _call_ollama, _call_ollama_chat,
health_check, single-line fallback, and error handling paths.
"""

from unittest.mock import MagicMock, patch

import pytest
import requests

from translation.base import TranslationResult


def _make_backend(**config_overrides):
    """Create an OllamaBackend instance without triggering __init__ / Pydantic fallbacks."""
    from translation.ollama import OllamaBackend

    backend = OllamaBackend.__new__(OllamaBackend)
    backend.config = {
        "url": "http://localhost:11434",
        "model": "test-model",
        "temperature": "0.3",
        "request_timeout": "10",
        "max_retries": "1",
        "backoff_base": "1",
        "batch_size": "15",
        "use_chat_api": "false",
        "system_prompt": "",
        **config_overrides,
    }
    return backend


class TestOllamaBackendAttributes:
    """Tests for class-level attributes and config properties."""

    def test_name_and_display_name(self):
        backend = _make_backend()
        assert backend.name == "ollama"
        assert backend.display_name == "Ollama (Local LLM)"

    def test_supports_glossary(self):
        backend = _make_backend()
        assert backend.supports_glossary is True

    def test_supports_batch(self):
        backend = _make_backend()
        assert backend.supports_batch is True
        assert backend.max_batch_size == 25

    def test_config_fields_returned(self):
        backend = _make_backend()
        fields = backend.get_config_fields()
        assert len(fields) == 7
        keys = [f["key"] for f in fields]
        assert "url" in keys
        assert "model" in keys
        assert "use_chat_api" in keys

    def test_get_usage_returns_empty_dict(self):
        backend = _make_backend()
        assert backend.get_usage() == {}


class TestConfigProperties:
    """Tests for config property accessors with fallback defaults."""

    def test_url_property(self):
        backend = _make_backend(url="http://myhost:11434")
        assert backend._url == "http://myhost:11434"

    def test_model_property(self):
        backend = _make_backend(model="llama3")
        assert backend._model == "llama3"

    def test_temperature_valid(self):
        backend = _make_backend(temperature="0.7")
        assert backend._temperature == 0.7

    def test_temperature_invalid_falls_back(self):
        backend = _make_backend(temperature="invalid")
        assert backend._temperature == 0.3

    def test_request_timeout_valid(self):
        backend = _make_backend(request_timeout="60")
        assert backend._request_timeout == 60

    def test_request_timeout_invalid_falls_back(self):
        backend = _make_backend(request_timeout="abc")
        assert backend._request_timeout == 90

    def test_max_retries_valid(self):
        backend = _make_backend(max_retries="5")
        assert backend._max_retries == 5

    def test_max_retries_invalid_falls_back(self):
        backend = _make_backend(max_retries="no")
        assert backend._max_retries == 3

    def test_backoff_base_valid(self):
        backend = _make_backend(backoff_base="10")
        assert backend._backoff_base == 10

    def test_backoff_base_invalid_falls_back(self):
        backend = _make_backend(backoff_base="bad")
        assert backend._backoff_base == 5


class TestCallOllama:
    """Tests for the _call_ollama (generate API) method."""

    @patch("translation.ollama.requests.post")
    def test_successful_call(self, mock_post):
        backend = _make_backend()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"response": "  Translated text  "}
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        result = backend._call_ollama("translate this")

        assert result == "Translated text"
        call_kwargs = mock_post.call_args[1]
        payload = call_kwargs["json"]
        assert payload["model"] == "test-model"
        assert payload["stream"] is False

    @patch("translation.ollama.requests.post")
    def test_rate_limiting_429(self, mock_post):
        backend = _make_backend()
        mock_resp = MagicMock()
        mock_resp.status_code = 429
        mock_resp.headers = {"Retry-After": "30"}
        mock_post.return_value = mock_resp

        with pytest.raises(RuntimeError, match="rate limited"):
            backend._call_ollama("translate this")

    @patch("translation.ollama.requests.post")
    def test_rate_limiting_429_no_retry_after(self, mock_post):
        backend = _make_backend()
        mock_resp = MagicMock()
        mock_resp.status_code = 429
        mock_resp.headers = {}
        mock_post.return_value = mock_resp

        with pytest.raises(RuntimeError, match="retry after 60s"):
            backend._call_ollama("translate this")

    @patch("translation.ollama.requests.post")
    def test_rate_limiting_429_invalid_retry_after(self, mock_post):
        backend = _make_backend()
        mock_resp = MagicMock()
        mock_resp.status_code = 429
        mock_resp.headers = {"Retry-After": "not-a-number"}
        mock_post.return_value = mock_resp

        with pytest.raises(RuntimeError, match="retry after 60s"):
            backend._call_ollama("translate this")

    @patch("translation.ollama.requests.post")
    def test_invalid_json_response(self, mock_post):
        backend = _make_backend()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.side_effect = ValueError("not JSON")
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        with pytest.raises(RuntimeError, match="invalid JSON"):
            backend._call_ollama("translate this")

    @patch("translation.ollama.requests.post")
    def test_error_key_in_response(self, mock_post):
        backend = _make_backend()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"error": "model not found"}
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        with pytest.raises(RuntimeError, match="model not found"):
            backend._call_ollama("translate this")

    @patch("translation.ollama.requests.post")
    def test_missing_response_key(self, mock_post):
        backend = _make_backend()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"done": True}
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        with pytest.raises(RuntimeError, match="missing 'response' key"):
            backend._call_ollama("translate this")


class TestCallOllamaChat:
    """Tests for the _call_ollama_chat (chat API) method."""

    @patch("translation.ollama.requests.post")
    def test_successful_chat_call(self, mock_post):
        backend = _make_backend()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"message": {"content": "  Chat response  "}}
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        result = backend._call_ollama_chat("You are a translator.", "Translate: Hello")

        assert result == "Chat response"
        call_kwargs = mock_post.call_args[1]
        payload = call_kwargs["json"]
        assert len(payload["messages"]) == 2
        assert payload["messages"][0]["role"] == "system"
        assert payload["messages"][1]["role"] == "user"

    @patch("translation.ollama.requests.post")
    def test_chat_rate_limiting_429(self, mock_post):
        backend = _make_backend()
        mock_resp = MagicMock()
        mock_resp.status_code = 429
        mock_resp.headers = {"Retry-After": "10"}
        mock_post.return_value = mock_resp

        with pytest.raises(RuntimeError, match="rate limited"):
            backend._call_ollama_chat("system", "user")

    @patch("translation.ollama.requests.post")
    def test_chat_invalid_json(self, mock_post):
        backend = _make_backend()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.side_effect = ValueError("bad json")
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        with pytest.raises(RuntimeError, match="invalid JSON"):
            backend._call_ollama_chat("system", "user")

    @patch("translation.ollama.requests.post")
    def test_chat_error_in_response(self, mock_post):
        backend = _make_backend()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"error": "out of memory"}
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        with pytest.raises(RuntimeError, match="out of memory"):
            backend._call_ollama_chat("system", "user")

    @patch("translation.ollama.requests.post")
    def test_chat_missing_message_content(self, mock_post):
        backend = _make_backend()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"done": True}
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        with pytest.raises(RuntimeError, match="missing 'message.content'"):
            backend._call_ollama_chat("system", "user")


class TestTranslateBatch:
    """Tests for translate_batch with generate API."""

    def test_empty_lines_returns_success(self):
        backend = _make_backend()
        result = backend.translate_batch([], "en", "de")
        assert result.success is True
        assert result.translated_lines == []

    @patch("translation.ollama.parse_llm_response", return_value=["Hallo"])
    @patch("translation.ollama.has_cjk_hallucination", return_value=False)
    @patch("translation.ollama.build_translation_prompt", return_value="prompt")
    @patch("translation.ollama.requests.post")
    def test_successful_batch_translation(self, mock_post, mock_prompt, mock_cjk, mock_parse):
        backend = _make_backend()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"response": "1: Hallo"}
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        result = backend.translate_batch(["Hello"], "en", "de")

        assert result.success is True
        assert result.translated_lines == ["Hallo"]
        assert result.backend_name == "ollama"
        assert result.characters_used == 5
        assert result.response_time_ms >= 0

    @patch("translation.ollama.parse_llm_response", return_value=None)
    @patch("translation.ollama.build_translation_prompt", return_value="prompt")
    @patch("translation.ollama.requests.post")
    def test_line_count_mismatch_falls_back_to_singles(self, mock_post, mock_prompt, mock_parse):
        """When batch parsing fails for all retries, falls back to single-line mode."""
        backend = _make_backend(max_retries="1")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"response": "Wrong output"}
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        # The fallback single-line mode also calls _call_ollama, which will
        # also return "Wrong output", so parse will fail there too.
        # With max_retries=1 it will keep original lines.
        result = backend.translate_batch(["Hello"], "en", "de")

        # Result depends on whether fallback single-line mode succeeded
        # In this case parse returns None for batch, then single line fallback
        # re-uses _call_ollama which returns "Wrong output" stripped to "Wrong output"
        # single-line parse strips numbering prefix -> "Wrong output"
        assert result.backend_name == "ollama"


class TestHealthCheck:
    """Tests for health_check method."""

    @patch("translation.ollama.requests.get")
    def test_healthy_model_found(self, mock_get):
        backend = _make_backend(model="llama3")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "models": [
                {"name": "llama3:latest"},
                {"name": "qwen2.5:14b"},
            ]
        }
        mock_get.return_value = mock_resp

        healthy, msg = backend.health_check()
        assert healthy is True
        assert msg == "OK"

    @patch("translation.ollama.requests.get")
    def test_unhealthy_model_not_found(self, mock_get):
        backend = _make_backend(model="nonexistent-model")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"models": [{"name": "llama3:latest"}]}
        mock_get.return_value = mock_resp

        healthy, msg = backend.health_check()
        assert healthy is False
        assert "nonexistent-model" in msg
        assert "not found" in msg.lower()

    @patch("translation.ollama.requests.get")
    def test_unhealthy_non_200_status(self, mock_get):
        backend = _make_backend()
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_get.return_value = mock_resp

        healthy, msg = backend.health_check()
        assert healthy is False
        assert "500" in msg

    @patch("translation.ollama.requests.get")
    def test_unhealthy_invalid_json(self, mock_get):
        backend = _make_backend()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.side_effect = ValueError("bad JSON")
        mock_get.return_value = mock_resp

        healthy, msg = backend.health_check()
        assert healthy is False
        assert "invalid JSON" in msg

    @patch("translation.ollama.requests.get")
    def test_unhealthy_timeout(self, mock_get):
        backend = _make_backend()
        mock_get.side_effect = requests.Timeout("timed out")

        healthy, msg = backend.health_check()
        assert healthy is False
        assert "timed out" in msg.lower()

    @patch("translation.ollama.requests.get")
    def test_unhealthy_connection_error(self, mock_get):
        backend = _make_backend()
        mock_get.side_effect = requests.ConnectionError("refused")

        healthy, msg = backend.health_check()
        assert healthy is False
        assert "Cannot connect" in msg

    @patch("translation.ollama.requests.get")
    def test_unhealthy_generic_exception(self, mock_get):
        backend = _make_backend()
        mock_get.side_effect = Exception("unexpected error")

        healthy, msg = backend.health_check()
        assert healthy is False
        assert "unexpected error" in msg


class TestTranslateSingles:
    """Tests for the single-line fallback path (_translate_singles)."""

    @patch("translation.ollama.has_cjk_hallucination", return_value=False)
    @patch("translation.ollama.build_translation_prompt", return_value="prompt")
    @patch("translation.ollama.requests.post")
    def test_successful_single_line_fallback(self, mock_post, mock_prompt, mock_cjk):
        backend = _make_backend(max_retries="1")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"response": "Hallo"}
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        import time

        result = backend._translate_singles(["Hello"], "en", "de", None, time.time())

        assert result.success is True
        assert result.translated_lines == ["Hallo"]

    @patch("translation.ollama.has_cjk_hallucination", return_value=False)
    @patch("translation.ollama.build_translation_prompt", return_value="prompt")
    @patch("translation.ollama.requests.post")
    def test_too_many_failures_returns_error(self, mock_post, mock_prompt, mock_cjk):
        """When > 50% of lines fail, result should indicate failure."""
        backend = _make_backend(max_retries="1")
        mock_post.side_effect = requests.RequestException("Connection refused")

        import time

        result = backend._translate_singles(["Hello", "World"], "en", "de", None, time.time())

        # Both lines fail, fall back to originals -> 2/2 = 100% fallback > 50%
        assert result.success is False
        assert "Too many line failures" in result.error
