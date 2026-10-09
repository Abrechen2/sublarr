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
    "customapi": {"rate_limit": (0, 0), "timeout": 20, "retries": 2},
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
    "customapi",
    "gestdown",
    "podnapisi",
    "kitsunekko",
    "napisy24",
    "titrari",
    "legendasdivx",
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
    # Plan B2 — Subliminal-flavor wrappers for the 6 non-pilot Subliminal providers
    "subliminal_addic7ed",
    "subliminal_gestdown",
    "subliminal_napiprojekt",
    "subliminal_opensubtitlescom",
    "subliminal_podnapisi",
    # "subliminal_tvsubtitles" — retired 2026-09-14 (GH #207). The vendored
    # Bazarr copy POSTs to tvsubtitles.net/search.php, which has answered 404
    # (403 through its UA) since the site moved to search1.php; it logged 98
    # failures in 24 h and has never returned a result. The native
    # "tvsubtitles" provider now covers the same site end to end.
)


def default_enabled_names() -> set[str]:
    """What an empty ``providers_enabled`` means: every provider that is not opt-in.

    Catalog providers (providers/hub) are opt-in — they must be named. Every
    place that resolves the setting goes through ``resolve_enabled_names`` so
    the rule cannot drift between the manager, the status list and the UI.
    """
    return {name for name, cls in _PROVIDER_CLASSES.items() if not getattr(cls, "opt_in", False)}


def resolve_enabled_names(value) -> set[str]:
    """The provider names a ``providers_enabled`` value enables."""
    text = (value or "").strip()
    if not text:
        return default_enabled_names()
    return {p.strip() for p in text.split(",") if p.strip()}


def _unregister_hub_providers() -> None:
    """Drop catalog provider classes so switching the catalog off takes effect at once."""
    for name in [n for n, cls in _PROVIDER_CLASSES.items() if getattr(cls, "hub_id", "")]:
        del _PROVIDER_CLASSES[name]


def import_builtin_providers() -> None:
    """Import all built-in provider modules to trigger @register_provider decorators."""
    import importlib

    for name in _BUILTIN_PROVIDERS:
        try:
            importlib.import_module(f"providers.{name}")
        except ImportError as e:
            logger.debug("Provider %s not available: %s", name, e)

    # Catalog providers (providers/hub) only when the install switched them on.
    try:
        from config import get_settings

        if getattr(get_settings(), "provider_hub_enabled", False):
            from providers.hub import register_hub_providers

            register_hub_providers()
        else:
            _unregister_hub_providers()
    except Exception as e:
        logger.warning("Catalog providers not loaded: %s", e)

    # Re-sync dynamically registered Custom API instances (customapi-<name>)
    # so ProviderManager re-initialization picks up config changes.
    try:
        from providers.customapi import sync_instances

        sync_instances()
    except Exception as e:
        logger.debug("Custom API instance sync skipped: %s", e)


__all__ = [
    "PROVIDER_METADATA",
    "_PROVIDER_CLASSES",
    "register_provider",
    "default_enabled_names",
    "resolve_enabled_names",
    "_BUILTIN_PROVIDERS",
    "import_builtin_providers",
]
