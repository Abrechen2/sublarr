"""Regression test for the 2026-05-06 legacy_frozen relapse.

Production audit on 2026-05-06 found 2005 wanted_items in
``(search_count=3, failure_kind=NULL, retry_after=NULL)`` despite the
2026-04-27 resurrection migration. The migration's ``_filter_eligible``
fix shipped fine, but ``process_wanted_item`` itself still produced new
legacy_frozen rows when:

  * ``wanted_auto_translate`` is False (typical Sublarr setup —
    translation is gated off because the local model is unreliable),
  * provider Steps 1-4 all return None (genuine "no provider has it").

The flow:
  1. ``_check_max_search_attempts`` lets items below the cap pass.
  2. ``update_wanted_search(item_id)`` bumps ``search_count`` (e.g. 2 → 3)
     and sets ``last_search_at`` — but does NOT touch ``failure_kind``.
  3. Steps 1-4 search, return None.
  4. ``_fallback_translate_file`` with ``auto_translate=False``:
     just ``update_wanted_status(item_id, "wanted")`` and returns. It
     never funnels through ``record_search_outcome``, so
     ``failure_kind`` stays NULL and ``retry_after`` stays NULL.

Result: item at ``search_count=cap, failure_kind=NULL, retry_after=NULL``
— exact legacy_frozen shape. ``_filter_eligible`` then drops it forever.

These tests pin the contract: any "no provider result" outcome from
``process_wanted_item`` must funnel through ``record_search_outcome``
so failure_kind + retry_after are set on the row.
"""

from __future__ import annotations

from datetime import UTC, datetime

from db.models.core import WantedItem
from extensions import db


def _seed_item(*, search_count: int, file_path: str) -> int:
    """Insert a movie-type wanted item one configurable step from the cap."""
    now = datetime.now(UTC)
    item = WantedItem(
        item_type="movie",
        file_path=file_path,
        title="Test_Movie",
        existing_sub="",
        missing_languages='["de"]',
        embedded_languages="[]",
        target_language="de",
        subtitle_type="full",
        status="wanted",
        search_count=search_count,
        added_at=now,
        updated_at=now,
    )
    db.session.add(item)
    db.session.commit()
    return item.id


def _patch_process_module(monkeypatch) -> None:
    """Patch the per-item helpers so ``process_wanted_item`` walks straight
    through the orchestrator into ``_fallback_translate_file``.

    We mock:
      * profile filters → empty (no cutoff, no audio_exclude),
      * existing-sidecar probe → None (no on-disk shortcut),
      * build_query → minimal stub (avoids Sonarr/Radarr/file-hash work),
      * all 4 provider Step functions → None (= "no result").
    """
    from wanted_search import process as proc

    monkeypatch.setattr(
        proc,
        "_load_profile_filters",
        lambda item, item_id: {
            "cutoff_language": None,
            "audio_exclude_languages": [],
            "must_contain": [],
            "must_not_contain": [],
            "hi_preference": "include",
            "forced_scoring": "include",
        },
    )
    monkeypatch.setattr(proc, "_check_existing_sidecar", lambda *a, **kw: None)

    class _StubQuery:
        languages: list[str] = []
        hi_preference: str = "include"
        forced_scoring: str = "include"

    monkeypatch.setattr(proc, "build_query_from_wanted", lambda item: _StubQuery())
    monkeypatch.setattr(proc, "_try_target_ass_direct", lambda ctx: None)
    monkeypatch.setattr(proc, "_try_source_ass_translation", lambda ctx: None)
    monkeypatch.setattr(proc, "_try_target_srt_direct", lambda ctx: None)
    monkeypatch.setattr(proc, "_try_source_srt_translation", lambda ctx: None)


def _settings(monkeypatch, *, max_attempts: int = 3) -> None:
    """Pin the settings ``process_wanted_item`` reads."""
    from config import get_settings

    s = get_settings()
    monkeypatch.setattr(s, "wanted_auto_translate", False, raising=False)
    monkeypatch.setattr(s, "wanted_max_search_attempts", max_attempts, raising=False)
    monkeypatch.setattr(s, "wanted_adaptive_backoff_enabled", True, raising=False)
    monkeypatch.setattr(s, "wanted_backoff_base_hours", 1.0, raising=False)
    monkeypatch.setattr(s, "wanted_backoff_cap_hours", 168, raising=False)
    monkeypatch.setattr(s, "wanted_skip_srt_on_no_ass", False, raising=False)
    monkeypatch.setattr(s, "target_language", "de", raising=False)


def test_no_result_at_cap_enters_slow_mode(app_ctx, monkeypatch, tmp_path):
    """search_count=2 → process → expect (3, no_result_slow, retry_after=+30d).

    This is the failure shape that produced 2005 stuck items in production.
    """
    video = tmp_path / "movie.mkv"
    video.write_bytes(b"fake")

    _settings(monkeypatch, max_attempts=3)
    _patch_process_module(monkeypatch)

    item_id = _seed_item(search_count=2, file_path=str(video))

    from wanted_search.process import process_wanted_item

    result = process_wanted_item(item_id)
    assert result["status"] == "not_found"

    db.session.expire_all()
    row = db.session.get(WantedItem, item_id)
    assert row.search_count == 3, "increment must happen exactly once"
    # THE bug-fix assertion: failure_kind must be set so _filter_eligible
    # can route the item through slow-mode rather than legacy-freezing it.
    assert row.failure_kind == "no_result_slow", (
        f"legacy_frozen regression — failure_kind={row.failure_kind!r}, "
        "expected 'no_result_slow' once search_count reaches the cap"
    )
    assert row.retry_after is not None, "slow-mode requires a populated retry_after"
    assert row.status == "wanted", "item must stay in the queue"


def test_no_result_below_cap_marks_no_result_failure_kind(app_ctx, monkeypatch, tmp_path):
    """search_count=0 → process → expect (1, no_result, retry_after=+1h).

    Even below the cap, every no-result outcome must funnel through
    record_search_outcome so retry_after governs the next attempt.
    """
    video = tmp_path / "movie.mkv"
    video.write_bytes(b"fake")

    _settings(monkeypatch, max_attempts=3)
    _patch_process_module(monkeypatch)

    item_id = _seed_item(search_count=0, file_path=str(video))

    from wanted_search.process import process_wanted_item

    process_wanted_item(item_id)

    db.session.expire_all()
    row = db.session.get(WantedItem, item_id)
    assert row.search_count == 1
    assert row.failure_kind == "no_result", (
        f"sub-cap no-result must still set failure_kind, got {row.failure_kind!r}"
    )
    assert row.retry_after is not None
    assert row.status == "wanted"
