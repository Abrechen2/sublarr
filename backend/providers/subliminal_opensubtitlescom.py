"""Subliminal-flavor wrapper: OpenSubtitles.com (REST API).

Distinct from:
- Sublarr's native `opensubtitles_fetch` (uses Sublarr's key-pool + budget manager)
- `opensubtitles_subliminal` (XML-RPC legacy, shipped in B1)

This flavor uses the official REST API via Subliminal's implementation.
Requires api_key, username, password.
"""

from __future__ import annotations

import providers._vendor  # noqa: F401
from providers.registry import register_provider
from providers.subliminal_adapter import SubliminalProviderAdapter


@register_provider
class OpenSubtitlesComSubliminalProvider(SubliminalProviderAdapter):
    name = "opensubtitlescom_subliminal"
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
        "el",
        "hu",
        "ro",
        "sk",
        "uk",
        "vi",
    }
    config_fields = [
        {"key": "apikey", "label": "API Key", "type": "password", "required": True, "default": ""},
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
        from subliminal.providers.opensubtitlescom import OpenSubtitlesComProvider

        super().__init__(
            subliminal_provider_cls=OpenSubtitlesComProvider,
            provider_name="opensubtitlescom_subliminal",
            **config,
        )
