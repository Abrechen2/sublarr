"""Pilot test for opensubtitles_subliminal registration."""

import providers._vendor  # noqa: F401


def test_pilot_provider_registered():
    """After import_builtin_providers runs, 'opensubtitles_subliminal' is registered."""
    from providers.registry import _PROVIDER_CLASSES, import_builtin_providers

    import_builtin_providers()
    assert "opensubtitles_subliminal" in _PROVIDER_CLASSES
    cls = _PROVIDER_CLASSES["opensubtitles_subliminal"]
    assert cls.name == "opensubtitles_subliminal"


def test_pilot_provider_instantiates_via_adapter():
    """Instantiating opensubtitles_subliminal gives a SubliminalProviderAdapter."""
    from providers.registry import _PROVIDER_CLASSES, import_builtin_providers
    from providers.subliminal_adapter import SubliminalProviderAdapter

    import_builtin_providers()
    cls = _PROVIDER_CLASSES["opensubtitles_subliminal"]
    instance = cls(username="u", password="p")
    assert isinstance(instance, SubliminalProviderAdapter)
