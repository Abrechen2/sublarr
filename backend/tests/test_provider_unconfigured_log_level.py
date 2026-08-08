"""An unconfigured provider is an expected state, not a warning.

Sublarr ships ~29 providers and most installs configure a handful. Every other
one logged at WARNING that it had no credentials and was disabling itself — and
the manager logged a second, generic WARNING for the same provider right after.
That is roughly a dozen benign WARNING lines on every single startup, which is
what makes `grep WARNING` useless on a log a user sends: in one real 24k-line
report only 3 of 21 ERROR/WARNING-class lines were actionable.

`customapi` already did this correctly at INFO; these tests pin the rest to the
same level. Nothing is hidden — the lines still exist, one level down.
"""

import logging

import pytest

UNCONFIGURED_PROVIDERS = [
    ("providers.jimaku", "JimakuProvider", {}),
    ("providers.opensubtitles", "OpenSubtitlesProvider", {}),
    ("providers.subdl", "SubDLProvider", {}),
    ("providers.legendasdivx", "LegendasDivxProvider", {}),
    ("providers.turkcealtyazi", "TurkcealtyaziProvider", {}),
]


@pytest.mark.parametrize("module_name,class_name,kwargs", UNCONFIGURED_PROVIDERS)
def test_missing_credentials_is_not_a_warning(module_name, class_name, kwargs, caplog):
    import importlib

    module = importlib.import_module(module_name)
    provider = getattr(module, class_name)(**kwargs)

    with caplog.at_level(logging.DEBUG):
        provider.initialize()

    warnings = [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert not warnings, (
        f"{class_name} logged at WARNING for a provider the user simply did not "
        f"configure: {[r.getMessage() for r in warnings]}"
    )


@pytest.mark.parametrize("module_name,class_name,kwargs", UNCONFIGURED_PROVIDERS)
def test_missing_credentials_is_still_reported(module_name, class_name, kwargs, caplog):
    """Downgraded, not deleted — the reason must remain discoverable."""
    import importlib

    module = importlib.import_module(module_name)
    provider = getattr(module, class_name)(**kwargs)

    with caplog.at_level(logging.DEBUG):
        provider.initialize()

    assert caplog.records, f"{class_name} must still say why it disabled itself"
    assert provider.session is None
