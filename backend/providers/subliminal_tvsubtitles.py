"""Subliminal-flavor wrapper: TVsubtitles.

Scrape-based TV subtitle source. No auth.
"""

from __future__ import annotations

import providers._vendor  # noqa: F401
from providers.registry import register_provider
from providers.subliminal_adapter import SubliminalProviderAdapter


@register_provider
class TVsubtitlesSubliminalProvider(SubliminalProviderAdapter):
    name = "tvsubtitles_subliminal"
    languages = {
        "en",
        "de",
        "es",
        "fr",
        "it",
        "pt",
        "ru",
        "pl",
        "cs",
        "nl",
        "sv",
        "tr",
        "ja",
        "ko",
        "zh",
        "ar",
        "he",
        "el",
        "hu",
        "ro",
    }
    config_fields = []

    def __init__(self, **config):
        from subliminal.providers.tvsubtitles import TVsubtitlesProvider

        super().__init__(
            subliminal_provider_cls=TVsubtitlesProvider,
            provider_name="tvsubtitles_subliminal",
            **config,
        )
