"""Per-backend concurrency semaphore.

Each registered translation backend gets its own BoundedSemaphore. The
slot() context manager acquires+releases safely (release guaranteed even
on exception).

Limit changes via set_limit are picked up by subsequent acquisitions;
in-flight workers are unaffected.
"""

from __future__ import annotations

import logging
import threading
from contextlib import contextmanager

logger = logging.getLogger(__name__)


class ConcurrencyTimeoutError(TimeoutError):
    """Raised when slot() blocks longer than timeout_s."""


class _NoopGauge:
    """Fallback when monitoring.metrics has not been populated yet."""

    def labels(self, **kw):
        return self

    def inc(self):
        pass

    def dec(self):
        pass

    def set(self, v):
        pass


# Module-level gauges, replaced by Task 14 when monitoring.metrics declares them.
_in_use_gauge = _NoopGauge()
_limit_gauge = _NoopGauge()


def _wire_prometheus_gauges():
    """Called lazily on first register; tolerates missing metrics module."""
    global _in_use_gauge, _limit_gauge
    # Skip wiring if already patched by tests (monkeypatch sets them to non-NoopGauge)
    if not isinstance(_in_use_gauge, _NoopGauge):
        return
    try:
        from monitoring.metrics import (
            translation_concurrency_in_use,
            translation_concurrency_limit,
        )

        _in_use_gauge = translation_concurrency_in_use
        _limit_gauge = translation_concurrency_limit
    except (ImportError, AttributeError):
        # Metrics module exists but translation gauges haven't been added yet
        # (Task 14). Keep no-op fallback — tests can still inject their own.
        pass


class BackendConcurrency:
    """Per-backend BoundedSemaphore registry."""

    def __init__(self) -> None:
        self._semaphores: dict[str, threading.BoundedSemaphore] = {}
        self._limits: dict[str, int] = {}
        self._lock = threading.Lock()
        _wire_prometheus_gauges()

    def register(self, backend_name: str, initial_limit: int) -> None:
        if initial_limit < 1:
            raise ValueError("initial_limit must be >= 1")
        with self._lock:
            self._semaphores[backend_name] = threading.BoundedSemaphore(initial_limit)
            self._limits[backend_name] = initial_limit
        _limit_gauge.labels(backend=backend_name).set(initial_limit)

    def get_limit(self, backend_name: str) -> int:
        return self._limits.get(backend_name, 0)

    def set_limit(self, backend_name: str, new_limit: int) -> None:
        """Resize semaphore. Increases release slots immediately; decreases
        don't evict in-flight workers but new acquires obey the lower cap."""
        if new_limit < 1:
            raise ValueError("limit must be >= 1")
        with self._lock:
            old = self._limits.get(backend_name, 0)
            if old == new_limit:
                return
            # Replace semaphore. Existing holders still valid via their own reference.
            self._semaphores[backend_name] = threading.BoundedSemaphore(new_limit)
            self._limits[backend_name] = new_limit
        _limit_gauge.labels(backend=backend_name).set(new_limit)
        logger.info(
            "translation concurrency limit: %s %d -> %d",
            backend_name,
            old,
            new_limit,
        )

    @contextmanager
    def slot(self, backend_name: str, timeout_s: float = 120.0):
        """Acquire slot (blocks up to timeout_s), yield, release.

        Raises KeyError if backend not registered.
        Raises ConcurrencyTimeoutError on timeout.
        """
        with self._lock:
            if backend_name not in self._semaphores:
                raise KeyError(f"backend {backend_name!r} not registered")
            sem = self._semaphores[backend_name]

        acquired = sem.acquire(timeout=timeout_s)
        if not acquired:
            raise ConcurrencyTimeoutError(f"{backend_name} concurrency timeout after {timeout_s}s")
        _in_use_gauge.labels(backend=backend_name).inc()
        try:
            yield
        finally:
            sem.release()
            _in_use_gauge.labels(backend=backend_name).dec()


# Module singleton — wired by TranslationManager at startup.
_instance: BackendConcurrency | None = None


def get_concurrency() -> BackendConcurrency:
    global _instance
    if _instance is None:
        _instance = BackendConcurrency()
    return _instance


def reset_for_tests() -> None:
    global _instance
    _instance = None
