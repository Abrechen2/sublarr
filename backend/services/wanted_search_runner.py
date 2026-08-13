"""Wanted search runner — searches providers for all wanted items.

Extracted from WantedScanner to keep the core module focused on
scanning/scheduling coordination. Used by WantedScanner.search_all().

The outcome-recording side (backoff table + record_search_outcome) lives
in sibling ``wanted_search_outcome``; the standalone gate/filter helpers
(backlog reserve, eligibility, embedded extraction) in
``wanted_search_filters``. Both are re-exported so
``from services.wanted_search_runner import X`` keeps working.

min-attempts helpers (``_series_min_attempts_config``, ``_series_searches_today``,
``_wanted_items_by_series``, ``_collect_min_attempts_items``) stay in this
module so tests can patch them via ``services.wanted_search_runner.X``.
"""

import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime

from config import get_settings
from db.activity import log_activity
from db.models.activity import EVENT_SEARCH
from services.scheduler.cancellation import abort_requested
from services.wanted_search_filters import (  # noqa: F401 — re-exported for back-compat
    _EMBEDDED_TYPES,
    _apply_backlog_reserve_gate,
    _enqueue_embedded_items,
    _extract_embedded_items,
    _filter_eligible,
    _split_local_translate_items,
    _translate_local_sidecar_items,
)
from services.wanted_search_outcome import (  # noqa: F401 — re-exported for back-compat
    _ERROR_BACKOFF_TABLE,
    compute_retry_after_for_error,
    record_search_outcome,
)

logger = logging.getLogger(__name__)

# Candidate-pool fetch cap for the scheduler's eligibility filter. The repo's
# ORDER BY + LIMIT fetch must not be capped at `wanted_search_max_items_per_run`
# — that would apply the ordering LIMIT before `_filter_eligible` ever runs,
# silently starving due items that merely have a more recent `last_search_at`
# than the rest of the backlog (confirmed on prod: 29 eligible items invisible
# behind a stale 2000-row fair-order window). 10_000 comfortably covers any
# realistic Sublarr wanted-item backlog (real libraries stay in the low
# thousands) while keeping the ORDER BY + LIMIT query cheap.
_ELIGIBILITY_FETCH_CAP = 10_000

# Ceiling for the local-sidecar translate phase, on top of
# `wanted_search_max_items_per_run`. That setting bounds the provider phase,
# which is parallel and cheap per item — prod runs it at 2000. The sidecar
# phase is serial and every item is a full LLM translation, so the same number
# describes a tick that cannot finish inside any sane timeout.
#
# The primary bound on this phase is time, not count: it checks the
# cancellation signal between items, so a scheduled tick stops when its budget
# runs out. This ceiling is the count-bound for the paths that have no such
# signal — a manual "search all" from the UI carries a cancel event nobody has
# pressed yet, and would otherwise take on the entire backlog.
_MAX_LOCAL_TRANSLATES_PER_TICK = 100


def _compute_max_workers(total: int, cpu_count: int | None) -> int:
    """Search workers = min(4, cores - 2), floor 1 — a 4-core NAS keeps 2
    cores free for API requests instead of saturating all of them."""
    cores = cpu_count or 4
    return max(1, min(4, cores - 2, total))


def _search_with_ctx(app, item_id: int) -> dict:
    """Worker wrapper: push a new Flask app context for each thread."""
    with app.app_context():
        from wanted_search import process_wanted_item

        return process_wanted_item(item_id)


def _series_min_attempts_config() -> dict[int, int]:
    """Return ``{sonarr_series_id: min_attempts_per_day}`` for series with min > 0."""
    from sqlalchemy import select as _select

    from db.models.core import SeriesSettings
    from extensions import db as _db

    try:
        rows = _db.session.execute(
            _select(
                SeriesSettings.sonarr_series_id,
                SeriesSettings.min_attempts_per_day,
            ).where(SeriesSettings.min_attempts_per_day > 0)
        ).all()
    except Exception as exc:  # noqa: BLE001
        logger.warning("series_min_attempts_config fetch failed: %s", exc)
        return {}
    return {sid: count for sid, count in rows}


def _series_searches_today(series_ids: list[int]) -> dict[int, int]:
    """Count wanted_item searches performed today per series.

    Defined as rows with ``last_search_at`` within the current UTC day.
    """
    # NOTE: counts items touched today (at least once), not discrete search
    # events. With `last_search_at` overwritten per attempt, a 2nd tick within
    # the same day re-counts the item as "already done". Safe direction:
    # under-counts attempts, so the prefix errs on the side of more searches,
    # not fewer — the quota guarantee is preserved. A discrete-event log
    # would let us count attempts exactly, but the under-counting bias here
    # is acceptable until that need materialises.
    from sqlalchemy import func as _func
    from sqlalchemy import select as _select

    from db.models.core import WantedItem
    from extensions import db as _db

    if not series_ids:
        return {}
    day_start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    try:
        rows = _db.session.execute(
            _select(
                WantedItem.sonarr_series_id,
                _func.count(WantedItem.id),
            )
            .where(
                WantedItem.sonarr_series_id.in_(series_ids),
                WantedItem.last_search_at >= day_start,
            )
            .group_by(WantedItem.sonarr_series_id)
        ).all()
    except Exception as exc:  # noqa: BLE001
        logger.warning("series_searches_today fetch failed: %s", exc)
        return {}
    return {sid: count for sid, count in rows}


def _wanted_items_by_series(series_ids: list[int]) -> dict[int, list[dict]]:
    """Return ``{series_id: [wanted_item_dict, ...]}`` ordered by oldest-searched first."""
    from db.repositories.wanted import WantedRepository

    if not series_ids:
        return {}
    repo = WantedRepository()
    out = repo.get_wanted_by_series_bulk(series_ids)
    for sid in out:
        out[sid].sort(
            key=lambda it: (
                it.get("last_search_at") or "",  # NULLs first
                it.get("search_count", 0),
            )
        )
    return out


def _collect_min_attempts_items() -> list[dict]:
    """Collect wanted items that must be included this tick to honor
    ``series_settings.min_attempts_per_day``. Items are prefixed to the
    eligible list by the caller and survive the backlog-reserve gate."""
    config = _series_min_attempts_config()
    if not config:
        return []
    series_ids = list(config.keys())
    already = _series_searches_today(series_ids)
    by_series = _wanted_items_by_series(series_ids)
    out: list[dict] = []
    for sid, min_n in config.items():
        remaining = max(0, min_n - already.get(sid, 0))
        if remaining <= 0:
            continue
        items = by_series.get(sid, [])
        out.extend(items[:remaining])
    return out


def run_wanted_search(
    *,
    app=None,
    socketio=None,
    cancel_event=None,
    include_upgrades: bool | None = None,
) -> dict:
    """Search providers for all wanted items (respects max_items_per_run).

    Args:
        app: Flask application instance for worker thread contexts.
        socketio: SocketIO instance for progress emission.
        cancel_event: Threading event to signal cancellation.
        include_upgrades: Whether to include upgrade candidates. Defaults to
            True when upgrade_scan_interval_hours > 0, False otherwise.

    Returns summary dict: {total, processed, found, failed, skipped}
    """
    start = time.time()

    # Resolve Flask app reference
    _app = app
    if _app is None:
        try:
            from flask import current_app as _current_app

            _app = _current_app._get_current_object()
        except RuntimeError:
            _app = None

    settings = get_settings()

    # Disk safety-valve: refuse to run when /config is critically full. Downloads
    # land next to the DB on the same volume in the default Cardinal layout,
    # and a full /config corrupts the DB. Returning paused_reason rather than
    # raising lets the scheduler record the run as ok and try again next tick.
    from services.disk_safety import format_disk_status, is_disk_critical

    _config_dir = getattr(settings, "config_dir", "/config")
    _disk_threshold = float(getattr(settings, "wanted_search_disk_pause_pct", 98.0))
    if is_disk_critical(_config_dir, _disk_threshold):
        _disk_status = format_disk_status(_config_dir)
        logger.warning(
            "Wanted search paused — %s disk at %s (threshold %.1f%%)",
            _config_dir,
            _disk_status,
            _disk_threshold,
        )
        return {
            "total": 0,
            "processed": 0,
            "found": 0,
            "failed": 0,
            "skipped": 0,
            "paused_reason": "disk_critical",
            "disk_pct": _disk_status,
        }

    # Phase 3: ramp learned factors toward 1.0 once per tick (daily in default config).
    try:
        from services.provider_budget import get_budget_manager

        get_budget_manager().tick_recovery()
    except Exception as exc:  # noqa: BLE001
        logger.warning("tick_recovery failed (non-blocking): %s", exc)

    max_items = settings.wanted_search_max_items_per_run

    # Determine whether upgrade candidates are included
    upgrade_enabled = getattr(settings, "upgrade_scan_interval_hours", 0) > 0
    if include_upgrades is None:
        include_upgrades = upgrade_enabled

    from db.wanted import get_items_for_scheduled_search

    order = getattr(settings, "wanted_search_order", "fair")
    # Fetch a generous candidate pool, NOT `max_items` — see
    # _ELIGIBILITY_FETCH_CAP for why the fetch limit and the per-tick
    # processing cap must be decoupled.
    items = get_items_for_scheduled_search(limit=_ELIGIBILITY_FETCH_CAP, order=order)

    if not include_upgrades:
        items = [i for i in items if not i.get("upgrade_candidate")]

    # Pull out items with a source-language sidecar already on disk BEFORE
    # the retry_after gate — they need zero provider calls, so they must
    # never wait behind the same backoff as items with no local material at
    # all (see _split_local_translate_items docstring).
    local_translate_items, items = _split_local_translate_items(items, settings)

    # Filter by backoff / cooldown — runs across the FULL fetched pool so due
    # items are never invisible to this filter (see _ELIGIBILITY_FETCH_CAP).
    eligible = _filter_eligible(items, settings)

    # Phase 4a: min-per-day prefix — must-include items that survive the backlog gate.
    try:
        min_prefix = _collect_min_attempts_items()
    except Exception as exc:  # noqa: BLE001
        logger.warning("min_attempts prefix failed (non-blocking): %s", exc)
        min_prefix = []
    if min_prefix:
        seen = {i["id"] for i in min_prefix}
        eligible = min_prefix + [i for i in eligible if i["id"] not in seen]
    else:
        seen = set()

    # Phase 3: drop backlog items when any provider is >N% spent. Best-effort —
    # if any part of the lookup fails we keep the original list.
    if eligible:
        try:
            from providers import get_provider_manager
            from services.provider_budget import get_budget_manager

            budget_mgr = get_budget_manager()
            provider_mgr = get_provider_manager()
            budget_states: list[dict] = []
            for name, provider in provider_mgr._providers.items():
                tier = getattr(provider, "tier", "free")
                rate_limits = getattr(type(provider), "rate_limits", {}) or {}
                limits = rate_limits.get(tier) or rate_limits.get("free") or {}
                usage = budget_mgr.get_usage(name)
                budget_states.append({"usage": usage, "limits": limits})
            reserve_pct = max(
                1,
                min(100, int(getattr(settings, "wanted_scheduler_backlog_reserve_pct", 50))),
            )
            eligible = _apply_backlog_reserve_gate(
                eligible, budget_states, reserve_pct, exempt_ids=seen
            )
        except Exception as _bge:  # noqa: BLE001
            logger.warning("backlog reserve gate failed (non-blocking): %s", _bge)

    # Truncate to the per-tick processing cap AFTER eligibility filtering (and
    # after the min-per-day prefix + backlog reserve gate), so max_items still
    # bounds the actual workload without reintroducing the LIMIT-before-filter
    # starvation bug. Ordering (fair/newest_first/weighted, plus the min-prefix
    # items kept at the front) is preserved since we only slice the list.
    eligible = eligible[:max_items]

    # The sidecar phase needs its own bound. It is split off the raw fetch pool
    # above, so without one it was the single workload a tick could take on
    # without limit: 3124 items on prod 2026-08-12, each a full LLM
    # translation, and the tick never returned.
    #
    # `max_items` alone does not supply that bound — prod has it at 2000, which
    # for a serial multi-minute phase is no bound at all. Hence the smaller
    # ceiling, with `max_items` still respected when a user has set it lower.
    #
    # The two phases are bounded separately rather than sharing one budget:
    # they spend different resources (local compute vs provider quota), and a
    # shared budget would let a sidecar backlog starve provider search tick
    # after tick — the failure this whole bound exists to prevent.
    local_translate_items = local_translate_items[: min(max_items, _MAX_LOCAL_TRANSLATES_PER_TICK)]

    if not eligible and not local_translate_items:
        return {"total": 0, "processed": 0, "found": 0, "failed": 0, "skipped": 0}

    # Split: embedded subs → extraction, rest → provider search.
    # Issue #159: the split only happens when the user opted into an
    # extraction path. With subtitle_automation_enabled and
    # wanted_auto_extract both off, embedded items stay in the normal
    # provider search and their files are never touched.
    automation_on = bool(getattr(settings, "subtitle_automation_enabled", False))
    auto_extract_on = bool(getattr(settings, "wanted_auto_extract", False))

    if automation_on or auto_extract_on:
        embedded_items = [i for i in eligible if i.get("existing_sub") in _EMBEDDED_TYPES]
        search_items = [i for i in eligible if i.get("existing_sub") not in _EMBEDDED_TYPES]
    else:
        embedded_items = []
        search_items = list(eligible)

    enqueued_count = 0
    if automation_on and embedded_items:
        # Preferred path: hand embedded items to the automation queue — the
        # drain worker owns extraction (and respects its own gates). Items
        # that could not be enqueued fall through to the legacy inline path,
        # or back to the provider search when that toggle is off too.
        embedded_items, enqueued_count = _enqueue_embedded_items(embedded_items, settings)
        if enqueued_count:
            logger.info(
                "[search_all] %d items have embedded subs — enqueued for the automation drain",
                enqueued_count,
            )
    if embedded_items and not auto_extract_on:
        search_items = embedded_items + search_items
        embedded_items = []

    if embedded_items:
        logger.info(
            "[search_all] %d items have embedded subs — extracting instead of searching",
            len(embedded_items),
        )
    if local_translate_items:
        logger.info(
            "[search_all] %d items have a local source sidecar — translating "
            "directly instead of searching",
            len(local_translate_items),
        )

    total = len(eligible) + len(local_translate_items)
    processed = 0
    found = 0
    failed = 0
    skipped = 0

    # Enqueued items are handed off to the drain worker, not searched this tick.
    processed += enqueued_count
    skipped += enqueued_count

    # Translate local-sidecar items first — no provider involved at all.
    processed, found, failed = _translate_local_sidecar_items(
        local_translate_items, processed, found, failed, total, socketio, settings, cancel_event
    )

    # Extract embedded-sub items next
    processed, found, failed = _extract_embedded_items(
        embedded_items, processed, found, failed, total, socketio, settings, cancel_event
    )

    # Parallel provider search
    eligible = search_items
    max_workers = _compute_max_workers(total, os.cpu_count())
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        if _app is not None:
            future_to_item = {
                executor.submit(_search_with_ctx, _app, item["id"]): item for item in eligible
            }
        else:
            from wanted_search import process_wanted_item

            future_to_item = {
                executor.submit(process_wanted_item, item["id"]): item for item in eligible
            }

        for future in as_completed(future_to_item):
            # Two ways to be told to stop, one exit: the user's Cancel button
            # sets cancel_event, while the scheduler sets its own signal on a
            # timeout or a pause. Both mean "stop after the items already in
            # flight", which is exactly what this branch already did.
            if (cancel_event and cancel_event.is_set()) or abort_requested():
                logger.info("Wanted search cancelled after %d/%d items", processed, total)
                for f in future_to_item:
                    f.cancel()
                break

            item = future_to_item[future]
            try:
                res = future.result()
                processed += 1
                if res.get("status") == "found":
                    found += 1
                elif res.get("status") == "failed":
                    failed += 1
                else:
                    skipped += 1
            except Exception as e:
                processed += 1
                failed += 1
                logger.warning("Search-all: error on item %d: %s", item["id"], e)

            if socketio:
                progress_data = {
                    "processed": processed,
                    "total": total,
                    "found": found,
                    "failed": failed,
                    "current_item": item.get("title", str(item["id"])),
                }
                try:
                    from providers import get_provider_manager

                    progress_data["provider_summary"] = (
                        get_provider_manager().get_provider_summary()
                    )
                except Exception:
                    pass
                socketio.emit("wanted_search_progress", progress_data)

    duration = round(time.time() - start, 1)

    summary = {
        "total": total,
        "processed": processed,
        "found": found,
        "failed": failed,
        "skipped": skipped,
        "duration_seconds": duration,
    }

    logger.info(
        "Wanted search complete: %d/%d processed, %d found, %d failed (%.1fs)",
        processed,
        total,
        found,
        failed,
        duration,
    )

    from events import emit_event

    emit_event("wanted_search_complete", summary)

    log_activity(
        EVENT_SEARCH,
        status="success",
        details={
            "found": summary.get("found", 0),
            "processed": summary.get("processed", 0),
            "failed": summary.get("failed", 0),
            "duration": summary.get("duration_seconds"),
        },
    )

    return summary
