"""Standalone eligibility and extraction helpers for the wanted scheduler.

Extracted from services/wanted_search_runner.py. Pure functions that
do not participate in test patching of the runner module — they operate
only on arguments passed in.
"""

import logging
import time
from datetime import UTC, datetime

from services.embedded_extractor import extract_embedded_sub
from services.scheduler.cancellation import abort_requested

logger = logging.getLogger(__name__)


def _stop_requested(cancel_event) -> bool:
    """Whether this tick has been told to stop.

    Two independent signals, one meaning: the user's Cancel button sets
    ``cancel_event``, the scheduler sets its own event on the running thread
    when a tick overruns its timeout. A phase that only watches one of them
    keeps working through the other — which is how a 1800s ``wanted_search``
    timeout turned into a 21-hour run on prod.
    """
    return (cancel_event is not None and cancel_event.is_set()) or abort_requested()


def _deadline_passed(deadline) -> bool:
    """Whether a phase's wall-clock budget is spent.

    ``deadline`` is a monotonic timestamp, a callable returning one, or None
    for "no budget". The callable form exists so a caller can move the
    deadline while the phase is running.
    """
    if deadline is None:
        return False
    try:
        value = deadline() if callable(deadline) else deadline
    except Exception:  # noqa: BLE001 — an unreadable budget must not stop work
        logger.debug("deadline callable raised — treating the budget as open", exc_info=True)
        return False
    return time.monotonic() >= value


# existing_sub values that already route through the embedded-extraction path
# in run_wanted_search — these never need the local-sidecar split below since
# they're already provider-free.
_EMBEDDED_TYPES = ("embedded_ass", "embedded_srt")


def _apply_backlog_reserve_gate(
    items: list[dict],
    budget_states: list[dict],
    reserve_pct: int,
    exempt_ids: set[int] | None = None,
) -> list[dict]:
    """Drop ``priority == 'backlog'`` items when any provider is above reserve_pct.

    Each ``budget_states`` entry is a dict with ``usage.day`` and ``limits.day``
    (matching the shape returned by ``/api/v1/system/budget``). Providers with
    missing/zero day limit contribute ratio 0.

    ``exempt_ids`` is a set of item ids that should bypass the backlog gate —
    used by the Phase 4a min-per-day prefix so quota items survive even when a
    provider is above the reserve threshold.
    """

    def _ratio(state: dict) -> float:
        usage = (state.get("usage") or {}).get("day", 0)
        limit = (state.get("limits") or {}).get("day", 0)
        if not limit:
            return 0.0
        return usage / limit

    max_ratio = max((_ratio(s) for s in budget_states), default=0.0)
    threshold = reserve_pct / 100.0
    if max_ratio < threshold:
        return items
    return [
        i
        for i in items
        if (exempt_ids is not None and i.get("id") in exempt_ids)
        or (i.get("priority") or "standard") != "backlog"
    ]


def _filter_eligible(items: list[dict], settings) -> list[dict]:
    """Filter items by adaptive backoff, fixed cooldown, and search-count cap.

    Eligibility rules:
      1. ``retry_after`` (when set) governs the backoff window; items in the
         future are skipped.
      2. The ``search_count`` cap (``wanted_max_search_attempts``) hard-stops
         items unless they carry the explicit ``failure_kind='no_result_slow'``
         marker AND their ``retry_after`` window has elapsed. Slow-mode is the
         intentional bypass: once an item exhausted its budget, it gets
         re-tried roughly once per 30 days instead of being frozen forever.
    """
    eligible = []
    now = datetime.now(UTC)
    adaptive_enabled = getattr(settings, "wanted_adaptive_backoff_enabled", True)

    for item in items:
        retry_at: datetime | None = None
        if adaptive_enabled:
            retry_after_str = item.get("retry_after")
            if retry_after_str:
                try:
                    retry_at = datetime.fromisoformat(retry_after_str)
                    if retry_at.tzinfo is None:
                        retry_at = retry_at.replace(tzinfo=UTC)
                    if now < retry_at:
                        continue
                except (ValueError, TypeError):
                    retry_at = None
        else:
            last_str = item.get("last_search_at")
            if last_str:
                try:
                    last = datetime.fromisoformat(last_str)
                    if last.tzinfo is None:
                        last = last.replace(tzinfo=UTC)
                    if (now - last).total_seconds() < 3600:
                        continue
                except (ValueError, TypeError):
                    pass

        if item["search_count"] < settings.wanted_max_search_attempts:
            eligible.append(item)
            continue

        # Slow-mode bypass: at-or-above the cap, but the recorder explicitly
        # marked this item for periodic retries. retry_at must already be set
        # (and elapsed — checked above), otherwise the cap stands.
        if item.get("failure_kind") == "no_result_slow" and retry_at is not None:
            eligible.append(item)

    return eligible


def _enqueue_embedded_items(embedded_items, settings) -> tuple[list[dict], int]:
    """Enqueue embedded-sub items to the subtitle-automation queue.

    Mirrors the scan-time routing in
    ``wanted_scanner_sources._maybe_auto_extract``: when automation is on,
    the drain worker owns extraction. Returns ``(leftover, enqueued)`` —
    leftovers are items that could not be enqueued (no resolvable target
    language, or the repository raised); the caller decides whether they
    fall back to inline extraction or to the normal provider search.
    """
    from db.repositories.subtitle_automation_queue import (
        SubtitleAutomationQueueRepository,
    )

    leftover: list[dict] = []
    enqueued = 0
    repo = SubtitleAutomationQueueRepository()
    for item in embedded_items:
        target_lang = item.get("target_language") or getattr(settings, "target_language", "")
        if not target_lang:
            leftover.append(item)
            continue
        try:
            repo.enqueue(
                wanted_item_id=item["id"],
                file_path=item["file_path"],
                target_language=target_lang,
            )
            enqueued += 1
        except Exception as exc:  # noqa: BLE001 — enqueue must never break the search tick
            logger.warning(
                "[search_all] automation enqueue failed for item %d: %s — falling back",
                item["id"],
                exc,
            )
            leftover.append(item)
    return leftover, enqueued


def _extract_embedded_items(
    embedded_items, processed, found, failed, total, socketio, settings, cancel_event=None
) -> tuple[int, int, int]:
    """Extract embedded subtitles for items that have them."""
    auto_translate = getattr(settings, "wanted_auto_translate", False)
    for item in embedded_items:
        if _stop_requested(cancel_event):
            logger.info("[search_all] embedded extraction cancelled after %d items", processed)
            break
        try:
            extract_embedded_sub(item["id"], item["file_path"], auto_translate=auto_translate)
            found += 1
        except Exception as exc:
            logger.warning("[search_all] Extraction failed for item %d: %s", item["id"], exc)
            failed += 1
        processed += 1
        if socketio:
            socketio.emit(
                "wanted_search_progress",
                {
                    "processed": processed,
                    "total": total,
                    "found": found,
                    "failed": failed,
                    "current_item": item.get("title", str(item["id"])),
                },
            )
    return processed, found, failed


def _split_local_translate_items(items: list[dict], settings) -> tuple[list[dict], list[dict]]:
    """Pull out items with an external source-language sidecar already on disk.

    These need zero provider calls — ``translate_file`` (Case C2b) would find
    and use the sidecar anyway once an item reaches Step 5 of the normal
    pipeline. The problem this closes: the ``retry_after`` eligibility gate
    (``_filter_eligible``) operates purely on DB fields and has no idea a
    local sidecar exists, so an item with real material sitting on disk waits
    behind the same provider-rate-limit backoff as one with nothing at all —
    confirmed on prod: 1012 of 2133 wanted items had a ready ``.eng.ass``
    sidecar, 0 were ever picked up while auto-translate was on.

    Only applies when ``wanted_auto_translate`` is enabled — otherwise
    diverting these items would skip Steps 1/3's chance at a genuine
    target-language provider match for no benefit (nothing would translate
    the sidecar anyway).

    Returns ``(local_translate_items, remaining_items)``.
    """
    if not getattr(settings, "wanted_auto_translate", False):
        return [], items

    from translator._helpers import find_any_source_sub

    local_items = []
    remaining = []
    for item in items:
        if item.get("existing_sub") in _EMBEDDED_TYPES:
            remaining.append(item)
            continue
        try:
            src_path, _src_lang = find_any_source_sub(
                item["file_path"], target_language=item.get("target_language")
            )
        except Exception as exc:  # noqa: BLE001 — a probe failure must not block the item
            logger.debug("[search_all] local-sidecar probe failed for item %d: %s", item["id"], exc)
            src_path = None
        if src_path:
            local_items.append(item)
        else:
            remaining.append(item)
    return local_items, remaining


def _translate_local_sidecar_items(
    local_items,
    processed,
    found,
    failed,
    total,
    socketio,
    settings,
    cancel_event=None,
    deadline=None,
) -> tuple[int, int, int]:
    """Translate items whose external source sidecar was found by the split above.

    Calls the same Step-5 fallback the normal per-item pipeline would
    eventually reach (``wanted_search.process._fallback_translate_file``) —
    no provider search, no retry_after gate, just the local translate.

    Each item is a full LLM translation, so this loop is the most expensive
    phase of the tick and the one most likely to be running when a timeout
    fires. It checks the stop signal between items, and stops at ``deadline``
    when the caller gives it one — a count cap cannot bound a phase whose
    unit cost is minutes and varies with subtitle length.
    """
    from wanted_search.process import _fallback_translate_file

    auto_translate = getattr(settings, "wanted_auto_translate", False)
    for item in local_items:
        if _stop_requested(cancel_event) or _deadline_passed(deadline):
            logger.info(
                "[search_all] local-sidecar translation stopped after %d items "
                "(cancelled or out of budget)",
                processed,
            )
            break
        item_lang = item.get("target_language") or settings.target_language
        ctx = {
            "item": item,
            "item_id": item["id"],
            "item_lang": item_lang,
            "settings": settings,
            "auto_translate": auto_translate,
            "file_path": item["file_path"],
        }
        try:
            result = _fallback_translate_file(ctx)
            if result.get("status") == "found":
                found += 1
            else:
                failed += 1
        except Exception as exc:
            logger.warning(
                "[search_all] Local sidecar translate failed for item %d: %s", item["id"], exc
            )
            failed += 1
        processed += 1
        if socketio:
            socketio.emit(
                "wanted_search_progress",
                {
                    "processed": processed,
                    "total": total,
                    "found": found,
                    "failed": failed,
                    "current_item": item.get("title", str(item["id"])),
                },
            )
    return processed, found, failed
