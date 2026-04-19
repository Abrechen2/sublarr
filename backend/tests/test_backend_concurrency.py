"""BackendConcurrency semaphore tests."""

import threading
import time

import pytest


def test_register_and_get_limit():
    from translation.concurrency import BackendConcurrency

    c = BackendConcurrency()
    c.register("claude", 3)
    assert c.get_limit("claude") == 3


def test_slot_acquires_and_releases():
    from translation.concurrency import BackendConcurrency

    c = BackendConcurrency()
    c.register("b", 2)

    with c.slot("b"):
        pass  # release on exit
    # If not released properly, next test would fail
    with c.slot("b"):
        pass


def test_slot_blocks_when_full():
    from translation.concurrency import BackendConcurrency

    c = BackendConcurrency()
    c.register("b", 1)

    acquired = []

    def worker(slot_num):
        with c.slot("b"):
            acquired.append(slot_num)
            time.sleep(0.2)

    t1 = threading.Thread(target=worker, args=(1,))
    t2 = threading.Thread(target=worker, args=(2,))
    t1.start()
    time.sleep(0.05)  # ensure t1 acquires first
    t2.start()
    t1.join()
    t2.join()
    assert acquired == [1, 2]  # sequential, not concurrent


def test_slot_timeout_raises():
    from translation.concurrency import BackendConcurrency, ConcurrencyTimeoutError

    c = BackendConcurrency()
    c.register("b", 1)

    def hold():
        with c.slot("b"):
            time.sleep(1.0)

    t = threading.Thread(target=hold)
    t.start()
    time.sleep(0.05)

    with pytest.raises(ConcurrencyTimeoutError), c.slot("b", timeout_s=0.1):
        pass
    t.join()


def test_set_limit_upgrades_immediately():
    from translation.concurrency import BackendConcurrency

    c = BackendConcurrency()
    c.register("b", 1)

    def hold():
        with c.slot("b"):
            time.sleep(0.3)

    t1 = threading.Thread(target=hold)
    t1.start()
    time.sleep(0.05)
    # Now all 1 slot used. Raise limit to 2.
    c.set_limit("b", 2)
    # New acquire should succeed without blocking
    acquired = threading.Event()

    def try_acquire():
        with c.slot("b", timeout_s=0.3):
            acquired.set()

    t2 = threading.Thread(target=try_acquire)
    t2.start()
    t2.join()
    t1.join()
    assert acquired.is_set()


def test_release_on_exception():
    """Regression for semaphore leak on exception."""
    from translation.concurrency import BackendConcurrency

    c = BackendConcurrency()
    c.register("b", 1)

    with pytest.raises(RuntimeError), c.slot("b"):
        raise RuntimeError("boom")

    # Slot should be free again
    with c.slot("b", timeout_s=0.1):
        pass  # if slot was leaked, this would timeout


def test_per_backend_independence():
    from translation.concurrency import BackendConcurrency

    c = BackendConcurrency()
    c.register("a", 1)
    c.register("b", 1)

    # b's limit is independent from a's — should not block
    with c.slot("a"), c.slot("b", timeout_s=0.1):
        pass


def test_unregistered_backend_raises():
    from translation.concurrency import BackendConcurrency

    c = BackendConcurrency()
    with pytest.raises(KeyError), c.slot("never_registered"):
        pass


def test_prometheus_gauge_reflects_usage(monkeypatch):
    """In-use gauge increments + decrements with slot acquisitions."""
    from translation.concurrency import BackendConcurrency

    calls = []

    class FakeGauge:
        def labels(self, **kw):
            return self

        def inc(self):
            calls.append(("inc",))

        def dec(self):
            calls.append(("dec",))

        def set(self, v):
            calls.append(("set", v))

    monkeypatch.setattr("translation.concurrency._in_use_gauge", FakeGauge())
    monkeypatch.setattr("translation.concurrency._limit_gauge", FakeGauge())
    c = BackendConcurrency()
    c.register("b", 2)
    with c.slot("b"):
        pass
    ops = [c[0] for c in calls]
    assert "inc" in ops and "dec" in ops


def test_concurrent_stress_100_threads():
    """100 concurrent workers on 5 slots — all eventually acquire."""
    from translation.concurrency import BackendConcurrency

    c = BackendConcurrency()
    c.register("b", 5)

    acquired = [False] * 100

    def worker(i):
        with c.slot("b", timeout_s=30):
            acquired[i] = True
            time.sleep(0.01)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(100)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert all(acquired)
