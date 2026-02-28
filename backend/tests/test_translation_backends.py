"""Tests for the translation multi-backend system.

Covers: ABC contract, LLM utilities, TranslationManager orchestration,
backend stats recording, profile-based backend resolution, and individual
backend config field smoke tests. All external services are mocked.
"""

import json
import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest

from config import reload_settings
from db import _db_lock, close_db, get_db, init_db

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _isolate_db(tmp_path):
    """Create an isolated temp database for each test with Flask app context."""
    from app import create_app

    db_path = str(tmp_path / "test_translation.db")
    os.environ["SUBLARR_DB_PATH"] = db_path
    os.environ["SUBLARR_API_KEY"] = ""
    os.environ["SUBLARR_LOG_LEVEL"] = "ERROR"
    reload_settings()
    app = create_app(testing=True)
    with app.app_context():
        init_db()
        yield
    close_db()
    for key in ("SUBLARR_DB_PATH", "SUBLARR_API_KEY", "SUBLARR_LOG_LEVEL"):
        os.environ.pop(key, None)


@pytest.fixture()
def manager():
    """Return a fresh TranslationManager (no singleton, no builtin backends)."""
    from translation import TranslationManager

    return TranslationManager()


# ---------------------------------------------------------------------------
# Mock backend used by TranslationManager tests
# ---------------------------------------------------------------------------

from translation.base import TranslationBackend, TranslationResult


class MockBackend(TranslationBackend):
    """Configurable mock backend for manager orchestration tests."""

    name = "mock"
    display_name = "Mock Backend"
    config_fields = []
    supports_glossary = False
    supports_batch = True
    max_batch_size = 0

    def __init__(self, *, should_fail=False, **config):
        super().__init__(**config)
        self.should_fail = should_fail

    def translate_batch(self, lines, source_lang, target_lang, glossary_entries=None):
        if self.should_fail:
            return TranslationResult(
                translated_lines=[],
                backend_name=self.name,
                error="mock failure",
                success=False,
            )
        return TranslationResult(
            translated_lines=[f"translated:{l}" for l in lines],
            backend_name=self.name,
            response_time_ms=42.0,
            characters_used=sum(len(l) for l in lines),
            success=True,
        )

    def health_check(self):
        return (True, "mock OK")

    def get_config_fields(self):
        return self.config_fields


class MockBackendFail(MockBackend):
    """A second mock backend that always fails (different name for chaining)."""

    name = "mock_fail"
    display_name = "Mock Fail"

    def __init__(self, **config):
        super().__init__(should_fail=True, **config)


class MockBackendAlt(MockBackend):
    """Alternative mock backend that always succeeds (different name)."""

    name = "mock_alt"
    display_name = "Mock Alt"


# =========================================================================
# 1. ABC Contract Tests
# =========================================================================


def test_cannot_instantiate_abc():
    """TranslationBackend ABC cannot be instantiated directly."""
    with pytest.raises(TypeError):
        TranslationBackend()


def test_concrete_backend_must_implement_methods():
    """Subclass without implementing abstract methods raises TypeError."""

    class IncompleteBackend(TranslationBackend):
        pass

    with pytest.raises(TypeError):
        IncompleteBackend()


def test_translation_result_defaults():
    """TranslationResult has correct default values."""
    result = TranslationResult()
    assert result.translated_lines == []
    assert result.backend_name == ""
    assert result.response_time_ms == 0
    assert result.characters_used == 0
    assert result.error is None
    assert result.success is True


def test_translation_result_success_false():
    """TranslationResult with success=False carries error message."""
    result = TranslationResult(
        success=False,
        error="something went wrong",
        backend_name="test",
    )
    assert result.success is False
    assert result.error == "something went wrong"
    assert result.backend_name == "test"


# =========================================================================
# 2. LLM Utilities Tests
# =========================================================================

from translation.llm_utils import (
    build_prompt_with_glossary,
    build_translation_prompt,
    has_cjk_hallucination,
    parse_llm_response,
)


def test_build_translation_prompt_basic():
    """Numbered lines produced, no glossary section."""
    prompt = build_prompt_with_glossary("Translate:\n", None, ["Hello", "World"])
    assert "1: Hello" in prompt
    assert "2: World" in prompt
    assert "Glossary" not in prompt


def test_build_translation_prompt_with_glossary():
    """Glossary entries prepended before prompt template."""
    entries = [
        {"source_term": "senpai", "target_term": "Sempai"},
        {"source_term": "baka", "target_term": "Idiot"},
    ]
    prompt = build_prompt_with_glossary("Translate:\n", entries, ["Hello"])
    assert "Glossary:" in prompt
    assert "senpai" in prompt
    assert "Sempai" in prompt
    assert "baka" in prompt
    assert "1: Hello" in prompt


def test_build_translation_prompt_glossary_max_15():
    """Only the first 15 glossary entries are used."""
    entries = [{"source_term": f"term_{i}", "target_term": f"ziel_{i}"} for i in range(20)]
    prompt = build_prompt_with_glossary("T:\n", entries, ["x"])
    assert "term_14" in prompt
    assert "term_15" not in prompt


def test_parse_llm_response_exact_count():
    """Correct number of lines are returned as-is."""
    text = "Line one\nLine two\nLine three"
    result = parse_llm_response(text, 3)
    assert result == ["Line one", "Line two", "Line three"]


def test_parse_llm_response_numbered():
    """Numbered prefixes like '1: ' and '2. ' are stripped."""
    text = "1: Hallo\n2. Welt"
    result = parse_llm_response(text, 2)
    assert result == ["Hallo", "Welt"]


def test_parse_llm_response_too_many_merge():
    """Unnumbered continuation lines are merged with the previous numbered line."""
    # Lines 2 and 4 are unnumbered continuations — they get merged into lines 1 and 3
    text = "1: Line A\ncontinuation of A\n2: Line B\ncontinuation of B"
    result = parse_llm_response(text, 2)
    assert result is not None
    assert len(result) == 2


def test_parse_llm_response_too_few_returns_none():
    """Too few lines returns None (cannot be resolved)."""
    text = "Only one"
    result = parse_llm_response(text, 3)
    assert result is None


def test_has_cjk_hallucination_true():
    """Chinese characters in text are detected as CJK hallucination."""
    assert has_cjk_hallucination("Das ist ein Test \u4e16\u754c") is True


def test_has_cjk_hallucination_false():
    """Normal German/English text has no CJK hallucination."""
    assert has_cjk_hallucination("Hello World, wie geht es dir?") is False
    assert has_cjk_hallucination("Umlauts are fine: ae oe ue") is False


# =========================================================================
# 3. TranslationManager Tests
# =========================================================================


def test_register_backend(manager):
    """Registered backend class appears in internal registry."""
    manager.register_backend(MockBackend)
    assert "mock" in manager._backend_classes
    assert manager._backend_classes["mock"] is MockBackend


def test_get_backend_creates_instance(manager):
    """get_backend lazily creates an instance on first call."""
    manager.register_backend(MockBackend)
    backend = manager.get_backend("mock")
    assert backend is not None
    assert isinstance(backend, MockBackend)
    # Second call returns cached instance
    assert manager.get_backend("mock") is backend


def test_get_backend_unknown_returns_none(manager):
    """get_backend for an unregistered name returns None."""
    assert manager.get_backend("nonexistent") is None


def test_get_all_backends_lists_registered(manager):
    """get_all_backends returns info dicts for all registered backends."""
    manager.register_backend(MockBackend)
    manager.register_backend(MockBackendAlt)
    infos = manager.get_all_backends()
    names = [i["name"] for i in infos]
    assert "mock" in names
    assert "mock_alt" in names
    for info in infos:
        assert "display_name" in info
        assert "config_fields" in info
        assert "supports_glossary" in info


def test_translate_with_fallback_success(manager):
    """First backend succeeds, result is returned."""
    manager.register_backend(MockBackend)
    result = manager.translate_with_fallback(["Hello"], "en", "de", fallback_chain=["mock"])
    assert result.success is True
    assert result.translated_lines == ["translated:Hello"]
    assert result.backend_name == "mock"


def test_translate_with_fallback_tries_next(manager):
    """First backend fails, second backend succeeds."""
    manager.register_backend(MockBackendFail)
    manager.register_backend(MockBackendAlt)
    result = manager.translate_with_fallback(
        ["Hi"], "en", "de", fallback_chain=["mock_fail", "mock_alt"]
    )
    assert result.success is True
    assert result.backend_name == "mock_alt"


def test_translate_with_fallback_all_fail(manager):
    """All backends fail, error result returned."""
    manager.register_backend(MockBackendFail)
    result = manager.translate_with_fallback(["Hi"], "en", "de", fallback_chain=["mock_fail"])
    assert result.success is False
    assert "All backends failed" in result.error


def test_translate_with_fallback_skips_circuit_breaker_open(manager):
    """Backend with open circuit breaker is skipped."""
    manager.register_backend(MockBackendFail)
    manager.register_backend(MockBackendAlt)

    # Trip the circuit breaker for mock_fail
    cb = manager._get_circuit_breaker("mock_fail")
    for _ in range(cb.failure_threshold):
        cb.record_failure()
    assert cb.is_open

    result = manager.translate_with_fallback(
        ["Hi"], "en", "de", fallback_chain=["mock_fail", "mock_alt"]
    )
    assert result.success is True
    assert result.backend_name == "mock_alt"


def test_invalidate_backend_clears_cache(manager):
    """Invalidated backend is re-created on next use."""
    manager.register_backend(MockBackend)
    first = manager.get_backend("mock")
    assert first is not None

    manager.invalidate_backend("mock")
    assert "mock" not in manager._backends

    second = manager.get_backend("mock")
    assert second is not None
    assert second is not first


# =========================================================================
# 4. Backend Stats Tests
# =========================================================================

from db.translation import (
    get_backend_stat,
    get_backend_stats,
    record_backend_failure,
    record_backend_success,
)


def test_record_backend_success():
    """Stats row is created with success counters on first call."""
    record_backend_success("test_back", 120.0, 500)
    stat = get_backend_stat("test_back")
    assert stat is not None
    assert stat["total_requests"] == 1
    assert stat["successful_translations"] == 1
    assert stat["total_characters"] == 500
    assert stat["avg_response_time_ms"] == 120.0
    assert stat["consecutive_failures"] == 0


def test_record_backend_failure():
    """Stats row is created with failure counters on first call."""
    record_backend_failure("fail_back", "timeout error")
    stat = get_backend_stat("fail_back")
    assert stat is not None
    assert stat["total_requests"] == 1
    assert stat["failed_translations"] == 1
    assert stat["consecutive_failures"] == 1
    assert stat["last_error"] == "timeout error"


def test_consecutive_failures_reset_on_success():
    """Consecutive failure counter resets to 0 after a success."""
    record_backend_failure("reset_back", "err1")
    record_backend_failure("reset_back", "err2")
    stat = get_backend_stat("reset_back")
    assert stat["consecutive_failures"] == 2

    record_backend_success("reset_back", 50.0, 100)
    stat = get_backend_stat("reset_back")
    assert stat["consecutive_failures"] == 0
    assert stat["total_requests"] == 3
    assert stat["successful_translations"] == 1


def test_get_backend_stats():
    """get_backend_stats returns list of all stats rows."""
    record_backend_success("alpha", 10.0, 50)
    record_backend_success("beta", 20.0, 100)
    stats = get_backend_stats()
    names = [s["backend_name"] for s in stats]
    assert "alpha" in names
    assert "beta" in names


def test_avg_response_time_weighted():
    """Running average uses weighted formula: (old_avg * n + new) / (n+1)."""
    record_backend_success("avg_back", 100.0, 10)
    record_backend_success("avg_back", 200.0, 10)
    stat = get_backend_stat("avg_back")
    # After 2 requests: (100*1 + 200)/2 = 150
    assert abs(stat["avg_response_time_ms"] - 150.0) < 0.01

    record_backend_success("avg_back", 300.0, 10)
    stat = get_backend_stat("avg_back")
    # After 3 requests: (150*2 + 300)/3 = 200
    assert abs(stat["avg_response_time_ms"] - 200.0) < 0.01


# =========================================================================
# 5. Profile Backend Resolution Tests
# =========================================================================

from db.profiles import (
    assign_series_profile,
    create_language_profile,
    get_default_profile,
    get_language_profile,
    get_series_profile,
)


def test_resolve_default_profile_backend():
    """Default profile returns translation_backend and fallback_chain."""
    profile = get_default_profile()
    assert profile["translation_backend"] == "ollama"
    assert "ollama" in profile["fallback_chain"]


def test_resolve_series_profile_backend():
    """Series-specific profile returns its own backend setting."""
    pid = create_language_profile(
        "DeepL Profile",
        "en",
        "English",
        ["de"],
        ["German"],
        translation_backend="deepl",
        fallback_chain=["deepl", "ollama"],
    )
    assign_series_profile(sonarr_series_id=999, profile_id=pid)
    profile = get_series_profile(999)
    assert profile["translation_backend"] == "deepl"
    assert profile["fallback_chain"] == ["deepl", "ollama"]


def test_fallback_chain_from_profile():
    """Profile's fallback_chain is a list of backend names."""
    pid = create_language_profile(
        "Chain Test",
        "en",
        "English",
        ["fr"],
        ["French"],
        translation_backend="openai_compat",
        fallback_chain=["openai_compat", "deepl", "ollama"],
    )
    profile = get_language_profile(pid)
    assert profile["fallback_chain"] == ["openai_compat", "deepl", "ollama"]


def test_primary_backend_prepended_to_chain():
    """When fallback_chain is default, primary backend is the first entry."""
    pid = create_language_profile(
        "Primary First",
        "en",
        "English",
        ["de"],
        ["German"],
        translation_backend="libretranslate",
    )
    profile = get_language_profile(pid)
    assert profile["translation_backend"] == "libretranslate"
    # Default fallback_chain should be [translation_backend]
    assert profile["fallback_chain"][0] == "libretranslate"


# =========================================================================
# 6. Individual Backend Config Field Smoke Tests
# =========================================================================


def test_ollama_backend_config_fields():
    """OllamaBackend has url, model, temperature fields."""
    from translation.ollama import OllamaBackend

    fields = OllamaBackend.config_fields
    keys = [f["key"] for f in fields]
    assert "url" in keys
    assert "model" in keys
    assert "temperature" in keys


def test_deepl_backend_config_fields():
    """DeepLBackend has api_key field."""
    from translation.deepl_backend import DeepLBackend

    fields = DeepLBackend.config_fields
    keys = [f["key"] for f in fields]
    assert "api_key" in keys


def test_libretranslate_backend_config_fields():
    """LibreTranslateBackend has url and api_key fields."""
    from translation.libretranslate import LibreTranslateBackend

    fields = LibreTranslateBackend.config_fields
    keys = [f["key"] for f in fields]
    assert "url" in keys
    assert "api_key" in keys


def test_openai_compat_backend_config_fields():
    """OpenAICompatBackend has api_key, base_url, model fields."""
    from translation.openai_compat import OpenAICompatBackend

    fields = OpenAICompatBackend.config_fields
    keys = [f["key"] for f in fields]
    assert "api_key" in keys
    assert "base_url" in keys
    assert "model" in keys


def test_google_backend_config_fields():
    """GoogleTranslateBackend has project_id field."""
    from translation.google_translate import GoogleTranslateBackend

    fields = GoogleTranslateBackend.config_fields
    keys = [f["key"] for f in fields]
    assert "project_id" in keys
