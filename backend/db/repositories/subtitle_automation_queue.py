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

from datetime import UTC, datetime

from sqlalchemy import func, or_, select

from db.models.core import SubtitleAutomationQueueEntry
from db.repositories.base import BaseRepository


class SubtitleAutomationQueueRepository(BaseRepository):
    """CRUD + atomic claim for the subtitle automation drain queue."""

    # ----- reads ----------------------------------------------------------
    def get_by_wanted_item(self, wanted_item_id: int) -> dict | None:
        row = (
            self.session.query(SubtitleAutomationQueueEntry)
            .filter(SubtitleAutomationQueueEntry.wanted_item_id == wanted_item_id)
            .one_or_none()
        )
        return self._to_dict(row) if row else None

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
    ) -> int:
        """Idempotent enqueue by `wanted_item_id`.

        - No existing row → insert `pending` and return new id.
        - Existing `done` row → reset to `pending`, attempt_count=0, clear
          error/next_retry_at, return existing id.
        - Existing `pending`/`running`/`failed` row → return existing id
          unchanged.
        """
        now = self._now()
        existing = (
            self.session.query(SubtitleAutomationQueueEntry)
            .filter(SubtitleAutomationQueueEntry.wanted_item_id == wanted_item_id)
            .one_or_none()
        )
        if existing is not None:
            if existing.state == "done":
                existing.state = "pending"
                existing.attempt_count = 0
                existing.last_error = None
                existing.next_retry_at = None
                existing.file_path = file_path
                existing.target_language = target_language
                existing.updated_at = now
                self._commit()
            return existing.id
        entry = SubtitleAutomationQueueEntry(
            wanted_item_id=wanted_item_id,
            file_path=file_path,
            target_language=target_language,
            state="pending",
            attempt_count=0,
            created_at=now,
            updated_at=now,
        )
        self.session.add(entry)
        self._commit()
        return entry.id

    def claim_next(self, *, now: datetime | None = None) -> dict | None:
        """Atomically claim one eligible row and transition it to `running`.

        Eligibility:
            state = 'pending'
          OR
            state = 'failed' AND next_retry_at <= now

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
        stmt = (
            select(SubtitleAutomationQueueEntry)
            .where(or_(pending_clause, retry_clause))
            .order_by(
                SubtitleAutomationQueueEntry.next_retry_at.asc().nullsfirst(),
                SubtitleAutomationQueueEntry.created_at.asc(),
            )
            .limit(1)
        )
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

    # ----- helpers --------------------------------------------------------
    def _now(self) -> datetime:
        return datetime.now(UTC)
