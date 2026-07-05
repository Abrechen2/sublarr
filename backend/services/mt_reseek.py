"""Provisional machine-translation re-seek (feature #8b, Phase 2).

A dedicated scheduled job that re-searches wanted items sitting in the
``provisional`` state — a Sublarr machine-translation kept alive because the
governing profile has ``mt_keep_seeking_original=1`` — for a GENUINE
provider/embedded original. It runs the normal search pipeline in
ORIGINAL-ONLY mode (``process_wanted_item(..., auto_translate=False)``) so no
re-translate loop can occur, and respects a per-item search backoff so the job
stays cheap.

Task 1 (this module) wires selection + original-only search + backoff. When an
original is found the actual replace/trash/notify handling is delegated to
``_on_original_found`` — a hook the next task (Phase 2 Task 2) fills in. It is a
no-op stub here; the call site is already wired so Task 2 only fills the body.

The job is naturally inert by default: ``mt_keep_seeking_original`` defaults to
0, so with no opted-in profile there are no ``provisional`` items to select.

Scheduler contract: ``mt_reseek_tick`` is a module-level, picklable callable
(SQLAlchemyJobStore pickles jobs — no closures). It runs inside the app context
the scheduler ``_tick_wrapper`` establishes, mirroring ``upgrade_tick``.
"""

from __future__ import annotations

import contextlib
import logging
from datetime import UTC, datetime, timedelta

logger = logging.getLogger(__name__)

#: Max provisional items to re-seek per tick (budget cap; mirrors the
#: wanted-search per-run cap so a large backlog is drained gradually).
DEFAULT_RESEEK_LIMIT = 50

#: Floor for the per-item backoff window (hours). The effective cutoff is
#: ``max(wanted_search_interval_hours, this)`` so re-seek never hammers the
#: same item more often than the normal wanted-search cadence.
_MIN_BACKOFF_HOURS = 24


def _reseek_backoff_cutoff(settings) -> datetime:
    """Return the ``last_search_at`` cutoff: items searched more recently than
    this are skipped this pass (respecting the wanted-search cadence)."""
    interval_h = getattr(settings, "wanted_search_interval_hours", _MIN_BACKOFF_HOURS)
    hours = max(int(interval_h or _MIN_BACKOFF_HOURS), _MIN_BACKOFF_HOURS)
    return datetime.now(UTC) - timedelta(hours=hours)


def _is_pinned(item: dict) -> bool:
    """Whether this provisional MT is pinned (user-edited/confirmed) and must
    never be auto-replaced.

    Phase 2 Task 1 STUB — pinning is defined + honoured in Task 2. Returns
    ``False`` until then (no item is pinned yet), so the selection wiring is in
    place for Task 2 to fill.
    """
    return False


def _on_original_found(item: dict, result: dict) -> None:
    """Hook: a genuine provider/embedded original was found for a provisional
    MT item during an original-only re-seek.

    Phase 2 Task 1 STUB — no-op. Task 2 fills the body: honour the profile's
    ``mt_on_original_found`` (``auto_replace`` vs ``notify``), trash the
    superseded MT sidecar (soft/recoverable), resolve the provisional item, and
    record the swap for stats/history. The call site is wired here so Task 2
    only fills this function.
    """
    logger.info(
        "mt_reseek: original candidate found for wanted %s (search status=%s) — "
        "replace/notify handling is Phase-2 Task 2 (no-op for now)",
        item.get("id"),
        result.get("status") if result else None,
    )


def _mark_reseek_miss(item_id: int) -> None:
    """No qualifying original this pass: bump ``last_search_at`` (so backoff is
    respected) and keep the item ``provisional`` (design: leave it provisional).

    The normal search pipeline flips status to ``searching`` at the start of a
    run; re-asserting ``provisional`` here restores the invariant so the item
    remains selectable on the next re-seek pass.
    """
    from db.wanted import update_wanted_search_outcome

    with contextlib.suppress(Exception):
        update_wanted_search_outcome(
            item_id,
            status="provisional",
            last_search_at=datetime.now(UTC),
        )


def reseek_provisional_items(app) -> dict:
    """Re-search every eligible provisional item in original-only mode.

    Selection: ``status="provisional"``, profile still keep-seeking, not pinned,
    respecting the per-item backoff. Runs inside ``app.app_context()`` so the
    request-scoped SQLAlchemy session is available.

    Returns a summary dict ``{searched, found, skipped}``.
    """
    with app.app_context():
        return _reseek()


def _reseek() -> dict:
    """Core re-seek loop. Assumes an active Flask app context."""
    from config import get_settings
    from db.repositories.wanted import WantedRepository
    from services.mt_provisional import resolve_keep_seeking
    from wanted_search import process_wanted_item

    settings = get_settings()
    limit = int(
        getattr(settings, "mt_reseek_max_items_per_run", DEFAULT_RESEEK_LIMIT)
        or DEFAULT_RESEEK_LIMIT
    )
    cutoff = _reseek_backoff_cutoff(settings)

    items = WantedRepository().get_provisional_items(limit=limit, search_cutoff=cutoff)

    searched = 0
    found = 0
    skipped = 0

    for item in items:
        item_id = item.get("id")
        # Profile turned keep-seeking off → leave the item inert, don't search.
        if not resolve_keep_seeking(item):
            skipped += 1
            continue
        # Pinned (user-edited/confirmed) MT is never auto-replaced (Task 2).
        if _is_pinned(item):
            skipped += 1
            continue

        # Original-only search: auto_translate=False skips the translate steps
        # so only a genuine provider/embedded original can be returned.
        result = process_wanted_item(item_id, auto_translate=False)
        searched += 1

        if result and result.get("status") == "found":
            found += 1
            _on_original_found(item, result)
        else:
            _mark_reseek_miss(item_id)

    return {"searched": searched, "found": found, "skipped": skipped}


def mt_reseek_tick() -> None:
    """Module-level tick (picklable) invoked by APScheduler.

    Runs inside the app context established by the scheduler ``_tick_wrapper``
    (mirrors ``upgrade_tick`` calling its scan body directly).
    """
    result = _reseek()
    logger.info(
        "mt_reseek complete: %d searched, %d original(s) found, %d skipped",
        result.get("searched", 0),
        result.get("found", 0),
        result.get("skipped", 0),
    )
