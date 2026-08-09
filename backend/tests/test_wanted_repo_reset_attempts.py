"""Bulk reset of the search backoff on wanted items (#184).

Why this exists: an item that exhausts its attempts enters slow mode and is
retried roughly once per 30 days. That is right while the problem is the
subtitle's availability — and wrong once the problem was the install. One user
had hundreds of items burn every attempt during a period when their provider
fleet was effectively down (an expired token, and keyless providers gated out).
The fleet works again; without this, those items sit until next month, and the
stagnation is indistinguishable from "still broken".

The reset must clear exactly what holds an item back, which
`_filter_eligible` defines: `retry_after` in the future, and `search_count` at
or above the cap unless `failure_kind='no_result_slow'` with an elapsed
`retry_after`.
"""

from datetime import UTC, datetime, timedelta

import pytest

from db.models.core import WantedItem
from db.repositories.wanted import WantedRepository
from extensions import db

NOW = datetime(2026, 8, 9, tzinfo=UTC)


def _make(file_path, **kwargs):
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
        added_at=NOW,
        updated_at=NOW,
    )
    defaults.update(kwargs)
    item = WantedItem(**defaults)
    db.session.add(item)
    db.session.commit()
    return item


@pytest.fixture
def repo(app_ctx):
    return WantedRepository()


def test_reset_clears_every_field_that_holds_an_item_back(repo):
    item = _make(
        "/m/parked.mkv",
        search_count=12,
        retry_after=NOW + timedelta(days=27),
        failure_kind="no_result_slow",
        error_count=4,
        last_error_at=NOW - timedelta(days=3),
        error="Authentication failed for .../download: HTTP 401",
    )

    assert repo.reset_search_attempts([item.id]) == 1

    db.session.refresh(item)
    assert item.search_count == 0
    assert item.retry_after is None
    assert item.failure_kind is None
    # error_count does not gate eligibility directly, but it sets the LENGTH of
    # the next backoff (compute_retry_after_for_error). Leaving it would send
    # the item straight back into a long wait on its first hiccup after the
    # recovery this reset exists to follow.
    assert item.error_count == 0
    assert item.last_error_at is None
    assert item.error == ""


def test_a_reset_item_is_eligible_to_search_again(repo):
    """The property that matters — the queue actually moves.

    Asserting the columns alone would pass against a reset that clears fields
    the eligibility filter does not read.
    """
    from types import SimpleNamespace

    from services.wanted_search_filters import _filter_eligible

    item = _make(
        "/m/parked.mkv",
        search_count=12,
        retry_after=NOW + timedelta(days=27),
        failure_kind="no_result_slow",
    )
    settings = SimpleNamespace(wanted_max_search_attempts=10, wanted_adaptive_backoff_enabled=True)

    before = _filter_eligible([repo.get_wanted_item(item.id)], settings)
    assert before == [], "test is meaningless unless the item starts out blocked"

    repo.reset_search_attempts([item.id])

    after = _filter_eligible([repo.get_wanted_item(item.id)], settings)
    assert len(after) == 1


def test_only_the_named_items_are_reset(repo):
    parked = _make("/m/a.mkv", search_count=12, retry_after=NOW + timedelta(days=27))
    other = _make("/m/b.mkv", search_count=12, retry_after=NOW + timedelta(days=27))

    repo.reset_search_attempts([parked.id])

    db.session.refresh(other)
    assert other.search_count == 12, "a bulk action must not reach past its selection"
    assert other.retry_after is not None


def test_an_empty_selection_changes_nothing(repo):
    item = _make("/m/a.mkv", search_count=12)

    assert repo.reset_search_attempts([]) == 0

    db.session.refresh(item)
    assert item.search_count == 12


def test_found_items_are_left_alone(repo):
    """Resetting a found item would put it back in the search queue.

    A bulk action over a filter that happens to include found rows must not
    silently re-open settled work.
    """
    found = _make("/m/done.mkv", status="found", search_count=3)

    assert repo.reset_search_attempts([found.id]) == 0

    db.session.refresh(found)
    assert found.search_count == 3
