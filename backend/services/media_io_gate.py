"""One gate for every heavy media subprocess.

mkvmerge/ffmpeg remuxes, ffmpeg subtitle extraction, ffsubsync/alass and the
metadata probe batches all stream whole media files off the library. Left to
their own thread pools they fan out: on 2026-09-04 a wanted search started
three 7 GB remuxes within 200 ms of each other while the automation queue
read entire movies for ffsubsync — 81.8 GB rewritten in the first hour after
a reboot, the array at load 14, ffprobe calls timing out behind it.

``media_io_gate`` is the single choke point. ``media_io_max_parallel`` (UI
setting, default 1) says how many of those subprocesses may run at once,
process-wide. Search threads keep querying providers in parallel; only the
disk-heavy step behind a download queues up.

Why not a ``BoundedSemaphore``: the limit is a live setting. A semaphore
cannot be resized, and swapping it out leaks slots held by in-flight callers.
A counter under a ``Condition`` resizes safely — raising the limit wakes
waiters, lowering it never evicts anyone, new acquires just obey the new cap.

Wait policy: inside an HTTP request the caller waits ``REQUEST_WAIT_S`` at
most and then gets ``MediaGateBusyError`` — gunicorn has four threads, and a
ten-minute remux must not be able to park them; ten seconds keeps even four
simultaneous UI callers from holding the whole thread budget for long.
Background callers (scheduler ticks, search workers, the automation drain)
wait up to ``BACKGROUND_WAIT_S``; their work is exactly what the gate is for.

The gate keeps the ``with gate:`` / ``acquire(timeout=)`` / ``release()``
protocol of the ``BoundedSemaphore(1)`` it replaces in
``services.sync_engines.concurrency`` so the sync engines and the sync preview
run unchanged.
"""

from __future__ import annotations

import logging
import threading
import time
from contextlib import contextmanager

from config_singleton import peek_settings

logger = logging.getLogger(__name__)

SETTING_NAME = "media_io_max_parallel"

#: Log a line when a caller has been queued this long — that is the
#: observable symptom an operator can correlate with array load.
_SLOW_WAIT_LOG_S = 5.0


class MediaGateBusyError(RuntimeError):
    """The gate stayed full for the whole wait; the caller did not run."""


class _NoopGauge:
    def set(self, *_a, **_k):
        pass


class MediaIOGate:
    """Resizable counting gate; see the module docstring."""

    REQUEST_WAIT_S = 10.0
    BACKGROUND_WAIT_S = 3600.0

    def __init__(self, limit: int = 1) -> None:
        self._cond = threading.Condition()
        self._limit = max(1, int(limit))
        self._in_use = 0
        self._in_use_gauge = _NoopGauge()
        self._limit_gauge = _NoopGauge()

    # -- observability -----------------------------------------------------

    def wire_gauges(self, in_use_gauge, limit_gauge) -> None:
        self._in_use_gauge = in_use_gauge
        self._limit_gauge = limit_gauge
        limit_gauge.set(self._limit)
        in_use_gauge.set(self._in_use)

    @property
    def limit(self) -> int:
        return self._limit

    @property
    def in_use(self) -> int:
        return self._in_use

    # -- sizing ------------------------------------------------------------

    def set_limit(self, new_limit: int) -> None:
        new_limit = max(1, int(new_limit))
        with self._cond:
            if new_limit == self._limit:
                return
            old, self._limit = self._limit, new_limit
            self._cond.notify_all()
        self._limit_gauge.set(new_limit)
        logger.info("media IO gate: limit %d -> %d", old, new_limit)

    def _sync_limit_from_settings(self) -> None:
        settings = peek_settings()
        if settings is None:
            return
        try:
            configured = int(getattr(settings, SETTING_NAME, self._limit))
        except (TypeError, ValueError):
            return
        if configured != self._limit:
            self.set_limit(configured)

    def cap_workers(self, requested: int) -> int:
        """Bound a thread-pool size by the gate so a probe batch cannot fan
        out wider than the gate would let its subprocesses run."""
        self._sync_limit_from_settings()
        return max(1, min(int(requested), self._limit))

    # -- wait policy -------------------------------------------------------

    def default_wait_s(self) -> float:
        try:
            from flask import has_request_context

            if has_request_context():
                return self.REQUEST_WAIT_S
        except Exception:  # pragma: no cover - flask always present in the app
            pass
        return self.BACKGROUND_WAIT_S

    # -- the semaphore protocol -------------------------------------------

    #: A sleeping waiter re-reads the setting this often, so a raised limit
    #: takes effect without anyone releasing or calling ``set_limit``.
    _SETTINGS_POLL_S = 1.0

    def acquire(self, blocking: bool = True, timeout: float | None = None) -> bool:
        if not blocking and timeout is not None:
            raise ValueError("can't specify timeout for non-blocking acquire")
        deadline = None if timeout is None else time.monotonic() + timeout
        while True:
            self._sync_limit_from_settings()
            with self._cond:
                if self._in_use < self._limit:
                    self._in_use += 1
                    held = self._in_use
                    break
                if not blocking:
                    return False
                remaining = None if deadline is None else deadline - time.monotonic()
                if remaining is not None and remaining <= 0:
                    return False
                nap = (
                    self._SETTINGS_POLL_S
                    if remaining is None
                    else min(remaining, self._SETTINGS_POLL_S)
                )
                self._cond.wait(nap)
        self._in_use_gauge.set(held)
        return True

    def release(self) -> None:
        with self._cond:
            if self._in_use <= 0:
                raise ValueError("media IO gate released more often than acquired")
            self._in_use -= 1
            held = self._in_use
            self._cond.notify()
        self._in_use_gauge.set(held)

    def __enter__(self) -> MediaIOGate:
        self.acquire()
        return self

    def __exit__(self, *_exc) -> None:
        self.release()

    @contextmanager
    def slot(self, label: str, timeout: float | None = None):
        """Hold one slot for the duration of the block.

        ``timeout`` defaults to the wait policy above. A caller that does not
        get in raises ``MediaGateBusyError`` and has done nothing.
        """
        wait_s = self.default_wait_s() if timeout is None else timeout
        started = time.monotonic()
        if not self.acquire(timeout=wait_s):
            raise MediaGateBusyError(
                f"media IO gate busy: {label} waited {wait_s:.0f}s, "
                f"{self._in_use}/{self._limit} slot(s) in use"
            )
        waited = time.monotonic() - started
        if waited >= _SLOW_WAIT_LOG_S:
            logger.info(
                "media IO gate: %s queued %.1fs behind other media work (limit %d)",
                label,
                waited,
                self._limit,
            )
        try:
            yield self
        finally:
            self.release()


media_io_gate = MediaIOGate()


def _wire_prometheus() -> None:
    try:
        from monitoring.metrics import media_io_gate_in_use, media_io_gate_limit
    except Exception:  # metrics optional (prometheus_client may be absent)
        return
    media_io_gate.wire_gauges(media_io_gate_in_use, media_io_gate_limit)


_wire_prometheus()
