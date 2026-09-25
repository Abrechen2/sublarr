"""Tests for slow-mode eligibility in `_filter_eligible`.

The slow-mode contract (see record_search_outcome): once an item hits
`wanted_max_search_attempts`, status stays `wanted`, `failure_kind` is set
to `'no_result_slow'`, and `retry_after` is pushed ~30 days into the future.
After that window, the item must become eligible again — otherwise slow-mode
is a name without a behaviour.

These tests pin the eligibility contract so the filter cannot regress to a
hard `search_count < max_attempts` cap that ignores `retry_after`.
"""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from services.wanted_search_filters import _filter_eligible


def _settings(adaptive: bool = True, max_attempts: int = 3) -> SimpleNamespace:
    return SimpleNamespace(
        wanted_adaptive_backoff_enabled=adaptive,
        wanted_max_search_attempts=max_attempts,
    )


def _item(**kwargs) -> dict:
    """Build a wanted-item dict with sensible defaults."""
    base = {
        "id": 1,
        "search_count": 0,
        "retry_after": None,
        "last_search_at": None,
        "failure_kind": None,
    }
    base.update(kwargs)
    return base


# ---------- baseline: pre-existing behaviour stays intact ----------


def test_fresh_item_is_eligible():
    items = [_item(id=1, search_count=0)]
    assert _filter_eligible(items, _settings()) == items


def test_item_under_limit_is_eligible():
    items = [_item(id=1, search_count=2)]
    assert _filter_eligible(items, _settings()) == items


def test_item_at_or_above_limit_without_slow_mode_marker_stays_blocked():
    """Legacy frozen items (failure_kind=None, retry_after=None) must NOT
    be quietly resurrected — that would re-enter the old freeze loop without
    a backoff. Slow-mode requires the explicit marker."""
    items = [_item(id=1, search_count=3, failure_kind=None, retry_after=None)]
    assert _filter_eligible(items, _settings()) == []


def test_retry_after_in_future_blocks_eligible_items():
    future = (datetime.now(UTC) + timedelta(hours=2)).isoformat()
    items = [_item(id=1, search_count=1, retry_after=future, failure_kind="no_result")]
    assert _filter_eligible(items, _settings()) == []


# ---------- slow-mode: at-or-above-limit but retry window passed ----------


def test_slow_mode_item_with_past_retry_after_is_eligible():
    """`failure_kind='no_result_slow'` + retry_after in the past must beat
    the search_count cap. This is THE slow-mode promise."""
    past = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
    items = [
        _item(
            id=1,
            search_count=3,
            retry_after=past,
            failure_kind="no_result_slow",
        )
    ]
    assert _filter_eligible(items, _settings()) == items


def test_slow_mode_item_with_future_retry_after_stays_blocked():
    future = (datetime.now(UTC) + timedelta(days=10)).isoformat()
    items = [
        _item(
            id=1,
            search_count=3,
            retry_after=future,
            failure_kind="no_result_slow",
        )
    ]
    assert _filter_eligible(items, _settings()) == []


def test_slow_mode_marker_without_retry_after_does_not_unfreeze():
    """Defensive: marker alone shouldn't bypass the cap. The retry_after
    timestamp is what carries the time semantics."""
    items = [
        _item(
            id=1,
            search_count=3,
            retry_after=None,
            failure_kind="no_result_slow",
        )
    ]
    assert _filter_eligible(items, _settings()) == []


def test_slow_mode_item_far_above_limit_still_works():
    past = (datetime.now(UTC) - timedelta(days=1)).isoformat()
    items = [
        _item(
            id=1,
            search_count=10,
            retry_after=past,
            failure_kind="no_result_slow",
        )
    ]
    assert _filter_eligible(items, _settings(max_attempts=3)) == items


# ---------- non-slow-mode failure_kinds at limit stay blocked ----------


def test_provider_error_at_limit_with_past_retry_stays_in_rotation():
    """Reversed 2026-09-25. This used to pin the opposite ("must not be
    unfrozen"), which froze every slow-mode item whose due search hit a
    transient fault: provider_error keeps search_count at the cap but drops
    the slow-mode marker. Since searches nobody answered are booked as
    provider_error, that would have frozen most of the slow-mode cohort.
    The cap still holds — the next genuine miss sends the item back to the
    30-day slow-mode cadence (see test_slow_mode_actually_searches.py)."""
    past = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
    items = [
        _item(
            id=1,
            search_count=3,
            retry_after=past,
            failure_kind="provider_error",
        )
    ]
    assert [i["id"] for i in _filter_eligible(items, _settings())] == [1]


def test_unknown_failure_kind_at_limit_stays_blocked():
    past = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
    items = [_item(id=1, search_count=3, retry_after=past, failure_kind="no_result")]
    assert _filter_eligible(items, _settings()) == []


# ---------- adaptive disabled: legacy 1h cooldown path ----------


def test_legacy_cooldown_blocks_recent_searches():
    recent = (datetime.now(UTC) - timedelta(minutes=10)).isoformat()
    items = [_item(id=1, search_count=1, last_search_at=recent)]
    assert _filter_eligible(items, _settings(adaptive=False)) == []


def test_legacy_cooldown_releases_after_1h():
    long_ago = (datetime.now(UTC) - timedelta(hours=2)).isoformat()
    items = [_item(id=1, search_count=1, last_search_at=long_ago)]
    assert _filter_eligible(items, _settings(adaptive=False)) == items
