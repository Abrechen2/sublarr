"""Standalone eligibility and extraction helpers for the wanted scheduler.

Extracted from services/wanted_search_runner.py. Pure functions that
do not participate in test patching of the runner module — they operate
only on arguments passed in.
"""

import logging
from datetime import UTC, datetime

logger = logging.getLogger(__name__)


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
