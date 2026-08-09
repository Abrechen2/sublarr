"""Drain worker for subtitle_automation_queue (0.71.0 Phase 3b).

Called by the scheduler every `subtitle_automation_drain_interval_minutes`
(default 2) to process pending embedded-extract work. One tick drains up to
`max_items` rows from the queue, calling `_extract_embedded_sub` for each
and transitioning the row to `done` or `failed` (with exponential backoff)
depending on the outcome.

Master toggle: if `Settings.subtitle_automation_enabled` is False, the
drain is a no-op. Users opt in via the new Subtitle Automation settings
page (Phase 7).

Error taxonomy:
    - `FileNotFoundError` → terminal failure (file gone). `next_retry_at`
      set to None so the row sits in `failed` until the user fixes it or
      the scanner re-enqueues after re-add.
    - any other exception → retryable. Backoff schedule is
      5m → 15m → 1h → 6h → 24h (capped).
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from db.repositories.subtitle_automation_queue import (
    SubtitleAutomationQueueRepository,
)

# Aliased import: tests patch "services.subtitle_automation_runner._extract_embedded_sub".
from services.embedded_extractor import extract_embedded_sub as _extract_embedded_sub
from services.scheduler.cancellation import abort_requested

logger = logging.getLogger(__name__)

# 5m → 15m → 1h → 6h → 24h, then capped.
_BACKOFF_LADDER: tuple[timedelta, ...] = (
    timedelta(minutes=5),
    timedelta(minutes=15),
    timedelta(hours=1),
    timedelta(hours=6),
    timedelta(hours=24),
)


def compute_backoff(*, attempt: int) -> timedelta:
    """Exponential backoff capped at 24h.

    `attempt` is 1-indexed (first retry = attempt 1 after the first
    failure). Values above the ladder length clamp to the last step.
    """
    if attempt <= 0:
        return _BACKOFF_LADDER[0]
    idx = min(attempt - 1, len(_BACKOFF_LADDER) - 1)
    return _BACKOFF_LADDER[idx]


def _automation_enabled() -> bool:
    """Read the master toggle. Indirected so tests can patch it cheaply."""
    from config import get_settings

    try:
        return bool(get_settings().subtitle_automation_enabled)
    except Exception:
        # If settings can't load, act as if disabled — safe default.
        logger.exception("failed to read subtitle_automation_enabled; treating as off")
        return False


class SubtitleAutomationRunner:
    """Pull items off the queue and drive `_extract_embedded_sub` for each."""

    def __init__(
        self,
        repo: SubtitleAutomationQueueRepository | None = None,
    ) -> None:
        self._repo = repo or SubtitleAutomationQueueRepository()

    def process_one(self) -> bool:
        """Claim and process a single queue entry.

        Returns True if a row was processed (success or failure), False if
        the queue is empty / everyone is running / all failures still in
        backoff.
        """
        claim = self._repo.claim_next(now=datetime.now(UTC))
        if claim is None:
            return False
        entry_id = claim["id"]
        wanted_item_id = claim["wanted_item_id"]
        file_path = claim["file_path"]
        # attempt_count BEFORE this attempt; mark_failed will increment it.
        prior_attempt = claim.get("attempt_count") or 0
        try:
            _extract_embedded_sub(wanted_item_id, file_path, auto_translate=False)
        except FileNotFoundError as exc:
            logger.warning(
                "subtitle_automation: media file gone for wanted_item=%s (%s); "
                "marking terminal failure",
                wanted_item_id,
                file_path,
            )
            self._repo.mark_failed(entry_id, error=str(exc), next_retry_at=None)
            return True
        except Exception as exc:
            delay = compute_backoff(attempt=prior_attempt + 1)
            retry_at = datetime.now(UTC) + delay
            logger.warning(
                "subtitle_automation: extract failed for wanted_item=%s: %s — retry in %s",
                wanted_item_id,
                exc,
                delay,
            )
            self._repo.mark_failed(entry_id, error=str(exc), next_retry_at=retry_at)
            return True
        self._repo.mark_done(entry_id)
        return True

    def drain(self, *, max_items: int = 50) -> int:
        """Drain up to `max_items` entries. Returns the number processed.

        Stops early if the queue is empty. Stops hard (no per-item retry
        loop) if the master toggle is off.
        """
        if not _automation_enabled():
            return 0
        if max_items <= 0:
            return 0
        processed = 0
        while processed < max_items:
            # One queue item is the unit of work: claiming the row starts a
            # ffprobe/extract operation that cannot be interrupted, so a stop
            # takes effect before the next item is claimed.
            if abort_requested():
                logger.info(
                    "subtitle_automation_tick: stopping as asked after %d item(s)",
                    processed,
                )
                return processed
            if not self.process_one():
                break
            processed += 1
        return processed


def subtitle_automation_tick() -> None:
    """Scheduler-entry-point for the drain worker.

    Module-level so APScheduler's SQLAlchemyJobStore can pickle the
    textual reference. Called every `subtitle_automation_drain_interval_minutes`
    per the JobSpec in `_build_default_jobs`.
    """
    runner = SubtitleAutomationRunner()
    # Cap per tick so a very large backlog doesn't monopolize the worker.
    # 50 items × a few seconds = ~minutes; runs every 2 minutes by default.
    processed = runner.drain(max_items=50)
    if processed:
        logger.info("subtitle_automation_tick: processed %d items", processed)
