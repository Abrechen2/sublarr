"""Tests for ProviderBudgetManager → provider_budget_updated event emission."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import patch

from services.provider_budget import (
    _EMIT_MIN_INTERVAL_SECONDS,
    _LAST_EMIT_AT,
    ProviderBudgetManager,
)


def _clear_emit_cache():
    _LAST_EMIT_AT.clear()


def test_consume_emits_event_with_usage_snapshot():
    _clear_emit_cache()
    mgr = ProviderBudgetManager(redis=None, safety_margin_pct=0)
    now = datetime(2026, 4, 16, 12, 0, 0, tzinfo=UTC)

    with patch("events.emit_event") as mock_emit:
        mgr.consume("opensubtitles", now=now)

    mock_emit.assert_called_once()
    args, _ = mock_emit.call_args
    assert args[0] == "provider_budget_updated"
    assert args[1]["provider"] == "opensubtitles"
    assert args[1]["usage"] == {"second": 1, "hour": 1, "day": 1}


def test_refund_also_emits_event():
    _clear_emit_cache()
    mgr = ProviderBudgetManager(redis=None, safety_margin_pct=0)
    now = datetime(2026, 4, 16, 12, 0, 0, tzinfo=UTC)
    mgr.consume("opensubtitles", now=now)

    _clear_emit_cache()
    with patch("events.emit_event") as mock_emit:
        mgr.refund("opensubtitles", now=now)
    mock_emit.assert_called_once_with(
        "provider_budget_updated",
        {"provider": "opensubtitles", "usage": {"second": 0, "hour": 0, "day": 0}},
    )


def test_emission_is_rate_limited_to_one_per_second_per_provider():
    _clear_emit_cache()
    mgr = ProviderBudgetManager(redis=None, safety_margin_pct=0)
    base = datetime(2026, 4, 16, 12, 0, 0, tzinfo=UTC)

    with patch("events.emit_event") as mock_emit:
        # 5 consumes in the same second — only 1 emit
        for _ in range(5):
            mgr.consume("opensubtitles", now=base)

    assert mock_emit.call_count == 1


def test_emission_resumes_after_rate_limit_window():
    _clear_emit_cache()
    mgr = ProviderBudgetManager(redis=None, safety_margin_pct=0)
    base = datetime(2026, 4, 16, 12, 0, 0, tzinfo=UTC)
    later = base + timedelta(seconds=_EMIT_MIN_INTERVAL_SECONDS + 0.1)

    with patch("events.emit_event") as mock_emit:
        mgr.consume("opensubtitles", now=base)
        mgr.consume("opensubtitles", now=later)

    assert mock_emit.call_count == 2


def test_emit_is_per_provider_rate_limited():
    _clear_emit_cache()
    mgr = ProviderBudgetManager(redis=None, safety_margin_pct=0)
    base = datetime(2026, 4, 16, 12, 0, 0, tzinfo=UTC)

    with patch("events.emit_event") as mock_emit:
        mgr.consume("opensubtitles", now=base)  # emits
        mgr.consume("subdl", now=base)  # different provider — emits
        mgr.consume("opensubtitles", now=base)  # same provider, within 1s — suppressed

    assert mock_emit.call_count == 2


def test_emit_failure_does_not_break_consume():
    _clear_emit_cache()
    mgr = ProviderBudgetManager(redis=None, safety_margin_pct=0)
    now = datetime(2026, 4, 16, 12, 0, 0, tzinfo=UTC)

    with patch("events.emit_event", side_effect=RuntimeError("bus down")):
        # Must not raise
        mgr.consume("opensubtitles", now=now)

    # The accounting side-effect still happened
    assert mgr.get_usage("opensubtitles", now=now)["day"] == 1
