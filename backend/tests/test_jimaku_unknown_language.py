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


def test_unmarked_file_is_not_assumed_to_be_japanese_or_english():
    provider = JimakuProvider(api_key="test")

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


def test_fallback_setting_is_opt_in_and_available_in_provider_config():
    from config_settings import Settings
    from config_views import ProviderSettings

    field = next(
        field for field in JimakuProvider.config_fields
        if field["key"] == "jimaku_unknown_language_fallback"
    )
    settings = Settings()

    assert field["default"] == "none"
    assert field["options"] == ["none", "en", "ja"]
    assert settings.jimaku_unknown_language_fallback == "none"
    assert ProviderSettings(settings).jimaku_unknown_language_fallback == "none"
