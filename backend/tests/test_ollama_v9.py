"""Tests for Ollama V9 chat-API integration."""

from unittest.mock import MagicMock, patch


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
    def test_legacy_path_calls_generate(self):
        backend = _make_backend(use_chat_api=False)
        backend._call_ollama = MagicMock(return_value="1: Hallo")
        backend._call_ollama_chat = MagicMock()
        with (
            patch("translation.llm_utils.parse_llm_response", return_value=["Hallo"]),
            patch("translation.llm_utils.has_cjk_hallucination", return_value=False),
        ):
            backend.translate_batch(["Hello"], "en", "de")
        backend._call_ollama.assert_called_once()
        backend._call_ollama_chat.assert_not_called()

    def test_chat_path_calls_chat_api(self):
        backend = _make_backend(use_chat_api=True, system_prompt="You translate.")
        backend._call_ollama = MagicMock()
        backend._call_ollama_chat = MagicMock(return_value="Hallo")
        with (
            patch("translation.llm_utils.parse_llm_response", return_value=["Hallo"]),
            patch("translation.llm_utils.has_cjk_hallucination", return_value=False),
        ):
            backend.translate_batch(["Hello"], "en", "de")
        backend._call_ollama_chat.assert_called_once()
        backend._call_ollama.assert_not_called()

    def test_series_context_passed_through(self):
        backend = _make_backend(use_chat_api=True, system_prompt="Base. {series_context}")
        backend._call_ollama_chat = MagicMock(return_value="Hallo")
        with (
            patch("translation.llm_utils.parse_llm_response", return_value=["Hallo"]),
            patch("translation.llm_utils.has_cjk_hallucination", return_value=False),
        ):
            backend.translate_batch(["Hello"], "en", "de", series_context="Serie: Naruto.")
        call_args = backend._call_ollama_chat.call_args
        system_arg = call_args[0][0]
        assert "Naruto" in system_arg


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
        import pytest

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
