"""Whisper routes package: /transcribe, /queue, /jobs, /backends, /config, /stats.

The `_queue` singleton, `_get_queue`, `_get_config`, and `_reset_queue` all live at
the package level so tests and submodules can reach them via `routes.whisper.<name>`.
Submodules attach their routes to the shared `bp` Blueprint defined here.
"""

import logging

from flask import Blueprint

bp = Blueprint("whisper", __name__, url_prefix="/api/v1/whisper")
logger = logging.getLogger(__name__)


# --- WhisperQueue singleton ---

_queue = None


def _get_queue():
    """Get or create the WhisperQueue singleton."""
    global _queue
    if _queue is None:
        from whisper.queue import WhisperQueue

        max_concurrent = int(_get_config("max_concurrent_whisper", "1"))
        _queue = WhisperQueue(max_concurrent=max_concurrent)
    return _queue


def _reset_queue():
    """Reset the queue singleton so the next _get_queue call re-reads max_concurrent."""
    global _queue
    _queue = None


def _get_config(key, default=""):
    """Read a config entry with fallback."""
    try:
        from db.config import get_config_entry

        value = get_config_entry(key)
        return value if value is not None else default
    except Exception:
        return default


# Register route submodules — must come after bp is defined.
from routes.whisper import (  # noqa: E402, F401
    backends,
    config,
    jobs,
    stats,
    transcribe,
)
