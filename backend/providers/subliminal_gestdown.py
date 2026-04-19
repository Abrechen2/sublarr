"""Subliminal-flavor wrapper: Gestdown.

Gestdown is a free, unauthenticated TV subtitle API (successor to Addic7ed-API).
No config fields required.
"""

from __future__ import annotations

import providers._vendor  # noqa: F401
from providers.registry import register_provider
from providers.subliminal_adapter import SubliminalProviderAdapter


@register_provider
class GestdownSubliminalProvider(SubliminalProviderAdapter):
    name = "gestdown_subliminal"
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
    }
    config_fields = []

    def __init__(self, **config):
        from subliminal.providers.gestdown import GestdownProvider

        super().__init__(
            subliminal_provider_cls=GestdownProvider,
            provider_name="gestdown_subliminal",
            **config,
        )
