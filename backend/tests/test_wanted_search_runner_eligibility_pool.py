"""Regression test: eligibility filtering must run on the FULL candidate
pool before ``wanted_search_max_items_per_run`` truncation, not after a
premature fetch-time LIMIT.

Production incident (2026-07-05, reproduced via direct SQL against Cardinal):
with 2284 ``wanted`` rows and ``wanted_search_max_items_per_run=2000``, 29
items were individually eligible (``retry_after`` elapsed, ``search_count``
under the cap) but had a slightly MORE RECENT ``last_search_at`` than the
rest of the backlog. The fair-order fetch (``ORDER BY last_search_at ASC
NULLS FIRST, search_count ASC LIMIT 2000``) excluded them before
``_filter_eligible`` ever ran, so ``run_wanted_search`` returned
``{"total": 0, ...}`` despite eligible work existing.

These tests fake the repository call to mimic the real DB's fair-order-then-
LIMIT semantics (sort the pool, then slice by whatever ``limit`` the runner
passes in) — the exact mechanism that starves due items in production.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _item(item_id: int, *, last_search_at: str, retry_after: str | None, search_count: int):
    return {
        "id": item_id,
        "title": f"item-{item_id}",
        "file_path": f"/media/item-{item_id}.mkv",
        "existing_sub": "",
        "priority": "standard",
        "upgrade_candidate": False,
        "last_search_at": last_search_at,
        "retry_after": retry_after,
        "search_count": search_count,
    }


def _fake_fair_order_selector(pool: list[dict]):
    """Mimic ``WantedRepository.get_items_for_scheduled_search``'s real
    behaviour for ``order='fair'``: sort the WHOLE pool by
    ``(last_search_at ASC NULLS FIRST, search_count ASC)``, THEN apply the
    caller-supplied ``limit`` — i.e. the LIMIT is applied to the ordering
    candidates, not to whichever subset later turns out eligible.
    """

    def _select(limit: int, order: str):
        ordered = sorted(
            pool,
            key=lambda i: (i.get("last_search_at") or "", i.get("search_count", 0)),
        )
        return ordered[:limit]

    return _select


@pytest.fixture
def fake_worker(monkeypatch):
    """Replace the real provider search with a no-op recorder."""
    processed_ids: list[int] = []

    def _fake_process(item_id: int) -> dict:
        processed_ids.append(item_id)
        return {"status": "found", "wanted_id": item_id}

    import wanted_search

    monkeypatch.setattr(wanted_search, "process_wanted_item", _fake_process, raising=True)
    return processed_ids


def _configure_settings(monkeypatch, max_items: int):
    from config import get_settings

    s = get_settings()
    monkeypatch.setattr(s, "wanted_search_order", "fair", raising=False)
    monkeypatch.setattr(s, "wanted_search_max_items_per_run", max_items, raising=False)
    monkeypatch.setattr(s, "wanted_max_search_attempts", 3, raising=False)
    monkeypatch.setattr(s, "wanted_adaptive_backoff_enabled", True, raising=False)
    return s


def test_due_items_are_not_starved_by_stale_ineligible_backlog(app_ctx, monkeypatch, fake_worker):
    """The 29-items-on-prod bug: items with a slightly newer last_search_at
    that ARE due must not be excluded by the fair-order fetch LIMIT before
    eligibility is checked.
    """
    now = datetime.now(UTC)
    max_items = 3

    # N=5 stale-but-NOT-due items: oldest by fair order (last_search_at far in
    # the past), so a naive fetch of `max_items` rows returns only these —
    # and every one of them is ineligible (retry_after in the future).
    stale_not_due = [
        _item(
            i,
            last_search_at=_iso(now - timedelta(hours=200)),
            retry_after=_iso(now + timedelta(hours=100)),
            search_count=1,
        )
        for i in range(5)
    ]
    # M=2 due items: slightly more recent last_search_at (sorted AFTER the
    # stale cohort) but actually eligible right now.
    due = [
        _item(
            100 + i,
            last_search_at=_iso(now - timedelta(hours=50)),
            retry_after=None,
            search_count=0,
        )
        for i in range(2)
    ]
    pool = stale_not_due + due

    _configure_settings(monkeypatch, max_items)

    with patch(
        "db.wanted.get_items_for_scheduled_search",
        side_effect=_fake_fair_order_selector(pool),
    ):
        from services.wanted_search_runner import run_wanted_search

        summary = run_wanted_search(app=app_ctx, include_upgrades=True)

    assert summary["total"] > 0, (
        "eligibility filter must see the full candidate pool, not just the "
        "oldest max_items rows — otherwise due items are silently starved"
    )
    assert summary["processed"] == len(due)
    assert set(fake_worker) == {i["id"] for i in due}


def test_max_items_still_caps_per_tick_workload(app_ctx, monkeypatch, fake_worker):
    """max_items must still bound the per-tick workload when MORE eligible
    items exist than the configured cap — the fix must not remove the cap,
    only move it to after eligibility filtering."""
    now = datetime.now(UTC)
    max_items = 3

    due = [
        _item(
            i,
            last_search_at=_iso(now - timedelta(hours=1)),
            retry_after=None,
            search_count=0,
        )
        for i in range(10)
    ]

    _configure_settings(monkeypatch, max_items)

    with patch(
        "db.wanted.get_items_for_scheduled_search",
        side_effect=_fake_fair_order_selector(due),
    ):
        from services.wanted_search_runner import run_wanted_search

        summary = run_wanted_search(app=app_ctx, include_upgrades=True)

    assert summary["total"] == max_items
    assert summary["processed"] == max_items
