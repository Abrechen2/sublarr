"""Process-wide singleton accessor for ProviderManager.

Other modules call `get_provider_manager()` to retrieve the active
ProviderManager instance and `invalidate_manager()` to clear it.
`update_manager_providers(...)` mutates the live instance's provider set.

Importing rule: this module MUST NOT import `ProviderManager` at the
module level — that would cause a circular import because
`providers/__init__.py` re-exports symbols from this file. The actual
ProviderManager instantiation happens via a lazy import inside the
function bodies.
"""

from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from providers import ProviderManager

logger = logging.getLogger(__name__)

_provider_manager_lock = threading.Lock()
_manager: ProviderManager | None = None


def _has_flask_app_context() -> bool:
    try:
        from flask import has_app_context

        return has_app_context()
    except ImportError:
        return False


def _get_from_extensions(key: str):
    try:
        from flask import current_app

        return current_app.extensions.get(key)
    except RuntimeError:
        return None


def _set_in_extensions(key: str, value) -> None:
    try:
        from flask import current_app

        current_app.extensions[key] = value
    except RuntimeError:
        pass


def _pop_from_extensions(key: str) -> None:
    try:
        from flask import current_app

        current_app.extensions.pop(key, None)
    except RuntimeError:
        pass


def get_provider_manager() -> ProviderManager:
    """Get or create the singleton ProviderManager (thread-safe).

    When called inside a Flask app context, the result is stored in and
    retrieved from ``app.extensions["provider_manager"]`` — this lets tests
    inject a mock by writing to that key. Falls back to a module-level
    global when no app context is available (e.g. scheduler threads).
    """
    global _manager
    # Lazy import to avoid circular dependency with providers.__init__
    from providers import ProviderManager  # noqa: E402

    in_ctx = _has_flask_app_context()
    if in_ctx:
        manager = _get_from_extensions("provider_manager")
        if manager is not None:
            return manager
    if _manager is None:
        with _provider_manager_lock:
            if _manager is None:
                _manager = ProviderManager()
    # Re-populate extensions if inside an app context (self-healing after invalidation)
    if in_ctx:
        _set_in_extensions("provider_manager", _manager)
    return _manager


def invalidate_manager():
    """Reset the manager (call after config changes)."""
    global _manager
    if _manager:
        _manager.shutdown()
    _manager = None
    _pop_from_extensions("provider_manager")


def update_manager_providers(new_enabled_str: str) -> None:
    """Selectively update enabled providers without reinitializing the whole manager.

    Call this instead of invalidate_manager() when only providers_enabled changed.
    If the manager hasn't been initialized yet, this is a no-op (it will pick up
    the correct config on first access).
    """
    global _manager
    if _manager is None:
        return
    with _provider_manager_lock:
        if _manager is not None:
            _manager.update_providers(new_enabled_str)


__all__ = [
    "get_provider_manager",
    "invalidate_manager",
    "update_manager_providers",
]
