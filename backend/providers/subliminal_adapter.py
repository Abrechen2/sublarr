"""Thin adapter that wraps a Subliminal Provider class as a Sublarr SubtitleProvider.

Usage:

    from subliminal.providers.opensubtitles import OpenSubtitlesProvider
    from providers.subliminal_adapter import SubliminalProviderAdapter

    adapter = SubliminalProviderAdapter(
        subliminal_provider_cls=OpenSubtitlesProvider,
        provider_name="opensubtitles_subliminal",
        username="...",
        password="...",
    )
    results = adapter.search(query)
    content = adapter.download(results[0])

The adapter translates between Sublarr's `VideoQuery` / `SubtitleResult` dataclasses
and Subliminal's `Video` / `Subtitle` types.
"""

from __future__ import annotations

import logging

import providers._vendor  # noqa: F401 — side-effect import adds vendor to sys.path

from providers.base import SubtitleProvider, SubtitleResult, VideoQuery

logger = logging.getLogger(__name__)


class SubliminalProviderAdapter(SubtitleProvider):
    """Wraps a Subliminal Provider class and exposes Sublarr's provider interface."""

    # Instance-level overrides so each adapter instance can present a distinct name
    name: str = "subliminal_adapter"

    def __init__(
        self,
        subliminal_provider_cls: type,
        provider_name: str,
        **config,
    ):
        super().__init__(**config)
        self._subliminal_provider_cls = subliminal_provider_cls
        self.name = provider_name
        self._impl = None  # Instantiated in initialize()

    def initialize(self):
        """Instantiate the wrapped Subliminal provider and enter its context."""
        self._impl = self._subliminal_provider_cls(**self._subliminal_kwargs())
        self._impl.initialize()

    def terminate(self):
        """Cleanly tear down the wrapped Subliminal provider."""
        if self._impl is not None:
            try:
                self._impl.terminate()
            finally:
                self._impl = None

    def _subliminal_kwargs(self) -> dict:
        """Subclasses of Subliminal providers accept different kwargs.

        The adapter forwards ALL non-empty values from self.config as kwargs.
        Subliminal providers that don't need certain kwargs ignore them.
        """
        return {k: v for k, v in self.config.items() if v not in (None, "")}

    def search(self, query: VideoQuery) -> list[SubtitleResult]:
        """Not yet implemented — filled in by Task 8."""
        raise NotImplementedError("search() wired up in Task 8")

    def download(self, result: SubtitleResult) -> bytes:
        """Not yet implemented — filled in by Task 9."""
        raise NotImplementedError("download() wired up in Task 9")
