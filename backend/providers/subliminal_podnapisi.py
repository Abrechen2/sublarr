"""Subliminal-flavor wrapper: Podnapisi.

Free public subtitle source. No auth. Supports movies + TV.
"""

from __future__ import annotations

import providers._vendor  # noqa: F401
from providers.registry import register_provider
from providers.subliminal_adapter import SubliminalProviderAdapter


@register_provider
class PodnapisiSubliminalProvider(SubliminalProviderAdapter):
    name = "podnapisi_subliminal"
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
        "da",
        "fi",
        "nl",
        "no",
        "sv",
        "tr",
        "zh",
        "ja",
        "ko",
        "ar",
        "he",
        "sl",
        "hr",
        "sr",
        "bg",
        "mk",
    }
    config_fields = []

    def __init__(self, **config):
        from subliminal.providers.podnapisi import PodnapisiProvider

        super().__init__(
            subliminal_provider_cls=PodnapisiProvider,
            provider_name="podnapisi_subliminal",
            **config,
        )
