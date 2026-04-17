"""Priority-weighted ordering tests for WantedRepository.get_items_for_scheduled_search.

Follows the same pattern as test_wanted_repo_scheduled_search.py — uses
``app_ctx`` fixture, ``db.session``, and parameterless ``WantedRepository()``.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from db.models.core import WantedItem
from db.repositories.wanted import WantedRepository
from extensions import db


def _make(file_path: str, **kwargs) -> WantedItem:
    now = datetime(2026, 4, 17, tzinfo=UTC)
    defaults = dict(
        item_type="episode",
        file_path=file_path,
        title=file_path,
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


def test_fair_order_with_priority_puts_premium_first(app_ctx):
    now = datetime(2026, 4, 17, tzinfo=UTC)
    # backlog is the oldest-searched (would win under fair alone) but must
    # land last under priority weighting.
    a = _make("/media/A.mkv", priority="backlog", last_search_at=now - timedelta(days=30))
    b = _make("/media/B.mkv", priority="standard", last_search_at=now - timedelta(days=5))
    c = _make("/media/C.mkv", priority="premium", last_search_at=None)
    repo = WantedRepository()
    rows = repo.get_items_for_scheduled_search(limit=10, order="fair")
    ids = [r["id"] for r in rows]
    assert ids == [c.id, b.id, a.id]


def test_priority_weighting_disabled_preserves_fair_order(app_ctx):
    now = datetime(2026, 4, 17, tzinfo=UTC)
    a = _make("/media/A.mkv", priority="backlog", last_search_at=now - timedelta(days=30))
    b = _make("/media/B.mkv", priority="premium", last_search_at=now - timedelta(days=1))
    repo = WantedRepository()
    # Explicit override bypasses the setting.
    rows = repo.get_items_for_scheduled_search(
        limit=10,
        order="fair",
        priority_weighting=False,
    )
    # backlog has older last_search_at -> wins under pure fair
    assert rows[0]["id"] == a.id
    assert rows[1]["id"] == b.id
