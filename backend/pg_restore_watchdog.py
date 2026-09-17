"""Cancel a pg_restore that waits too long on a table lock.

``pg_restore --clean`` drops every table and index, which needs an exclusive
lock on each. A connection holding a lock elsewhere made the restore wait out
its whole five-minute timeout while app queries queued behind it. A plain
``lock_timeout`` cannot bound that: pg_dump writes ``SET lock_timeout = 0`` into
every dump, and pg_restore replays it (VM test of 1.14.4-rc.2 waited 47.7 s on a
lock held for 45 s despite ``PGOPTIONS=-c lock_timeout=30s``).

This watchdog polls ``pg_stat_activity`` for the restore's own backend, found by
the unique ``application_name`` that restore was started with, and cancels it
once **one statement** has been waiting on a lock for ``limit_s`` without a
break. The restore runs in one transaction, so a cancel rolls it back
completely.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable

logger = logging.getLogger(__name__)

POLL_INTERVAL_S = 1.0

#: A sample is (pid, wait_event_type, query).
Sample = tuple[int, str | None, str]


class LockWatchdog:
    """Decides when to cancel; the polling and the cancel call are injected."""

    def __init__(
        self,
        *,
        query: Callable[[], list[Sample]],
        cancel: Callable[[int], bool],
        limit_s: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._query = query
        self._cancel = cancel
        self._limit_s = limit_s
        self._clock = clock
        # (pid, statement) -> first time we saw THIS statement waiting on a lock.
        # Keyed by statement as well: separate statements each waiting briefly
        # must not add up to one cancellation.
        self._waiting_since: dict[tuple[int, str], float] = {}
        self.cancelled = False
        self.sample_failures = 0

    def tick(self) -> None:
        """Take one sample and cancel a backend that has waited past the limit.

        A failing sample is counted and ignored: losing sight of the restore for
        a moment must not silently end the watch.
        """
        if self.cancelled:
            return
        try:
            samples = self._query()
        except Exception as exc:  # noqa: BLE001 — the watch outlives a bad sample
            self.sample_failures += 1
            logger.debug("pg_restore watchdog could not read pg_stat_activity: %s", exc)
            return

        now = self._clock()
        seen: set[tuple[int, str]] = set()
        for pid, wait_event_type, query in samples:
            key = (pid, query or "")
            if wait_event_type != "Lock":
                continue
            seen.add(key)
            since = self._waiting_since.setdefault(key, now)
            if now - since < self._limit_s:
                continue
            logger.warning(
                "pg_restore backend %s waited %.0f s on a lock — cancelling the restore (%s)",
                pid,
                now - since,
                (query or "")[:80],
            )
            if self._cancel(pid):
                self.cancelled = True
            else:
                logger.warning("pg_restore backend %s did not accept the cancel request", pid)
                self._waiting_since[key] = now  # try again after another limit
            return
        # Anything not waiting on a lock right now starts over next time.
        for key in set(self._waiting_since) - seen:
            del self._waiting_since[key]


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
        finally:
            # Owned by the thread: a stop() that times out still releases it.
            try:
                self._dispose()
            except Exception as exc:  # noqa: BLE001
                logger.debug("pg_restore watchdog cleanup failed: %s", exc)

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=5)
        if self._thread.is_alive():
            logger.warning("pg_restore lock watchdog did not stop within 5 s; leaving it to finish")


def start(database_url: str, app_name: str, limit_s: float) -> RunningWatchdog:
    """Watch backends named ``app_name`` on the database behind ``database_url``."""
    from sqlalchemy import create_engine, text
    from sqlalchemy.pool import NullPool

    # Own engine, autocommit, no pool: the watchdog must never hold a
    # transaction (or a lock) of its own while the restore runs. The connect
    # timeout keeps a blackholed server from pinning the thread.
    engine = create_engine(
        database_url,
        poolclass=NullPool,
        isolation_level="AUTOCOMMIT",
        connect_args={"connect_timeout": 5},
    )

    def query() -> list[Sample]:
        with engine.connect() as conn:
            conn.execute(text("SET statement_timeout = '5s'"))
            rows = conn.execute(
                text(
                    "SELECT pid, wait_event_type, query FROM pg_stat_activity "
                    "WHERE application_name = :name AND datname = current_database() "
                    "AND pid <> pg_backend_pid()"
                ),
                {"name": app_name},
            ).fetchall()
        return [(int(pid), wait, sql or "") for pid, wait, sql in rows]

    def cancel(pid: int) -> bool:
        with engine.connect() as conn:
            return bool(conn.execute(text("SELECT pg_cancel_backend(:pid)"), {"pid": pid}).scalar())

    dog = LockWatchdog(query=query, cancel=cancel, limit_s=limit_s)
    return RunningWatchdog(dog, dispose=engine.dispose)
