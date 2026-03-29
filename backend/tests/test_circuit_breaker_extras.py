"""Tests for CircuitBreaker.is_open property and persistence integration."""


def test_is_open_false_when_closed():
    from circuit_breaker import CircuitBreaker

    cb = CircuitBreaker("test", failure_threshold=2, cooldown_seconds=60)
    assert cb.is_open is False


def test_is_open_true_after_threshold():
    from circuit_breaker import CircuitBreaker

    cb = CircuitBreaker("test", failure_threshold=2, cooldown_seconds=60)
    cb.record_failure()
    cb.record_failure()
    assert cb.is_open is True


def test_is_open_false_after_success():
    from circuit_breaker import CircuitBreaker

    cb = CircuitBreaker("test", failure_threshold=1, cooldown_seconds=60)
    cb.record_failure()
    assert cb.is_open is True
    cb.record_success()
    assert cb.is_open is False
