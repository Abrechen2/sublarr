"""End-to-end: run_wanted_search against a mixed library validates the full
Phase 1 flow: fair-rotation selection, provider-error path (no search_count
bump), found path, and that no item ever gets permanently frozen.

Scenario: a 15-item library with three cohorts — 10 never-searched,
3 recent-fails (search_count=2, last_search_at=-2h), 2 old-backlog
(search_count=5, added 200 days ago). The per-item worker is mocked to
simulate 3 provider hits followed by 2 provider errors (HTTP 429).

Assertions:
  1. Fair rotation picks only never-searched items when limit=5.
  2. summary["processed"] == 5.
  3. Hit items end up status="found", 429 items end up with failure_kind=
     "provider_error", error_count=1, search_count still 0, retry_after set.
  4. No item is ever marked with the legacy "Max search attempts reached"
     freeze — slow-mode replaces it.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from db.models.core import WantedItem
from extensions import db


def _make(title: str, **kwargs) -> WantedItem:
    """Insert a WantedItem with defaults suitable for the scheduler."""
    now = datetime(2026, 4, 1, tzinfo=UTC)
    defaults = dict(
        item_type="episode",
        file_path=f"/media/{title}.mkv",
        title=title,
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


def _seed_mixed_library() -> list[WantedItem]:
    """15 items: 10 never-searched + 3 recent-fails + 2 old-backlog."""
    now = datetime.now(UTC)
    items: list[WantedItem] = []
    for i in range(10):
        items.append(
            _make(
                f"Never_{i:02d}",
                added_at=now - timedelta(days=i * 3),
                last_search_at=None,
                search_count=0,
            )
        )
    for i in range(3):
        items.append(
            _make(
                f"RecentFail_{i}",
                search_count=2,
                last_search_at=now - timedelta(hours=2),
            )
        )
    for i in range(2):
        items.append(
            _make(
                f"OldBacklog_{i}",
                search_count=5,
                added_at=now - timedelta(days=200),
            )
        )
    return items


def test_phase1_full_cycle(app_ctx, monkeypatch):
    # ── Arrange: settings ──────────────────────────────────────────────────
    from config import get_settings

    s = get_settings()
    monkeypatch.setattr(s, "wanted_search_order", "fair", raising=False)
    monkeypatch.setattr(s, "wanted_search_max_items_per_run", 5, raising=False)
    monkeypatch.setattr(s, "wanted_adaptive_backoff_enabled", True, raising=False)
    monkeypatch.setattr(s, "provider_budget_enabled", True, raising=False)
    # Default is 3; make it explicit so the eligibility filter (search_count < N)
    # picks the 10 never-searched first and rejects the 2 old-backlog (5 >= 3).
    monkeypatch.setattr(s, "wanted_max_search_attempts", 3, raising=False)

    # ── Arrange: seed library ──────────────────────────────────────────────
    _seed_mixed_library()

    # ── Arrange: mock the per-item worker ──────────────────────────────────
    # The runner submits ``_search_with_ctx(app, item_id)`` to the executor.
    # Replace it with a deterministic counter-based dispatcher: first 3 calls
    # simulate a provider hit, next 2 simulate HTTP 429 (provider_error).
    #
    # Both branches also set ``last_search_at`` explicitly — the real
    # ``process_wanted_item`` normally does this via mark_search_attempted /
    # no_result outcomes, but ``record_search_outcome(kind="found"|"
    # provider_error")`` does not. We mimic that side-effect here so the
    # fair-rotation assertion below has a clean signal ("which items got
    # touched this run?").
    from services import wanted_search_runner as runner

    calls = {"n": 0}

    def _fake_worker(_app, item_id: int, *_args, **_kwargs) -> dict:
        # Mirror the real ``_search_with_ctx``: push an app context in the
        # worker thread so DB writes land on the same Flask app.
        with _app.app_context():
            calls["n"] += 1
            now = datetime.now(UTC)
            from db.wanted import update_wanted_search_outcome

            if calls["n"] <= 3:
                runner.record_search_outcome(item_id, kind="found")
                update_wanted_search_outcome(item_id, last_search_at=now)
                return {"status": "found", "wanted_id": item_id}
            runner.record_search_outcome(item_id, kind="provider_error", error_message="HTTP 429")
            update_wanted_search_outcome(item_id, last_search_at=now)
            return {"status": "failed", "wanted_id": item_id, "error": "HTTP 429"}

    monkeypatch.setattr(runner, "_search_with_ctx", _fake_worker)

    # ── Act ────────────────────────────────────────────────────────────────
    summary = runner.run_wanted_search(include_upgrades=False)

    # ── Assert: summary counts ─────────────────────────────────────────────
    assert summary["processed"] == 5
    assert summary["found"] == 3
    assert summary["failed"] == 2

    # ── Assert: fair-rotation selection ────────────────────────────────────
    # All 5 items processed (last_search_at IS NOT NULL and our fake worker
    # touched them) must come from the never-searched cohort. The 3 RecentFail
    # rows already had last_search_at set at seed time, so we filter those out.
    touched = db.session.query(WantedItem).filter(WantedItem.last_search_at.isnot(None)).all()
    # 5 newly-touched + 3 pre-existing recent-fail rows = 8
    assert len(touched) == 8
    touched_never = [i for i in touched if i.title.startswith("Never_")]
    assert len(touched_never) == 5, (
        f"expected 5 Never_ items touched, got {[i.title for i in touched_never]}"
    )

    # ── Assert: found items ────────────────────────────────────────────────
    found_items = db.session.query(WantedItem).filter(WantedItem.status == "found").all()
    assert len(found_items) == 3
    for item in found_items:
        assert item.title.startswith("Never_")
        # found path resets failure state
        assert item.failure_kind is None
        assert item.error_count == 0

    # ── Assert: provider-error items ───────────────────────────────────────
    errored = db.session.query(WantedItem).filter(WantedItem.failure_kind == "provider_error").all()
    assert len(errored) == 2
    for item in errored:
        assert item.title.startswith("Never_")
        assert item.error_count == 1
        # Crucial: provider errors must NOT bump search_count.
        assert item.search_count == 0
        assert item.retry_after is not None
        # Error column should carry the truncated message for operator visibility.
        assert item.error and "429" in item.error
        # Status stays "wanted" — the item is still in the search queue.
        assert item.status == "wanted"

    # ── Assert: no legacy freeze ───────────────────────────────────────────
    # The whole point of Phase 1: no item is ever marked with the old
    # "Max search attempts reached" error string. The 2 old-backlog items
    # are ineligible (search_count=5 >= 3) but they sit idle — never frozen.
    frozen = (
        db.session.query(WantedItem)
        .filter(WantedItem.error == "Max search attempts reached")
        .count()
    )
    assert frozen == 0

    # Sanity: the 2 old-backlog items were skipped entirely (still
    # search_count=5, still status="wanted", no failure_kind churn).
    old_backlog = db.session.query(WantedItem).filter(WantedItem.title.like("OldBacklog_%")).all()
    assert len(old_backlog) == 2
    for item in old_backlog:
        assert item.status == "wanted"
        assert item.search_count == 5
