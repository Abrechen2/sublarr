"""Demand-histogram tests — drives adaptive stretch mode."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest

from services.demand_histogram import (
    DEMAND_UNIFORM,
    get_demand_shares,
    invalidate_demand_cache,
)


def test_demand_shares_sum_to_1():
    invalidate_demand_cache()
    with patch(
        "services.demand_histogram._fetch_added_at_hours",
        return_value=[0, 0, 0, 12, 12, 12, 23],  # 3 at 00, 3 at 12, 1 at 23
    ):
        shares = get_demand_shares(now=datetime(2026, 4, 17, tzinfo=UTC))
    assert len(shares) == 24
    assert sum(shares) == pytest.approx(1.0, rel=1e-6)
    assert shares[0] == pytest.approx(3 / 7)
    assert shares[12] == pytest.approx(3 / 7)
    assert shares[23] == pytest.approx(1 / 7)


def test_demand_shares_fallback_uniform_on_empty_history():
    invalidate_demand_cache()
    with patch("services.demand_histogram._fetch_added_at_hours", return_value=[]):
        shares = get_demand_shares(now=datetime(2026, 4, 17, tzinfo=UTC))
    assert shares == DEMAND_UNIFORM


def test_demand_cache_respects_ttl():
    invalidate_demand_cache()
    now = datetime(2026, 4, 17, 12, 0, 0, tzinfo=UTC)
    with patch("services.demand_histogram._fetch_added_at_hours", return_value=[0] * 24) as fetch:
        get_demand_shares(now=now)
        # Within TTL — fetch must not be invoked
        get_demand_shares(now=now + timedelta(minutes=30))
        assert fetch.call_count == 1
        # After TTL
        get_demand_shares(now=now + timedelta(hours=2))
        assert fetch.call_count == 2
