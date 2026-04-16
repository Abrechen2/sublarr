"""Tests for the failure-kind split + exponential backoff helpers.

Covers:
- ``compute_retry_after_for_error`` — pure backoff math (6h, 24h, 3d, 7d, 30d).
- ``record_search_outcome`` — central mutation point for scheduler outcomes.

The slow-mode path replaces the old permanent freeze; a provider error must
never touch ``search_count`` so transient outages (429, circuit-breaker) do not
burn an item's retry budget.
"""

from datetime import UTC, datetime, timedelta

from db.models.core import WantedItem
from extensions import db
from services.wanted_search_runner import (
    compute_retry_after_for_error,
    record_search_outcome,
)

# ---------- compute_retry_after_for_error (pure) ----------


def test_first_error_backs_off_6h():
    now = datetime(2026, 4, 16, 10, 0, 0, tzinfo=UTC)
    assert compute_retry_after_for_error(1, now) == now + timedelta(hours=6)


def test_second_error_backs_off_24h():
    now = datetime(2026, 4, 16, 10, 0, 0, tzinfo=UTC)
    assert compute_retry_after_for_error(2, now) == now + timedelta(hours=24)


def test_third_error_backs_off_3d():
    now = datetime(2026, 4, 16, 10, 0, 0, tzinfo=UTC)
    assert compute_retry_after_for_error(3, now) == now + timedelta(days=3)


def test_fourth_error_backs_off_7d():
    now = datetime(2026, 4, 16, 10, 0, 0, tzinfo=UTC)
    assert compute_retry_after_for_error(4, now) == now + timedelta(days=7)


def test_fifth_and_above_cap_at_30d():
    now = datetime(2026, 4, 16, 10, 0, 0, tzinfo=UTC)
    assert compute_retry_after_for_error(5, now) == now + timedelta(days=30)
    assert compute_retry_after_for_error(99, now) == now + timedelta(days=30)


# ---------- record_search_outcome (needs app_ctx) ----------


def _make_wanted_item(**kwargs) -> WantedItem:
    """Insert a minimal WantedItem for outcome tests; returns the persisted row."""
    now = datetime(2026, 4, 16, tzinfo=UTC)
    defaults = dict(
        item_type="episode",
        file_path=f"/media/test_{id(kwargs):x}.mkv",
        title="Test",
        season_episode="S01E01",
        existing_sub="",
        missing_languages="[]",
        embedded_languages="[]",
        target_language="de",
        subtitle_type="full",
        status="wanted",
        added_at=now,
        updated_at=now,
    )
    defaults.update(kwargs)
    item = WantedItem(**defaults)
    db.session.add(item)
    db.session.commit()
    return item


def test_provider_error_does_not_increment_search_count(app_ctx):
    item = _make_wanted_item(search_count=0, error_count=0)
    record_search_outcome(item.id, kind="provider_error", error_message="HTTP 429")
    db.session.refresh(item)
    assert item.search_count == 0  # unchanged
    assert item.error_count == 1  # incremented
    assert item.failure_kind == "provider_error"
    assert item.retry_after is not None


def test_no_result_increments_search_count_only(app_ctx):
    item = _make_wanted_item(search_count=0, error_count=0)
    record_search_outcome(item.id, kind="no_result")
    db.session.refresh(item)
    assert item.search_count == 1
    assert item.error_count == 0
    assert item.failure_kind == "no_result"


def test_max_attempts_switches_to_slow_mode_not_freeze(app_ctx, monkeypatch):
    # Force max_attempts=3 so the test deterministically hits slow-mode
    from config import get_settings

    s = get_settings()
    monkeypatch.setattr(s, "wanted_max_search_attempts", 3, raising=False)

    item = _make_wanted_item(search_count=3, error_count=0)
    record_search_outcome(item.id, kind="no_result")
    db.session.refresh(item)
    # No more freezing — status stays wanted, item will be re-tried in 30d
    assert item.status == "wanted"
    assert item.error != "Max search attempts reached"
    assert item.failure_kind == "no_result_slow"
    assert item.retry_after is not None
    # retry_after should be ~30 days from now
    retry_after = item.retry_after
    if retry_after.tzinfo is None:
        retry_after = retry_after.replace(tzinfo=UTC)
    delta = retry_after - datetime.now(UTC)
    assert timedelta(days=29) < delta < timedelta(days=31)
