"""Subliminal-flavor wrapper: NapiProjekt.

NapiProjekt is a free Polish-focused subtitle source. No auth.
"""

from __future__ import annotations

import providers._vendor  # noqa: F401
from providers.registry import register_provider
from providers.subliminal_adapter import SubliminalProviderAdapter


@register_provider
class NapiProjektSubliminalProvider(SubliminalProviderAdapter):
    name = "napiprojekt_subliminal"
    languages = {"pl", "en"}
    config_fields = []

    def __init__(self, **config):
        from subliminal.providers.napiprojekt import NapiProjektProvider

        super().__init__(
            subliminal_provider_cls=NapiProjektProvider,
            provider_name="napiprojekt_subliminal",
            **config,
        )
