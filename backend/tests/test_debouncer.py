"""Tests for utils.debouncer -- DebouncedCallback + KeyedDebouncedCallback."""

import threading
import time

import pytest

from utils.debouncer import DebouncedCallback, KeyedDebouncedCallback


def test_single_trigger_fires_after_delay():
    calls = []
    d = DebouncedCallback(delay_s=0.1, callback=lambda: calls.append(1))
    d.trigger()
    time.sleep(0.2)
    assert calls == [1]
    d.shutdown()


def test_retrigger_resets_countdown():
    """Regression for feedback_scheduler_timer_leak -- retrigger must cancel."""
    calls = []
    d = DebouncedCallback(delay_s=0.15, callback=lambda: calls.append(1))
    d.trigger()
    time.sleep(0.05)
    d.trigger()  # should cancel first
    time.sleep(0.05)
    d.trigger()  # should cancel second
    time.sleep(0.3)
    # Only the last trigger fires (three triggers, one callback)
    assert calls == [1]
    d.shutdown()


def test_shutdown_cancels_pending():
    calls = []
    d = DebouncedCallback(delay_s=0.1, callback=lambda: calls.append(1))
    d.trigger()
    d.shutdown()
    time.sleep(0.2)
    assert calls == []


def test_shutdown_is_idempotent():
    d = DebouncedCallback(delay_s=0.1, callback=lambda: None)
    d.trigger()
    d.shutdown()
    d.shutdown()  # no raise


def test_trigger_after_shutdown_is_noop():
    calls = []
    d = DebouncedCallback(delay_s=0.1, callback=lambda: calls.append(1))
    d.shutdown()
    d.trigger()
    time.sleep(0.2)
    assert calls == []


def test_callback_exception_does_not_break_timer():
    calls = []

    def boom():
        calls.append(1)
        raise RuntimeError("deliberate")

    d = DebouncedCallback(delay_s=0.05, callback=boom, name="test")
    d.trigger()
    time.sleep(0.15)
    assert calls == [1]  # fired, exception caught
    # Re-trigger still works
    d.trigger()
    time.sleep(0.15)
    assert calls == [1, 1]
    d.shutdown()


def test_rejects_nonpositive_delay():
    with pytest.raises(ValueError, match="positive"):
        DebouncedCallback(delay_s=0, callback=lambda: None)
    with pytest.raises(ValueError, match="positive"):
        DebouncedCallback(delay_s=-1, callback=lambda: None)


def test_thread_safety_many_triggers():
    """Concurrent triggers from many threads must not leak timers."""
    calls = []
    d = DebouncedCallback(delay_s=0.1, callback=lambda: calls.append(1))

    def spam():
        for _ in range(50):
            d.trigger()

    threads = [threading.Thread(target=spam) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    time.sleep(0.3)
    # Despite 500 triggers, only one callback
    assert len(calls) == 1
    d.shutdown()


# ---- KeyedDebouncedCallback tests ----


def test_keyed_independent_keys():
    calls = []
    d = KeyedDebouncedCallback(delay_s=0.1, callback=lambda k: calls.append(k))
    d.trigger("a")
    d.trigger("b")
    time.sleep(0.3)
    assert set(calls) == {"a", "b"}
    d.shutdown()


def test_keyed_retrigger_same_key_resets():
    calls = []
    d = KeyedDebouncedCallback(delay_s=0.15, callback=lambda k: calls.append(k))
    d.trigger("a")
    time.sleep(0.05)
    d.trigger("a")
    time.sleep(0.3)
    assert calls == ["a"]
    d.shutdown()


def test_keyed_retrigger_different_keys_are_independent():
    calls = []
    d = KeyedDebouncedCallback(delay_s=0.1, callback=lambda k: calls.append(k))
    d.trigger("a")
    time.sleep(0.03)
    d.trigger("b")  # does NOT cancel "a"
    time.sleep(0.3)
    assert set(calls) == {"a", "b"}
    d.shutdown()


def test_keyed_shutdown_cancels_all():
    calls = []
    d = KeyedDebouncedCallback(delay_s=0.1, callback=lambda k: calls.append(k))
    for k in ("a", "b", "c"):
        d.trigger(k)
    d.shutdown()
    time.sleep(0.2)
    assert calls == []


def test_keyed_key_removed_from_dict_after_fire():
    d = KeyedDebouncedCallback(delay_s=0.05, callback=lambda k: None, name="test")
    d.trigger("x")
    time.sleep(0.15)
    # Internal _timers should not leak
    assert "x" not in d._timers
    d.shutdown()
