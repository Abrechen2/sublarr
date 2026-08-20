"""Search-outcome recording for the wanted scheduler.

Extracted from services/wanted_search_runner.py. Owns the exponential
backoff table for provider errors and the central ``record_search_outcome``
mutation point used by both the scheduler and wanted-processing workers.
"""

import logging
from datetime import UTC, datetime, timedelta

from config import get_settings

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
    - ``'file_missing'``: the media file is not on disk — usually a mount or
      permission fault (2026-08-01 prod incident class), not a provider miss.
      Same mechanics as ``'provider_error'`` but labelled apart, so the item
      self-heals when the mount returns instead of dying in ``'failed'``.

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

    if kind in ("provider_error", "file_missing"):
        # Both are environment faults, not misses: the providers were never
        # meaningfully asked, so neither burns ``search_count``. They share
        # the error-side backoff curve; ``failure_kind`` keeps them apart so
        # a mount outage (file_missing en masse) reads differently from a
        # provider outage in the DB and the UI.
        item = get_wanted_item(item_id)
        if not item:
            logger.debug("record_search_outcome: item %d not found", item_id)
            return
        prior = item.get("error_count") or 0
        retry_at = compute_retry_after_for_error(prior + 1, now)
        update_wanted_search_outcome(
            item_id,
            error_count_increment=1,
            failure_kind=kind,
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
        max_slow_cycles = getattr(settings, "wanted_search_max_slow_cycles", 3)
        base_h = getattr(settings, "wanted_backoff_base_hours", 1.0)
        cap_h = getattr(settings, "wanted_backoff_cap_hours", 168)
        # Tri-state escalation: normal backoff → slow-mode → unsourceable.
        # The terminal state moves the row out of the wanted queue entirely
        # (status='unsourceable') so it stops eating scheduler budget. Reverse
        # path is manual (admin re-queues, or a future provider-coverage event
        # rehydrates the cohort).
        if new_count >= max_attempts + max_slow_cycles:
            update_wanted_search_outcome(
                item_id,
                status="unsourceable",
                failure_kind="unsourceable",
                retry_after=None,
            )
            return
        if new_count >= max_attempts:
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
