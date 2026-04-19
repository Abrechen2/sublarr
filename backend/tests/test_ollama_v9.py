"""Tests for Ollama V9 chat-API integration."""

from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def _register_ollama_concurrency():
    """Register the Ollama concurrency slot for LLMBackend orchestration."""
    from translation.concurrency import get_concurrency, reset_for_tests

    reset_for_tests()
    get_concurrency().register("ollama", 3)
    yield
    reset_for_tests()


def _make_backend(use_chat_api: bool = False, system_prompt: str = ""):
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
        "use_chat_api": "true" if use_chat_api else "false",
        "system_prompt": system_prompt,
    }
    return backend


class TestOllamaV9ConfigFields:
    def test_use_chat_api_false_by_default(self):
        backend = _make_backend()
        assert backend._use_chat_api is False

    def test_use_chat_api_true_when_set(self):
        backend = _make_backend(use_chat_api=True)
        assert backend._use_chat_api is True

    def test_system_prompt_default(self):
        backend = _make_backend()
        assert isinstance(backend._system_prompt, str)

    def test_system_prompt_from_config(self):
        backend = _make_backend(system_prompt="You are a translator.")
        assert backend._system_prompt == "You are a translator."


class TestBuildSystemPrompt:
    def test_no_series_context(self):
        backend = _make_backend(system_prompt="Base prompt.")
        result = backend._build_system_prompt(series_context=None)
        assert result == "Base prompt."

    def test_with_series_context(self):
        backend = _make_backend(system_prompt="Base prompt. {series_context}")
        result = backend._build_system_prompt(series_context="Serie: Naruto. Genre: Action.")
        assert "Naruto" in result
        assert "{series_context}" not in result

    def test_no_placeholder_context_appended(self):
        backend = _make_backend(system_prompt="Base prompt.")
        result = backend._build_system_prompt(series_context="Serie: Naruto.")
        assert "Naruto" in result


class TestChatApiDispatch:
    """V9+ chat-API dispatch routes through _call_api to /api/chat or /api/generate."""

    @patch("translation.ollama.requests.post")
    def test_legacy_path_hits_generate_endpoint(self, mock_post):
        backend = _make_backend(use_chat_api=False)
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "response": "1: Hallo",
            "prompt_eval_count": 5,
            "eval_count": 3,
        }
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        backend.translate_batch(["Hello"], "en", "de")

        assert mock_post.called
        # Find the call — tests run _verify_line_count too, but 1 line matches
        call_urls = [call.args[0] for call in mock_post.call_args_list]
        assert any(u.endswith("/api/generate") for u in call_urls)
        assert not any(u.endswith("/api/chat") for u in call_urls)

    @patch("translation.ollama.requests.post")
    def test_chat_path_hits_chat_endpoint(self, mock_post):
        backend = _make_backend(use_chat_api=True, system_prompt="You translate.")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "message": {"content": "Hallo"},
            "prompt_eval_count": 5,
            "eval_count": 3,
        }
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        backend.translate_batch(["Hello"], "en", "de")

        call_urls = [call.args[0] for call in mock_post.call_args_list]
        assert any(u.endswith("/api/chat") for u in call_urls)
        assert not any(u.endswith("/api/generate") for u in call_urls)

    @patch("translation.ollama.requests.post")
    def test_series_context_passed_through(self, mock_post):
        backend = _make_backend(use_chat_api=True, system_prompt="Base. {series_context}")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "message": {"content": "Hallo"},
            "prompt_eval_count": 5,
            "eval_count": 3,
        }
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        backend.translate_batch(["Hello"], "en", "de", series_context="Serie: Naruto.")

        # System message should contain the injected series context
        sent_payload = mock_post.call_args.kwargs["json"]
        system_msg = next(m for m in sent_payload["messages"] if m["role"] == "system")
        assert "Naruto" in system_msg["content"]


class TestCallOllamaChat:
    def test_returns_message_content(self):
        backend = _make_backend(use_chat_api=True)
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"message": {"content": "Hallo Welt"}}
        mock_resp.raise_for_status = MagicMock()
        with patch("requests.post", return_value=mock_resp):
            result = backend._call_ollama_chat("system text", "user text")
        assert result == "Hallo Welt"

    def test_raises_on_missing_message_key(self):
        backend = _make_backend(use_chat_api=True)
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"done": True}
        mock_resp.raise_for_status = MagicMock()
        with (
            patch("requests.post", return_value=mock_resp),
            pytest.raises(RuntimeError, match="message"),
        ):
            backend._call_ollama_chat("system text", "user text")
