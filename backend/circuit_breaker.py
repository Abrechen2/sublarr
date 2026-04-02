"""Circuit Breaker pattern for resilient external service calls.

States:
    CLOSED  — Normal operation, failures are counted.
    OPEN    — Calls are rejected immediately (service assumed down).
    HALF_OPEN — A single probe call is allowed through to test recovery.

State transitions:
    CLOSED → OPEN         when failure_count >= failure_threshold
    OPEN → HALF_OPEN      when cooldown_seconds have elapsed
    HALF_OPEN → CLOSED    when the probe call succeeds
    HALF_OPEN → OPEN      when the probe call fails
"""

import logging
import threading
import time
from collections.abc import Callable
from enum import StrEnum
from typing import Any

logger = logging.getLogger(__name__)


class CircuitState(StrEnum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    """Thread-safe circuit breaker for a single external dependency.

    Args:
        name: Human-readable name (e.g. provider name) for logging.
        failure_threshold: Number of consecutive failures before opening.
        cooldown_seconds: Seconds to wait in OPEN before transitioning to HALF_OPEN.
        persist_fn: Optional callback invoked after every state change with signature
            ``persist_fn(name, state, failure_count, last_failure_time)``.
            Exceptions raised by persist_fn are caught and logged — they never affect
            the circuit breaker's own operation.
    """

    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        cooldown_seconds: int = 60,
        persist_fn: Callable[[str, CircuitState, int, float | None], Any] | None = None,
    ) -> None:
        self.name = name
        self.failure_threshold = failure_threshold
        self.cooldown_seconds = cooldown_seconds

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time: float | None = None
        self._lock = threading.Lock()
        self._persist_fn = persist_fn

    def _call_persist(self) -> None:
        """Invoke persist_fn with current state snapshot. Never raises."""
        if self._persist_fn is None:
            return
        try:
            self._persist_fn(self.name, self._state, self._failure_count, self._last_failure_time)
        except Exception as e:
            logger.warning("CircuitBreaker[%s]: persist_fn failed: %s", self.name, e)

    def load_state(
        self,
        state: CircuitState | str,
        failure_count: int,
        last_failure_time: float | None,
    ) -> None:
        """Restore persisted state — called once at startup before any requests.

        If the restored state is OPEN but the cooldown has already elapsed the
        breaker transitions immediately to HALF_OPEN so the first real request
        acts as the probe call.
        """
        with self._lock:
            self._state = CircuitState(state) if isinstance(state, str) else state
            self._failure_count = failure_count
            self._last_failure_time = last_failure_time
            # Eagerly evaluate OPEN→HALF_OPEN so we don't block traffic unnecessarily
            self._check_half_open_transition_locked()
            logger.info(
                "CircuitBreaker[%s]: state restored — %s (failures: %d)",
                self.name,
                self._state.value,
                self._failure_count,
            )

    def _check_half_open_transition_locked(self) -> None:
        """Evaluate the OPEN→HALF_OPEN transition. Must be called while self._lock is held."""
        if self._state == CircuitState.OPEN and self._last_failure_time is not None:
            elapsed = time.monotonic() - self._last_failure_time
            if elapsed >= self.cooldown_seconds:
                self._state = CircuitState.HALF_OPEN
                logger.info(
                    "CircuitBreaker[%s]: OPEN → HALF_OPEN (cooldown %ds elapsed)",
                    self.name,
                    self.cooldown_seconds,
                )

    @property
    def state(self) -> CircuitState:
        """Current state (evaluates OPEN→HALF_OPEN transition lazily)."""
        with self._lock:
            self._check_half_open_transition_locked()
            return self._state

    @property
    def is_open(self) -> bool:
        """True if the circuit is OPEN (calls should be skipped)."""
        return self.state == CircuitState.OPEN

    def allow_request(self) -> bool:
        """Check whether a request should be allowed through.

        Returns True for CLOSED and HALF_OPEN, False for OPEN.
        """
        state = self.state  # triggers lazy OPEN→HALF_OPEN check
        return state != CircuitState.OPEN

    def record_success(self) -> None:
        """Record a successful call — resets the breaker to CLOSED."""
        with self._lock:
            if self._state != CircuitState.CLOSED:
                logger.info(
                    "CircuitBreaker[%s]: %s → CLOSED (success)",
                    self.name,
                    self._state.value,
                )
            self._state = CircuitState.CLOSED
            self._failure_count = 0
            self._last_failure_time = None
            self._call_persist()

    def record_failure(self) -> None:
        """Record a failed call — may trip the breaker to OPEN."""
        with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.monotonic()

            if self._state == CircuitState.HALF_OPEN:
                # Probe failed — go back to OPEN
                self._state = CircuitState.OPEN
                logger.warning(
                    "CircuitBreaker[%s]: HALF_OPEN → OPEN (probe failed)",
                    self.name,
                )
            elif (
                self._state == CircuitState.CLOSED and self._failure_count >= self.failure_threshold
            ):
                self._state = CircuitState.OPEN
                logger.warning(
                    "CircuitBreaker[%s]: CLOSED → OPEN (%d consecutive failures)",
                    self.name,
                    self._failure_count,
                )
            self._call_persist()

    def reset(self) -> None:
        """Manually reset the breaker to CLOSED."""
        with self._lock:
            old_state = self._state
            self._state = CircuitState.CLOSED
            self._failure_count = 0
            self._last_failure_time = None
            if old_state != CircuitState.CLOSED:
                logger.info(
                    "CircuitBreaker[%s]: %s → CLOSED (manual reset)", self.name, old_state.value
                )
            self._call_persist()

    def get_status(self) -> dict:
        """Return a JSON-serialisable status dict."""
        with self._lock:
            # Evaluate OPEN→HALF_OPEN transition inside the lock for consistency
            self._check_half_open_transition_locked()
            return {
                "name": self.name,
                "state": self._state.value,
                "failure_count": self._failure_count,
                "failure_threshold": self.failure_threshold,
                "cooldown_seconds": self.cooldown_seconds,
            }
