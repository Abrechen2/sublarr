"""Subliminal-flavor wrapper: Addic7ed.

Addic7ed is a scrape-based TV subtitle source requiring username+password.
Subliminal's implementation handles the HTML parsing + session auth.
Registered as 'addic7ed_subliminal' to coexist with Sublarr's native
'addic7ed' provider.
"""

from __future__ import annotations

import providers._vendor  # noqa: F401 — side-effect import
from providers.registry import register_provider
from providers.subliminal_adapter import SubliminalProviderAdapter


@register_provider
class Addic7edSubliminalProvider(SubliminalProviderAdapter):
    name = "addic7ed_subliminal"
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
    }
    config_fields = [
        {"key": "username", "label": "Username", "type": "text", "required": True, "default": ""},
        {
            "key": "password",
            "label": "Password",
            "type": "password",
            "required": True,
            "default": "",
        },
    ]

    def __init__(self, **config):
        from subliminal.providers.addic7ed import Addic7edProvider

        super().__init__(
            subliminal_provider_cls=Addic7edProvider,
            provider_name="addic7ed_subliminal",
            **config,
        )
