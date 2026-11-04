from unittest.mock import MagicMock

import pytest

from providers.base import VideoQuery
from providers.jimaku import JimakuProvider


def _search_with_file(provider: JimakuProvider, filename: str, languages: list[str]):
    provider.session = MagicMock()
    provider._search_by_name = MagicMock(return_value=[{"id": 7, "name": "Example Show"}])
    provider._get_entry_files = MagicMock(
        return_value=[(filename, "https://jimaku.cc/files/example.ass", False)]
    )
    return provider.search(
        VideoQuery(series_title="Example Show", season=1, episode=1, languages=languages)
    )


def test_unmarked_file_is_japanese_by_default():
    # The behaviour before the setting existed; an update keeps it.
    provider = JimakuProvider(api_key="test")

    results = _search_with_file(provider, "Example.Show.S01E01.ass", ["ja"])

    assert len(results) == 1
    assert results[0].language == "ja"


def test_unmarked_file_can_be_skipped():
    provider = JimakuProvider(api_key="test", unknown_language_fallback="none")

    assert provider._detect_language("Example.Show.S01E01.ass") is None
    assert _search_with_file(provider, "Example.Show.S01E01.ass", ["en"]) == []
    assert _search_with_file(provider, "Example.Show.S01E01.ass", ["ja"]) == []


def test_unmarked_file_can_use_explicit_english_fallback():
    provider = JimakuProvider(api_key="test", unknown_language_fallback="en")

    results = _search_with_file(provider, "Example.Show.S01E01.ass", ["en"])

    assert len(results) == 1
    assert results[0].language == "en"


def test_explicit_filename_language_marker_overrides_fallback():
    provider = JimakuProvider(api_key="test", unknown_language_fallback="en")

    results = _search_with_file(provider, "Example.Show.S01E01.ja.ass", ["ja"])

    assert len(results) == 1
    assert results[0].language == "ja"
    assert _search_with_file(provider, "Example.Show.S01E01.ja.ass", ["en"]) == []


def test_invalid_fallback_is_disabled():
    provider = JimakuProvider(api_key="test", unknown_language_fallback="de")

    assert provider.unknown_language_fallback == "none"
    assert _search_with_file(provider, "Example.Show.S01E01.ass", ["en"]) == []


def test_fallback_setting_keeps_japanese_and_is_in_provider_config():
    from config_settings import Settings
    from config_views import ProviderSettings

    field = next(
        field
        for field in JimakuProvider.config_fields
        if field["key"] == "jimaku_unknown_language_fallback"
    )
    settings = Settings()

    assert field["default"] == "ja"
    assert field["options"] == ["none", "en", "ja"]
    assert settings.jimaku_unknown_language_fallback == "ja"
    assert ProviderSettings(settings).jimaku_unknown_language_fallback == "ja"
