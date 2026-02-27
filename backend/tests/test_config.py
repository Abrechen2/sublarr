"""Tests for config.py — Settings and language tag handling."""

import os

import pytest

from config import _get_language_tags, get_settings, reload_settings


def test_default_settings():
    """Test default settings values."""
    settings = get_settings()
    assert settings.port == 5765
    assert settings.source_language == "en"
    assert settings.target_language == "de"
    assert settings.ollama_url == "http://localhost:11434"


def test_env_prefix():
    """Test that SUBLARR_ prefix works."""
    os.environ["SUBLARR_PORT"] = "8080"
    os.environ["SUBLARR_TARGET_LANGUAGE"] = "fr"
    settings = reload_settings()
    assert settings.port == 8080
    assert settings.target_language == "fr"
    # Cleanup
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
