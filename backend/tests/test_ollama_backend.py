"""Tests for translation.ollama — Ollama translation backend.

Complements test_ollama_v9.py (which tests V9 chat-API specific features)
by covering config properties, the legacy ``_call_ollama`` /
``_call_ollama_chat`` helpers that back health checks and tooling, the new
LLMBackend hooks (_build_request / _call_api / _parse_response), and
health_check.
"""

from unittest.mock import MagicMock, patch

import pytest
import requests

from translation.base import TranslationResult  # noqa: F401 — retained for type parity


@pytest.fixture(autouse=True)
def _register_ollama_concurrency():
    """Ensure the Ollama semaphore is registered for LLMBackend orchestration.

    LLMBackend.translate_batch acquires a slot from get_concurrency();
    without registration the slot() context manager raises KeyError.
    """
    from translation.concurrency import get_concurrency, reset_for_tests

    reset_for_tests()
    get_concurrency().register("ollama", 3)
    yield
    reset_for_tests()


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

    def test_is_llm_backend_subclass(self):
        """OllamaBackend must inherit from LLMBackend (Phase A1)."""
        from translation.llm_base import LLMBackend
        from translation.ollama import OllamaBackend

        assert issubclass(OllamaBackend, LLMBackend)

    def test_cost_is_zero(self):
        """Self-hosted backend: price sheet declares zero for Ollama."""
        from decimal import Decimal

        from translation.ollama import OllamaBackend

        assert OllamaBackend.cost_per_1m_tokens_in == Decimal("0")
        assert OllamaBackend.cost_per_1m_tokens_out == Decimal("0")


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


class TestLLMBackendHooks:
    """Tests for the LLMBackend integration (new _build_request/_call_api/_parse_response)."""

    def test_assemble_messages_generate_mode_is_single_user(self):
        backend = _make_backend(use_chat_api="false")
        msgs = backend._assemble_messages(
            ["Hello"], "en", "de", glossary_entries=None, series_context=None
        )
        assert len(msgs) == 1
        assert msgs[0]["role"] == "user"

    def test_assemble_messages_chat_mode_has_system(self):
        backend = _make_backend(use_chat_api="true", system_prompt="You translate.")
        msgs = backend._assemble_messages(
            ["Hello"], "en", "de", glossary_entries=None, series_context=None
        )
        assert len(msgs) == 2
        assert msgs[0]["role"] == "system"
        assert msgs[1]["role"] == "user"
        assert "You translate" in msgs[0]["content"]

    def test_build_request_generate_mode(self):
        backend = _make_backend(use_chat_api="false")
        msgs = [{"role": "user", "content": "TRAINED PROMPT"}]
        payload = backend._build_request(msgs, max_tokens=1000)
        assert payload["_mode"] == "generate"
        assert payload["model"] == "test-model"
        assert payload["prompt"] == "TRAINED PROMPT"
        assert payload["stream"] is False
        assert payload["options"]["temperature"] == 0.3

    def test_build_request_chat_mode(self):
        backend = _make_backend(use_chat_api="true")
        msgs = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "usr"},
        ]
        payload = backend._build_request(msgs, max_tokens=1000)
        assert payload["_mode"] == "chat"
        assert payload["messages"] == msgs
        assert payload["options"]["num_ctx"] == 4096

    @patch("translation.ollama.requests.post")
    def test_call_api_routes_generate_to_generate_endpoint(self, mock_post):
        backend = _make_backend(use_chat_api="false")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"response": "Hallo"}
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        raw = backend._call_api(
            {"_mode": "generate", "model": "test-model", "prompt": "x", "options": {}},
            timeout_s=10,
        )

        call_url = mock_post.call_args[0][0]
        assert call_url.endswith("/api/generate")
        assert raw["_mode"] == "generate"
        assert raw["response"] == "Hallo"

    @patch("translation.ollama.requests.post")
    def test_call_api_routes_chat_to_chat_endpoint(self, mock_post):
        backend = _make_backend(use_chat_api="true")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"message": {"content": "Hallo"}}
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        raw = backend._call_api(
            {"_mode": "chat", "model": "test-model", "messages": []},
            timeout_s=10,
        )

        call_url = mock_post.call_args[0][0]
        assert call_url.endswith("/api/chat")
        assert raw["_mode"] == "chat"
        assert raw["message"]["content"] == "Hallo"

    @patch("translation.ollama.requests.post")
    def test_call_api_rate_limit_raises(self, mock_post):
        backend = _make_backend()
        mock_resp = MagicMock()
        mock_resp.status_code = 429
        mock_resp.headers = {"Retry-After": "5"}
        mock_post.return_value = mock_resp

        with pytest.raises(RuntimeError, match="rate limited"):
            backend._call_api({"_mode": "generate"}, timeout_s=10)

    def test_parse_response_generate_splits_numbered_lines(self):
        backend = _make_backend()
        from translation.llm_base import LLMResponse

        raw = {
            "_mode": "generate",
            "response": "1: Hallo\n2: Welt",
            "prompt_eval_count": 10,
            "eval_count": 12,
            "model": "test-model",
            "done_reason": "stop",
        }
        resp = backend._parse_response(raw)
        assert isinstance(resp, LLMResponse)
        assert resp.translations == ["Hallo", "Welt"]
        assert resp.tokens_in == 10
        assert resp.tokens_out == 12
        assert resp.finish_reason == "stop"

    def test_parse_response_strips_think_block_pair(self):
        # Reasoning models (qwen3, deepseek-r1) emit <think>…</think> before
        # the answer — it must never reach the subtitle output.
        backend = _make_backend()
        raw = {
            "_mode": "generate",
            "response": "<think>The user wants German.\nLet me translate.</think>\nHallo\nWelt",
        }
        resp = backend._parse_response(raw)
        assert resp.translations == ["Hallo", "Welt"]

    def test_parse_response_strips_dangling_think_close(self):
        # Some models emit the reasoning then a closing </think> with no opening
        # tag (the API suppressed it). Keep only what follows the close.
        backend = _make_backend()
        raw = {
            "_mode": "generate",
            "response": "Okay, translate casually.\nUse 'Lass uns'.</think>\nHallo\nWelt",
        }
        resp = backend._parse_response(raw)
        assert resp.translations == ["Hallo", "Welt"]

    def test_parse_response_chat_reads_message_content(self):
        backend = _make_backend()
        raw = {
            "_mode": "chat",
            "message": {"content": "Hallo\nWelt"},
            "prompt_eval_count": 5,
            "eval_count": 7,
        }
        resp = backend._parse_response(raw)
        assert resp.translations == ["Hallo", "Welt"]
        assert resp.tokens_in == 5
        assert resp.tokens_out == 7

    def test_parse_response_chat_missing_content_raises(self):
        backend = _make_backend()
        raw = {"_mode": "chat", "done": True}
        with pytest.raises(RuntimeError, match="message.content"):
            backend._parse_response(raw)

    def test_parse_response_generate_missing_response_key_raises(self):
        backend = _make_backend()
        raw = {"_mode": "generate", "done": True}
        with pytest.raises(RuntimeError, match="missing 'response' key"):
            backend._parse_response(raw)


class TestCjkHallucinationRetry:
    """Plan A3 follow-up — Ollama retries once on CJK hallucination."""

    def _make_resp(self, translations: list[str]):
        from translation.llm_base import LLMResponse

        return LLMResponse(
            translations=translations,
            tokens_in=10,
            tokens_out=10,
            model="test-model",
            finish_reason="stop",
            raw_latency_ms=0,
        )

    def test_clean_response_returns_unchanged_no_retry(self):
        backend = _make_backend()
        resp = self._make_resp(["Hallo", "Welt"])
        with patch.object(backend, "_attempt") as mock_attempt:
            out = backend._verify_line_count(
                resp=resp,
                lines=["Hello", "World"],
                source_lang="en",
                target_lang="de",
                glossary_entries=None,
                series_context=None,
            )
        assert out is resp
        mock_attempt.assert_not_called()

    def test_cjk_hallucination_triggers_single_retry(self):
        backend = _make_backend()
        # First response has Chinese characters (hallucination)
        tainted = self._make_resp(["你好", "Welt"])
        clean_retry = self._make_resp(["Hallo", "Welt"])

        with patch.object(backend, "_attempt", return_value=clean_retry) as mock_attempt:
            out = backend._verify_line_count(
                resp=tainted,
                lines=["Hello", "World"],
                source_lang="en",
                target_lang="de",
                glossary_entries=None,
                series_context=None,
            )

        assert mock_attempt.call_count == 1
        # is_retry=True must be passed so strict prompt kicks in
        assert mock_attempt.call_args.kwargs.get("is_retry") is True
        # Retry result accepted because it's clean
        assert out.translations == ["Hallo", "Welt"]
        # Tokens summed across both attempts
        assert out.tokens_in == 20
        assert out.tokens_out == 20

    def test_cjk_persists_after_retry_keeps_original_with_summed_tokens(self):
        backend = _make_backend()
        tainted_first = self._make_resp(["你好", "Welt"])
        tainted_retry = self._make_resp(["你好", "世界"])  # still CJK

        with patch.object(backend, "_attempt", return_value=tainted_retry) as mock_attempt:
            out = backend._verify_line_count(
                resp=tainted_first,
                lines=["Hello", "World"],
                source_lang="en",
                target_lang="de",
                glossary_entries=None,
                series_context=None,
            )

        assert mock_attempt.call_count == 1
        # Original kept (best-effort — CJK translation better than none)
        assert out.translations == ["你好", "Welt"]
        # But tokens reflect both attempts
        assert out.tokens_in == 20
        assert out.tokens_out == 20


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
