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

from providers.base import ProviderRateLimitError, SubtitleFormat, SubtitleResult, VideoQuery
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
        # Phase 4a: KeySelector is now in the gate path — feed a stub key.
        ks_mock = MagicMock()
        ks_mock.pick.return_value = {
            "id": 1,
            "api_key": "x",
            "username": None,
            "password": None,
        }
        monkeypatch.setattr("providers.search_coordinator.get_key_selector", lambda: ks_mock)

        manager.search(_make_query())

        provider.search.assert_called_once()
        budget_allows.consume.assert_called_once_with("test_provider", key_id=1)

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


class TestRecord429Hook:
    """Phase 3: record_429 is called on ProviderRateLimitError."""

    def test_rate_limit_calls_record_429_with_day_window_by_default(
        self, app_ctx, monkeypatch, budget_allows
    ):
        """retry_after > 120 → window=DAY, limit from rate_limits['free']['day']."""
        provider = _make_provider("opensubtitles")
        provider.search.side_effect = ProviderRateLimitError("rate limited", retry_after=3600)
        manager = _build_manager(monkeypatch, provider)
        monkeypatch.setattr(
            "providers.search_coordinator.get_budget_manager", lambda: budget_allows
        )
        # Phase 4a: KeySelector is now in the gate path — feed a stub key.
        ks_mock = MagicMock()
        ks_mock.pick.return_value = {
            "id": 1,
            "api_key": "x",
            "username": None,
            "password": None,
        }
        monkeypatch.setattr("providers.search_coordinator.get_key_selector", lambda: ks_mock)
        # Prevent the existing throttle persistence (auto_disable_provider) from
        # touching the DB during this test.
        monkeypatch.setattr(
            "db.providers.auto_disable_provider", lambda *a, **kw: None, raising=False
        )

        manager.search(_make_query())

        budget_allows.record_429.assert_called_once()
        args, kwargs = budget_allows.record_429.call_args
        from services.provider_budget import BudgetWindow

        # Positional: (provider_name,)
        assert args[0] == "opensubtitles"
        assert kwargs["window"] == BudgetWindow.DAY
        assert kwargs["configured_limit"] == 1000  # rate_limits["free"]["day"] from _make_provider

    def test_short_retry_after_classifies_as_second_window(
        self, app_ctx, monkeypatch, budget_allows
    ):
        """retry_after <= 120 → window=SECOND, limit from rate_limits['free']['second']."""
        provider = _make_provider("opensubtitles")
        provider.search.side_effect = ProviderRateLimitError("too fast", retry_after=60)
        manager = _build_manager(monkeypatch, provider)
        monkeypatch.setattr(
            "providers.search_coordinator.get_budget_manager", lambda: budget_allows
        )
        # Phase 4a: KeySelector is now in the gate path — feed a stub key.
        ks_mock = MagicMock()
        ks_mock.pick.return_value = {
            "id": 1,
            "api_key": "x",
            "username": None,
            "password": None,
        }
        monkeypatch.setattr("providers.search_coordinator.get_key_selector", lambda: ks_mock)
        monkeypatch.setattr(
            "db.providers.auto_disable_provider", lambda *a, **kw: None, raising=False
        )

        manager.search(_make_query())

        budget_allows.record_429.assert_called_once()
        kwargs = budget_allows.record_429.call_args.kwargs
        from services.provider_budget import BudgetWindow

        assert kwargs["window"] == BudgetWindow.SECOND
        assert kwargs["configured_limit"] == 5  # rate_limits["free"]["second"]

    def test_budget_disabled_skips_record_429(self, app_ctx, monkeypatch, budget_allows):
        """When provider_budget_enabled=False, record_429 must not fire."""
        provider = _make_provider("opensubtitles")
        provider.search.side_effect = ProviderRateLimitError("rate limited", retry_after=3600)
        manager = _build_manager(monkeypatch, provider)
        manager.settings = manager.settings.model_copy(update={"provider_budget_enabled": False})
        monkeypatch.setattr(
            "providers.search_coordinator.get_budget_manager", lambda: budget_allows
        )
        monkeypatch.setattr(
            "db.providers.auto_disable_provider", lambda *a, **kw: None, raising=False
        )

        manager.search(_make_query())

        budget_allows.record_429.assert_not_called()

    def test_missing_window_limit_skips_record_429(self, app_ctx, monkeypatch, budget_allows):
        """When rate_limits[tier] has no matching window, record_429 must not fire."""
        # vip tier has "day" but no "second"; retry_after=60 classifies as SECOND.
        vip_limits = {"vip": {"day": 500}}
        provider = _make_provider("vip_provider", tier="vip", rate_limits=vip_limits)
        provider.search.side_effect = ProviderRateLimitError("too fast", retry_after=60)
        manager = _build_manager(monkeypatch, provider)
        monkeypatch.setattr(
            "providers.search_coordinator.get_budget_manager", lambda: budget_allows
        )
        monkeypatch.setattr(
            "db.providers.auto_disable_provider", lambda *a, **kw: None, raising=False
        )

        manager.search(_make_query())

        budget_allows.record_429.assert_not_called()


class TestKeySelectorIntegration:
    """Phase 4a: SearchCoordinator routes each call through KeySelector."""

    def test_allowed_budget_consumes_with_key_id(self, app_ctx, monkeypatch, budget_allows):
        provider = _make_provider("opensubtitles")
        manager = _build_manager(monkeypatch, provider)
        monkeypatch.setattr(
            "providers.search_coordinator.get_budget_manager", lambda: budget_allows
        )
        ks_mock = MagicMock()
        ks_mock.pick.return_value = {
            "id": 42,
            "api_key": "k",
            "username": None,
            "password": None,
        }
        monkeypatch.setattr("providers.search_coordinator.get_key_selector", lambda: ks_mock)

        manager.search(_make_query())

        # consume must be called with key_id=42 (kwarg)
        budget_allows.consume.assert_called_once()
        args, kwargs = budget_allows.consume.call_args
        assert args[0] == "opensubtitles"
        assert kwargs.get("key_id") == 42

    def test_selector_returns_none_skips_provider(self, app_ctx, monkeypatch, budget_allows):
        provider = _make_provider("opensubtitles")
        manager = _build_manager(monkeypatch, provider)
        monkeypatch.setattr(
            "providers.search_coordinator.get_budget_manager", lambda: budget_allows
        )
        ks_mock = MagicMock()
        ks_mock.pick.return_value = None
        monkeypatch.setattr("providers.search_coordinator.get_key_selector", lambda: ks_mock)

        manager.search(_make_query())

        provider.search.assert_not_called()
        budget_allows.consume.assert_not_called()

    def test_selector_result_injects_credentials_on_provider(
        self, app_ctx, monkeypatch, budget_allows
    ):
        provider = _make_provider("opensubtitles")
        manager = _build_manager(monkeypatch, provider)
        monkeypatch.setattr(
            "providers.search_coordinator.get_budget_manager", lambda: budget_allows
        )
        ks_mock = MagicMock()
        ks_mock.pick.return_value = {
            "id": 7,
            "api_key": "my-key",
            "username": "user",
            "password": "pw",
        }
        monkeypatch.setattr("providers.search_coordinator.get_key_selector", lambda: ks_mock)

        manager.search(_make_query())

        # By the time provider.search is called, credentials from the pool row
        # must have been injected onto the provider instance.
        assert provider.api_key == "my-key"
        assert provider.username == "user"
        assert provider.password == "pw"

    def test_budget_gate_unchanged_when_budget_enabled_is_false(
        self, app_ctx, monkeypatch, budget_allows
    ):
        """Disabling provider_budget_enabled bypasses KeySelector too —
        legacy path still works without pool rows."""
        provider = _make_provider("opensubtitles")
        manager = _build_manager(monkeypatch, provider)
        manager.settings = manager.settings.model_copy(update={"provider_budget_enabled": False})
        ks_mock = MagicMock()
        monkeypatch.setattr("providers.search_coordinator.get_key_selector", lambda: ks_mock)
        manager.search(_make_query())

        ks_mock.pick.assert_not_called()
        provider.search.assert_called_once()
