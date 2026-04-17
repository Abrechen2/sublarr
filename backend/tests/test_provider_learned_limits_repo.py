"""Unit tests for ProviderLearnedLimitsRepository."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from db.repositories.provider_learned_limits import ProviderLearnedLimitsRepository


def test_get_returns_none_when_missing(app_ctx):
    repo = ProviderLearnedLimitsRepository()
    assert repo.get("opensubtitles", "day") is None


def test_upsert_on_429_creates_row_at_factor_0_9(app_ctx):
    repo = ProviderLearnedLimitsRepository()
    now = datetime(2026, 4, 17, 12, 0, 0, tzinfo=UTC)
    repo.upsert_on_429(
        provider="opensubtitles",
        window="day",
        configured_limit=1000,
        observed_limit=None,
        now=now,
    )
    row = repo.get("opensubtitles", "day")
    assert row is not None
    assert row["adjustment_factor"] == pytest.approx(0.9)
    assert row["consecutive_good_days"] == 0
    assert row["last_429_at"] == now


def test_upsert_on_429_multiplies_existing_factor(app_ctx):
    repo = ProviderLearnedLimitsRepository()
    now = datetime(2026, 4, 17, 12, 0, 0, tzinfo=UTC)
    repo.upsert_on_429("opensubtitles", "day", 1000, None, now)
    repo.upsert_on_429("opensubtitles", "day", 1000, None, now)
    row = repo.get("opensubtitles", "day")
    assert row["adjustment_factor"] == pytest.approx(0.81)


def test_upsert_on_429_floors_at_0_1(app_ctx):
    repo = ProviderLearnedLimitsRepository()
    now = datetime(2026, 4, 17, tzinfo=UTC)
    for _ in range(50):  # would drive factor below 0.1
        repo.upsert_on_429("subdl", "day", 100, None, now)
    row = repo.get("subdl", "day")
    assert row["adjustment_factor"] == pytest.approx(0.1)


def test_ramp_recovery_noop_within_24h_of_429(app_ctx):
    repo = ProviderLearnedLimitsRepository()
    now = datetime(2026, 4, 17, 12, 0, 0, tzinfo=UTC)
    repo.upsert_on_429("opensubtitles", "day", 1000, None, now)
    twenty_three_hours_later = now + timedelta(hours=23)
    factor = repo.ramp_recovery("opensubtitles", "day", step=0.02, now=twenty_three_hours_later)
    assert factor == pytest.approx(0.9)
    row = repo.get("opensubtitles", "day")
    assert row["consecutive_good_days"] == 0


def test_ramp_recovery_increments_good_days_after_24h(app_ctx):
    repo = ProviderLearnedLimitsRepository()
    now = datetime(2026, 4, 17, 12, 0, 0, tzinfo=UTC)
    repo.upsert_on_429("opensubtitles", "day", 1000, None, now)
    later = now + timedelta(days=1, hours=1)
    factor = repo.ramp_recovery("opensubtitles", "day", step=0.02, now=later)
    assert factor == pytest.approx(0.9)  # still 0.9 — only 1 good day, need 7
    row = repo.get("opensubtitles", "day")
    assert row["consecutive_good_days"] == 1


def test_ramp_recovery_ramps_factor_after_7_good_days(app_ctx):
    repo = ProviderLearnedLimitsRepository()
    base = datetime(2026, 4, 17, 12, 0, 0, tzinfo=UTC)
    repo.upsert_on_429("opensubtitles", "day", 1000, None, base)
    # Six ramp calls spaced >24h each -> 6 good days, factor still 0.9
    for day in range(1, 7):
        repo.ramp_recovery(
            "opensubtitles", "day", step=0.02, now=base + timedelta(days=day, hours=1)
        )
    row_mid = repo.get("opensubtitles", "day")
    assert row_mid["consecutive_good_days"] == 6
    assert row_mid["adjustment_factor"] == pytest.approx(0.9)
    # Seventh call: 7 good days -> bump factor
    factor = repo.ramp_recovery(
        "opensubtitles",
        "day",
        step=0.02,
        now=base + timedelta(days=7, hours=1),
    )
    assert factor == pytest.approx(0.92)


def test_ramp_recovery_caps_at_1_0(app_ctx):
    repo = ProviderLearnedLimitsRepository()
    base = datetime(2026, 4, 17, 12, 0, 0, tzinfo=UTC)
    repo.upsert_on_429("opensubtitles", "day", 1000, None, base)
    for day in range(1, 200):
        repo.ramp_recovery(
            "opensubtitles",
            "day",
            step=0.02,
            now=base + timedelta(days=day, hours=1),
        )
    row = repo.get("opensubtitles", "day")
    assert row["adjustment_factor"] == pytest.approx(1.0)


def test_get_all_returns_mapping_keyed_by_provider_window(app_ctx):
    repo = ProviderLearnedLimitsRepository()
    now = datetime(2026, 4, 17, tzinfo=UTC)
    repo.upsert_on_429("opensubtitles", "day", 1000, None, now)
    repo.upsert_on_429("subdl", "day", 100, None, now)
    rows = repo.get_all()
    assert ("opensubtitles", "day") in rows
    assert ("subdl", "day") in rows
    assert rows[("opensubtitles", "day")]["adjustment_factor"] == pytest.approx(0.9)
