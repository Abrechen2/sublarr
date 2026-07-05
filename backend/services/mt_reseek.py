"""Provisional machine-translation re-seek (feature #8b, Phase 2).

A dedicated scheduled job that re-searches wanted items sitting in the
``provisional`` state — a Sublarr machine-translation kept alive because the
governing profile has ``mt_keep_seeking_original=1`` — for a GENUINE
provider/embedded original. It runs the normal search pipeline in
ORIGINAL-ONLY mode (``process_wanted_item(..., auto_translate=False)``) so no
re-translate loop can occur, and respects a per-item search backoff so the job
stays cheap.

Task 1 wired selection + original-only search + backoff. Task 2 (this
revision) fills in the on-found handling:

- Every candidate is first previewed with ``dry_run=True`` (see
  ``wanted_search.process.process_wanted_item``) — the normal "found" path is
  atomic (search -> download -> save -> record -> delete, all before
  returning), so a preview is the only way to learn whether a qualifying
  original exists before deciding what to do about it.
- ``mt_min_original_score`` gates the preview: a candidate scoring below the
  profile's floor is treated as a miss (MT is always score 0, so the default
  floor of 1 accepts any genuine result).
- ``mt_on_original_found == "auto_replace"``: the superseded MT sidecar is
  moved to the recoverable trash (``services.sidecar_trash``) BEFORE the real
  (non-preview) call runs — the normal save path is a raw atomic overwrite,
  not a trash-and-replace, so without this step the MT bytes would be
  silently clobbered in place with no recovery path. The real call then
  performs the actual install (download, save, record, delete the wanted
  item) exactly as a normal successful search would.
- ``mt_on_original_found == "notify"``: nothing is written. A minimal pending
  signal (``WantedItem.mt_pending_original``, a JSON blob) is recorded for
  Task 3's approve/reject API, and the item's status — bumped to "searching"
  by the preview call — is restored to "provisional".
- Pinned items (``WantedItem.mt_pinned``, a user-edited/confirmed MT) are
  never selected in the first place — see ``_is_pinned``.

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
    never be auto-replaced or re-searched.

    Backed by ``WantedItem.mt_pinned`` (migration 3c4b1a2d5e6f). There is no
    setter API yet — Task 3/4 wires the UI/route that flips it; this function
    only needs to honour the column once it exists.
    """
    return bool(item.get("mt_pinned"))


def _resolve_min_original_score(profile: dict | None) -> int:
    """Read ``mt_min_original_score`` off a resolved profile dict, defaulting
    to 1 (any genuine result outscores the MT's fixed score of 0)."""
    try:
        return int((profile or {}).get("mt_min_original_score", 1) or 1)
    except (TypeError, ValueError):
        return 1


def _trash_existing_mt_file(path: str) -> None:
    """Move the superseded MT sidecar into the recoverable trash.

    The normal save path (``providers.download_manager.save_subtitle`` ->
    ``utils.atomic_write.atomic_write_bytes``) is a raw atomic OVERWRITE, not a
    trash-and-replace — verified empirically while building this feature (see
    docs/plans/2026-07-05-provisional-mt-phase2-reseek.md, Task 2). Without
    this step the MT bytes would be silently clobbered in place with no
    recovery path when ``auto_replace`` installs the real original at the same
    path. No-ops when the file is already gone (nothing to trash).
    """
    import os

    from config import get_settings
    from services.sidecar_trash import get_batch_dir, trash_sidecar

    if not path or not os.path.exists(path):
        return

    settings = get_settings()
    media_path = getattr(settings, "media_path", "") or os.path.dirname(path)
    batch_id = f"mt-reseek-{datetime.now(UTC):%Y%m%d%H%M%S%f}"
    batch_dir = get_batch_dir(media_path, batch_id)

    trashed_path, err = trash_sidecar(path, media_path, batch_dir)
    if err:
        logger.warning("mt_reseek: could not trash superseded MT sidecar %s: %s", path, err)
    else:
        logger.info("mt_reseek: trashed superseded MT sidecar %s -> %s", path, trashed_path)


def _replace_original(item: dict, preview: dict) -> None:
    """``mt_on_original_found == "auto_replace"``: install the genuine
    original in place of the MT.

    The preview call (``dry_run=True``) already confirmed a qualifying
    candidate exists at ``preview["output_path"]`` without writing anything.
    Trash the superseded MT sidecar there FIRST (see
    ``_trash_existing_mt_file``), then re-run the search for real
    (``dry_run=False``) — this repeats the provider search/download once more,
    but it is the only way to let the normal, unmodified success path
    (download -> save -> record -> delete the wanted item) run to completion
    exactly as it would for any other successful search.
    """
    item_id = item.get("id")
    output_path = preview.get("output_path")
    if output_path:
        _trash_existing_mt_file(output_path)

    from wanted_search import process_wanted_item

    result = process_wanted_item(
        item_id, auto_translate=False, dry_run=False, bypass_existing_target_check=True
    )
    if result and result.get("status") == "found":
        logger.info(
            "mt_reseek: auto_replace installed a genuine original for wanted %s via %s (score=%s)",
            item_id,
            result.get("provider"),
            preview.get("score"),
        )
    else:
        # Rare race: the preview found something a moment ago but the real
        # (second) search came up empty or failed. Nothing was trashed-and-
        # left-orphaned since the MT copy is safely in the trash batch —
        # treat it as a miss so the next pass tries again.
        logger.warning(
            "mt_reseek: auto_replace re-run for wanted %s did not reproduce the preview "
            "result (status=%s) — will retry on the next pass",
            item_id,
            result.get("status") if result else None,
        )
        _mark_reseek_miss(item_id)


def _record_pending_notification(item: dict, preview: dict) -> None:
    """``mt_on_original_found == "notify"``: flag a pending original without
    touching any files.

    Records a minimal JSON marker on the wanted row
    (``WantedItem.mt_pending_original``) for Task 3's approve/reject API to
    query and act on later. The preview call bumped the item's status to
    "searching" (the normal first step of ``process_wanted_item``) — since
    nothing else happened, restore "provisional" so the invariant holds and
    the item remains visible/selectable as provisional.
    """
    import json

    from db.wanted import set_mt_pending_original, update_wanted_status

    item_id = item.get("id")
    payload = json.dumps(
        {
            "provider": preview.get("provider"),
            "score": preview.get("score"),
            "output_path": preview.get("output_path"),
            "format": preview.get("format"),
            "found_at": datetime.now(UTC).isoformat(),
        }
    )
    set_mt_pending_original(item_id, payload)
    update_wanted_status(item_id, "provisional")
    logger.info(
        "mt_reseek: original candidate found for wanted %s (provider=%s, score=%s) — "
        "recorded pending notification, item stays provisional",
        item_id,
        preview.get("provider"),
        preview.get("score"),
    )


def _on_original_found(item: dict, preview: dict) -> None:
    """Hook: a genuine provider/embedded original was found (preview, no
    writes yet) for a provisional MT item during an original-only re-seek.

    Dispatches on the governing profile's ``mt_on_original_found``
    (``auto_replace`` vs ``notify``, default ``notify`` — the safer choice
    when a profile predates this feature). ``mt_min_original_score`` gates the
    dispatch: a candidate scoring below the profile's floor is treated as a
    miss rather than acted on.
    """
    from services.mt_provisional import _resolve_profile_for_item

    item_id = item.get("id")
    profile = _resolve_profile_for_item(item)
    mode = (profile or {}).get("mt_on_original_found", "notify")
    min_score = _resolve_min_original_score(profile)
    score = preview.get("score")

    if score is not None and score < min_score:
        logger.info(
            "mt_reseek: candidate for wanted %s scored %s < mt_min_original_score=%s, skipping",
            item_id,
            score,
            min_score,
        )
        _mark_reseek_miss(item_id)
        return

    if mode == "auto_replace":
        _replace_original(item, preview)
    else:
        _record_pending_notification(item, preview)


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

        # Original-only PREVIEW: auto_translate=False skips the translate
        # steps so only a genuine provider/embedded original can be returned;
        # dry_run=True guarantees nothing is written yet (the normal "found"
        # path is atomic — see process_wanted_item's dry_run docstring);
        # bypass_existing_target_check=True is required because the item's
        # existing sidecar IS the machine translation being re-sought
        # against, not a completed original.
        preview = process_wanted_item(
            item_id, auto_translate=False, dry_run=True, bypass_existing_target_check=True
        )
        searched += 1

        if preview and preview.get("status") == "found":
            found += 1
            _on_original_found(item, preview)
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
