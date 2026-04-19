"""Parametrized registration tests for Plan B2 Subliminal-flavor providers."""

import providers._vendor  # noqa: F401,I001 — trigger sys.path shim

import pytest

from providers.subliminal_adapter import SubliminalProviderAdapter


B2_PROVIDER_NAMES = [
    "addic7ed_subliminal",
    "gestdown_subliminal",
    "napiprojekt_subliminal",
    "opensubtitlescom_subliminal",
    "podnapisi_subliminal",
    "tvsubtitles_subliminal",
]


@pytest.mark.parametrize("provider_name", B2_PROVIDER_NAMES)
def test_b2_provider_registered(provider_name):
    """Each B2 Subliminal-flavor provider must be registered after import_builtin_providers()."""
    from providers.registry import _PROVIDER_CLASSES, import_builtin_providers

    import_builtin_providers()
    assert provider_name in _PROVIDER_CLASSES, (
        f"Expected '{provider_name}' in _PROVIDER_CLASSES, got: {sorted(_PROVIDER_CLASSES.keys())}"
    )


@pytest.mark.parametrize("provider_name", B2_PROVIDER_NAMES)
def test_b2_provider_instantiates_via_adapter(provider_name):
    """Each B2 provider must instantiate as a SubliminalProviderAdapter subclass."""
    from providers.registry import _PROVIDER_CLASSES, import_builtin_providers

    import_builtin_providers()
    cls = _PROVIDER_CLASSES[provider_name]
    kwargs = {f["key"]: "dummy" for f in cls.config_fields}
    instance = cls(**kwargs)
    assert isinstance(instance, SubliminalProviderAdapter)
    assert instance.name == provider_name


def test_b2_total_provider_count_meets_goal():
    """After B2 registration, the builtin registry holds >= 23 providers total."""
    from providers.registry import _PROVIDER_CLASSES, import_builtin_providers

    import_builtin_providers()
    assert len(_PROVIDER_CLASSES) >= 23, (
        f"Expected >= 23 registered providers after B2, got {len(_PROVIDER_CLASSES)}: "
        f"{sorted(_PROVIDER_CLASSES.keys())}"
    )
