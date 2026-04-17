"""End-to-end: 429 storm reduces factor, 7 clean days ramp it back up.

Integrates Tasks 3-5: record_429 writes the DB factor, tick_recovery reads it
and ramps via the 7-good-days threshold in the repo.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from services.provider_budget import BudgetWindow, ProviderBudgetManager


def test_429_storm_plus_recovery_cycle(app_ctx):
    mgr = ProviderBudgetManager(redis=None, safety_margin_pct=0)

    # Storm: 3 consecutive 429s — factor goes 1.0 -> 0.9 -> 0.81 -> 0.729.
    storm_time = datetime(2026, 4, 17, 10, 0, 0, tzinfo=UTC)
    for i in range(3):
        mgr.record_429(
            "opensubtitles",
            BudgetWindow.DAY,
            configured_limit=1000,
            now=storm_time + timedelta(minutes=i),
        )

    factor_after_storm = mgr._factors[("opensubtitles", "day")]
    # 1.0 * 0.9 * 0.9 * 0.9 = 0.729
    assert factor_after_storm == pytest.approx(0.729, rel=1e-3)

    # Scheduler ticks once per day for the next 7 days. ramp_recovery's guard is
    # "24h since last 429 OR last ramp write" — so each tick at +day+1h qualifies.
    # The repo only bumps the factor once consecutive_good_days >= 7, so after 7
    # ticks we expect exactly one +0.02 bump: 0.729 + 0.02 = 0.749.
    for day in range(1, 8):
        tick_time = storm_time + timedelta(days=day, hours=1)
        mgr.tick_recovery(now=tick_time)

    factor_after_recovery = mgr._factors.get(("opensubtitles", "day"), 1.0)
    assert factor_after_recovery == pytest.approx(0.749, rel=1e-3)
