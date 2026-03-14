"""Tests for glossary_enabled and glossary_max_terms settings."""

from config import Settings


def test_glossary_disabled_setting_exists():
    """Settings class has a glossary_enabled field defaulting to True."""
    s = Settings()
    assert hasattr(s, "glossary_enabled")
    assert s.glossary_enabled is True


def test_glossary_max_terms_setting_exists():
    """Settings class has a glossary_max_terms field defaulting to 100."""
    s = Settings()
    assert hasattr(s, "glossary_max_terms")
    assert s.glossary_max_terms == 100
