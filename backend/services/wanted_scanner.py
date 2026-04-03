"""Wanted subtitle scanner — public facade.

All external callers import from this module. Implementation lives in
wanted_scanner_core.py.
"""

import logging
import threading

from services.wanted_scanner_core import (
    FULL_SCAN_INTERVAL,  # noqa: F401 — re-export for callers
    WantedScanner,  # noqa: F401
)

logger = logging.getLogger(__name__)

_scanner: WantedScanner | None = None
_scanner_lock = threading.Lock()


def get_scanner() -> WantedScanner:
    """Get or create the singleton WantedScanner (thread-safe).

    When called inside a Flask app context, the result is stored in and
    retrieved from ``app.extensions["wanted_scanner"]`` — this lets tests
    inject a mock by writing to that key. Falls back to a module-level
    global when no app context is available (e.g. scheduler threads).
    """
    global _scanner
    in_ctx = _has_flask_app_context()
    # Use app.extensions when an app context is active
    if in_ctx:
        scanner = _get_flask_extension("wanted_scanner")
        if scanner is not None:
            return scanner
    if _scanner is None:
        with _scanner_lock:
            if _scanner is None:
                _scanner = WantedScanner()
    # Re-populate extensions if inside an app context (self-healing after invalidation)
    if in_ctx:
        _set_flask_extension("wanted_scanner", _scanner)
    return _scanner


def invalidate_scanner() -> None:
    """Reset the scanner singleton (call after config changes)."""
    global _scanner
    if _scanner:
        _scanner.stop_scheduler()
    _scanner = None
    _pop_flask_extension("wanted_scanner")


def _has_flask_app_context() -> bool:
    try:
        from flask import has_app_context

        return has_app_context()
    except ImportError:
        return False


def _get_flask_extension(key: str):
    try:
        from flask import current_app

        return current_app.extensions.get(key)
    except RuntimeError:
        return None


def _set_flask_extension(key: str, value) -> None:
    try:
        from flask import current_app

        current_app.extensions[key] = value
    except RuntimeError:
        pass


def _pop_flask_extension(key: str) -> None:
    try:
        from flask import current_app

        current_app.extensions.pop(key, None)
    except RuntimeError:
        pass
