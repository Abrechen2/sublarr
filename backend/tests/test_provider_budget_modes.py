"""Burst + adaptive stretch-mode tests."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest

from services.provider_budget import BudgetWindow, ProviderBudgetManager, window_start_for


def _settings_stub(**overrides):
    defaults = {
        "provider_budget_stretch_mode": "burst",
        "provider_budget_burst_window_hours": 6,
    }
    defaults.update(overrides)
    stub = MagicMock()
    for k, v in defaults.items():
        setattr(stub, k, v)
    return stub


def test_burst_mode_allows_full_rate_inside_window():
    mgr = ProviderBudgetManager(redis=None, safety_margin_pct=0)
    now = datetime(2026, 4, 17, 2, 30, 0, tzinfo=UTC)  # 02:30 UTC
    # Seed usage: already burned 500/1000 — stretch would normally deny at this hour
    key = ("opensubtitles", "day", window_start_for(BudgetWindow.DAY, now))
    mgr._in_memory_counts[key] = 500
    with patch("services.provider_budget.get_settings", return_value=_settings_stub()):
        decision = mgr.check("opensubtitles", {"day": 1000}, now=now)
    assert decision.allow is True


def test_burst_mode_enforces_stretch_after_window_ends():
    mgr = ProviderBudgetManager(redis=None, safety_margin_pct=0)
    # 08:00 UTC — window ended 2h ago. Remaining budget must pace across remaining 16h.
    now = datetime(2026, 4, 17, 8, 0, 0, tzinfo=UTC)
    key = ("opensubtitles", "day", window_start_for(BudgetWindow.DAY, now))
    # Seed over the remaining-budget pace to force a deny.
    mgr._in_memory_counts[key] = 670
    with patch("services.provider_budget.get_settings", return_value=_settings_stub()):
        decision = mgr.check("opensubtitles", {"day": 1000}, now=now)
    assert decision.allow is False
    assert "burst" in decision.reason or "stretch" in decision.reason


def test_burst_mode_still_enforces_raw_caps():
    mgr = ProviderBudgetManager(redis=None, safety_margin_pct=0)
    now = datetime(2026, 4, 17, 2, 30, 0, tzinfo=UTC)
    key = ("opensubtitles", "day", window_start_for(BudgetWindow.DAY, now))
    mgr._in_memory_counts[key] = 1000  # At the raw cap
    with patch("services.provider_budget.get_settings", return_value=_settings_stub()):
        decision = mgr.check("opensubtitles", {"day": 1000}, now=now)
    assert decision.allow is False
    assert "day limit reached" in decision.reason
