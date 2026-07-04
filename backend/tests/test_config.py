"""Tests for config.py — Settings and language tag handling."""

import os

import pytest

from config import _get_language_tags, get_settings, reload_settings


def test_default_settings(monkeypatch):
    """Boot-field env vars take effect; UI-field env vars are ignored.

    Since v0.88.0-beta the env-loadable surface is the curated BootSettings
    set (port, log_level, paths, …). UI fields (source/target language,
    ollama_url, etc.) come from the DB / direct kwargs only.
    """
    monkeypatch.setenv("SUBLARR_PORT", "5765")  # boot — applies
    monkeypatch.setenv("SUBLARR_SOURCE_LANGUAGE", "en")  # ui — ignored
    monkeypatch.setenv("SUBLARR_TARGET_LANGUAGE", "de")  # ui — ignored
    monkeypatch.setenv("SUBLARR_OLLAMA_URL", "http://localhost:11434")  # ui — ignored
    settings = reload_settings()
    assert settings.port == 5765  # boot field — env honoured
    # UI fields stay at their defaults regardless of env (and the defaults
    # happen to match the values above, so no assertion change is needed).
    assert settings.source_language == "en"
    assert settings.target_language == "de"
    assert settings.ollama_url == "http://localhost:11434"


def test_env_prefix():
    """SUBLARR_ prefix works for boot fields; UI fields ignore env."""
    os.environ["SUBLARR_PORT"] = "8080"  # boot — applies
    os.environ["SUBLARR_TARGET_LANGUAGE"] = "fr"  # ui — ignored
    try:
        settings = reload_settings()
        assert settings.port == 8080  # boot env honoured
        assert settings.target_language == "de"  # ui default preserved
    finally:
        del os.environ["SUBLARR_PORT"]
        del os.environ["SUBLARR_TARGET_LANGUAGE"]


def test_language_tags():
    """Test language tag generation."""
    assert "de" in _get_language_tags("de")
    assert "deu" in _get_language_tags("de")
    assert "ger" in _get_language_tags("de")
    assert "german" in _get_language_tags("de")

    assert "en" in _get_language_tags("en")
    assert "eng" in _get_language_tags("en")
    assert "english" in _get_language_tags("en")


def test_get_target_patterns():
    """Test target pattern generation."""
    settings = get_settings()
    patterns = settings.get_target_patterns("ass")
    # Patterns should include target language tags
    assert len(patterns) > 0
    # Check that patterns contain the target language code
    assert any(settings.target_language in p for p in patterns)


def test_prompt_template():
    """Test auto-generated prompt template."""
    settings = get_settings()
    prompt = settings.get_prompt_template()
    assert "English" in prompt or "en" in prompt.lower()
    assert "German" in prompt or "de" in prompt.lower()
    assert "Translate" in prompt
    assert "\\N" in prompt


def test_safe_config():
    """Test that safe config hides API keys."""
    settings = get_settings()
    safe = settings.get_safe_config()
    assert "api_key" in safe
    # API keys should be masked or empty
    assert safe.get("api_key") == "" or "***" in str(safe.get("api_key"))


def test_github_token_defaults_empty():
    """Test that github_token defaults to empty string."""
    from config import Settings

    s = Settings()
    assert s.github_token == ""


def test_translation_enabled_default():
    """translation_enabled defaults to False (opt-in feature)."""
    settings = reload_settings()
    assert settings.translation_enabled is False


def test_translation_enabled_env_is_ignored(monkeypatch):
    """``translation_enabled`` is a UI field — env vars are ignored.

    Since v0.88.0-beta translation_enabled is configured exclusively via
    the UI (Settings → Translation). Setting SUBLARR_TRANSLATION_ENABLED
    has no effect; users must enable the feature through the UI.
    """
    monkeypatch.setenv("SUBLARR_TRANSLATION_ENABLED", "true")
    settings = reload_settings()
    # Default preserved despite env var being set.
    assert settings.translation_enabled is False


def test_translation_enabled_via_db_override():
    """``translation_enabled`` is settable through the DB-override path."""
    settings = reload_settings(overrides={"translation_enabled": "true"})
    assert settings.translation_enabled is True
    # Reset for downstream tests
    reload_settings()


def test_translation_default_backend_fields_exposed():
    """The global default-backend keys are UISettings so the /config API
    surfaces + accepts them (the Backends-page control reads/writes them).
    Regression: they were config_entries-only and invisible to /config, so the
    control always displayed the fallback 'ollama'."""
    settings = get_settings()
    assert settings.translation_default_backend == "ollama"
    assert settings.translation_default_fallback == ""
    # must be part of the serialized settings surface (what /config returns)
    dumped = settings.model_dump()
    assert "translation_default_backend" in dumped
    assert "translation_default_fallback" in dumped
