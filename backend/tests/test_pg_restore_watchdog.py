"""The lock watchdog must cancel the right backend, once, and only for good reason.

Cold review (Codex, 2026-09-17) on the watchdog added earlier the same day:

* every restore in one process used the same application name, so two restores
  cancelled each other;
* timing was keyed by pid only, so short waits of *different* statements added
  up to one 30 s cancellation;
* a failing query ended monitoring for good, silently;
* the result of ``pg_cancel_backend`` was ignored.
"""

from __future__ import annotations

import pytest

from pg_restore_watchdog import LockWatchdog


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


def _dog(samples, cancelled_pids, clock, cancel_result=True, limit_s=30):
    it = iter(samples)
    return LockWatchdog(
        query=lambda: next(it),
        cancel=lambda pid: (cancelled_pids.append(pid), cancel_result)[-1],
        limit_s=limit_s,
        clock=clock,
    )


def test_a_new_statement_restarts_the_clock():
    """Each statement waited under the limit; only the pid was the same."""
    clock = Clock()
    cancelled = []
    samples = [
        [(7, "Lock", "DROP INDEX a")],
        [(7, "Lock", "DROP INDEX b")],
        [(7, "Lock", "DROP INDEX c")],
    ]
    dog = _dog(samples, cancelled, clock)
    for t in (0, 20, 40):
        clock.now = t
        dog.tick()
    assert cancelled == []


def test_one_statement_waiting_past_the_limit_is_cancelled_once():
    clock = Clock()
    cancelled = []
    dog = _dog([[(7, "Lock", "DROP INDEX a")]] * 4, cancelled, clock)
    for t in (0, 20, 31, 45):
        clock.now = t
        dog.tick()
    assert cancelled == [7]
    assert dog.cancelled is True


def test_a_failed_cancel_is_not_reported_as_cancelled():
    clock = Clock()
    cancelled = []
    dog = _dog([[(7, "Lock", "DROP a")]] * 2, cancelled, clock, cancel_result=False)
    for t in (0, 31):
        clock.now = t
        dog.tick()
    assert cancelled == [7]
    assert dog.cancelled is False, "a refused cancel must not be reported as a cancelled restore"


def test_a_failing_sample_does_not_end_the_watch():
    clock = Clock()
    cancelled = []
    state = {"calls": 0}

    def query():
        state["calls"] += 1
        if state["calls"] == 2:
            raise RuntimeError("pg_stat_activity unavailable")
        return [(7, "Lock", "DROP a")]

    dog = LockWatchdog(
        query=query, cancel=lambda pid: (cancelled.append(pid), True)[-1], limit_s=30, clock=clock
    )
    for t in (0, 10, 31):
        clock.now = t
        dog.tick()

    assert cancelled == [7], "monitoring must continue after a failed sample"


def test_nothing_is_cancelled_once_the_lock_is_granted():
    clock = Clock()
    cancelled = []
    dog = _dog(
        [[(7, "Lock", "DROP a")], [(7, None, "COPY data")], [(7, "Lock", "DROP b")]],
        cancelled,
        clock,
    )
    for t in (0, 29, 31):
        clock.now = t
        dog.tick()
    assert cancelled == []


@pytest.mark.parametrize("wait", ["IO", "Client", None])
def test_only_lock_waits_count(wait):
    clock = Clock()
    cancelled = []
    dog = _dog([[(7, wait, "COPY data")]] * 2, cancelled, clock)
    for t in (0, 60):
        clock.now = t
        dog.tick()
    assert cancelled == []


def test_each_restore_gets_its_own_application_name():
    from database_backup_postgres import _restore_app_name

    assert _restore_app_name() != _restore_app_name()
    assert all(len(_restore_app_name()) <= 63 for _ in range(5))
    assert _restore_app_name().startswith("sublarr-restore-")
