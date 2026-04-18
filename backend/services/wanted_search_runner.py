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
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime

from config import get_settings
from db.activity import log_activity
from db.models.activity import EVENT_SEARCH
from services.wanted_search_filters import (  # noqa: F401 — re-exported for back-compat
    _apply_backlog_reserve_gate,
    _extract_embedded_items,
    _filter_eligible,
)
from services.wanted_search_outcome import (  # noqa: F401 — re-exported for back-compat
    _ERROR_BACKOFF_TABLE,
    compute_retry_after_for_error,
    record_search_outcome,
)

logger = logging.getLogger(__name__)


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
    # not fewer — the quota guarantee is preserved. TODO: revisit if a
    # search_event log table is introduced in Phase 4b.
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
    out: dict[int, list[dict]] = {}
    # TODO: batch into a single WHERE sonarr_series_id IN (...) query if
    # series_ids grows materially (e.g. Radarr collections).
    for sid in series_ids:
        items = repo.get_wanted_by_series(sid)
        items.sort(
            key=lambda it: (
                it.get("last_search_at") or "",  # NULLs first
                it.get("search_count", 0),
            )
        )
        out[sid] = items
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
    items = get_items_for_scheduled_search(limit=max_items, order=order)

    if not include_upgrades:
        items = [i for i in items if not i.get("upgrade_candidate")]

    # Filter by backoff / cooldown
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

    if not eligible:
        return {"total": 0, "processed": 0, "found": 0, "failed": 0, "skipped": 0}

    # Split: embedded subs → extraction, rest → provider search
    _embedded_types = ("embedded_ass", "embedded_srt")
    embedded_items = [i for i in eligible if i.get("existing_sub") in _embedded_types]
    search_items = [i for i in eligible if i.get("existing_sub") not in _embedded_types]

    if embedded_items:
        logger.info(
            "[search_all] %d items have embedded subs — extracting instead of searching",
            len(embedded_items),
        )

    total = len(eligible)
    processed = 0
    found = 0
    failed = 0
    skipped = 0

    # Extract embedded-sub items first
    processed, found, failed = _extract_embedded_items(
        embedded_items, processed, found, failed, total, socketio, settings
    )

    # Parallel provider search
    eligible = search_items
    max_workers = min(4, total)
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
            if cancel_event and cancel_event.is_set():
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
