"""Subtitle provider system — search and download subtitles from multiple sources.

The ProviderManager orchestrates searches across enabled providers,
scores results, and returns the best match.

Two-tier caching:
- Fast layer: app.cache_backend (Redis or in-memory) for sub-millisecond lookups
- Persistent layer: DB provider_cache table for audit trail and UI stats

Usage:
    from providers import get_provider_manager

    manager = get_provider_manager()
    results = manager.search(query)
    if results:
        content = manager.download(results[0])
"""

import logging
import threading
from collections import defaultdict
from datetime import datetime

from circuit_breaker import CircuitBreaker
from providers.base import (
    ProviderAuthError,  # noqa: F401 — re-exported for callers
    ProviderRateLimitError,  # noqa: F401 — re-exported for callers
    ProviderTimeoutError,  # noqa: F401 — re-exported for callers
    SubtitleFormat,
    SubtitleProvider,
    SubtitleResult,
    VideoQuery,
    compute_score,  # noqa: F401 — re-exported for callers
)
from providers.download_manager import _stream_download  # noqa: F401 — re-exported for providers
from providers.format_validator import (  # noqa: F401 — re-exported for callers
    _validate_subtitle_content,
)
from providers.manager_config_mixin import ConfigResolvingMixin
from providers.manager_status_mixin import StatusReportingMixin
from providers.registry import (  # noqa: F401 — _PROVIDER_CLASSES, _BUILTIN_PROVIDERS, register_provider re-exported
    _BUILTIN_PROVIDERS,
    _PROVIDER_CLASSES,
    PROVIDER_METADATA,
    import_builtin_providers,
    register_provider,
)
from providers.search_coordinator import SearchCoordinatorMixin

logger = logging.getLogger(__name__)

# Flask-context singleton — re-exported via this module for backwards compatibility.
from providers.manager_singleton import (  # noqa: E402, F401
    get_provider_manager,
    invalidate_manager,
    update_manager_providers,
)


class ProviderManager(SearchCoordinatorMixin, ConfigResolvingMixin, StatusReportingMixin):
    """Manages multiple subtitle providers with priority ordering and scoring."""

    def __init__(self):
        from config import get_settings

        self.settings = get_settings()
        self._providers: dict[str, SubtitleProvider] = {}
        self._rate_limits: dict[str, list[datetime]] = defaultdict(list)
        self._rate_limit_lock = threading.Lock()
        self._server_rate_limit_until: dict[str, float] = {}
        self._circuit_breakers: dict[str, CircuitBreaker] = {}
        self._init_providers()

    def _load_plugins(self):
        """Load plugins from the plugin manager (if available).

        Called after built-in providers are registered. Plugin providers
        are discovered from the plugins directory and registered into
        _PROVIDER_CLASSES with is_plugin=True.
        """
        try:
            from providers.plugins import get_plugin_manager

            manager = get_plugin_manager()
            if manager:
                loaded, errors = manager.discover()
                if loaded:
                    logger.info("Loaded %d plugin providers: %s", len(loaded), loaded)
                if errors:
                    for err in errors:
                        logger.warning("Plugin load error: %s -- %s", err["file"], err["error"])
        except ImportError:
            logger.debug("Plugin system not available")
        except Exception as e:
            logger.debug("Plugin loading skipped: %s", e)

    def _init_providers(self):
        """Initialize enabled providers based on config."""
        # Import providers to trigger registration
        import_builtin_providers()

        # Load plugin providers (from plugins directory)
        self._load_plugins()

        # Get enabled providers
        enabled_str = getattr(self.settings, "providers_enabled", "")
        if enabled_str:
            enabled_set = {p.strip() for p in enabled_str.split(",") if p.strip()}
        else:
            # Default: enable all registered providers
            enabled_set = set(_PROVIDER_CLASSES.keys())

        # Get priority order from config
        priority_str = getattr(
            self.settings, "provider_priorities", "animetosho,jimaku,opensubtitles,subdl"
        )
        manual_priority_list = [p.strip() for p in priority_str.split(",") if p.strip()]

        # Auto-prioritize based on success rate if enabled
        if getattr(self.settings, "provider_auto_prioritize", True):
            from db.providers import get_provider_stats

            # Batch fetch all provider stats in a single query (avoids N×2 DB hits)
            all_stats = get_provider_stats()  # returns {name: stats_dict}

            # Compute success rates from batch data (no extra per-provider queries)
            provider_success_rates = {}
            for name in enabled_set:
                if name in _PROVIDER_CLASSES:
                    stats = all_stats.get(name, {})
                    if (
                        stats and stats.get("total_searches", 0) >= 10
                    ):  # Minimum 10 searches for auto-prioritization
                        total = stats.get("total_searches", 0) or 1
                        success_rate = (stats.get("successful_downloads", 0) or 0) / total
                        provider_success_rates[name] = success_rate

            # Sort by success rate (descending), then by manual priority
            if provider_success_rates:
                # Create priority list: high success rate first, then manual priority
                sorted_by_success = sorted(
                    provider_success_rates.items(),
                    key=lambda x: (
                        -x[1],
                        manual_priority_list.index(x[0]) if x[0] in manual_priority_list else 999,
                    ),
                )
                priority_list = [name for name, _ in sorted_by_success]

                # Add providers not in stats (new providers) at the end, in manual priority order
                for name in manual_priority_list:
                    if name in enabled_set and name not in priority_list:
                        priority_list.append(name)

                # Add any remaining enabled providers
                for name in enabled_set:
                    if name not in priority_list and name in _PROVIDER_CLASSES:
                        priority_list.append(name)

                logger.info("Auto-prioritized providers by success rate: %s", priority_list)
            else:
                # Not enough stats, use manual priority
                priority_list = manual_priority_list
                # Add any enabled providers not in manual priority list
                for name in enabled_set:
                    if name not in priority_list and name in _PROVIDER_CLASSES:
                        priority_list.append(name)
        else:
            # Manual priority only
            priority_list = manual_priority_list
            # Add any enabled providers not in priority list
            for name in enabled_set:
                if name not in priority_list and name in _PROVIDER_CLASSES:
                    priority_list.append(name)

        # Initialize providers in priority order
        from db.providers import is_provider_auto_disabled

        for name in priority_list:
            if name not in _PROVIDER_CLASSES:
                logger.debug("Provider %s not found in registry", name)
                continue
            if name not in enabled_set:
                logger.debug("Provider %s not in enabled set", name)
                continue
            if is_provider_auto_disabled(name):
                logger.info("Provider %s is auto-disabled, skipping initialization", name)
                continue

            try:
                config = self._get_provider_config(name)
                logger.debug(
                    "Initializing provider %s with config keys: %s", name, list(config.keys())
                )
                provider = _PROVIDER_CLASSES[name](**config)
                provider.initialize()

                # Check if provider was actually initialized
                if hasattr(provider, "session") and provider.session is None:
                    # INFO, not WARNING: the provider has already logged WHY it
                    # disabled itself, so this line is a duplicate for an expected
                    # state. Emitting ~one WARNING per unconfigured provider on
                    # every startup is what made `grep WARNING` worthless on logs
                    # users send.
                    logger.info("Provider %s not active (no credentials configured)", name)
                else:
                    self._providers[name] = provider
                    self._circuit_breakers[name] = CircuitBreaker(
                        name=name,
                        failure_threshold=self.settings.circuit_breaker_failure_threshold,
                        cooldown_seconds=self.settings.circuit_breaker_cooldown_seconds,
                    )
                    logger.info("Provider initialized successfully: %s", name)
            except Exception as e:
                logger.error("Failed to initialize provider %s: %s", name, e, exc_info=True)

        # Add any enabled providers not in priority list
        for name in enabled_set:
            if name in self._providers:
                continue
            if name not in _PROVIDER_CLASSES:
                logger.debug("Provider %s not found in registry (fallback)", name)
                continue
            try:
                config = self._get_provider_config(name)
                logger.debug(
                    "Initializing provider %s (fallback) with config keys: %s",
                    name,
                    list(config.keys()),
                )
                provider = _PROVIDER_CLASSES[name](**config)
                provider.initialize()

                # Check if provider was actually initialized
                if hasattr(provider, "session") and provider.session is None:
                    # INFO, not WARNING: the provider has already logged WHY it
                    # disabled itself, so this line is a duplicate for an expected
                    # state. Emitting ~one WARNING per unconfigured provider on
                    # every startup is what made `grep WARNING` worthless on logs
                    # users send.
                    logger.info("Provider %s not active (no credentials configured)", name)
                else:
                    self._providers[name] = provider
                    self._circuit_breakers[name] = CircuitBreaker(
                        name=name,
                        failure_threshold=self.settings.circuit_breaker_failure_threshold,
                        cooldown_seconds=self.settings.circuit_breaker_cooldown_seconds,
                    )
                    logger.info("Provider initialized successfully (fallback): %s", name)
            except Exception as e:
                logger.error(
                    "Failed to initialize provider %s (fallback): %s", name, e, exc_info=True
                )

        if not self._providers:
            logger.warning(
                "No providers were successfully initialized! Check API keys and configuration."
            )
        else:
            logger.info(
                "Active providers (%d): %s", len(self._providers), list(self._providers.keys())
            )

    def download(self, result: SubtitleResult) -> bytes | None:
        """Download a subtitle from its provider.

        Args:
            result: A SubtitleResult from search()

        Returns:
            Raw subtitle file content, or None on failure
        """
        from providers.download_manager import download_subtitle

        return download_subtitle(
            providers=self._providers,
            circuit_breakers=self._circuit_breakers,
            rate_limit_checker=self._check_rate_limit,
            result=result,
        )

    def search_and_download_best(
        self,
        query: VideoQuery,
        format_filter: SubtitleFormat | None = None,
        min_score: int = 0,
        must_contain: list[str] | None = None,
        must_not_contain: list[str] | None = None,
    ) -> SubtitleResult | None:
        """Convenience: search with fallback, pick best, download it.

        Returns:
            SubtitleResult with content populated, or None
        """
        from db.providers import update_provider_stats
        from providers.download_manager import search_and_download_best as _sad_best

        return _sad_best(
            search_fn=self.search_with_fallback,
            download_fn=self.download,
            update_stats_fn=update_provider_stats,
            query=query,
            format_filter=format_filter,
            min_score=min_score,
            must_contain=must_contain,
            must_not_contain=must_not_contain,
        )

    def save_subtitle(
        self, result: SubtitleResult, output_path: str, series_id: int | None = None
    ) -> str:
        """Save a downloaded subtitle to disk.

        Args:
            result: SubtitleResult with content populated
            output_path: Base path (without extension — extension from format)
            series_id: Sonarr series ID, used to apply per-series pipeline overrides.
                       Pass None for movies or when no series context is available.

        Returns:
            Path to saved file

        Raises:
            ValueError: If result has no content
            OSError: If directory creation or file write fails
            RuntimeError: If disk space is insufficient
        """
        from providers.download_manager import save_subtitle as _save

        return _save(result, output_path, series_id=series_id)

    def get_provider(self, name: str) -> "SubtitleProvider | None":
        """Return an active provider instance by name, or None if not found."""
        return self._providers.get(name)

    def shutdown(self):
        """Terminate all providers and clear fast cache."""
        # Clear fast cache for provider results
        cache_backend = self._get_cache_backend()
        if cache_backend:
            try:
                cache_backend.clear(prefix="provider:")
            except Exception as e:
                logger.debug("Failed to clear fast cache on shutdown: %s", e)

        for name, provider in self._providers.items():
            try:
                provider.terminate()
            except Exception as e:
                logger.warning("Error terminating provider %s: %s", name, e)
        self._providers.clear()

    def update_providers(self, new_enabled_str: str) -> None:
        """Selectively add/remove providers without reinitializing unaffected ones.

        Use instead of invalidate_manager() when only providers_enabled changes.
        Providers that remain enabled keep their existing instances — no health
        checks re-run, no unnecessary network traffic.
        """
        from config import get_settings as _get_settings

        self.settings = _get_settings()

        if new_enabled_str:
            new_enabled_set = {p.strip() for p in new_enabled_str.split(",") if p.strip()}
        else:
            new_enabled_set = set(_PROVIDER_CLASSES.keys())

        current_names = set(self._providers.keys())

        # Remove providers no longer in the enabled set
        for name in current_names - new_enabled_set:
            provider = self._providers.pop(name, None)
            self._circuit_breakers.pop(name, None)
            if provider:
                try:
                    provider.terminate()
                except Exception as e:
                    logger.debug(
                        "Provider %s terminate() raised during update_providers: %s", name, e
                    )
            logger.info("Provider %s disabled (removed from pool)", name)

        # Add providers newly added to the enabled set
        for name in new_enabled_set - current_names:
            if name not in _PROVIDER_CLASSES:
                continue
            try:
                config = self._get_provider_config(name)
                provider = _PROVIDER_CLASSES[name](**config)
                provider.initialize()
                if hasattr(provider, "session") and provider.session is None:
                    logger.warning(
                        "Provider %s: session is None (likely missing credentials)", name
                    )
                else:
                    self._providers[name] = provider
                    self._circuit_breakers[name] = CircuitBreaker(
                        name=name,
                        failure_threshold=self.settings.circuit_breaker_failure_threshold,
                        cooldown_seconds=self.settings.circuit_breaker_cooldown_seconds,
                    )
                    logger.info("Provider %s enabled (added to pool)", name)
            except Exception as e:
                logger.error("Failed to initialize provider %s: %s", name, e)
