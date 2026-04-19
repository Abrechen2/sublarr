"""Tests for translation.openai_compat — OpenAI-compatible translation backend.

Phase A1: backend inherits from LLMBackend. Tests cover config props, lazy
client init, health_check, and the three LLMBackend hooks
(_assemble_messages / _build_request / _call_api / _parse_response).
"""

from unittest.mock import MagicMock, patch

import pytest

from translation.base import TranslationResult  # noqa: F401 — type parity


@pytest.fixture(autouse=True)
def _register_openai_concurrency():
    """Register the backend's concurrency slot for LLMBackend orchestration."""
    from translation.concurrency import get_concurrency, reset_for_tests

    reset_for_tests()
    get_concurrency().register("openai_compat", 3)
    yield
    reset_for_tests()


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
    # Price lookup — safe because model is in the sheet (gpt-4o-mini).
    from translation.price_sheet import get_llm_price

    backend.cost_per_1m_tokens_in, backend.cost_per_1m_tokens_out = get_llm_price(
        "openai_compat", backend.config["model"]
    )
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

    def test_is_llm_backend_subclass(self):
        from translation.llm_base import LLMBackend
        from translation.openai_compat import OpenAICompatBackend

        assert issubclass(OpenAICompatBackend, LLMBackend)

    def test_price_looked_up_for_gpt_4o_mini(self):
        """Price sheet ships with gpt-4o-mini => 0.15 / 0.60 per 1M tokens."""
        from decimal import Decimal

        backend = _make_backend(model="gpt-4o-mini")
        assert backend.cost_per_1m_tokens_in == Decimal("0.15")
        assert backend.cost_per_1m_tokens_out == Decimal("0.60")

    def test_price_falls_back_to_zero_for_unknown_model(self):
        from decimal import Decimal

        backend = _make_backend(model="custom-local-model")
        assert backend.cost_per_1m_tokens_in == Decimal("0")
        assert backend.cost_per_1m_tokens_out == Decimal("0")


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


class TestLLMBackendHooks:
    """Tests for the new LLMBackend hooks."""

    def test_assemble_messages_returns_single_user(self):
        backend = _make_backend()
        msgs = backend._assemble_messages(
            ["Hello"], "en", "de", glossary_entries=None, series_context=None
        )
        assert len(msgs) == 1
        assert msgs[0]["role"] == "user"

    def test_assemble_messages_injects_series_context(self):
        backend = _make_backend()
        msgs = backend._assemble_messages(
            ["Hello"],
            "en",
            "de",
            glossary_entries=None,
            series_context="Serie: Naruto.",
        )
        assert "Naruto" in msgs[0]["content"]

    def test_assemble_messages_strict_mode(self):
        backend = _make_backend()
        msgs = backend._assemble_messages(
            ["Hello", "World"],
            "en",
            "de",
            glossary_entries=None,
            strict=True,
        )
        assert "STRICT" in msgs[0]["content"]
        assert "2" in msgs[0]["content"]

    def test_build_request_shape(self):
        backend = _make_backend(temperature="0.5")
        msgs = [{"role": "user", "content": "translate please"}]
        payload = backend._build_request(msgs, max_tokens=1500)
        assert payload["model"] == "gpt-4o-mini"
        assert payload["messages"] == msgs
        assert payload["temperature"] == 0.5
        assert payload["max_tokens"] == 1500

    def test_call_api_invokes_sdk(self):
        backend = _make_backend()
        mock_client = MagicMock()
        mock_completion = MagicMock()
        mock_completion.model_dump.return_value = {
            "choices": [
                {
                    "message": {"content": "Hallo"},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5},
            "model": "gpt-4o-mini",
        }
        mock_client.chat.completions.create.return_value = mock_completion
        backend._client = mock_client

        raw = backend._call_api({"model": "gpt-4o-mini", "messages": []}, timeout_s=120)

        mock_client.chat.completions.create.assert_called_once()
        assert raw["choices"][0]["message"]["content"] == "Hallo"

    def test_call_api_without_model_dump_fallback(self):
        """SDKs returning plain objects (older versions / mocks) still parse."""
        backend = _make_backend()
        mock_client = MagicMock()
        mock_completion = MagicMock(spec=["choices", "usage", "model"])
        # explicitly no model_dump attribute
        del mock_completion.model_dump
        mock_completion.choices = [MagicMock()]
        mock_completion.choices[0].message.content = "Hallo"
        mock_completion.choices[0].finish_reason = "stop"
        mock_completion.usage = MagicMock(prompt_tokens=4, completion_tokens=2)
        mock_completion.model = "gpt-4o"
        mock_client.chat.completions.create.return_value = mock_completion
        backend._client = mock_client

        raw = backend._call_api({"model": "gpt-4o", "messages": []}, timeout_s=120)

        assert raw["choices"][0]["message"]["content"] == "Hallo"
        assert raw["model"] == "gpt-4o"

    def test_parse_response_extracts_translations_and_tokens(self):
        backend = _make_backend()
        from translation.llm_base import LLMResponse

        raw = {
            "choices": [
                {
                    "message": {"content": "1: Hallo\n2: Welt"},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 15, "completion_tokens": 8},
            "model": "gpt-4o-mini",
        }
        resp = backend._parse_response(raw)
        assert isinstance(resp, LLMResponse)
        assert resp.translations == ["Hallo", "Welt"]
        assert resp.tokens_in == 15
        assert resp.tokens_out == 8
        assert resp.finish_reason == "stop"
        assert resp.model == "gpt-4o-mini"

    def test_parse_response_missing_choices_raises(self):
        backend = _make_backend()
        with pytest.raises(RuntimeError, match="missing 'choices'"):
            backend._parse_response({})

    def test_parse_response_missing_content_raises(self):
        backend = _make_backend()
        with pytest.raises(RuntimeError, match="message.content"):
            backend._parse_response({"choices": [{"finish_reason": "stop"}]})

    def test_parse_response_handles_object_usage(self):
        """When usage is a pydantic-ish object, token extraction still works."""
        backend = _make_backend()
        usage_obj = MagicMock()
        usage_obj.prompt_tokens = 12
        usage_obj.completion_tokens = 7
        raw = {
            "choices": [{"message": {"content": "Hallo"}, "finish_reason": "stop"}],
            "usage": usage_obj,
            "model": "gpt-4o",
        }
        resp = backend._parse_response(raw)
        assert resp.tokens_in == 12
        assert resp.tokens_out == 7


class TestTranslateBatchViaLLMBackend:
    """End-to-end through LLMBackend.translate_batch using patched SDK."""

    @patch("translation.openai_compat._HAS_OPENAI", True)
    def test_successful_translation(self):
        backend = _make_backend()
        mock_client = MagicMock()
        mock_completion = MagicMock()
        mock_completion.model_dump.return_value = {
            "choices": [{"message": {"content": "Hallo"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 4},
            "model": "gpt-4o-mini",
        }
        mock_client.chat.completions.create.return_value = mock_completion
        backend._client = mock_client

        result = backend.translate_batch(["Hello"], "en", "de")

        assert result.success is True
        assert result.translated_lines == ["Hallo"]
        assert result.backend_name == "openai_compat"
        assert result.characters_used == 5

    @patch("translation.openai_compat._HAS_OPENAI", True)
    def test_api_failure_raises(self):
        """LLMBackend surfaces API errors as exceptions (no silent fallback)."""
        backend = _make_backend()
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = Exception("API overloaded")
        backend._client = mock_client

        with pytest.raises(Exception, match="API overloaded"):
            backend.translate_batch(["Hello"], "en", "de")

    @patch("translation.openai_compat._HAS_OPENAI", True)
    def test_line_count_mismatch_raises(self):
        """LLMBackend retries once then raises LineCountMismatchError."""
        from translation.llm_base import LineCountMismatchError

        backend = _make_backend()
        mock_client = MagicMock()
        mock_completion = MagicMock()
        mock_completion.model_dump.return_value = {
            "choices": [{"message": {"content": "Only one"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 5, "completion_tokens": 3},
            "model": "gpt-4o-mini",
        }
        mock_client.chat.completions.create.return_value = mock_completion
        backend._client = mock_client

        with pytest.raises(LineCountMismatchError):
            backend.translate_batch(["Hello", "World", "Third"], "en", "de")


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
