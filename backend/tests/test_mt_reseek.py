"""Tests for the provisional-MT re-seek job (feature #8b, Phase 2 — Task 1).

Covers:
- ``WantedRepository.get_provisional_items`` — selects ONLY ``status="provisional"``
  rows (a ``wanted`` item must never be picked by this job) and honours the
  per-item backoff cutoff.
- ``reseek_provisional_items`` — runs the normal search pipeline for each
  provisional item in ORIGINAL-ONLY mode (``auto_translate=False``), fires the
  ``_on_original_found`` hook on a found original, and bumps ``last_search_at``
  (leaving the item provisional) on a miss.

The re-seek loop tests mock the DB/repo + ``process_wanted_item`` exactly like
``tests/test_upgrade_scheduler.py`` so they need neither disk nor a real search.
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

from db.models.core import WantedItem
from extensions import db

# ── Repository selection (real DB via app_ctx) ───────────────────────────────


def _make_wanted_item(**kwargs) -> WantedItem:
    """Insert a minimal WantedItem; returns the persisted row."""
    now = datetime(2026, 7, 5, tzinfo=UTC)
    defaults = dict(
        item_type="episode",
        file_path=f"/media/reseek_{id(kwargs):x}.mkv",
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


def test_get_provisional_items_selects_only_provisional(app_ctx):
    from db.repositories.wanted import WantedRepository

    prov = _make_wanted_item(file_path="/media/prov.mkv", status="provisional")
    _make_wanted_item(file_path="/media/wanted.mkv", status="wanted")
    _make_wanted_item(file_path="/media/done.mkv", status="found")

    rows = WantedRepository().get_provisional_items(limit=10)

    ids = {r["id"] for r in rows}
    assert ids == {prov.id}
    assert all(r["status"] == "provisional" for r in rows)


def test_get_provisional_items_respects_backoff(app_ctx):
    from db.repositories.wanted import WantedRepository

    now = datetime.now(UTC)
    recent = _make_wanted_item(
        file_path="/media/recent.mkv",
        status="provisional",
        last_search_at=now - timedelta(hours=1),
    )
    old = _make_wanted_item(
        file_path="/media/old.mkv",
        status="provisional",
        last_search_at=now - timedelta(hours=48),
    )
    never = _make_wanted_item(
        file_path="/media/never.mkv",
        status="provisional",
        last_search_at=None,
    )

    cutoff = now - timedelta(hours=24)
    rows = WantedRepository().get_provisional_items(limit=10, search_cutoff=cutoff)

    ids = {r["id"] for r in rows}
    assert old.id in ids
    assert never.id in ids
    assert recent.id not in ids  # searched too recently → backed off


# ── Re-seek loop (mocked DB/repo/search, mirrors test_upgrade_scheduler) ──────


def _run_reseek(items, process_status="not_found", keep_seeking=True):
    """Run reseek_provisional_items with mocked DB, repo, and search entry.

    Returns (result, calls, mock_update, mock_hook) where ``calls`` is the list
    of (item_id, auto_translate) tuples passed to ``process_wanted_item``.
    """
    calls: list = []

    def fake_process(item_id, auto_translate=None):
        calls.append((item_id, auto_translate))
        return {"wanted_id": item_id, "status": process_status}

    mock_repo = MagicMock()
    mock_repo.get_provisional_items.return_value = items

    settings = MagicMock()
    settings.wanted_search_interval_hours = 24
    settings.mt_reseek_max_items_per_run = 50

    with (
        patch("config.get_settings", return_value=settings),
        patch("db.repositories.wanted.WantedRepository", return_value=mock_repo),
        patch("wanted_search.process_wanted_item", side_effect=fake_process),
        patch("services.mt_provisional.resolve_keep_seeking", return_value=keep_seeking),
        patch("db.wanted.update_wanted_search_outcome") as mock_update,
        patch("services.mt_reseek._on_original_found") as mock_hook,
    ):
        from services.mt_reseek import reseek_provisional_items

        result = reseek_provisional_items(MagicMock())
    return result, calls, mock_update, mock_hook


def test_reseek_searches_provisional_with_auto_translate_false():
    result, calls, mock_update, mock_hook = _run_reseek(
        [{"id": 7, "status": "provisional"}], process_status="not_found"
    )

    # Provisional item was searched — exactly once, with translation disabled.
    assert calls == [(7, False)]
    assert result["searched"] == 1
    assert result["found"] == 0
    # On a miss the on-found hook must NOT fire...
    assert not mock_hook.called
    # ...and last_search_at is bumped while the item stays provisional.
    assert mock_update.called
    _, kwargs = mock_update.call_args
    assert kwargs.get("status") == "provisional"
    assert kwargs.get("last_search_at") is not None


def test_reseek_fires_hook_when_original_found():
    result, calls, mock_update, mock_hook = _run_reseek(
        [{"id": 9, "status": "provisional"}], process_status="found"
    )

    assert calls == [(9, False)]
    assert result["found"] == 1
    assert mock_hook.called  # Task-2 replace/notify hook wired at the call site
    assert not mock_update.called  # found path does NOT bump last_search_at


def test_reseek_skips_when_profile_no_longer_keep_seeking():
    result, calls, mock_update, mock_hook = _run_reseek(
        [{"id": 3, "status": "provisional"}], keep_seeking=False
    )

    # Profile turned keep-seeking off → item is not searched at all.
    assert calls == []
    assert result["searched"] == 0
    assert result["skipped"] == 1
    assert not mock_hook.called
