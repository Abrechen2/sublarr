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
from datetime import UTC, datetime, timedelta
from typing import Optional

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
from providers.registry import PROVIDER_METADATA
from providers.search_coordinator import SearchCoordinatorMixin

logger = logging.getLogger(__name__)

# Provider registry — maps name to class
_PROVIDER_CLASSES: dict[str, type[SubtitleProvider]] = {}

# Singleton manager
_manager: Optional["ProviderManager"] = None


def register_provider(cls: type[SubtitleProvider]) -> type[SubtitleProvider]:
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


_provider_manager_lock = threading.Lock()


def get_provider_manager() -> "ProviderManager":
    """Get or create the singleton ProviderManager (thread-safe).

    When called inside a Flask app context, the result is stored in and
    retrieved from ``app.extensions["provider_manager"]`` — this lets tests
    inject a mock by writing to that key. Falls back to a module-level
    global when no app context is available (e.g. scheduler threads).
    """
    global _manager
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


class ProviderManager(SearchCoordinatorMixin):
    """Manages multiple subtitle providers with priority ordering and scoring."""

    def __init__(self):
        from config import get_settings

        self.settings = get_settings()
        self._providers: dict[str, SubtitleProvider] = {}
        self._rate_limits: dict[str, list[datetime]] = defaultdict(list)
        self._rate_limit_lock = threading.Lock()
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
        try:
            from providers import opensubtitles  # noqa: F401
        except ImportError as e:
            logger.debug("OpenSubtitles provider not available: %s", e)
        try:
            from providers import jimaku  # noqa: F401
        except ImportError as e:
            logger.debug("Jimaku provider not available: %s", e)
        try:
            from providers import animetosho  # noqa: F401
        except ImportError as e:
            logger.debug("AnimeTosho provider not available: %s", e)
        try:
            from providers import subdl  # noqa: F401
        except ImportError as e:
            logger.debug("SubDL provider not available: %s", e)
        try:
            from providers import subsdump  # noqa: F401
        except ImportError as e:
            logger.debug("SubsDump provider not available: %s", e)
        try:
            from providers import gestdown  # noqa: F401
        except ImportError as e:
            logger.debug("Gestdown provider not available: %s", e)
        try:
            from providers import podnapisi  # noqa: F401
        except ImportError as e:
            logger.debug("Podnapisi provider not available: %s", e)
        try:
            from providers import kitsunekko  # noqa: F401
        except ImportError as e:
            logger.debug("Kitsunekko provider not available: %s", e)
        try:
            from providers import napisy24  # noqa: F401
        except ImportError as e:
            logger.debug("Napisy24 provider not available: %s", e)
        try:
            from providers import titrari  # noqa: F401
        except ImportError as e:
            logger.debug("Titrari provider not available: %s", e)
        try:
            from providers import legendasdivx  # noqa: F401
        except ImportError as e:
            logger.debug("LegendasDivx provider not available: %s", e)
        try:
            from providers import subscene  # noqa: F401
        except ImportError as e:
            logger.debug("Subscene provider not available: %s", e)
        try:
            from providers import addic7ed  # noqa: F401
        except ImportError as e:
            logger.debug("Addic7ed provider not available: %s", e)
        try:
            from providers import tvsubtitles  # noqa: F401
        except ImportError as e:
            logger.debug("TVSubtitles provider not available: %s", e)
        try:
            from providers import turkcealtyazi  # noqa: F401
        except ImportError as e:
            logger.debug("Turkcealtyazi provider not available: %s", e)
        try:
            from providers import subsource  # noqa: F401
        except ImportError as e:
            logger.debug("Subsource provider not available: %s", e)
        try:
            from providers import subf2m  # noqa: F401
        except ImportError as e:
            logger.debug("Subf2m provider not available: %s", e)
        try:
            from providers import yifysubtitles  # noqa: F401
        except ImportError as e:
            logger.debug("YifySubtitles provider not available: %s", e)
        try:
            from providers import zimuku  # noqa: F401
        except ImportError as e:
            logger.debug("Zimuku provider not available: %s", e)
        try:
            from providers import betaseries  # noqa: F401
        except ImportError as e:
            logger.debug("BetaSeries provider not available: %s", e)
        try:
            from providers import titlovi  # noqa: F401
        except ImportError as e:
            logger.debug("Titlovi provider not available: %s", e)
        try:
            from providers import embedded  # noqa: F401
        except ImportError as e:
            logger.debug("Embedded subtitle provider not available: %s", e)

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
                    logger.warning(
                        "Provider %s initialized but session is None (likely missing API key)", name
                    )
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
                    logger.warning(
                        "Provider %s initialized but session is None (likely missing API key)", name
                    )
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

    def _get_provider_config(self, name: str) -> dict:
        """Get provider-specific config from settings or plugin DB config.

        For built-in providers, reads config from Pydantic Settings using
        the config_fields declared on the provider class. For plugins
        (is_plugin=True), reads from the plugin config DB table instead.
        """
        cls = _PROVIDER_CLASSES.get(name)
        if not cls:
            return {}

        config = {}

        if getattr(cls, "is_plugin", False):
            # Plugin providers: read config from DB
            try:
                from db.plugins import get_plugin_config

                plugin_config = get_plugin_config(name)
                for field in getattr(cls, "config_fields", []):
                    key = field["key"]
                    config[key] = plugin_config.get(key, field.get("default", ""))
            except Exception as e:
                logger.warning("Failed to read plugin config for %s: %s", name, e)
        else:
            # Built-in providers: read from Pydantic Settings
            for field in getattr(cls, "config_fields", []):
                key = field["key"]
                config[key] = getattr(self.settings, key, field.get("default", ""))

        # Map settings-level keys to constructor parameter names.
        # Built-in providers expect short param names (e.g. "api_key" not
        # "opensubtitles_api_key"), so strip the provider-name prefix.
        mapped_config = {}
        for key, value in config.items():
            # e.g. "opensubtitles_api_key" -> "api_key", "jimaku_api_key" -> "api_key"
            short_key = key
            prefix = f"{name}_"
            if key.startswith(prefix):
                short_key = key[len(prefix) :]
            mapped_config[short_key] = value

        # Strip whitespace from all credential values (prevent paste artifacts)
        for key in mapped_config:
            if isinstance(mapped_config[key], str):
                mapped_config[key] = mapped_config[key].strip()

        return mapped_config

    def _get_rate_limit(self, provider_name: str) -> tuple[int, int]:
        """Get rate limit for a provider: (max_requests, window_seconds).

        Prefers class attribute, falls back to registry, then (0, 0).
        """
        cls = _PROVIDER_CLASSES.get(provider_name)
        if cls:
            class_limit = getattr(cls, "rate_limit", (0, 0))
            if class_limit != (0, 0):
                return class_limit
        return PROVIDER_METADATA.get(provider_name, {}).get("rate_limit", (0, 0))

    def _compute_dynamic_timeout(self, provider_name: str, stats: dict) -> int | None:
        """Compute a dynamic timeout from provider stats (avg response time × multiplier + buffer).

        Returns None if dynamic timeouts are disabled or there are too few samples.
        Formula: max(min_s, min(avg_ms * multiplier / 1000 + buffer, max_s))
        """
        if not getattr(self.settings, "provider_dynamic_timeout_enabled", True):
            return None
        total = stats.get("total_searches", 0) or 0
        min_samples = getattr(self.settings, "provider_dynamic_timeout_min_samples", 5)
        if total < min_samples:
            return None
        avg_ms = stats.get("avg_response_time_ms", 0) or 0
        if avg_ms <= 0:
            return None
        multiplier = getattr(self.settings, "provider_dynamic_timeout_multiplier", 3.0)
        buffer = getattr(self.settings, "provider_dynamic_timeout_buffer_secs", 2.0)
        min_s = getattr(self.settings, "provider_dynamic_timeout_min_secs", 5)
        max_s = getattr(self.settings, "provider_dynamic_timeout_max_secs", 30)
        return int(max(min_s, min((avg_ms * multiplier / 1000) + buffer, max_s)))

    def _get_timeout(self, provider_name: str, all_stats: dict | None = None) -> int:
        """Get timeout for a provider (seconds).

        Priority:
        1. Dynamic timeout computed from historical avg_response_time_ms
        2. Class attribute (provider-specific hardcoded timeout)
        3. Registry (PROVIDER_METADATA)
        4. Global provider_search_timeout setting
        """
        # 1. Dynamic timeout from stats
        if all_stats and provider_name in all_stats:
            dynamic = self._compute_dynamic_timeout(provider_name, all_stats[provider_name])
            if dynamic:
                return dynamic
        # 2. Class attribute
        cls = _PROVIDER_CLASSES.get(provider_name)
        if cls:
            class_timeout = getattr(cls, "timeout", 0)
            if class_timeout > 0:
                return class_timeout
        # 3. Registry, 4. Global setting
        meta = PROVIDER_METADATA.get(provider_name, {})
        return meta.get("timeout", self.settings.provider_search_timeout)

    def _get_retries(self, provider_name: str) -> int:
        """Get retry count for a provider.

        Prefers class attribute, falls back to registry, then default 2.
        """
        cls = _PROVIDER_CLASSES.get(provider_name)
        if cls:
            class_retries = getattr(cls, "max_retries", -1)
            if class_retries >= 0:
                return class_retries
        return PROVIDER_METADATA.get(provider_name, {}).get("retries", 2)

    def _check_rate_limit(self, provider_name: str) -> bool:
        """Check if provider is within rate limit.

        Returns:
            True if request is allowed, False if rate limited
        """
        if not getattr(self.settings, "provider_rate_limit_enabled", True):
            return True

        max_requests, window_seconds = self._get_rate_limit(provider_name)
        if max_requests == 0 and window_seconds == 0:
            return True  # No rate limit configured
        with self._rate_limit_lock:
            now = datetime.now(UTC)
            timestamps = self._rate_limits[provider_name]

            # Remove old timestamps outside the window
            window = timedelta(seconds=window_seconds)
            timestamps[:] = [ts for ts in timestamps if now - ts < window]

            if len(timestamps) >= max_requests:
                logger.debug(
                    "Provider %s rate limited: %d/%d requests in %ds window",
                    provider_name,
                    len(timestamps),
                    max_requests,
                    window_seconds,
                )
                return False  # Rate limited

            # Record this request
            timestamps.append(now)
            return True

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

    def get_provider_status(self) -> list[dict]:
        """Get status of all providers (for API/UI) with priority, downloads, config_fields, and stats."""
        from db.providers import get_provider_download_stats, get_provider_stats

        # Build priority order (use current priority list from _init_providers)
        priority_str = getattr(
            self.settings, "provider_priorities", "animetosho,jimaku,opensubtitles,subdl"
        )
        priority_list = [p.strip() for p in priority_str.split(",") if p.strip()]

        # Get enabled set
        enabled_str = getattr(self.settings, "providers_enabled", "")
        if enabled_str:
            enabled_set = {p.strip() for p in enabled_str.split(",") if p.strip()}
        else:
            enabled_set = set(_PROVIDER_CLASSES.keys())

        # Download stats from DB (single batch query)
        download_stats = get_provider_download_stats()
        # Performance stats (single batch query — includes auto_disabled, disabled_until,
        # consecutive_failures, successful_downloads, total_searches, etc.)
        performance_stats = get_provider_stats()

        statuses = []
        for name, cls in _PROVIDER_CLASSES.items():
            priority = priority_list.index(name) if name in priority_list else len(priority_list)
            downloads = download_stats.get(name, {}).get("total", 0)
            config_fields = self._get_provider_config_fields(name)

            # Read all stats from the already-fetched batch (no extra per-provider queries)
            perf_stats = performance_stats.get(name, {})
            total_searches = perf_stats.get("total_searches", 0) or 0
            successful_downloads = perf_stats.get("successful_downloads", 0) or 0
            success_rate = successful_downloads / total_searches if total_searches > 0 else 0.0

            # auto_disabled is stored as int (0/1) in the ORM model; cast to bool.
            # Note: cooldown expiry side-effect (clearing the flag) runs on next actual
            # is_auto_disabled() call; for the status view, the batch value is sufficient.
            auto_disabled = bool(perf_stats.get("auto_disabled", 0))
            stats_dict = {
                "total_searches": perf_stats.get("total_searches", 0),
                "successful_downloads": perf_stats.get("successful_downloads", 0),
                "failed_downloads": perf_stats.get("failed_downloads", 0),
                "success_rate": success_rate,
                "avg_score": perf_stats.get("avg_score", 0),
                "consecutive_failures": perf_stats.get("consecutive_failures", 0),
                "last_success_at": perf_stats.get("last_success_at"),
                "last_failure_at": perf_stats.get("last_failure_at"),
                "avg_response_time_ms": perf_stats.get("avg_response_time_ms", 0) or 0,
                "last_response_time_ms": perf_stats.get("last_response_time_ms", 0) or 0,
                "auto_disabled": auto_disabled,
                "disabled_until": perf_stats.get("disabled_until", "") or "",
            }

            provider = self._providers.get(name)
            if provider:
                # Derive health from cached DB stats — no live HTTP requests.
                # Matches Bazarr's reactive approach: healthy until proven otherwise.
                consecutive_failures = perf_stats.get("consecutive_failures", 0) or 0
                if auto_disabled:
                    healthy, msg = False, "Auto-disabled"
                elif consecutive_failures >= 3:
                    healthy, msg = False, f"{consecutive_failures} consecutive failures"
                else:
                    healthy, msg = True, "OK"
                statuses.append(
                    {
                        "name": name,
                        "enabled": name in enabled_set,
                        "initialized": True,
                        "healthy": healthy,
                        "message": msg,
                        "priority": priority,
                        "downloads": downloads,
                        "config_fields": config_fields,
                        "stats": stats_dict,
                    }
                )
            else:
                statuses.append(
                    {
                        "name": name,
                        "enabled": name in enabled_set,
                        "initialized": False,
                        "healthy": False,
                        "message": "Not initialized",
                        "priority": priority,
                        "downloads": downloads,
                        "config_fields": config_fields,
                        "stats": stats_dict,
                    }
                )

        # Sort by priority
        statuses.sort(key=lambda s: s["priority"])
        return statuses

    @staticmethod
    def _get_provider_config_fields(name: str) -> list[dict]:
        """Return config field definitions for a provider (for dynamic UI forms).

        Reads from the provider class's config_fields attribute instead of
        a hardcoded map. Returns an empty list if the class has no config_fields.
        """
        cls = _PROVIDER_CLASSES.get(name)
        if cls:
            return getattr(cls, "config_fields", [])
        return []

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
