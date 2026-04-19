"""Thread-safe debouncer primitives.

Provides two callbacks for consolidating rapid events into a single
trailing-edge call:

- ``DebouncedCallback`` -- single pending timer; re-triggers reset the
  countdown. Use for "one global event stream, one trailing call".
- ``KeyedDebouncedCallback`` -- per-key dict of pending timers; re-triggers
  for the same key reset that key's countdown independently. Use for
  per-path or per-entity debouncing.

Both classes correctly cancel the existing timer before scheduling a new
one (fixes the feedback_scheduler_timer_leak regression pattern). Both
are thread-safe via an internal lock.

Timers are daemon threads so they do not prevent process exit. Call
``shutdown()`` for clean cancellation on application stop.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)


class DebouncedCallback:
    """Single-pending-timer debouncer.

    Example:
        reload_cb = DebouncedCallback(
            delay_s=2.0,
            callback=plugin_manager.reload,
            name="plugin_reload",
        )
        reload_cb.trigger()  # starts timer
        reload_cb.trigger()  # cancels + restarts -- only one fires
        reload_cb.shutdown()  # cancels any pending
    """

    def __init__(
        self,
        delay_s: float,
        callback: Callable[[], Any],
        name: str = "debounced",
    ) -> None:
        if delay_s <= 0:
            raise ValueError("delay_s must be positive")
        self._delay_s = delay_s
        self._callback = callback
        self._name = name
        self._timer: threading.Timer | None = None
        self._lock = threading.Lock()
        self._shutdown = False

    def trigger(self) -> None:
        """Start or restart the debounce countdown."""
        with self._lock:
            if self._shutdown:
                return
            if self._timer is not None:
                self._timer.cancel()
            self._timer = threading.Timer(self._delay_s, self._fire)
            self._timer.daemon = True
            self._timer.name = f"debounce-{self._name}"
            self._timer.start()

    def _fire(self) -> None:
        """Invoke the callback; exceptions are logged, never re-raised."""
        try:
            self._callback()
        except Exception:
            logger.error("DebouncedCallback %r raised", self._name, exc_info=True)

    def shutdown(self) -> None:
        """Cancel any pending timer. Safe to call multiple times."""
        with self._lock:
            self._shutdown = True
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None


class KeyedDebouncedCallback:
    """Per-key debouncer -- each key has its own independent pending timer.

    Example:
        fs_cb = KeyedDebouncedCallback(
            delay_s=10.0,
            callback=lambda path: on_new_file(path),
            name="fs_watcher",
        )
        fs_cb.trigger("/media/a.mkv")  # timer for /media/a.mkv
        fs_cb.trigger("/media/b.mkv")  # separate timer for /media/b.mkv
        fs_cb.trigger("/media/a.mkv")  # cancels + restarts /media/a.mkv only
    """

    def __init__(
        self,
        delay_s: float,
        callback: Callable[[str], Any],
        name: str = "keyed-debounced",
    ) -> None:
        if delay_s <= 0:
            raise ValueError("delay_s must be positive")
        self._delay_s = delay_s
        self._callback = callback
        self._name = name
        self._timers: dict[str, threading.Timer] = {}
        self._lock = threading.Lock()
        self._shutdown = False

    def trigger(self, key: str) -> None:
        """Start or restart the debounce countdown for ``key``."""
        with self._lock:
            if self._shutdown:
                return
            existing = self._timers.get(key)
            if existing is not None:
                existing.cancel()
            timer = threading.Timer(self._delay_s, self._fire, args=(key,))
            timer.daemon = True
            timer.name = f"debounce-{self._name}-{key}"
            self._timers[key] = timer
            timer.start()

    def _fire(self, key: str) -> None:
        """Invoke the callback for ``key``; exceptions are logged only."""
        with self._lock:
            self._timers.pop(key, None)
        try:
            self._callback(key)
        except Exception:
            logger.error(
                "KeyedDebouncedCallback %r key=%r raised",
                self._name,
                key,
                exc_info=True,
            )

    def shutdown(self) -> None:
        """Cancel all pending timers. Safe to call multiple times."""
        with self._lock:
            self._shutdown = True
            for timer in self._timers.values():
                timer.cancel()
            self._timers.clear()
