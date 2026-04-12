"""Tests for translation.openai_compat — OpenAI-compatible translation backend."""

from unittest.mock import MagicMock, patch

import pytest

from translation.base import TranslationResult


def _make_backend(**config_overrides):
    """Create an OpenAICompatBackend instance without __init__ side effects."""
    from translation.openai_compat import OpenAICompatBackend

    backend = OpenAICompatBackend.__new__(OpenAICompatBackend)
    backend.config = {
        "api_key": "sk-test-key",
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-4o-mini",
        "temperature": "0.3",
        "request_timeout": "120",
        "max_retries": "1",  # Keep retries low for fast tests
        **config_overrides,
    }
    backend._client = None
    import threading

    backend._client_lock = threading.Lock()
    return backend


class TestOpenAICompatAttributes:
    """Tests for class-level attributes and config properties."""

    def test_name_and_display_name(self):
        backend = _make_backend()
        assert backend.name == "openai_compat"
        assert "OpenAI" in backend.display_name

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
        assert len(fields) == 6
        keys = [f["key"] for f in fields]
        assert "api_key" in keys
        assert "base_url" in keys
        assert "model" in keys

    def test_api_key_property(self):
        backend = _make_backend(api_key="sk-my-key")
        assert backend._api_key == "sk-my-key"

    def test_base_url_property(self):
        backend = _make_backend(base_url="http://localhost:1234/v1")
        assert backend._base_url == "http://localhost:1234/v1"

    def test_model_property(self):
        backend = _make_backend(model="gpt-4o")
        assert backend._model == "gpt-4o"

    def test_temperature_property(self):
        backend = _make_backend(temperature="0.7")
        assert backend._temperature == 0.7

    def test_temperature_invalid_falls_back(self):
        backend = _make_backend(temperature="invalid")
        assert backend._temperature == 0.3

    def test_request_timeout_property(self):
        backend = _make_backend(request_timeout="60")
        assert backend._request_timeout == 60

    def test_request_timeout_invalid_falls_back(self):
        backend = _make_backend(request_timeout="abc")
        assert backend._request_timeout == 120

    def test_max_retries_property(self):
        backend = _make_backend(max_retries="5")
        assert backend._max_retries == 5

    def test_max_retries_invalid_falls_back(self):
        backend = _make_backend(max_retries="nope")
        assert backend._max_retries == 3


class TestGetClient:
    """Tests for lazy client initialization."""

    @patch("translation.openai_compat._HAS_OPENAI", False)
    def test_raises_when_openai_not_installed(self):
        backend = _make_backend()
        with pytest.raises(RuntimeError, match="openai package not installed"):
            backend._get_client()

    @patch("translation.openai_compat._HAS_OPENAI", True)
    @patch("translation.openai_compat.OpenAI")
    def test_creates_client_with_correct_params(self, mock_openai_cls):
        backend = _make_backend(api_key="sk-abc", base_url="http://local/v1", request_timeout="30")
        mock_openai_cls.return_value = MagicMock()
        client = backend._get_client()
        mock_openai_cls.assert_called_once_with(
            api_key="sk-abc",
            base_url="http://local/v1",
            timeout=30,
            max_retries=0,
        )
        assert client is not None

    @patch("translation.openai_compat._HAS_OPENAI", True)
    def test_returns_cached_client(self):
        backend = _make_backend()
        mock_client = MagicMock()
        backend._client = mock_client
        assert backend._get_client() is mock_client


class TestTranslateBatch:
    """Tests for translate_batch method."""

    def test_empty_lines_returns_success(self):
        backend = _make_backend()
        result = backend.translate_batch([], "en", "de")
        assert result.success is True
        assert result.translated_lines == []

    @patch("translation.openai_compat._HAS_OPENAI", False)
    def test_returns_failure_when_package_missing(self):
        backend = _make_backend()
        result = backend.translate_batch(["Hello"], "en", "de")
        assert result.success is False
        assert "openai package not installed" in result.error

    @patch("translation.openai_compat._HAS_OPENAI", True)
    @patch("translation.llm_utils.parse_llm_response", return_value=["Hallo"])
    @patch("translation.llm_utils.has_cjk_hallucination", return_value=False)
    @patch("translation.llm_utils.build_translation_prompt", return_value="translate prompt")
    def test_successful_translation(self, mock_prompt, mock_cjk, mock_parse):
        backend = _make_backend()
        mock_client = MagicMock()
        mock_completion = MagicMock()
        mock_completion.choices = [MagicMock()]
        mock_completion.choices[0].message.content = "Hallo"
        mock_client.chat.completions.create.return_value = mock_completion
        backend._client = mock_client

        result = backend.translate_batch(["Hello"], "en", "de")

        assert result.success is True
        assert result.translated_lines == ["Hallo"]
        assert result.backend_name == "openai_compat"
        assert result.characters_used == 5
        assert result.response_time_ms >= 0

    @patch("translation.openai_compat._HAS_OPENAI", True)
    @patch("translation.llm_utils.build_translation_prompt", return_value="prompt")
    def test_all_retries_fail_returns_failure(self, mock_prompt):
        backend = _make_backend(max_retries="1")
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = Exception("API overloaded")
        backend._client = mock_client

        result = backend.translate_batch(["Hello"], "en", "de")

        assert result.success is False
        assert "All 1 attempts failed" in result.error
        assert "API overloaded" in result.error

    @patch("translation.openai_compat._HAS_OPENAI", True)
    @patch("translation.llm_utils.parse_llm_response", return_value=None)
    @patch("translation.llm_utils.build_translation_prompt", return_value="prompt")
    def test_line_count_mismatch_retries_and_fails(self, mock_prompt, mock_parse):
        backend = _make_backend(max_retries="1")
        mock_client = MagicMock()
        mock_completion = MagicMock()
        mock_completion.choices = [MagicMock()]
        mock_completion.choices[0].message.content = "Wrong\nLine\nCount"
        mock_client.chat.completions.create.return_value = mock_completion
        backend._client = mock_client

        result = backend.translate_batch(["Hello"], "en", "de")

        assert result.success is False
        assert "line count mismatch" in result.error.lower() or "All" in result.error

    @patch("translation.openai_compat._HAS_OPENAI", True)
    @patch("translation.llm_utils.parse_llm_response", return_value=["Hallo Welt"])
    @patch("translation.llm_utils.has_cjk_hallucination", return_value=True)
    @patch("translation.llm_utils.build_translation_prompt", return_value="prompt")
    def test_cjk_hallucination_triggers_retry(self, mock_prompt, mock_cjk, mock_parse):
        backend = _make_backend(max_retries="1")
        mock_client = MagicMock()
        mock_completion = MagicMock()
        mock_completion.choices = [MagicMock()]
        mock_completion.choices[0].message.content = "Hallo Welt"
        mock_client.chat.completions.create.return_value = mock_completion
        backend._client = mock_client

        result = backend.translate_batch(["Hello World"], "en", "de")

        assert result.success is False
        assert "CJK hallucination" in result.error


class TestHealthCheck:
    """Tests for health_check method."""

    @patch("translation.openai_compat._HAS_OPENAI", False)
    def test_unhealthy_when_package_missing(self):
        backend = _make_backend()
        healthy, msg = backend.health_check()
        assert healthy is False
        assert "openai package not installed" in msg

    @patch("translation.openai_compat._HAS_OPENAI", True)
    def test_healthy_with_model_found(self):
        backend = _make_backend(model="gpt-4o-mini")
        mock_client = MagicMock()
        m1 = MagicMock()
        m1.id = "gpt-4o-mini"
        m2 = MagicMock()
        m2.id = "gpt-4o"
        mock_client.models.list.return_value = [m1, m2]
        backend._client = mock_client

        healthy, msg = backend.health_check()
        assert healthy is True
        assert "gpt-4o-mini" in msg
        assert "available" in msg

    @patch("translation.openai_compat._HAS_OPENAI", True)
    def test_healthy_model_not_in_first_10(self):
        backend = _make_backend(model="custom-model")
        mock_client = MagicMock()
        models = [MagicMock() for _ in range(10)]
        for i, m in enumerate(models):
            m.id = f"model-{i}"
        mock_client.models.list.return_value = models
        backend._client = mock_client

        healthy, msg = backend.health_check()
        assert healthy is True
        assert "not in first 10" in msg

    @patch("translation.openai_compat._HAS_OPENAI", True)
    def test_unhealthy_on_exception(self):
        backend = _make_backend()
        mock_client = MagicMock()
        mock_client.models.list.side_effect = Exception("connection refused")
        backend._client = mock_client

        healthy, msg = backend.health_check()
        assert healthy is False
        assert "Health check failed" in msg
