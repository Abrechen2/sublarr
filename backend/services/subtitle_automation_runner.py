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

from db.models.core import SubtitleAutomationQueueEntry
from db.repositories.subtitle_automation_queue import (
    SubtitleAutomationQueueRepository,
)

# Aliased import: tests patch "services.subtitle_automation_runner._extract_embedded_sub".
from services.embedded_extractor import extract_embedded_sub as _extract_embedded_sub
from services.scheduler.cancellation import abort_requested
from services.video_sync import SyncSanityThresholdError

logger = logging.getLogger(__name__)

# Failures that will fail identically on every retry. Sending these round the
# backoff ladder burns a drain slot per attempt for a result that is already
# known — and hides the rows that genuinely deserve another try.
#
# `SyncUnavailableError` is deliberately NOT here, though it looks the part.
# It means "ffsubsync is not installed", which an operator fixes — and a
# terminal row would then never be picked up again, so every sync queued
# before the install would stay lost after it. The backoff ladder caps at 24h,
# which is the right cadence for waiting on a human.
_TERMINAL_SYNC_ERRORS = (SyncSanityThresholdError,)

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


def _auto_sync_enabled() -> bool | None:
    """Read auto-sync's own toggle. None if it could not be read.

    Deliberately NOT `subtitle_automation_enabled`. Auto-sync is a separate
    feature that happens to share this queue, and the automation toggle
    defaults to off — gating auto-sync behind it would queue a sync after
    every download on a default install and drain none of them.

    The third answer matters since `_discard_disabled` started deleting rows.
    While "off" only meant "do not claim", collapsing an unreadable setting
    into False was free. It is not free any more: a transient config or
    database error would permanently delete queued work on the strength of a
    question nobody managed to ask. None means "do not claim, and do not
    touch anything either".
    """
    from config import get_settings

    try:
        return bool(get_settings().auto_sync_after_download)
    except Exception:
        logger.exception("failed to read auto_sync_after_download; skipping auto-sync this tick")
        return None


# Task types worth discarding when their feature is switched off, which is
# NOT the same as "every task type". `embedded_extract` and
# `sidecar_translate` rows are re-enqueued by the wanted scanner on its next
# pass, so leaving them costs nothing and deleting them would throw away a
# backlog the user gets back anyway — over a toggle they may flip for an hour.
#
# An `auto_sync` row has no such second chance: it is written once, at the
# moment a download lands, against a wanted item that is deleted on the next
# line. Nothing regenerates it. So it is the one type where "waiting for a
# worker that will never come" is a permanent state rather than a pause.
_DISCARDABLE_TASK_TYPES = {SubtitleAutomationQueueEntry.TASK_AUTO_SYNC}


def _eligible_task_types() -> set[str]:
    """Which kinds of queued work this tick is allowed to run.

    Two features live on one queue behind two independent toggles, so the
    answer is a set rather than a boolean. An empty set means there is
    nothing this tick may claim — see `drain`.
    """
    eligible: set[str] = set()
    if _automation_enabled():
        eligible.add(SubtitleAutomationQueueEntry.TASK_EMBEDDED_EXTRACT)
        eligible.add(SubtitleAutomationQueueEntry.TASK_SIDECAR_TRANSLATE)
    if _auto_sync_enabled():
        eligible.add(SubtitleAutomationQueueEntry.TASK_AUTO_SYNC)
    return eligible


class SubtitleAutomationRunner:
    """Pull items off the queue and drive `_extract_embedded_sub` for each."""

    def __init__(
        self,
        repo: SubtitleAutomationQueueRepository | None = None,
    ) -> None:
        self._repo = repo or SubtitleAutomationQueueRepository()

    def _translate_sidecar(self, wanted_item_id: int, file_path: str, target_language: str) -> None:
        """Translate an item that has a source-language sidecar on disk.

        The work `wanted_search` used to do inline while holding the global
        search lock. It reaches the same Step-5 fallback the normal per-item
        pipeline would eventually reach — no provider search, no retry_after
        gate, just the local translate.

        The wanted item is loaded here rather than snapshotted at enqueue
        time: `_fallback_translate_file` dereferences it for the arr context
        and the language profile, and a user who re-assigns a profile between
        enqueue and drain should get the new one. Same reasoning for settings.
        A `FileNotFoundError` for a vanished item is deliberate — `process_one`
        already treats that as terminal rather than cycling a dead row through
        the backoff ladder forever.
        """
        from config import get_settings
        from db.wanted import get_wanted_item
        from wanted_search.process import _fallback_translate_file

        item = get_wanted_item(wanted_item_id)
        if item is None:
            raise FileNotFoundError(
                f"wanted item {wanted_item_id} no longer exists; dropping its translation"
            )
        _fallback_translate_file(
            {
                "item": item,
                "item_id": wanted_item_id,
                "item_lang": item.get("target_language") or target_language,
                "settings": get_settings(),
                "auto_translate": True,
                "file_path": file_path,
            }
        )

    def _auto_sync(self, subtitle_path: str, video_path: str | None) -> None:
        """Time a downloaded sidecar against its video.

        The work `wanted_search` used to do inline, in the middle of a
        per-item chain. `sync_with_ffsubsync` caps a single run at 600s,
        which alone is two thirds of that job's cancel grace — the reason
        three consecutive prod sweeps were recorded `timeout_abandoned`.

        Both paths come off the row rather than from the wanted item: the
        item is usually deleted the moment its subtitle lands.
        """
        from services.video_sync import sync_with_ffsubsync

        if not video_path:
            # Only reachable for a row written before `video_path` existed.
            # Guessing the video from the sidecar name is how sync ends up
            # timing a subtitle against the wrong file.
            raise FileNotFoundError(
                f"auto_sync row for {subtitle_path} has no video_path; cannot sync"
            )
        logger.info("auto-sync: starting ffsubsync for %s against %s", subtitle_path, video_path)
        sync_with_ffsubsync(subtitle_path, video_path)
        logger.info("auto-sync: complete for %s", subtitle_path)

    def process_one(self, *, task_types: set[str] | None = None) -> bool:
        """Claim and process a single queue entry.

        Returns True if a row was processed (success or failure), False if
        the queue is empty / everyone is running / all failures still in
        backoff.
        """
        claim = self._repo.claim_next(now=datetime.now(UTC), task_types=task_types)
        if claim is None:
            return False
        entry_id = claim["id"]
        wanted_item_id = claim["wanted_item_id"]
        file_path = claim["file_path"]
        task_type = claim.get("task_type") or "embedded_extract"
        # attempt_count BEFORE this attempt; mark_failed will increment it.
        prior_attempt = claim.get("attempt_count") or 0
        try:
            if task_type == SubtitleAutomationQueueEntry.TASK_SIDECAR_TRANSLATE:
                self._translate_sidecar(wanted_item_id, file_path, claim["target_language"])
            elif task_type == SubtitleAutomationQueueEntry.TASK_AUTO_SYNC:
                self._auto_sync(file_path, claim.get("video_path"))
            else:
                _extract_embedded_sub(wanted_item_id, file_path, auto_translate=False)
        except _TERMINAL_SYNC_ERRORS as exc:
            # A rejected shift is the same shift next time — the sanity gate
            # compares the measured offset against a configured threshold, and
            # neither changes between attempts.
            logger.warning(
                "subtitle_automation: auto-sync will not be retried for wanted_item=%s: %s",
                wanted_item_id,
                exc,
            )
            self._repo.mark_failed(entry_id, error=str(exc), next_retry_at=None)
            return True
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

    def _discard_disabled(self) -> None:
        """Drop queued work whose feature is confirmed off.

        Runs before the drain rather than on the toggle itself: a setting can
        be changed by an API call, an env var or a direct database edit, and
        only the drain sees all three.

        `is False` rather than `not ...` on purpose — an unreadable setting
        answers None, and deleting a user's queue because a config read failed
        would be a far worse bug than the one this method exists to fix.
        """
        if _auto_sync_enabled() is not False:
            return
        disabled = set(_DISCARDABLE_TASK_TYPES)
        try:
            removed = self._repo.discard_waiting(disabled)
        except Exception:
            # Housekeeping must never cost the tick its actual work.
            logger.exception("subtitle_automation: could not discard rows for disabled features")
            return
        if removed:
            logger.info(
                "subtitle_automation: discarded %d queued item(s) for switched-off features (%s)",
                removed,
                ", ".join(sorted(disabled)),
            )

    def drain(self, *, max_items: int = 50) -> int:
        """Drain up to `max_items` entries. Returns the number processed.

        Stops early if the queue is empty. Claims only the task types whose
        feature is currently switched on — this queue serves two features
        with two independent toggles, so "off" is per task type, not for the
        whole drain.

        Auto-sync rows belonging to a switched-off feature are dropped rather
        than left waiting: nothing will ever claim them and nothing will ever
        regenerate them, so leaving them makes the status counts promise work
        that is not coming. The other task types are left alone — the scanner
        re-enqueues those, so waiting really is only waiting.
        """
        task_types = _eligible_task_types()
        self._discard_disabled()
        if not task_types:
            return 0
        if max_items <= 0:
            return 0
        processed = 0
        while processed < max_items:
            # One queue item is the unit of work: claiming the row starts a
            # ffprobe/extract/ffsubsync operation that cannot be interrupted,
            # so a stop takes effect before the next item is claimed.
            if abort_requested():
                logger.info(
                    "subtitle_automation_tick: stopping as asked after %d item(s)",
                    processed,
                )
                return processed
            if not self.process_one(task_types=task_types):
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
    # Cap per tick so a very large backlog doesn't monopolize the worker. The
    # cap bounds how many items are *claimed*, not how long the tick takes:
    # the rows here range from a few-second extraction to a ~16-minute
    # translation to a timing correction capped at 600s. What actually bounds
    # the tick is the JobSpec's timeout, and what bounds its wind-down is the
    # abort check between items in `drain`.
    processed = runner.drain(max_items=50)
    if processed:
        logger.info("subtitle_automation_tick: processed %d items", processed)
