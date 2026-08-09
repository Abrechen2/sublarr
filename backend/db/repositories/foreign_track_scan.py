"""Repository for the foreign-track scan cache / worklist.

Every state transition of the batched sweep goes through here, so the sweep
itself stays free of SQLAlchemy and is testable against a fake.
"""

import json
import logging

from sqlalchemy import delete, func, select

from db.models.foreign_tracks import (
    ERROR_VERIFY,
    MAX_ATTEMPTS,
    STATE_AFFECTED,
    STATE_CLEAN,
    STATE_FAILED,
    STATE_PENDING,
    STATE_STRIPPED,
    STATE_STRIPPING,
    ForeignTrackScan,
)
from db.repositories.base import BaseRepository

logger = logging.getLogger(__name__)


class ForeignTrackScanRepository(BaseRepository):
    """CRUD + state transitions for ``foreign_track_scan``."""

    def _get(self, path: str) -> ForeignTrackScan | None:
        return self.session.execute(
            select(ForeignTrackScan).where(ForeignTrackScan.path == path)
        ).scalar_one_or_none()

    def upsert_seen(self, path: str, size_bytes: int, mtime: float, generation: int) -> None:
        """Record that ``path`` exists in this generation.

        A row whose size or mtime moved is reset to pending — its cached
        verdict describes a file that no longer exists in that form. The
        attempt counter resets with it: a replaced file deserves a fresh try.
        """
        row = self._get(path)
        if row is None:
            self.session.add(
                ForeignTrackScan(
                    path=path,
                    size_bytes=size_bytes,
                    mtime=mtime,
                    state=STATE_PENDING,
                    generation=generation,
                )
            )
            self._commit()
            return

        row.generation = generation
        if row.size_bytes != size_bytes or row.mtime != mtime:
            row.size_bytes = size_bytes
            row.mtime = mtime
            row.state = STATE_PENDING
            row.attempts = 0
            row.error = None
            row.error_class = None
            row.foreign_langs = None
            row.track_count = 0
        self._commit()

    def prune_stale(self, generation: int) -> int:
        """Delete rows an enumeration pass did not see — the files are gone.

        The caller MUST only call this after a completed enumeration. An
        interrupted walk leaves every unvisited file looking deleted.
        """
        result = self.session.execute(
            delete(ForeignTrackScan).where(ForeignTrackScan.generation < generation)
        )
        self._commit()
        return int(result.rowcount or 0)

    def next_pending(self, limit: int) -> list[ForeignTrackScan]:
        return list(
            self.session.execute(
                select(ForeignTrackScan)
                .where(ForeignTrackScan.state == STATE_PENDING)
                .order_by(ForeignTrackScan.id)
                .limit(limit)
            ).scalars()
        )

    def mark_probed(self, path: str, foreign_langs: list[str]) -> None:
        row = self._get(path)
        if row is None:
            logger.warning("mark_probed: no row for path %s, ignoring", path)
            return
        row.probed_at = self._now()
        row.error = None
        row.error_class = None
        if foreign_langs:
            row.state = STATE_AFFECTED
            row.foreign_langs = json.dumps(sorted(set(foreign_langs)))
            row.track_count = len(foreign_langs)
        else:
            row.state = STATE_CLEAN
            row.foreign_langs = None
            row.track_count = 0
        self._commit()

    def claim_next_affected(self) -> ForeignTrackScan | None:
        """Move one affected row to ``stripping`` and return it.

        The select-then-update here is NOT row-locked (no ``FOR UPDATE SKIP
        LOCKED``) — that was deliberately rejected: this runs in a single
        process behind a single lock, and SQLite in CI would need a
        divergent fallback. Safety instead relies on callers being
        serialised by the sweep's own lock (added in a later task). Do not
        call this concurrently.
        """
        row = self.session.execute(
            select(ForeignTrackScan)
            .where(ForeignTrackScan.state == STATE_AFFECTED)
            .order_by(ForeignTrackScan.id)
            .limit(1)
        ).scalar_one_or_none()
        if row is None:
            return None
        row.state = STATE_STRIPPING
        row.processed_at = self._now()
        self._commit()
        return row

    def mark_stripped(self, path: str) -> None:
        row = self._get(path)
        if row is None:
            logger.warning("mark_stripped: no row for path %s, ignoring", path)
            return
        row.state = STATE_STRIPPED
        row.processed_at = self._now()
        row.error = None
        row.error_class = None
        self._commit()

    def mark_failed(self, path: str, error: str, error_class: str) -> None:
        """Record a failure; park the row once it has burned its attempts.

        A verification failure is never retried automatically — a file that
        failed verification is exactly the case a human should look at.
        """
        row = self._get(path)
        if row is None:
            logger.warning("mark_failed: no row for path %s, ignoring", path)
            return
        row.attempts += 1
        row.error = error[:2000]
        row.error_class = error_class
        if error_class == ERROR_VERIFY or row.attempts >= MAX_ATTEMPTS:
            row.state = STATE_FAILED
        elif row.state == STATE_STRIPPING:
            row.state = STATE_AFFECTED
        self._commit()

    def release_stripping(self) -> int:
        """Return rows abandoned mid-strip (a crash) to the affected pool."""
        rows = list(
            self.session.execute(
                select(ForeignTrackScan).where(ForeignTrackScan.state == STATE_STRIPPING)
            ).scalars()
        )
        for row in rows:
            row.state = STATE_AFFECTED
        self._commit()
        return len(rows)

    def reset_all_to_pending(self) -> int:
        """Invalidate every cached verdict, stripped rows included.

        Narrowing the keep-list means an already-cleaned file can carry a
        foreign track again, so ``stripped`` is not exempt.
        """
        rows = list(self.session.execute(select(ForeignTrackScan)).scalars())
        for row in rows:
            row.state = STATE_PENDING
            row.foreign_langs = None
            row.track_count = 0
            row.attempts = 0
            row.error = None
            row.error_class = None
        self._commit()
        return len(rows)

    def counts_by_state(self) -> dict[str, int]:
        rows = self.session.execute(
            select(ForeignTrackScan.state, func.count()).group_by(ForeignTrackScan.state)
        ).all()
        return {state: int(count) for state, count in rows}

    def affected_track_total(self) -> int:
        """Foreign tracks still to remove, across every affected row.

        The preview shows this next to the file count: on the production
        library it is 34,104 tracks over 2,375 files, and the track number is
        what conveys the scale of the pending work.
        """
        total = self.session.execute(
            select(func.sum(ForeignTrackScan.track_count)).where(
                ForeignTrackScan.state == STATE_AFFECTED
            )
        ).scalar()
        return int(total or 0)

    def sample_affected(self, limit: int) -> list[dict]:
        rows = self.session.execute(
            select(ForeignTrackScan)
            .where(ForeignTrackScan.state == STATE_AFFECTED)
            .order_by(ForeignTrackScan.id)
            .limit(limit)
        ).scalars()
        return [
            {
                "path": r.path,
                "tracks": r.track_count,
                "langs": json.loads(r.foreign_langs) if r.foreign_langs else [],
            }
            for r in rows
        ]
