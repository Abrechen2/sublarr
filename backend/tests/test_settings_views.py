"""Tests for Settings grouped view properties."""

import pytest


def test_general_view_delegates(app_ctx):
    from config import get_settings

    s = get_settings()
    assert s.general.port == s.port
    assert s.general.log_level == s.log_level
    assert s.general.db_path == s.db_path
    assert s.general.redis_url == s.redis_url


def test_translation_view_delegates(app_ctx):
    from config import get_settings

    s = get_settings()
    assert s.translation.ollama_url == s.ollama_url
    assert s.translation.target_language == s.target_language
    assert s.translation.batch_size == s.batch_size
    assert s.translation.glossary_enabled == s.glossary_enabled


def test_providers_view_delegates(app_ctx):
    from config import get_settings

    s = get_settings()
    assert s.providers.providers_enabled == s.providers_enabled
    assert s.providers.provider_search_timeout == s.provider_search_timeout
    assert s.providers.circuit_breaker_failure_threshold == s.circuit_breaker_failure_threshold


def test_media_servers_view_delegates(app_ctx):
    from config import get_settings

    s = get_settings()
    assert s.media_servers.sonarr_url == s.sonarr_url
    assert s.media_servers.streaming_enabled == s.streaming_enabled
    assert s.media_servers.ffmpeg_timeout == s.ffmpeg_timeout


def test_scanning_view_delegates(app_ctx):
    from config import get_settings

    s = get_settings()
    assert s.scanning.wanted_anime_only == s.wanted_anime_only
    assert s.scanning.upgrade_enabled == s.upgrade_enabled
    assert s.scanning.anidb_enabled == s.anidb_enabled


def test_view_attribute_error_on_unknown_field(app_ctx):
    from config import get_settings

    s = get_settings()
    with pytest.raises(AttributeError):
        _ = s.general.nonexistent_field_xyz


def test_flat_fields_unchanged(app_ctx):
    """Original flat access must still work after adding views."""
    from config import get_settings

    s = get_settings()
    # Flat access still works
    assert isinstance(s.ollama_url, str)
    assert isinstance(s.port, int)
    # View access returns same value
    assert s.translation.ollama_url == s.ollama_url
    assert s.general.port == s.port


def test_view_is_read_only(app_ctx):
    """Setting attributes on a view must raise AttributeError."""
    from config import get_settings

    s = get_settings()
    with pytest.raises(AttributeError):
        s.general.port = 9999


def test_views_are_importable():
    from config import (
        GeneralSettings,
        MediaServerSettings,
        ProviderSettings,
        ScanningSettings,
        TranslationSettings,
    )

    assert all(
        c is not None
        for c in [
            GeneralSettings,
            TranslationSettings,
            ProviderSettings,
            MediaServerSettings,
            ScanningSettings,
        ]
    )
