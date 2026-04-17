# backend/tests/test_provider_budget_learning.py
"""Tests for 429 learning hook in ProviderBudgetManager."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import patch

import pytest

from services.provider_budget import BudgetWindow, ProviderBudgetManager


def test_record_429_reduces_in_memory_factor():
    mgr = ProviderBudgetManager(redis=None, safety_margin_pct=0)
    now = datetime(2026, 4, 17, 12, 0, 0, tzinfo=UTC)
    with patch("services.provider_budget._persist_429") as persist:
        persist.return_value = 0.9  # what the repo would have returned
        mgr.record_429("opensubtitles", BudgetWindow.DAY, configured_limit=1000, now=now)
    assert mgr._factors[("opensubtitles", "day")] == pytest.approx(0.9)


def test_record_429_emits_provider_state_changed_event():
    mgr = ProviderBudgetManager(redis=None, safety_margin_pct=0)
    now = datetime(2026, 4, 17, 12, 0, 0, tzinfo=UTC)
    with (
        patch("services.provider_budget._persist_429", return_value=0.81),
        patch("services.provider_budget._emit_event") as emit,
    ):
        mgr.record_429("opensubtitles", BudgetWindow.DAY, configured_limit=1000, now=now)
    emit.assert_called_once()
    name, payload = emit.call_args.args
    assert name == "provider_state_changed"
    assert payload["provider"] == "opensubtitles"
    assert payload["state"] == "learning"
    assert payload["adjustment_factor"] == pytest.approx(0.81)


def test_record_429_swallows_persistence_error():
    mgr = ProviderBudgetManager(redis=None, safety_margin_pct=0)
    now = datetime(2026, 4, 17, tzinfo=UTC)
    with patch("services.provider_budget._persist_429", side_effect=RuntimeError("db down")):
        # Must not raise — search must continue even if DB is unreachable
        mgr.record_429("opensubtitles", BudgetWindow.DAY, configured_limit=1000, now=now)
    # Fall-back behaviour: factor is reduced in memory only so the next
    # check() still throttles the provider even without a persisted row.
    # Decay is 0.9x from the initial factor of 1.0
    assert mgr._factors[("opensubtitles", "day")] == pytest.approx(1.0 * 0.9)


def test_tick_recovery_updates_factor_cache():
    mgr = ProviderBudgetManager(redis=None, safety_margin_pct=0)
    mgr._factors = {("opensubtitles", "day"): 0.9}
    now = datetime(2026, 4, 25, tzinfo=UTC)
    with patch(
        "services.provider_budget._ramp_all",
        side_effect=lambda now: {("opensubtitles", "day"): 0.92},
    ):
        mgr.tick_recovery(now=now)
    assert mgr._factors[("opensubtitles", "day")] == pytest.approx(0.92)


def test_tick_recovery_swallows_db_error():
    mgr = ProviderBudgetManager(redis=None, safety_margin_pct=0)
    mgr._factors = {("opensubtitles", "day"): 0.9}
    now = datetime(2026, 4, 25, tzinfo=UTC)
    with patch("services.provider_budget._ramp_all", side_effect=RuntimeError("db down")):
        mgr.tick_recovery(now=now)  # must not raise
    # Cache remains at pre-tick value
    assert mgr._factors[("opensubtitles", "day")] == pytest.approx(0.9)
