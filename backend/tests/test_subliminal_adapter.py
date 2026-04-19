"""Unit tests for SubliminalProviderAdapter."""

import pytest

import providers._vendor  # noqa: F401 — trigger sys.path shim at test-collection time

from providers.base import SubtitleProvider


def test_adapter_is_a_sublarr_provider():
    """SubliminalProviderAdapter must be a subclass of Sublarr's SubtitleProvider."""
    from providers.subliminal_adapter import SubliminalProviderAdapter

    assert issubclass(SubliminalProviderAdapter, SubtitleProvider)


def test_adapter_constructor_accepts_provider_class():
    """Constructor takes a Subliminal Provider class + Sublarr config kwargs."""
    from subliminal.providers.opensubtitles import OpenSubtitlesProvider
    from providers.subliminal_adapter import SubliminalProviderAdapter

    adapter = SubliminalProviderAdapter(
        subliminal_provider_cls=OpenSubtitlesProvider,
        provider_name="opensubtitles_subliminal",
        username="test",
        password="test",
    )
    assert adapter.name == "opensubtitles_subliminal"
    assert adapter._subliminal_provider_cls is OpenSubtitlesProvider
