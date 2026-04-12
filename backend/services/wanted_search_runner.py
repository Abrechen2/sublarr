"""Wanted search runner — searches providers for all wanted items.

Extracted from WantedScanner to keep the core module focused on
scanning/scheduling coordination. Used by WantedScanner.search_all().
"""

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime

from config import get_settings
from db.activity import log_activity
from db.models.activity import EVENT_SEARCH

logger = logging.getLogger(__name__)


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
    max_items = settings.wanted_search_max_items_per_run

    # Determine whether upgrade candidates are included
    upgrade_enabled = getattr(settings, "upgrade_scan_interval_hours", 0) > 0
    if include_upgrades is None:
        include_upgrades = upgrade_enabled

    from db.wanted import get_wanted_items

    result = get_wanted_items(page=1, per_page=max_items, status="wanted")
    items = result.get("data", [])

    if not include_upgrades:
        items = [i for i in items if not i.get("upgrade_candidate")]

    # Filter by backoff / cooldown
    eligible = _filter_eligible(items, settings)

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
