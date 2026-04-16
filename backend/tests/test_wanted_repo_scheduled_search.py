"""Tests for WantedRepository.get_items_for_scheduled_search fair-rotation query.

Covers the three order presets used by the API-Budget Scheduler:
- 'fair': NULL last_search_at first, then oldest last_search_at, tiebreak on lowest search_count.
- 'newest_first': legacy added_at DESC behaviour.
- 'weighted': two-bucket (recent <30d vs. older) with fair ordering inside each bucket.
"""

from datetime import UTC, datetime, timedelta

import pytest

from db.models.core import WantedItem
from db.repositories.wanted import WantedRepository
from extensions import db


def _make(file_path, **kwargs):
    """Helper to insert a WantedItem with sensible defaults."""
    now = datetime(2026, 4, 1, tzinfo=UTC)
    defaults = dict(
        item_type="episode",
        file_path=file_path,
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


def test_fair_order_returns_never_searched_first(app_ctx):
    """Items never searched (last_search_at=NULL) come first, then oldest last_search_at,
    with lowest search_count as tiebreak."""
    now = datetime(2026, 4, 1, tzinfo=UTC)

    a = _make(
        "/media/A.mkv",
        last_search_at=None,
        search_count=0,
    )
    b = _make(
        "/media/B.mkv",
        last_search_at=now - timedelta(hours=2),
        search_count=2,
    )
    c = _make(
        "/media/C.mkv",
        last_search_at=now - timedelta(days=5),
        search_count=1,
    )

    repo = WantedRepository()
    result = repo.get_items_for_scheduled_search(limit=10, order="fair")
    ids = [row["id"] for row in result]

    assert ids == [a.id, c.id, b.id]


def test_newest_first_order_preserves_legacy_behavior(app_ctx):
    """'newest_first' returns items by added_at DESC — legacy scheduler behaviour."""
    base = datetime(2026, 4, 1, tzinfo=UTC)

    oldest = _make("/media/oldest.mkv", added_at=base - timedelta(days=10))
    middle = _make("/media/middle.mkv", added_at=base - timedelta(days=5))
    newest = _make("/media/newest.mkv", added_at=base - timedelta(days=1))

    repo = WantedRepository()
    result = repo.get_items_for_scheduled_search(limit=10, order="newest_first")
    ids = [row["id"] for row in result]

    assert ids == [newest.id, middle.id, oldest.id]


def test_weighted_order_buckets_recent_then_fair(app_ctx):
    """'weighted' puts items added within the last 30 days in bucket 0, older in bucket 1.
    Within each bucket the order follows the 'fair' preset (NULL last_search first, then
    oldest last_search, tiebreak on lowest search_count)."""
    now = datetime.now(UTC)

    recent1 = _make(
        "/media/recent1.mkv",
        added_at=now - timedelta(days=1),
        last_search_at=None,
        search_count=0,
    )
    recent2 = _make(
        "/media/recent2.mkv",
        added_at=now - timedelta(days=5),
        last_search_at=now - timedelta(hours=2),
        search_count=2,
    )
    old1 = _make(
        "/media/old1.mkv",
        added_at=now - timedelta(days=100),
        last_search_at=None,
        search_count=0,
    )

    repo = WantedRepository()
    result = repo.get_items_for_scheduled_search(limit=10, order="weighted")
    ids = [row["id"] for row in result]

    assert ids == [recent1.id, recent2.id, old1.id]


def test_invalid_order_raises_value_error(app_ctx):
    """Unsupported preset strings must raise ValueError (fail-fast at boundary)."""
    repo = WantedRepository()
    with pytest.raises(ValueError):
        repo.get_items_for_scheduled_search(limit=10, order="random_garbage")
