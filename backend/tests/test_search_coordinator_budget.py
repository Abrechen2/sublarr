"""Tests for ProviderBudgetManager integration into SearchCoordinator.search().

Covers the budget-gate block added to providers/search_coordinator.py:
- Exhausted budget -> provider skipped silently, no consume().
- Allowed budget -> consume() called once, provider.search() called once.
- Gate disabled via provider_budget_enabled -> check() never invoked.
- Tier lookup resolves the correct rate_limits[tier] dict.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from providers.base import SubtitleFormat, SubtitleResult, VideoQuery
from services.provider_budget import BudgetDecision, ProviderBudgetManager


def _make_result(provider_name: str = "test_provider") -> SubtitleResult:
    return SubtitleResult(
        provider_name=provider_name,
        subtitle_id="sub-001",
        language="de",
        format=SubtitleFormat.SRT,
        filename="test.srt",
        score=80,
        release_info="",
        hearing_impaired=False,
        forced=False,
        provider_data={},
    )


def _make_provider(name: str = "test_provider", tier: str = "free", rate_limits=None):
    """Build a lightweight fake provider with tier + rate_limits on its class.

    The gate reads ``type(provider).rate_limits`` so a real class with that
    ClassVar is required (a bare ``MagicMock().rate_limits`` would be read via
    ``type(mock).rate_limits`` and return a MagicMock, not a dict).
    """
    _rate_limits = rate_limits or {"free": {"second": 5, "hour": 200, "day": 1000}}
    _result = _make_result(name)

    class _FakeProvider:
        rate_limits = _rate_limits

        def __init__(self):
            self.name = name
            self.tier = tier
            # Avoid _search_provider_with_retry's "session is None" short-circuit.
            self.session = object()
            self.search = MagicMock(return_value=[_result])
            self.download = MagicMock(return_value=b"")

    return _FakeProvider()


def _patch_db_noop(monkeypatch):
    monkeypatch.setattr("db.providers.is_provider_auto_disabled", lambda name: False)
    monkeypatch.setattr("db.providers.update_provider_stats", lambda *a, **kw: None)
    monkeypatch.setattr("db.providers.cache_provider_results", lambda *a, **kw: None)
    monkeypatch.setattr("db.providers.get_cached_results", lambda *a, **kw: None)
    monkeypatch.setattr("db.providers.get_all_provider_stats", lambda: [], raising=False)
    monkeypatch.setattr("db.blacklist.is_blacklisted", lambda *a, **kw: False)


def _bypass_fast_cache(monkeypatch):
    monkeypatch.setattr("providers.ProviderManager._get_cache_backend", staticmethod(lambda: None))


def _make_query() -> VideoQuery:
    return VideoQuery(file_path="/test/movie.mkv", languages=["de"], forced_only=False)


@pytest.fixture
def budget_exhausted():
    m = MagicMock(spec=ProviderBudgetManager)
    m.check.return_value = BudgetDecision(allow=False, wait_seconds=3600, reason="day limit")
    return m


@pytest.fixture
def budget_allows():
    m = MagicMock(spec=ProviderBudgetManager)
    m.check.return_value = BudgetDecision(allow=True)
    return m


def _build_manager(monkeypatch, provider):
    from providers import ProviderManager

    _patch_db_noop(monkeypatch)
    _bypass_fast_cache(monkeypatch)

    manager = ProviderManager()
    manager._providers.clear()
    manager._providers[provider.name] = provider

    cb = MagicMock()
    cb.allow_request.return_value = True
    manager._circuit_breakers[provider.name] = cb

    return manager


class TestBudgetGate:
    """Integration tests around SearchCoordinatorMixin.search() budget gate."""

    def test_exhausted_budget_skips_provider_silently(self, app_ctx, monkeypatch, budget_exhausted):
        provider = _make_provider("test_provider")
        manager = _build_manager(monkeypatch, provider)
        # provider_budget_enabled is True by default — don't touch settings here.
        monkeypatch.setattr(
            "providers.search_coordinator.get_budget_manager", lambda: budget_exhausted
        )

        manager.search(_make_query())

        provider.search.assert_not_called()
        budget_exhausted.consume.assert_not_called()

    def test_allowed_budget_consumes_and_searches(self, app_ctx, monkeypatch, budget_allows):
        provider = _make_provider("test_provider")
        manager = _build_manager(monkeypatch, provider)
        monkeypatch.setattr(
            "providers.search_coordinator.get_budget_manager", lambda: budget_allows
        )

        manager.search(_make_query())

        provider.search.assert_called_once()
        budget_allows.consume.assert_called_once_with("test_provider")

    def test_gate_disabled_via_settings_bypasses_budget(self, app_ctx, monkeypatch):
        provider = _make_provider("test_provider")
        manager = _build_manager(monkeypatch, provider)

        # Disable the gate on this manager's settings
        manager.settings = manager.settings.model_copy(update={"provider_budget_enabled": False})

        sentinel_budget = MagicMock(spec=ProviderBudgetManager)
        monkeypatch.setattr(
            "providers.search_coordinator.get_budget_manager", lambda: sentinel_budget
        )

        manager.search(_make_query())

        sentinel_budget.check.assert_not_called()
        sentinel_budget.consume.assert_not_called()
        provider.search.assert_called_once()

    def test_tier_lookup_passes_correct_rate_limits(self, app_ctx, monkeypatch, budget_allows):
        vip_limits = {
            "free": {"second": 5, "hour": 200, "day": 1000},
            "vip": {"second": 10, "hour": 1000, "day": 10000},
        }
        provider = _make_provider("vip_provider", tier="vip", rate_limits=vip_limits)
        manager = _build_manager(monkeypatch, provider)
        monkeypatch.setattr(
            "providers.search_coordinator.get_budget_manager", lambda: budget_allows
        )

        manager.search(_make_query())

        budget_allows.check.assert_called_once()
        args, kwargs = budget_allows.check.call_args
        # check(name, limits_dict) — argument order depends on implementation
        # Accept positional or keyword
        passed_limits = args[1] if len(args) > 1 else kwargs.get("limits")
        passed_name = args[0] if args else kwargs.get("provider") or kwargs.get("name")
        assert passed_name == "vip_provider"
        assert passed_limits == vip_limits["vip"]
        assert passed_limits["day"] == 10000
