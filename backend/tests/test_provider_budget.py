"""Tests for services.provider_budget — ProviderBudgetManager window math + allow/deny flow."""

from __future__ import annotations

from datetime import UTC, datetime, timezone

import pytest

from services.provider_budget import (
    BudgetDecision,
    BudgetWindow,
    ProviderBudgetManager,
    window_start_for,
)


class TestWindowStartFor:
    """Window-start truncation — deterministic pure function."""

    def test_second_window_truncates_to_second(self):
        now = datetime(2026, 4, 16, 12, 34, 56, 789123, tzinfo=UTC)
        assert window_start_for(BudgetWindow.SECOND, now) == datetime(
            2026, 4, 16, 12, 34, 56, tzinfo=UTC
        )

    def test_hour_window_truncates_to_hour(self):
        now = datetime(2026, 4, 16, 12, 34, 56, tzinfo=UTC)
        assert window_start_for(BudgetWindow.HOUR, now) == datetime(
            2026, 4, 16, 12, 0, 0, tzinfo=UTC
        )

    def test_day_window_truncates_to_midnight_utc(self):
        now = datetime(2026, 4, 16, 12, 34, 56, tzinfo=UTC)
        assert window_start_for(BudgetWindow.DAY, now) == datetime(2026, 4, 16, 0, 0, 0, tzinfo=UTC)


class TestBudgetDecisions:
    """check() — returns allow/deny with reason + wait time."""

    def test_allows_when_all_windows_under_limit(self):
        mgr = ProviderBudgetManager(redis=None, safety_margin_pct=0)
        now = datetime(2026, 4, 16, 12, 0, 0, tzinfo=UTC)
        decision = mgr.check(
            "opensubtitles",
            limits={"second": 5, "hour": 200, "day": 1000},
            now=now,
        )
        assert decision.allow is True
        assert decision.wait_seconds == 0

    def test_blocks_when_day_exhausted_and_reports_wait(self):
        mgr = ProviderBudgetManager(redis=None, safety_margin_pct=0)
        now = datetime(2026, 4, 16, 23, 30, 0, tzinfo=UTC)
        # Simulate 1000 calls already in today's window
        day_start = window_start_for(BudgetWindow.DAY, now)
        mgr._in_memory_counts[("opensubtitles", "day", day_start)] = 1000
        decision = mgr.check("opensubtitles", limits={"day": 1000}, now=now)
        assert decision.allow is False
        assert "day" in decision.reason
        # 30 minutes left until midnight UTC
        assert 1700 <= decision.wait_seconds <= 1800

    def test_blocks_when_second_window_exhausted(self):
        mgr = ProviderBudgetManager(redis=None, safety_margin_pct=0)
        now = datetime(2026, 4, 16, 12, 0, 0, tzinfo=UTC)
        sec_start = window_start_for(BudgetWindow.SECOND, now)
        mgr._in_memory_counts[("opensubtitles", "second", sec_start)] = 5
        decision = mgr.check(
            "opensubtitles",
            limits={"second": 5, "hour": 200, "day": 1000},
            now=now,
        )
        assert decision.allow is False
        assert decision.wait_seconds == 1

    def test_safety_margin_reduces_effective_limit(self):
        mgr = ProviderBudgetManager(redis=None, safety_margin_pct=20)
        now = datetime(2026, 4, 16, 12, 0, 0, tzinfo=UTC)
        day_start = window_start_for(BudgetWindow.DAY, now)
        # With 20% margin, 1000 raw → 800 effective; 800 calls should already block
        mgr._in_memory_counts[("opensubtitles", "day", day_start)] = 800
        decision = mgr.check("opensubtitles", limits={"day": 1000}, now=now)
        assert decision.allow is False


class TestConsumeAndUsage:
    """consume() increments all three windows; get_usage() returns live counts."""

    def test_consume_increments_all_windows(self):
        mgr = ProviderBudgetManager(redis=None, safety_margin_pct=0)
        now = datetime(2026, 4, 16, 12, 34, 56, tzinfo=UTC)
        mgr.consume("opensubtitles", now=now)
        mgr.consume("opensubtitles", now=now)
        usage = mgr.get_usage("opensubtitles", now=now)
        assert usage == {"second": 2, "hour": 2, "day": 2}

    def test_consume_different_providers_are_independent(self):
        mgr = ProviderBudgetManager(redis=None, safety_margin_pct=0)
        now = datetime(2026, 4, 16, 12, 0, 0, tzinfo=UTC)
        mgr.consume("opensubtitles", now=now)
        mgr.consume("subdl", now=now)
        mgr.consume("subdl", now=now)
        assert mgr.get_usage("opensubtitles", now=now) == {"second": 1, "hour": 1, "day": 1}
        assert mgr.get_usage("subdl", now=now) == {"second": 2, "hour": 2, "day": 2}

    def test_get_usage_returns_zero_for_unknown_provider(self):
        mgr = ProviderBudgetManager(redis=None, safety_margin_pct=0)
        now = datetime(2026, 4, 16, 12, 0, 0, tzinfo=UTC)
        assert mgr.get_usage("never_called", now=now) == {"second": 0, "hour": 0, "day": 0}


class TestWindowRollover:
    """Counters naturally reset as the window boundary crosses."""

    def test_second_window_resets_on_next_second(self):
        mgr = ProviderBudgetManager(redis=None, safety_margin_pct=0)
        t0 = datetime(2026, 4, 16, 12, 0, 0, tzinfo=UTC)
        t1 = datetime(2026, 4, 16, 12, 0, 1, tzinfo=UTC)
        mgr.consume("opensubtitles", now=t0)
        # A second later, the per-second counter starts fresh
        assert mgr.get_usage("opensubtitles", now=t1)["second"] == 0
        # Hour and day counters still carry the earlier call
        assert mgr.get_usage("opensubtitles", now=t1)["hour"] == 1
        assert mgr.get_usage("opensubtitles", now=t1)["day"] == 1


class TestSingleton:
    """get_budget_manager() returns a process-wide singleton."""

    def test_get_budget_manager_returns_same_instance(self):
        from services.provider_budget import get_budget_manager

        mgr_a = get_budget_manager()
        mgr_b = get_budget_manager()
        assert mgr_a is mgr_b


class TestRefund:
    """refund() reverses consume()."""

    def test_refund_decrements_all_windows(self):
        mgr = ProviderBudgetManager(redis=None, safety_margin_pct=0)
        now = datetime(2026, 4, 16, 12, 0, 0, tzinfo=UTC)
        mgr.consume("opensubtitles", now=now)
        mgr.consume("opensubtitles", now=now)
        mgr.refund("opensubtitles", now=now)
        usage = mgr.get_usage("opensubtitles", now=now)
        assert usage == {"second": 1, "hour": 1, "day": 1}

    def test_refund_does_not_go_negative(self):
        mgr = ProviderBudgetManager(redis=None, safety_margin_pct=0)
        now = datetime(2026, 4, 16, 12, 0, 0, tzinfo=UTC)
        mgr.refund("opensubtitles", now=now)  # no prior consume
        mgr.refund("opensubtitles", now=now)
        usage = mgr.get_usage("opensubtitles", now=now)
        assert usage == {"second": 0, "hour": 0, "day": 0}


class TestRedisBackend:
    """Redis path — falls back cleanly when Redis raises."""

    def test_consume_tolerates_redis_failure(self):
        class _FailingRedis:
            def incr(self, key):
                raise ConnectionError("redis down")

            def expire(self, key, ttl):
                raise ConnectionError("redis down")

            def get(self, key):
                raise ConnectionError("redis down")

        mgr = ProviderBudgetManager(redis=_FailingRedis(), safety_margin_pct=0)
        now = datetime(2026, 4, 16, 12, 0, 0, tzinfo=UTC)
        # Must not raise — in-memory counter is the fallback
        mgr.consume("opensubtitles", now=now)
        assert mgr.get_usage("opensubtitles", now=now)["second"] == 1


class TestStretchMode:
    """Stretch-mode pacing gate — spreads daily budget evenly across 24h."""

    def _prime_usage(self, mgr, provider, now, day_count):
        """Helper: jam N consumes in the day window without tripping rate-limit counters."""
        from services.provider_budget import BudgetWindow, window_start_for

        day_start = window_start_for(BudgetWindow.DAY, now)
        mgr._in_memory_counts[(provider, "day", day_start)] = day_count

    def test_stretch_allows_when_on_pace(self, monkeypatch):
        from config import get_settings

        monkeypatch.setattr(
            get_settings(), "provider_budget_stretch_mode", "stretch", raising=False
        )
        mgr = ProviderBudgetManager(redis=None, safety_margin_pct=0)
        now = datetime(2026, 4, 16, 6, 0, 0, tzinfo=UTC)  # 6 AM UTC
        # At hour 6, threshold = ceil(1000 * 7/24) = 292. 100 used is well under.
        self._prime_usage(mgr, "opensubtitles", now, day_count=100)
        decision = mgr.check("opensubtitles", limits={"day": 1000}, now=now)
        assert decision.allow is True

    def test_stretch_blocks_when_ahead_of_schedule(self, monkeypatch):
        from config import get_settings

        monkeypatch.setattr(
            get_settings(), "provider_budget_stretch_mode", "stretch", raising=False
        )
        mgr = ProviderBudgetManager(redis=None, safety_margin_pct=0)
        now = datetime(2026, 4, 16, 6, 0, 0, tzinfo=UTC)
        # Threshold at hour 6 = ceil(1000 * 7/24) = 292. Priming with 292 -> at threshold -> blocked.
        self._prime_usage(mgr, "opensubtitles", now, day_count=292)
        decision = mgr.check("opensubtitles", limits={"day": 1000}, now=now)
        assert decision.allow is False
        assert "stretch pace" in decision.reason
        # wait_seconds -> until next hour
        assert 0 < decision.wait_seconds <= 3600

    def test_burst_mode_bypasses_stretch(self, monkeypatch):
        from config import get_settings

        monkeypatch.setattr(get_settings(), "provider_budget_stretch_mode", "burst", raising=False)
        mgr = ProviderBudgetManager(redis=None, safety_margin_pct=0)
        now = datetime(2026, 4, 16, 6, 0, 0, tzinfo=UTC)
        # Deep into the stretch-blocking zone
        self._prime_usage(mgr, "opensubtitles", now, day_count=500)
        decision = mgr.check("opensubtitles", limits={"day": 1000}, now=now)
        assert decision.allow is True

    def test_stretch_still_blocked_by_day_cap(self, monkeypatch):
        from config import get_settings

        monkeypatch.setattr(
            get_settings(), "provider_budget_stretch_mode", "stretch", raising=False
        )
        mgr = ProviderBudgetManager(redis=None, safety_margin_pct=0)
        now = datetime(2026, 4, 16, 6, 0, 0, tzinfo=UTC)
        self._prime_usage(mgr, "opensubtitles", now, day_count=1000)
        decision = mgr.check("opensubtitles", limits={"day": 1000}, now=now)
        # Day cap trips first — reason should be the window-limit message, not stretch
        assert decision.allow is False
        assert "day limit reached" in decision.reason

    def test_stretch_late_in_day_allows_more(self, monkeypatch):
        from config import get_settings

        monkeypatch.setattr(
            get_settings(), "provider_budget_stretch_mode", "stretch", raising=False
        )
        mgr = ProviderBudgetManager(redis=None, safety_margin_pct=0)
        now = datetime(2026, 4, 16, 23, 0, 0, tzinfo=UTC)  # Hour 23
        # Threshold at hour 23 = ceil(1000 * 24/24) = 1000 -> full budget fair game
        self._prime_usage(mgr, "opensubtitles", now, day_count=900)
        decision = mgr.check("opensubtitles", limits={"day": 1000}, now=now)
        assert decision.allow is True

    def test_stretch_noop_when_no_day_limit(self, monkeypatch):
        from config import get_settings

        monkeypatch.setattr(
            get_settings(), "provider_budget_stretch_mode", "stretch", raising=False
        )
        mgr = ProviderBudgetManager(redis=None, safety_margin_pct=0)
        now = datetime(2026, 4, 16, 6, 0, 0, tzinfo=UTC)
        decision = mgr.check("opensubtitles", limits={"second": 5, "hour": 100}, now=now)
        assert decision.allow is True


class TestFactorAwareEffectiveLimit:
    """Task 2 — learned adjustment factor bends the declared limits."""

    def test_effective_limit_applies_learned_factor(self):
        mgr = ProviderBudgetManager(redis=None, safety_margin_pct=0)
        mgr._factors[("opensubtitles", "day")] = 0.5
        assert mgr._effective_limit(1000, provider="opensubtitles", window=BudgetWindow.DAY) == 500

    def test_effective_limit_default_factor_1_0(self):
        mgr = ProviderBudgetManager(redis=None, safety_margin_pct=0)
        # No entry in _factors -> factor defaults to 1.0
        assert mgr._effective_limit(1000, provider="opensubtitles", window=BudgetWindow.DAY) == 1000

    def test_effective_limit_combines_safety_and_factor(self):
        mgr = ProviderBudgetManager(redis=None, safety_margin_pct=20)
        mgr._factors[("opensubtitles", "day")] = 0.5
        # 1000 * 0.5 * 0.8 = 400
        assert mgr._effective_limit(1000, provider="opensubtitles", window=BudgetWindow.DAY) == 400

    def test_check_uses_factor_aware_limit(self):
        mgr = ProviderBudgetManager(redis=None, safety_margin_pct=0)
        mgr._factors[("opensubtitles", "day")] = 0.5
        now = datetime(2026, 4, 16, 23, 30, 0, tzinfo=UTC)
        day_start = window_start_for(BudgetWindow.DAY, now)
        # Effective limit = 1000 * 0.5 = 500; pre-seed 500 used -> blocked
        mgr._in_memory_counts[("opensubtitles", "day", day_start)] = 500
        decision = mgr.check("opensubtitles", limits={"day": 1000}, now=now)
        assert decision.allow is False
        assert "day" in decision.reason


class TestPerKeyAccounting:
    """Phase 4a: per-key counters alongside the aggregate."""

    def test_consume_with_key_id_tracks_both_aggregate_and_per_key(self):
        mgr = ProviderBudgetManager(redis=None, safety_margin_pct=0)
        now = datetime(2026, 4, 17, 12, 0, tzinfo=UTC)
        mgr.consume("opensubtitles", key_id=1, now=now)
        mgr.consume("opensubtitles", key_id=1, now=now)
        mgr.consume("opensubtitles", key_id=2, now=now)
        agg = mgr.get_usage("opensubtitles", now=now)
        per_key = mgr.get_usage_per_key("opensubtitles", now=now)
        assert agg["day"] == 3
        assert per_key[1]["day"] == 2
        assert per_key[2]["day"] == 1

    def test_consume_without_key_id_only_updates_aggregate(self):
        mgr = ProviderBudgetManager(redis=None, safety_margin_pct=0)
        now = datetime(2026, 4, 17, 12, 0, tzinfo=UTC)
        mgr.consume("opensubtitles", now=now)
        agg = mgr.get_usage("opensubtitles", now=now)
        per_key = mgr.get_usage_per_key("opensubtitles", now=now)
        assert agg["day"] == 1
        assert per_key == {}  # no per-key tracking when key_id omitted

    def test_get_usage_per_key_empty_for_unknown_provider(self):
        mgr = ProviderBudgetManager(redis=None, safety_margin_pct=0)
        assert mgr.get_usage_per_key("ghost") == {}
