"""Cancel a pg_restore that waits too long on a table lock.

``pg_restore --clean`` drops every table and index, which needs an exclusive
lock on each. A connection holding a lock elsewhere made the restore wait out
its whole five-minute timeout while app queries queued behind it. A plain
``lock_timeout`` cannot bound that: pg_dump writes ``SET lock_timeout = 0`` into
every dump, and pg_restore replays it (VM test of 1.14.4-rc.2 waited 47.7 s on a
lock held for 45 s despite ``PGOPTIONS=-c lock_timeout=30s``).

This watchdog polls ``pg_stat_activity`` for the restore's own backend, found by
its ``application_name``, and cancels it once it has been waiting on a lock for
``limit_s`` without a break. The restore runs in one transaction, so a cancel
rolls it back completely.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable

logger = logging.getLogger(__name__)

POLL_INTERVAL_S = 1.0


class LockWatchdog:
    """Decides when to cancel; the polling and the cancel call are injected."""

    def __init__(
        self,
        *,
        query: Callable[[], list[tuple[int, str | None]]],
        cancel: Callable[[int], None],
        limit_s: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._query = query
        self._cancel = cancel
        self._limit_s = limit_s
        self._clock = clock
        self._waiting_since: dict[int, float] = {}
        self.cancelled = False

    def tick(self) -> None:
        """Take one sample and cancel a backend that has waited past the limit."""
        if self.cancelled:
            return
        now = self._clock()
        seen = set()
        for pid, wait_event_type in self._query():
            seen.add(pid)
            if wait_event_type != "Lock":
                self._waiting_since.pop(pid, None)
                continue
            since = self._waiting_since.setdefault(pid, now)
            if now - since >= self._limit_s:
                logger.warning(
                    "pg_restore backend %s waited %.0f s on a lock — cancelling the restore",
                    pid,
                    now - since,
                )
                self._cancel(pid)
                self.cancelled = True
                return
        for pid in set(self._waiting_since) - seen:
            del self._waiting_since[pid]


class RunningWatchdog:
    """A LockWatchdog ticking on a background thread until ``stop()``."""

    def __init__(self, dog: LockWatchdog, dispose: Callable[[], None]) -> None:
        self._dog = dog
        self._dispose = dispose
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="pg-restore-watchdog", daemon=True)
        self._thread.start()

    @property
    def cancelled(self) -> bool:
        return self._dog.cancelled

    def _run(self) -> None:
        try:
            while not self._stop.wait(POLL_INTERVAL_S):
                self._dog.tick()
        except Exception as exc:  # noqa: BLE001 — a broken watchdog must not break the restore
            logger.warning("pg_restore lock watchdog stopped: %s", exc)

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=5)
        self._dispose()


def start(database_url: str, app_name: str, limit_s: float) -> RunningWatchdog:
    """Watch backends named ``app_name`` on the database behind ``database_url``."""
    from sqlalchemy import create_engine, text
    from sqlalchemy.pool import NullPool

    # Own engine, autocommit, no pool: the watchdog must never hold a
    # transaction (or a lock) of its own while the restore runs.
    engine = create_engine(database_url, poolclass=NullPool, isolation_level="AUTOCOMMIT")

    def query() -> list[tuple[int, str | None]]:
        with engine.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT pid, wait_event_type FROM pg_stat_activity "
                    "WHERE application_name = :name AND pid <> pg_backend_pid()"
                ),
                {"name": app_name},
            ).fetchall()
        return [(int(pid), wait) for pid, wait in rows]

    def cancel(pid: int) -> None:
        with engine.connect() as conn:
            conn.execute(text("SELECT pg_cancel_backend(:pid)"), {"pid": pid})

    dog = LockWatchdog(query=query, cancel=cancel, limit_s=limit_s)
    return RunningWatchdog(dog, dispose=engine.dispose)
