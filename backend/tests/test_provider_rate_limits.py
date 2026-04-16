"""Tests for rate_limits classvar — every enabled provider must declare realistic limits.

The ProviderBudgetManager consumes this metadata (see task 7). Missing or empty
rate_limits means the provider can never be budget-gated, so this is a contract
test that runs in CI.
"""

from __future__ import annotations

import pytest

# Providers that are listed in the prod `providers_enabled` config key as of V1.
# If you enable/disable a provider there, update this list too — intentionally
# hard-coded so accidentally shipping a provider without rate_limits fails CI.
ENABLED_PROVIDER_MODULES = [
    ("providers.animetosho", "AnimeToshoProvider"),
    ("providers.opensubtitles", "OpenSubtitlesProvider"),
    ("providers.subdl", "SubDLProvider"),
    ("providers.gestdown", "GestdownProvider"),
    ("providers.kitsunekko", "KitsunekkoProvider"),
    ("providers.napisy24", "Napisy24Provider"),
    ("providers.titrari", "TitrariProvider"),
    ("providers.subscene", "SubsceneProvider"),
    ("providers.addic7ed", "Addic7edProvider"),
    ("providers.tvsubtitles", "TVSubtitlesProvider"),
]


@pytest.mark.parametrize(("module_path", "class_name"), ENABLED_PROVIDER_MODULES)
def test_provider_declares_rate_limits(module_path: str, class_name: str):
    module = __import__(module_path, fromlist=[class_name])
    cls = getattr(module, class_name)
    limits = getattr(cls, "rate_limits", None)
    assert limits is not None, f"{class_name} is missing rate_limits classvar"
    assert isinstance(limits, dict), f"{class_name}.rate_limits must be a dict"
    assert "free" in limits, f"{class_name}.rate_limits must declare 'free' tier"

    for tier, windows in limits.items():
        assert isinstance(windows, dict), f"{class_name}.rate_limits[{tier!r}] must be a dict"
        assert "day" in windows, f"{class_name}.rate_limits[{tier!r}] missing 'day' key"
        for window_name, value in windows.items():
            assert window_name in ("second", "hour", "day"), (
                f"{class_name}.rate_limits[{tier!r}][{window_name!r}]: "
                f"only second/hour/day are honoured"
            )
            assert isinstance(value, int) and value > 0, (
                f"{class_name}.rate_limits[{tier!r}][{window_name!r}] "
                f"must be a positive int (got {value!r})"
            )


def test_base_class_declares_default_rate_limits():
    """Base SubtitleProvider has a conservative default so unknown subclasses
    are still rate-gated rather than uncapped."""
    from providers.base import SubtitleProvider

    limits = getattr(SubtitleProvider, "rate_limits", None)
    assert limits is not None
    assert "free" in limits
    assert "day" in limits["free"]


def test_opensubtitles_has_vip_tiers():
    """Tier auto-detection (task 4) relies on these tier names existing."""
    from providers.opensubtitles import OpenSubtitlesProvider

    assert "free" in OpenSubtitlesProvider.rate_limits
    assert "vip" in OpenSubtitlesProvider.rate_limits
    # VIP day limit must be strictly greater than free
    assert (
        OpenSubtitlesProvider.rate_limits["vip"]["day"]
        > OpenSubtitlesProvider.rate_limits["free"]["day"]
    )
