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
        assert window_start_for(BudgetWindow.DAY, now) == datetime(
            2026, 4, 16, 0, 0, 0, tzinfo=UTC
        )


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
