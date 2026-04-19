"""Pilot wrapper that exposes Subliminal's OpenSubtitles XML-RPC provider.

Registered as 'opensubtitles_subliminal' — distinct from Sublarr's native
'opensubtitles_fetch' (REST API with key pools) to keep circuit-breaker and
rate-limit state per-flavor.
"""

from __future__ import annotations

import providers._vendor  # noqa: F401 — side-effect import
from providers.registry import register_provider
from providers.subliminal_adapter import SubliminalProviderAdapter


@register_provider
class OpenSubtitlesSubliminalProvider(SubliminalProviderAdapter):
    """Subliminal's OpenSubtitles provider, wrapped through SubliminalProviderAdapter."""

    name = "opensubtitles_subliminal"
    languages = {"en", "de", "es", "fr", "it", "nl", "pl", "pt", "ru", "ja", "zh"}

    # Declarative config fields for the dynamic UI form
    config_fields = [
        {
            "key": "username",
            "label": "Username",
            "type": "text",
            "required": True,
            "default": "",
        },
        {
            "key": "password",
            "label": "Password",
            "type": "password",
            "required": True,
            "default": "",
        },
    ]

    def __init__(self, **config):
        from subliminal.providers.opensubtitles import OpenSubtitlesProvider

        super().__init__(
            subliminal_provider_cls=OpenSubtitlesProvider,
            provider_name="opensubtitles_subliminal",
            **config,
        )
