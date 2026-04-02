"""Tests for CircuitBreaker state persistence via persist_fn callback."""

import time
from unittest.mock import MagicMock

from circuit_breaker import CircuitBreaker, CircuitState


class TestCircuitBreakerPersistFn:
    def test_persist_fn_called_on_record_failure(self):
        persist = MagicMock()
        cb = CircuitBreaker("test", failure_threshold=3, cooldown_seconds=60, persist_fn=persist)
        cb.record_failure()
        persist.assert_called_once()

    def test_persist_fn_called_on_record_success(self):
        persist = MagicMock()
        cb = CircuitBreaker("test", failure_threshold=1, cooldown_seconds=60, persist_fn=persist)
        cb.record_failure()
        persist.reset_mock()
        cb.record_success()
        persist.assert_called_once()

    def test_persist_fn_called_on_reset(self):
        persist = MagicMock()
        cb = CircuitBreaker("test", failure_threshold=1, cooldown_seconds=60, persist_fn=persist)
        cb.record_failure()
        persist.reset_mock()
        cb.reset()
        persist.assert_called_once()

    def test_no_persist_fn_works_normally(self):
        cb = CircuitBreaker("test", failure_threshold=2, cooldown_seconds=60)
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitState.OPEN
        cb.record_success()
        assert cb.state == CircuitState.CLOSED

    def test_load_state_restores_open(self):
        cb = CircuitBreaker("test", failure_threshold=5, cooldown_seconds=60)
        cb.load_state(
            state=CircuitState.OPEN,
            failure_count=5,
            last_failure_time=time.monotonic() - 10,
        )
        assert cb.state == CircuitState.OPEN
        assert not cb.allow_request()

    def test_load_state_restores_closed(self):
        cb = CircuitBreaker("test", failure_threshold=5, cooldown_seconds=60)
        cb.load_state(state=CircuitState.CLOSED, failure_count=0, last_failure_time=None)
        assert cb.state == CircuitState.CLOSED
        assert cb.allow_request()

    def test_load_state_expired_open_becomes_half_open(self):
        cb = CircuitBreaker("test", failure_threshold=5, cooldown_seconds=10)
        cb.load_state(
            state=CircuitState.OPEN,
            failure_count=5,
            last_failure_time=time.monotonic() - 20,
        )
        assert cb.state == CircuitState.HALF_OPEN

    def test_persist_fn_signature(self):
        captured = {}

        def my_persist(name, state, failure_count, last_failure_time):
            captured.update(
                name=name,
                state=state,
                failure_count=failure_count,
                last_failure_time=last_failure_time,
            )

        cb = CircuitBreaker(
            "prov_test", failure_threshold=1, cooldown_seconds=60, persist_fn=my_persist
        )
        cb.record_failure()
        assert captured["name"] == "prov_test"
        assert captured["state"] == CircuitState.OPEN
        assert captured["failure_count"] == 1
