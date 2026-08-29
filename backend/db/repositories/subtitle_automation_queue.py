"""Repository for `subtitle_automation_queue` (0.71.0 Phase 3a).

The drain worker uses this repo to:

- `enqueue()` new embedded-extract work when the scanner discovers a
  wanted_item with a matching target-language track. Idempotent by
  `wanted_item_id`: a row that finished (`done`) is reset to `pending`
  on re-enqueue; pending/running/failed rows are kept as-is and their
  existing id is returned.
- `claim_next()` atomically transitions one eligible row to `running`
  and returns it. Eligible = `state='pending'` OR `state='failed'` with
  `next_retry_at <= now`. Implemented as optimistic-lock
  (SELECT candidate, then UPDATE … WHERE id=? AND state=?) so it
  works on SQLite (tests) and Postgres (prod) without dialect-specific
  SQL. Under real concurrency in PG we could add `FOR UPDATE SKIP
  LOCKED` in a follow-up, but the single-replica deployment assumption
  means two workers should not race today.
- `mark_done()` / `mark_failed()` transition the claimed row to its
  terminal / retry state and update bookkeeping fields.
- `get_counts()` feeds the status API (`/api/v1/wanted/automation/status`).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import case, func, or_, select

from db.models.core import SubtitleAutomationQueueEntry
from db.repositories.base import BaseRepository

# Shortest job first. An `auto_sync` is capped at 600s by ffsubsync, while a
# `sidecar_translate` on this same queue has been measured at ~16 minutes.
# Without this, a sync queued the second its subtitle landed could sit behind
# a run of translations and arrive hours late — and unlike a translation, its
# whole point is that it happens close to the download. The cost is the
# mirror image: a large backlog of syncs delays translations. That is the
# trade this ordering deliberately makes.
_TASK_PRIORITY = case(
    (SubtitleAutomationQueueEntry.task_type == SubtitleAutomationQueueEntry.TASK_AUTO_SYNC, 0),
    else_=1,
)


class SubtitleAutomationQueueRepository(BaseRepository):
    """CRUD + atomic claim for the subtitle automation drain queue."""

    # ----- reads ----------------------------------------------------------
    def get_by_wanted_item(
        self, wanted_item_id: int, *, task_type: str | None = None
    ) -> dict | None:
        """One row for this item, optionally narrowed to a task type.

        Since an item may hold both an extraction and a translation this can
        no longer be ``one_or_none()`` — that raised MultipleResultsFound as
        soon as the second row existed. Without ``task_type`` the oldest row
        wins, which is the pre-1.11.3 row for any item that already had one.
        """
        q = self.session.query(SubtitleAutomationQueueEntry).filter(
            SubtitleAutomationQueueEntry.wanted_item_id == wanted_item_id
        )
        if task_type is not None:
            q = q.filter(SubtitleAutomationQueueEntry.task_type == task_type)
        row = q.order_by(SubtitleAutomationQueueEntry.id.asc()).first()
        return self._to_dict(row) if row else None

    def list_for_item(self, wanted_item_id: int) -> list[dict]:
        """Every queued task for one wanted item, oldest first."""
        rows = (
            self.session.query(SubtitleAutomationQueueEntry)
            .filter(SubtitleAutomationQueueEntry.wanted_item_id == wanted_item_id)
            .order_by(SubtitleAutomationQueueEntry.id.asc())
            .all()
        )
        return [self._to_dict(r) for r in rows]

    def get_counts(self) -> dict[str, int]:
        """Return `{'pending': N, 'running': N, 'failed': N, 'done': N}`."""
        q = self.session.query(
            SubtitleAutomationQueueEntry.state,
            func.count(SubtitleAutomationQueueEntry.id),
        ).group_by(SubtitleAutomationQueueEntry.state)
        counts = {"pending": 0, "running": 0, "failed": 0, "done": 0}
        for state, n in q.all():
            if state in counts:
                counts[state] = n
        return counts

    # ----- writes ---------------------------------------------------------
    def enqueue(
        self,
        *,
        wanted_item_id: int,
        file_path: str,
        target_language: str,
        task_type: str = SubtitleAutomationQueueEntry.TASK_EMBEDDED_EXTRACT,
        source_language: str | None = None,
        video_path: str | None = None,
    ) -> int:
        """Idempotent enqueue by `(wanted_item_id, task_type, file_path)`.

        - No existing row → insert `pending` and return new id.
        - Existing `done` row → reset to `pending`, attempt_count=0, clear
          error/next_retry_at, return existing id.
        - Existing `pending`/`running`/`failed` row → return existing id
          unchanged.

        The key is not the item alone: an item with an embedded track to
        extract can also have a source sidecar to translate, and enqueueing
        one must not be read as a duplicate of the other.

        `file_path` is in the key because `wanted_item_id` is not durable for
        `auto_sync` — the item is deleted right after the row is written and
        SQLite reuses its rowid, so a later item can inherit the id of a
        still-pending sync. Without the path it would match that row, get it
        back unchanged, and lose its own sync silently.
        """
        now = self._now()
        existing = (
            self.session.query(SubtitleAutomationQueueEntry)
            .filter(
                SubtitleAutomationQueueEntry.wanted_item_id == wanted_item_id,
                SubtitleAutomationQueueEntry.task_type == task_type,
                SubtitleAutomationQueueEntry.file_path == file_path,
            )
            .one_or_none()
        )
        if existing is not None:
            if existing.state == "done":
                existing.state = "pending"
                existing.attempt_count = 0
                existing.last_error = None
                existing.next_retry_at = None
                existing.file_path = file_path
                existing.video_path = video_path
                existing.target_language = target_language
                existing.source_language = source_language
                existing.updated_at = now
                self._commit()
            return existing.id
        entry = SubtitleAutomationQueueEntry(
            wanted_item_id=wanted_item_id,
            task_type=task_type,
            file_path=file_path,
            video_path=video_path,
            target_language=target_language,
            source_language=source_language,
            state="pending",
            attempt_count=0,
            created_at=now,
            updated_at=now,
        )
        self.session.add(entry)
        self._commit()
        return entry.id

    def claim_next(
        self, *, now: datetime | None = None, task_types: set[str] | None = None
    ) -> dict | None:
        """Atomically claim one eligible row and transition it to `running`.

        Eligibility:
            state = 'pending'
          OR
            state = 'failed' AND next_retry_at <= now

        `task_types` narrows the claim to those kinds of work. The drain
        worker needs it because the task types on this queue no longer share
        one master toggle: `auto_sync` belongs to `auto_sync_after_download`,
        the other two to `subtitle_automation_enabled`. Claiming a row the
        caller is not allowed to run would park it in `running` with nobody
        to finish it. None means no filter.

        Returns the claimed row as a dict, or None if the queue is
        empty / everyone is running / all failures still back off.
        """
        if now is None:
            now = datetime.now(UTC)
        # Find a candidate. Order: pending with NULL next_retry_at first
        # (fresh work), then failed rows by earliest next_retry_at.
        pending_clause = SubtitleAutomationQueueEntry.state == "pending"
        retry_clause = (SubtitleAutomationQueueEntry.state == "failed") & (
            SubtitleAutomationQueueEntry.next_retry_at <= now
        )
        stmt = select(SubtitleAutomationQueueEntry).where(or_(pending_clause, retry_clause))
        if task_types is not None:
            stmt = stmt.where(SubtitleAutomationQueueEntry.task_type.in_(sorted(task_types)))
        stmt = stmt.order_by(
            _TASK_PRIORITY,
            SubtitleAutomationQueueEntry.next_retry_at.asc().nullsfirst(),
            SubtitleAutomationQueueEntry.created_at.asc(),
        ).limit(1)
        candidate = self.session.execute(stmt).scalars().first()
        if candidate is None:
            return None
        prior_state = candidate.state
        # Optimistic claim: only succeed if state hasn't changed between
        # the SELECT and the UPDATE.
        updated = (
            self.session.query(SubtitleAutomationQueueEntry)
            .filter(
                SubtitleAutomationQueueEntry.id == candidate.id,
                SubtitleAutomationQueueEntry.state == prior_state,
            )
            .update(
                {
                    "state": "running",
                    "last_started_at": now,
                    "updated_at": now,
                },
                synchronize_session=False,
            )
        )
        self._commit()
        if updated == 0:
            # Another worker beat us to it. Caller may retry.
            return None
        self.session.expire_all()
        return self.get_by_id(candidate.id)

    def reclaim_orphaned(self, *, grace_minutes: int = 0) -> int:
        """Return `running` rows whose worker is gone to `pending`.

        `claim_next()` is the only way into `running`, and only
        `mark_done()` / `mark_failed()` lead out of it. When the process
        dies mid-item — restart, SIGKILL, shutdown timeout — the claim
        outlives the thread that held it and nothing ever releases it.
        `enqueue()` keeps an existing `running` row as-is by design, so a
        fresh search does not rescue one either: the item is stranded for
        good.

        Called once at scheduler startup, mirroring
        `scheduler.reconcile_stale_runs()` for the job-run table. At that
        moment no drain worker exists yet in this process, so every
        `running` row is by definition abandoned and the default grace of
        0 is correct. `grace_minutes` exists for callers that run while a
        worker may be live and must not steal an in-flight claim.

        `attempt_count` is incremented: an item that kills the process on
        every boot would otherwise be retried forever, and the counter is
        the only signal the backoff ladder has. The row goes back to
        `pending` (not `failed`) with `next_retry_at` cleared, so the work
        resumes on the next drain rather than waiting out a backoff it
        never earned.

        Returns the number of rows reclaimed.
        """
        from datetime import timedelta

        now = self._now()
        cutoff = now - timedelta(minutes=grace_minutes)

        stale = (
            self.session.query(SubtitleAutomationQueueEntry)
            .filter(SubtitleAutomationQueueEntry.state == "running")
            .filter(SubtitleAutomationQueueEntry.last_started_at <= cutoff)
            .all()
        )
        for row in stale:
            row.state = "pending"
            row.attempt_count = (row.attempt_count or 0) + 1
            row.next_retry_at = None
            row.last_error = (
                "Interrupted: claimed by a worker that no longer exists "
                "(process restart or shutdown timeout). Requeued."
            )
            row.updated_at = now
        self._commit()
        return len(stale)

    def discard_waiting(self, task_types: set[str]) -> int:
        """Drop rows of these types that are waiting for a worker.

        A task type whose feature has been switched off is never claimed
        again: `claim_next` filters on the types the drain is allowed to run,
        so its rows sit `pending` forever, inflate the status counts, and
        misreport work that will not happen as work that is about to.

        Only `pending` and `failed` rows go. A `running` row belongs to a
        worker that is still inside it, and `done` rows are history.

        Deleting rather than parking them is deliberate: the queue is a work
        list, not an audit log, and nothing is lost that the user did not just
        switch off — the subtitle itself is already on disk, only its optional
        follow-up work is dropped. Turning the feature back on queues fresh
        rows from the next download.

        Returns the number of rows removed.
        """
        if not task_types:
            return 0
        removed = (
            self.session.query(SubtitleAutomationQueueEntry)
            .filter(
                SubtitleAutomationQueueEntry.task_type.in_(sorted(task_types)),
                SubtitleAutomationQueueEntry.state.in_(("pending", "failed")),
            )
            .delete(synchronize_session=False)
        )
        self._commit()
        return int(removed or 0)

    def purge_finished(
        self,
        *,
        done_retention_days: int = 7,
        failed_retention_days: int = 30,
    ) -> int:
        """Delete finished rows past their retention window.

        The queue had no retention at all: on 2026-08-27 prod carried 5429
        ``done`` rows (3179 of them for long-deleted wanted items) and
        hundreds of terminal failures back to June. The queue is a work
        list, not an audit log (see ``discard_waiting``).

        Goes: ``done`` older than ``done_retention_days``, and ``failed``
        rows that are *terminal* (``next_retry_at IS NULL``) older than
        ``failed_retention_days`` — the longer window keeps them visible
        for diagnosis. Stays: everything ``pending``/``running``, and every
        ``failed`` row still on the backoff ladder — that is pending work,
        however old.

        Returns the number of rows removed.
        """
        now = self._now()
        done_cutoff = now - timedelta(days=done_retention_days)
        failed_cutoff = now - timedelta(days=failed_retention_days)
        removed = (
            self.session.query(SubtitleAutomationQueueEntry)
            .filter(
                or_(
                    (SubtitleAutomationQueueEntry.state == "done")
                    & (SubtitleAutomationQueueEntry.updated_at < done_cutoff),
                    (SubtitleAutomationQueueEntry.state == "failed")
                    & (SubtitleAutomationQueueEntry.next_retry_at.is_(None))
                    & (SubtitleAutomationQueueEntry.updated_at < failed_cutoff),
                )
            )
            .delete(synchronize_session=False)
        )
        self._commit()
        return int(removed or 0)

    def get_by_id(self, entry_id: int) -> dict | None:
        row = self.session.get(SubtitleAutomationQueueEntry, entry_id)
        return self._to_dict(row) if row else None

    def mark_done(self, entry_id: int) -> None:
        now = self._now()
        self.session.query(SubtitleAutomationQueueEntry).filter(
            SubtitleAutomationQueueEntry.id == entry_id
        ).update(
            {
                "state": "done",
                "last_finished_at": now,
                "last_error": None,
                "updated_at": now,
            },
            synchronize_session=False,
        )
        self._commit()

    def mark_failed(
        self,
        entry_id: int,
        *,
        error: str,
        next_retry_at: datetime | None,
    ) -> None:
        now = self._now()
        row = self.session.get(SubtitleAutomationQueueEntry, entry_id)
        if row is None:
            return
        row.state = "failed"
        row.attempt_count = (row.attempt_count or 0) + 1
        row.last_finished_at = now
        row.last_error = (error or "")[:1000]
        row.next_retry_at = next_retry_at
        row.updated_at = now
        self._commit()

    def release_for_retry(self, entry_id: int, *, reason: str) -> None:
        """Return a claimed row to ``pending`` without spending an attempt.

        For work that stopped because the *scheduler* ran out of time, not
        because the item misbehaved. ``mark_failed`` would increment
        ``attempt_count`` and set a backoff, so an item that happens to be in
        flight whenever the tick times out would climb the retry ladder and
        eventually be buried for something that was never its fault — the same
        shape as the terminal-``failed`` dead path closed in 1.12.2.

        ``next_retry_at`` is cleared for the same reason ``reclaim_orphaned``
        clears it: the item did not earn a wait, so the next drain should pick
        it straight back up. A partly translated file resumes from the
        translation memory, which is written per batch.
        """
        now = self._now()
        row = self.session.get(SubtitleAutomationQueueEntry, entry_id)
        if row is None:
            return
        row.state = "pending"
        row.last_finished_at = now
        row.last_error = (reason or "")[:1000]
        row.next_retry_at = None
        row.updated_at = now
        self._commit()

    # ----- helpers --------------------------------------------------------
    def _now(self) -> datetime:
        return datetime.now(UTC)
