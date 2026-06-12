"""Shared bounded executor for fire-and-forget background work.

Request handlers that kick off async work (single search, batch probe/extract,
retranslate, system tasks) historically did ``threading.Thread(target=_run,
daemon=True).start()`` per request. That is unbounded: N concurrent requests
spawn N OS threads, and under sustained load the process hits the OS thread
limit and starts failing connections.

This module provides one process-wide ``ThreadPoolExecutor`` so the number of
concurrent background workers is capped. Call sites keep their existing
``_run`` closures (which push their own Flask app context and handle their own
exceptions) — they just submit instead of spawning. Response contracts are
unchanged: the handler still returns immediately (typically HTTP 202).
"""

import logging
import os
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)


def _resolve_max_workers() -> int:
    raw = os.environ.get("SUBLARR_BACKGROUND_WORKERS", "").strip()
    try:
        value = int(raw) if raw else 8
    except ValueError:
        value = 8
    return max(2, value)


_executor = ThreadPoolExecutor(
    max_workers=_resolve_max_workers(),
    thread_name_prefix="sublarr-bg",
)


def _guard(fn, *args, **kwargs):
    """Backstop so a task that raises can never take down a pool worker."""
    try:
        return fn(*args, **kwargs)
    except Exception:
        logger.exception("Background task %r failed", getattr(fn, "__name__", fn))
        return None


def submit_background(fn, *args, **kwargs):
    """Submit a fire-and-forget task to the shared bounded pool.

    Returns the ``concurrent.futures.Future`` (callers usually ignore it).
    """
    return _executor.submit(_guard, fn, *args, **kwargs)


def shutdown_background(wait: bool = False) -> None:
    """Stop accepting new tasks; used during graceful app shutdown."""
    _executor.shutdown(wait=wait, cancel_futures=True)
