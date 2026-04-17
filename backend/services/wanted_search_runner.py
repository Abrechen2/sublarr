"""Wanted search runner — searches providers for all wanted items.

Extracted from WantedScanner to keep the core module focused on
scanning/scheduling coordination. Used by WantedScanner.search_all().
"""

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime, timedelta

from config import get_settings
from db.activity import log_activity
from db.models.activity import EVENT_SEARCH

logger = logging.getLogger(__name__)


# ── Failure-kind split + exponential backoff ─────────────────────────────────
# Backoff schedule for provider-side errors (network, 429, circuit-breaker).
# Index N in the list is the delay after the (N+1)-th error. Anything beyond
# the last entry caps at the final value — here, 30 days.
# Keeping the values as timedelta objects means callers just add to `now`.
_ERROR_BACKOFF_TABLE: list[timedelta] = [
    timedelta(hours=6),  # 1st error
    timedelta(hours=24),  # 2nd error
    timedelta(days=3),  # 3rd error
    timedelta(days=7),  # 4th error
    timedelta(days=30),  # 5th+ error (cap)
]


def compute_retry_after_for_error(error_count: int, now: datetime) -> datetime:
    """Pure function: return ``now + backoff`` for the N-th provider error.

    Provider errors are counted separately from ``search_count`` so transient
    outages (network, 429, circuit-breaker OPEN) do not burn an item's retry
    budget. The backoff curve is:

    - 1st error: +6h
    - 2nd error: +24h
    - 3rd error: +3d
    - 4th error: +7d
    - 5th+: +30d (cap)

    ``error_count`` values below 1 are clamped to 1 so callers passing the raw
    column value (e.g. before increment) still get a sensible result.
    """
    idx = max(1, error_count) - 1
    if idx >= len(_ERROR_BACKOFF_TABLE):
        idx = len(_ERROR_BACKOFF_TABLE) - 1
    return now + _ERROR_BACKOFF_TABLE[idx]


def record_search_outcome(
    item_id: int,
    kind: str,
    error_message: str | None = None,
) -> None:
    """Central mutation point for any scheduler-driven search outcome.

    - ``'found'``: clear failure state (error_count=0, failure_kind=None, …) and
      set ``status='found'``.
    - ``'no_result'``: genuine miss — providers have nothing. Increments
      ``search_count`` and sets a short backoff. Once ``search_count`` reaches
      ``wanted_max_search_attempts``, the item enters slow-mode: status stays
      ``'wanted'``, ``failure_kind='no_result_slow'``, retry in 30 days. This
      replaces the old permanent freeze.
    - ``'provider_error'``: transient provider failure (network, 429, circuit
      breaker). Increments ``error_count`` only (never ``search_count``), with
      the exponential backoff from ``compute_retry_after_for_error``. Stores
      the first 500 chars of ``error_message`` in the existing ``error``
      column for operator visibility.

    Unknown ``kind`` values raise ``ValueError`` — silently accepting typos
    would mask scheduler bugs that only show up in production.
    """
    # Imports deferred: keeps top-level import graph clean and avoids a
    # circular dependency (db.wanted imports repositories which import models
    # which pull in extensions which can transitively touch services).
    from db.wanted import get_wanted_item, update_wanted_search_outcome

    now = datetime.now(UTC)
    settings = get_settings()

    if kind == "found":
        update_wanted_search_outcome(
            item_id,
            status="found",
            reset_failure=True,
        )
        return

    if kind == "provider_error":
        # Read CURRENT count FIRST for the backoff-table lookup only. The DB
        # write below is atomic via error_count_increment, so even if two
        # threads race and both read the same pre-increment value, the
        # counter is still correct; the only cost is a marginal retry_after
        # delay difference, which is acceptable.
        item = get_wanted_item(item_id)
        if not item:
            logger.debug("record_search_outcome: item %d not found", item_id)
            return
        prior = item.get("error_count") or 0
        retry_at = compute_retry_after_for_error(prior + 1, now)
        update_wanted_search_outcome(
            item_id,
            error_count_increment=1,
            failure_kind="provider_error",
            retry_after=retry_at,
            last_error_at=now,
            # None means "leave error column alone" (don't clobber prior notes);
            # an explicit message is truncated to the 500-char column limit.
            error=(error_message[:500] if error_message else None),
        )
        return

    if kind == "no_result":
        # Atomic increment via SQL, then re-read to decide slow-mode.
        # Two SQL calls total (update + select) vs. the previous three
        # (select + select + update). The slow-mode branch below may issue
        # a follow-up update to patch failure_kind/retry_after.
        updated = update_wanted_search_outcome(
            item_id,
            search_count_increment=1,
            failure_kind="no_result",
            last_search_at=now,
        )
        if not updated:
            logger.debug("record_search_outcome: item %d not found", item_id)
            return
        item = get_wanted_item(item_id)
        if not item:
            return
        new_count = item["search_count"]
        max_attempts = getattr(settings, "wanted_max_search_attempts", 3)
        base_h = getattr(settings, "wanted_backoff_base_hours", 1.0)
        cap_h = getattr(settings, "wanted_backoff_cap_hours", 168)
        if new_count >= max_attempts:
            # Slow-mode: one attempt per 30 days instead of freezing forever.
            retry_at = now + timedelta(days=30)
            failure_kind = "no_result_slow"
        else:
            backoff_hours = min(base_h * (2 ** (new_count - 1)), cap_h)
            retry_at = now + timedelta(hours=backoff_hours)
            failure_kind = "no_result"
        update_wanted_search_outcome(
            item_id,
            failure_kind=failure_kind,
            retry_after=retry_at,
        )
        return

    raise ValueError(f"unknown outcome kind: {kind}")


def _search_with_ctx(app, item_id: int) -> dict:
    """Worker wrapper: push a new Flask app context for each thread."""
    with app.app_context():
        from wanted_search import process_wanted_item

        return process_wanted_item(item_id)


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
    from datetime import UTC, datetime

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


def _filter_eligible(items: list[dict], settings) -> list[dict]:
    """Filter items by adaptive backoff or fixed cooldown."""
    eligible = []
    now = datetime.now(UTC)
    adaptive_enabled = getattr(settings, "wanted_adaptive_backoff_enabled", True)

    for item in items:
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
                    pass
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

    return eligible


def _extract_embedded_items(
    embedded_items, processed, found, failed, total, socketio, settings
) -> tuple[int, int, int]:
    """Extract embedded subtitles for items that have them."""
    auto_translate = getattr(settings, "wanted_auto_translate", False)
    for item in embedded_items:
        try:
            from routes.wanted import _extract_embedded_sub

            _extract_embedded_sub(item["id"], item["file_path"], auto_translate=auto_translate)
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
