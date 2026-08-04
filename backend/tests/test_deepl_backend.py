"""Tests for translation.deepl_backend — DeepL translation backend."""

from unittest.mock import MagicMock, patch

import pytest

from translation.base import TranslationResult


def _make_backend(**config_overrides):
    """Create a DeepLBackend instance without triggering __init__ side effects."""
    from translation.concurrency import get_concurrency
    from translation.deepl_backend import DeepLBackend

    get_concurrency().register("deepl", 3)

    backend = DeepLBackend.__new__(DeepLBackend)
    backend.config = {"api_key": "test-key:fx", **config_overrides}
    backend._client = None
    backend._glossary_cache = {}
    return backend


class TestToDeeplLang:
    """Tests for the _to_deepl_lang helper function."""

    def test_known_language_code(self):
        from translation.deepl_backend import _to_deepl_lang

        assert _to_deepl_lang("en") == "EN"
        assert _to_deepl_lang("de") == "DE"

    def test_portuguese_source_stays_bare(self):
        from translation.deepl_backend import _to_deepl_lang

        assert _to_deepl_lang("pt") == "PT"

    def test_english_target_uses_regional_variant(self):
        """DeepL rejects bare EN as a target: 'deprecated, use EN-GB or EN-US'."""
        from translation.deepl_backend import _to_deepl_lang

        assert _to_deepl_lang("en", target=True) == "EN-US"

    def test_portuguese_target_uses_regional_variant(self):
        from translation.deepl_backend import _to_deepl_lang

        assert _to_deepl_lang("pt", target=True) == "PT-BR"

    def test_target_flag_does_not_affect_other_languages(self):
        from translation.deepl_backend import _to_deepl_lang

        assert _to_deepl_lang("de", target=True) == "DE"
        assert _to_deepl_lang("ja", target=True) == "JA"

    def test_norwegian_maps_to_nb(self):
        from translation.deepl_backend import _to_deepl_lang

        assert _to_deepl_lang("nb") == "NB"

    def test_unknown_language_falls_back_to_uppercase(self):
        from translation.deepl_backend import _to_deepl_lang

        assert _to_deepl_lang("xx") == "XX"

    def test_case_insensitive_input(self):
        from translation.deepl_backend import _to_deepl_lang

        assert _to_deepl_lang("EN") == "EN"
        assert _to_deepl_lang("De") == "DE"


class TestDeepLBackendAttributes:
    """Tests for class-level attributes and config."""

    def test_name_and_display_name(self):
        backend = _make_backend()
        assert backend.name == "deepl"
        assert backend.display_name == "DeepL"

    def test_supports_glossary(self):
        backend = _make_backend()
        assert backend.supports_glossary is True

    def test_supports_batch(self):
        backend = _make_backend()
        assert backend.supports_batch is True
        assert backend.max_batch_size == 50

    def test_config_fields_returned(self):
        backend = _make_backend()
        fields = backend.get_config_fields()
        assert len(fields) == 1
        assert fields[0]["key"] == "api_key"


class TestGetClient:
    """Tests for lazy client initialization."""

    @patch("translation.deepl_backend._DEEPL_AVAILABLE", False)
    def test_raises_when_deepl_not_installed(self):
        backend = _make_backend()
        with pytest.raises(RuntimeError, match="deepl package not installed"):
            backend._get_client()

    @patch("translation.deepl_backend._DEEPL_AVAILABLE", True)
    def test_raises_when_no_api_key(self):
        backend = _make_backend(api_key="")
        with pytest.raises(RuntimeError, match="API key not configured"):
            backend._get_client()

    @patch("translation.deepl_backend._DEEPL_AVAILABLE", True)
    @patch("translation.deepl_backend.deepl")
    def test_creates_client_on_first_call(self, mock_deepl):
        backend = _make_backend()
        mock_deepl.DeepLClient.return_value = MagicMock()
        client = backend._get_client()
        mock_deepl.DeepLClient.assert_called_once_with(auth_key="test-key:fx")
        assert client is not None

    @patch("translation.deepl_backend._DEEPL_AVAILABLE", True)
    def test_returns_cached_client_on_second_call(self):
        backend = _make_backend()
        mock_client = MagicMock()
        backend._client = mock_client
        assert backend._get_client() is mock_client


class TestTranslateBatch:
    """Tests for translate_batch method."""

    @patch("translation.deepl_backend._DEEPL_AVAILABLE", False)
    def test_raises_when_package_missing(self):
        backend = _make_backend()
        with pytest.raises(RuntimeError, match="deepl package not installed"):
            backend.translate_batch(["Hello"], "en", "de")

    @patch("translation.deepl_backend._DEEPL_AVAILABLE", True)
    def test_successful_translation(self):
        backend = _make_backend()
        mock_client = MagicMock()
        mock_result = MagicMock()
        mock_result.text = "Hallo"
        mock_client.translate_text.return_value = [mock_result]
        backend._client = mock_client

        result = backend.translate_batch(["Hello"], "en", "de")

        assert result.success is True
        assert result.translated_lines == ["Hallo"]
        assert result.backend_name == "deepl"
        assert result.characters_used == 5

    @patch("translation.deepl_backend._DEEPL_AVAILABLE", True)
    def test_multiple_lines(self):
        backend = _make_backend()
        mock_client = MagicMock()
        r1, r2 = MagicMock(), MagicMock()
        r1.text = "Hallo"
        r2.text = "Welt"
        mock_client.translate_text.return_value = [r1, r2]
        backend._client = mock_client

        result = backend.translate_batch(["Hello", "World"], "en", "de")

        assert result.translated_lines == ["Hallo", "Welt"]
        assert result.characters_used == 10

    @patch("translation.deepl_backend._DEEPL_AVAILABLE", True)
    def test_api_error_returns_failure_result(self):
        backend = _make_backend()
        mock_client = MagicMock()
        mock_client.translate_text.side_effect = Exception("API quota exceeded")
        backend._client = mock_client

        result = backend.translate_batch(["Hello"], "en", "de")

        assert result.success is False
        assert result.translated_lines == []
        assert "API quota exceeded" in result.error

    @patch("translation.deepl_backend._DEEPL_AVAILABLE", True)
    def test_glossary_entries_used(self):
        backend = _make_backend()
        mock_client = MagicMock()
        mock_result = MagicMock()
        mock_result.text = "Hallo"
        mock_client.translate_text.return_value = [mock_result]
        mock_glossary = MagicMock()
        mock_client.create_glossary.return_value = mock_glossary
        backend._client = mock_client

        glossary = [{"source_term": "hello", "target_term": "hallo"}]
        result = backend.translate_batch(["Hello"], "en", "de", glossary_entries=glossary)

        assert result.success is True
        # Verify glossary was passed to translate_text
        call_kwargs = mock_client.translate_text.call_args[1]
        assert "glossary" in call_kwargs

    @patch("translation.deepl_backend._DEEPL_AVAILABLE", True)
    def test_english_target_sent_as_regional_variant(self):
        """Prod incident: DeepL 400s on target_lang="EN" and the breaker latched OPEN."""
        backend = _make_backend()
        mock_client = MagicMock()
        mock_result = MagicMock()
        mock_result.text = "Hello"
        mock_client.translate_text.return_value = [mock_result]
        backend._client = mock_client

        result = backend.translate_batch(["Hallo"], "de", "en")

        assert result.success is True
        call_kwargs = mock_client.translate_text.call_args[1]
        assert call_kwargs["target_lang"] == "EN-US"
        assert call_kwargs["source_lang"] == "DE"

    @patch("translation.deepl_backend._DEEPL_AVAILABLE", True)
    def test_glossary_uses_base_target_code(self):
        """DeepL's glossary API rejects the regional variant translate_text requires."""
        backend = _make_backend()
        mock_client = MagicMock()
        mock_result = MagicMock()
        mock_result.text = "Hello"
        mock_client.translate_text.return_value = [mock_result]
        mock_client.create_glossary.return_value = MagicMock()
        backend._client = mock_client

        glossary = [{"source_term": "hallo", "target_term": "hello"}]
        backend.translate_batch(["Hallo"], "de", "en", glossary_entries=glossary)

        glossary_kwargs = mock_client.create_glossary.call_args[1]
        assert glossary_kwargs["target_lang"] == "EN"
        assert glossary_kwargs["source_lang"] == "DE"

    @patch("translation.deepl_backend._DEEPL_AVAILABLE", True)
    def test_hung_call_is_abandoned_after_timeout(self):
        """A translate_text call that never returns must not hang the job forever.

        Reproduces the prod incident: the deepl SDK's own retry/backoff didn't
        surface an exception even after 12+ minutes (TCP CLOSE_WAIT with
        unread bytes). _run_with_timeout must bound the wait regardless.
        """
        import threading
        import time

        backend = _make_backend()
        backend.timeout_s = 0.1
        mock_client = MagicMock()
        release_event = threading.Event()

        def _never_returns_in_time(*args, **kwargs):
            release_event.wait(timeout=5)  # released by the test at teardown
            return [MagicMock(text="unused")]

        mock_client.translate_text.side_effect = _never_returns_in_time
        backend._client = mock_client

        started = time.monotonic()
        result = backend.translate_batch(["Hello"], "en", "de")
        elapsed = time.monotonic() - started

        assert result.success is False
        assert "0.1s" in result.error
        assert elapsed < 1.0  # bounded by timeout_s, not the 5s side_effect wait
        release_event.set()  # let the abandoned thread finish so it doesn't leak past the test

    @patch("translation.deepl_backend._DEEPL_AVAILABLE", True)
    def test_translate_batch_uses_concurrency_slot(self):
        """translate_batch must acquire the shared per-backend concurrency slot."""
        from translation.concurrency import get_concurrency

        backend = _make_backend()
        mock_client = MagicMock()
        mock_result = MagicMock()
        mock_result.text = "Hallo"
        mock_client.translate_text.return_value = [mock_result]
        backend._client = mock_client

        with patch.object(get_concurrency(), "slot", wraps=get_concurrency().slot) as mock_slot:
            result = backend.translate_batch(["Hello"], "en", "de")

        assert result.success is True
        mock_slot.assert_called_once_with("deepl", timeout_s=backend.timeout_s)


class TestGetOrCreateGlossary:
    """Tests for glossary caching and creation."""

    @patch("translation.deepl_backend._DEEPL_AVAILABLE", True)
    def test_glossary_cached_on_second_call(self):
        backend = _make_backend()
        mock_client = MagicMock()
        mock_glossary = MagicMock()
        mock_client.create_glossary.return_value = mock_glossary
        backend._client = mock_client

        entries = [{"source_term": "hello", "target_term": "hallo"}]

        g1 = backend._get_or_create_glossary("EN", "DE", entries)
        g2 = backend._get_or_create_glossary("EN", "DE", entries)

        assert g1 is g2
        mock_client.create_glossary.assert_called_once()

    @patch("translation.deepl_backend._DEEPL_AVAILABLE", True)
    def test_empty_entries_returns_none(self):
        backend = _make_backend()
        mock_client = MagicMock()
        backend._client = mock_client

        result = backend._get_or_create_glossary(
            "EN", "DE", [{"source_term": "", "target_term": ""}]
        )
        assert result is None

    @patch("translation.deepl_backend._DEEPL_AVAILABLE", True)
    def test_glossary_creation_failure_returns_none(self):
        backend = _make_backend()
        mock_client = MagicMock()
        mock_client.create_glossary.side_effect = Exception("quota exceeded")
        backend._client = mock_client

        entries = [{"source_term": "hello", "target_term": "hallo"}]
        result = backend._get_or_create_glossary("EN", "DE", entries)
        assert result is None


class TestHealthCheck:
    """Tests for health_check method."""

    @patch("translation.deepl_backend._DEEPL_AVAILABLE", True)
    def test_healthy_free_plan(self):
        backend = _make_backend(api_key="test-key:fx")
        mock_client = MagicMock()
        mock_usage = MagicMock()
        mock_usage.character.count = 1000
        mock_usage.character.limit = 500000
        mock_client.get_usage.return_value = mock_usage
        backend._client = mock_client

        healthy, msg = backend.health_check()
        assert healthy is True
        assert "Free" in msg
        assert "1000/500000" in msg

    @patch("translation.deepl_backend._DEEPL_AVAILABLE", True)
    def test_healthy_pro_plan(self):
        backend = _make_backend(api_key="test-key-pro")
        mock_client = MagicMock()
        mock_usage = MagicMock()
        mock_usage.character.count = 500
        mock_usage.character.limit = 10000000
        mock_client.get_usage.return_value = mock_usage
        backend._client = mock_client

        healthy, msg = backend.health_check()
        assert healthy is True
        assert "Pro" in msg

    @patch("translation.deepl_backend._DEEPL_AVAILABLE", True)
    def test_unhealthy_on_exception(self):
        backend = _make_backend()
        mock_client = MagicMock()
        mock_client.get_usage.side_effect = Exception("connection refused")
        backend._client = mock_client

        healthy, msg = backend.health_check()
        assert healthy is False
        assert "connection refused" in msg


class TestGetUsage:
    """Tests for get_usage method."""

    @patch("translation.deepl_backend._DEEPL_AVAILABLE", True)
    def test_returns_usage_dict(self):
        backend = _make_backend(api_key="test-key:fx")
        mock_client = MagicMock()
        mock_usage = MagicMock()
        mock_usage.character.count = 2500
        mock_usage.character.limit = 500000
        mock_client.get_usage.return_value = mock_usage
        backend._client = mock_client

        usage = backend.get_usage()
        assert usage["characters_used"] == 2500
        assert usage["characters_limit"] == 500000
        assert usage["plan"] == "Free"

    @patch("translation.deepl_backend._DEEPL_AVAILABLE", True)
    def test_returns_empty_dict_on_error(self):
        backend = _make_backend()
        mock_client = MagicMock()
        mock_client.get_usage.side_effect = Exception("failed")
        backend._client = mock_client

        usage = backend.get_usage()
        assert usage == {}
