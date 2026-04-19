"""Provider metadata registry — single source of truth for per-provider configuration.

Each entry specifies:
  rate_limit  : (max_requests, window_seconds) — 0/0 means no limit
  timeout     : int seconds — used when provider class has no .timeout attribute
  retries     : int — used when provider class has no .max_retries attribute

Providers not listed use the ProviderManager defaults:
  rate_limit  -> (0, 0)   (no limit)
  timeout     -> settings.provider_search_timeout
  retries     -> 2
"""

PROVIDER_METADATA: dict[str, dict] = {
    "opensubtitles": {"rate_limit": (40, 10), "timeout": 10, "retries": 3},
    "jimaku": {"rate_limit": (100, 60), "timeout": 12, "retries": 2},
    "animetosho": {"rate_limit": (50, 30), "timeout": 10, "retries": 2},
    "subdl": {"rate_limit": (30, 10), "timeout": 10, "retries": 2},
    "subsdump": {"rate_limit": (0, 0), "timeout": 30, "retries": 2},
}

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from providers.base import SubtitleProvider

logger = logging.getLogger(__name__)

_PROVIDER_CLASSES: dict[str, "type[SubtitleProvider]"] = {}


def register_provider(cls: "type[SubtitleProvider]") -> "type[SubtitleProvider]":
    """Decorator to register a provider class.

    Built-in providers always win on name collision: if a name is already
    registered, a warning is logged and the duplicate is skipped.
    """
    if cls.name in _PROVIDER_CLASSES:
        logger.warning(
            "Provider name collision: '%s' already registered by %s, skipping %s",
            cls.name,
            _PROVIDER_CLASSES[cls.name].__name__,
            cls.__name__,
        )
        return cls
    _PROVIDER_CLASSES[cls.name] = cls
    return cls


_BUILTIN_PROVIDERS: tuple[str, ...] = (
    "opensubtitles",
    "jimaku",
    "animetosho",
    "subdl",
    "subsdump",
    "gestdown",
    "podnapisi",
    "kitsunekko",
    "napisy24",
    "titrari",
    "legendasdivx",
    "subscene",
    "addic7ed",
    "tvsubtitles",
    "turkcealtyazi",
    "subsource",
    "subf2m",
    "yifysubtitles",
    "zimuku",
    "betaseries",
    "titlovi",
    "embedded",
    "subliminal_opensubtitles",  # Subliminal-flavored pilot (Plan B1)
)


def import_builtin_providers() -> None:
    """Import all built-in provider modules to trigger @register_provider decorators."""
    import importlib

    for name in _BUILTIN_PROVIDERS:
        try:
            importlib.import_module(f"providers.{name}")
        except ImportError as e:
            logger.debug("Provider %s not available: %s", name, e)


__all__ = [
    "PROVIDER_METADATA",
    "_PROVIDER_CLASSES",
    "register_provider",
    "_BUILTIN_PROVIDERS",
    "import_builtin_providers",
]
