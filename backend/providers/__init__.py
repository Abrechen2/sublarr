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

import hashlib
import json
import logging
import os
import threading
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from concurrent.futures import TimeoutError as FutureTimeoutError
from datetime import UTC, datetime, timedelta
from typing import Optional

from circuit_breaker import CircuitBreaker
from forced_detection import classify_forced_result
from providers.base import (
    ProviderAuthError,
    ProviderRateLimitError,
    ProviderTimeoutError,  # noqa: F401 — re-exported for callers
    SubtitleFormat,
    SubtitleProvider,
    SubtitleResult,
    VideoQuery,
    compute_score,
)
from providers.registry import PROVIDER_METADATA


def _detect_format_from_content(content: bytes) -> SubtitleFormat:
    """Detect subtitle format by inspecting the first bytes of file content.

    Used when a provider doesn't include format metadata (e.g. OpenSubtitles
    returns filenames without extensions for some results).
    """
    # Strip UTF-8 BOM if present
    text_start = content[:512].lstrip(b"\xef\xbb\xbf")
    try:
        preview = text_start.decode("utf-8", errors="replace").strip()
    except (UnicodeDecodeError, ValueError):
        return SubtitleFormat.SRT
    # ASS/SSA files always begin with [Script Info]
    if preview.startswith("[Script Info]") or preview.lower().startswith("[v4"):
        return SubtitleFormat.ASS
    return SubtitleFormat.SRT


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


class ProviderManager:
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
            from providers import whisper_subgen  # noqa: F401
        except ImportError as e:
            logger.debug("WhisperSubgen provider not available: %s", e)
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

    @staticmethod
    def _get_cache_backend():
        """Get the app-level cache backend (Redis or memory), or None.

        Uses Flask's current_app to access the cache_backend. Returns None
        if called outside Flask context or if cache_backend is not configured.
        Never raises -- safe to call from any context.
        """
        try:
            from flask import current_app

            return getattr(current_app, "cache_backend", None)
        except (RuntimeError, ImportError):
            # Outside Flask app context or Flask not available
            return None

    @staticmethod
    def _deserialize_results(cached_data: list) -> list:
        """Deserialize a list of dicts into SubtitleResult objects."""
        results = []
        for r_data in cached_data:
            result = SubtitleResult(
                provider_name=r_data["provider_name"],
                subtitle_id=r_data["subtitle_id"],
                language=r_data["language"],
                format=SubtitleFormat(r_data.get("format", "unknown")),
                filename=r_data.get("filename", ""),
                download_url=r_data.get("download_url", ""),
                release_info=r_data.get("release_info", ""),
                hearing_impaired=r_data.get("hearing_impaired", False),
                forced=r_data.get("forced", False),
                score=r_data.get("score", 0),
                provider_data=r_data.get("provider_data", {}),
            )
            results.append(result)
        return results

    def _make_cache_key(
        self, query: VideoQuery, format_filter: SubtitleFormat | None = None
    ) -> str:
        """Generate a cache key for a query."""
        key_parts = [
            query.file_path or "",
            ",".join(sorted(query.languages)) if query.languages else "",
            format_filter.value if format_filter else "",
        ]
        key_str = "|".join(key_parts)
        return hashlib.md5(key_str.encode(), usedforsecurity=False).hexdigest()  # noqa: S324

    def _search_provider_with_retry(
        self, name: str, provider: SubtitleProvider, query: VideoQuery
    ) -> tuple[list[SubtitleResult], float]:
        """Search a single provider with retries.

        Returns:
            Tuple of (results list, elapsed_ms). elapsed_ms is 0 if no successful search.
        """
        import time as _time

        retries = self._get_retries(name)
        elapsed_ms = 0.0

        # Check if provider is initialized
        if hasattr(provider, "session") and provider.session is None:
            logger.warning("Provider %s not initialized (session is None), skipping search", name)
            return [], 0.0

        logger.debug(
            "Searching provider %s for: %s (languages: %s)",
            name,
            query.display_name,
            query.languages,
        )

        for attempt in range(retries + 1):
            try:
                start = _time.monotonic()
                results = provider.search(query)
                elapsed_ms = (_time.monotonic() - start) * 1000

                logger.info(
                    "Provider %s returned %d results in %.0fms (attempt %d/%d)",
                    name,
                    len(results),
                    elapsed_ms,
                    attempt + 1,
                    retries + 1,
                )
                if results:
                    logger.debug(
                        "Provider %s top result: %s (score: %d, format: %s)",
                        name,
                        results[0].filename,
                        results[0].score,
                        results[0].format.value,
                    )
                return results, elapsed_ms
            except ProviderAuthError as e:
                logger.error("Provider %s authentication failed: %s", name, e)
                return [], 0.0  # Don't retry auth errors
            except ProviderRateLimitError as e:
                logger.warning("Provider %s rate limit exceeded: %s", name, e)
                if attempt < retries:
                    # Wait a bit longer for rate limits
                    wait_time = 2**attempt  # Exponential backoff: 1s, 2s, 4s
                    logger.debug("Waiting %ds before retry...", wait_time)
                    _time.sleep(wait_time)
                else:
                    return [], 0.0  # Don't retry indefinitely for rate limits
            except Exception as e:
                if attempt < retries:
                    logger.debug(
                        "Provider %s search failed (attempt %d/%d), retrying: %s",
                        name,
                        attempt + 1,
                        retries + 1,
                        e,
                        exc_info=True,
                    )
                else:
                    logger.warning(
                        "Provider %s search failed after %d attempts: %s",
                        name,
                        retries + 1,
                        e,
                        exc_info=True,
                    )

        return [], 0.0

    def _check_auto_disable(self, name: str):
        """Check if a provider should be auto-disabled based on consecutive failures.

        Auto-disables when consecutive_failures >= 2x circuit_breaker_failure_threshold.
        """
        from db.providers import auto_disable_provider
        from db.providers import get_provider_stats as _get_stats

        stats = _get_stats(name)
        if not stats:
            return
        consecutive = stats.get("consecutive_failures", 0)
        threshold = self.settings.circuit_breaker_failure_threshold * 2
        if consecutive >= threshold:
            cooldown = getattr(self.settings, "provider_auto_disable_cooldown_minutes", 30)
            auto_disable_provider(name, cooldown_minutes=cooldown)

    def search(
        self,
        query: VideoQuery,
        format_filter: SubtitleFormat | None = None,
        min_score: int = 0,
        early_exit: bool = True,
    ) -> list[SubtitleResult]:
        """Search all providers in parallel and return scored, sorted results.

        Args:
            query: What to search for
            format_filter: Only return results of this format (e.g. ASS)
            min_score: Minimum score threshold
            early_exit: If True, stop searching when a perfect match (score >= 400) is found

        Returns:
            List of SubtitleResult sorted by score (highest first)
        """
        # Check cache first (two-tier: fast app cache, then persistent DB cache)
        cache_key = self._make_cache_key(query, format_filter)
        cache_ttl_minutes = getattr(self.settings, "provider_cache_ttl_minutes", 5)

        # Tier 1: Fast cache lookup (Redis or in-memory)
        app_cache_key = f"provider:combined:{cache_key}"
        cache_backend = self._get_cache_backend()
        if cache_backend:
            try:
                fast_cached = cache_backend.get(app_cache_key)
                if fast_cached:
                    try:
                        cached_data = json.loads(fast_cached)
                        cached_results = self._deserialize_results(cached_data)
                        logger.info("Returning %d results from fast cache", len(cached_results))
                        return cached_results
                    except Exception as e:
                        logger.debug("Failed to parse fast cached results: %s", e)
            except Exception as e:
                logger.debug("Fast cache lookup failed (non-blocking): %s", e)

        # Tier 2: Persistent DB cache lookup
        from db.providers import cache_provider_results, get_cached_results

        cached_json = get_cached_results(
            "combined", cache_key, format_filter.value if format_filter else None
        )
        if cached_json:
            try:
                cached_data = json.loads(cached_json)
                cached_results = self._deserialize_results(cached_data)
                logger.info("Returning %d cached results from DB", len(cached_results))
                # Backfill fast cache so next lookup is faster
                if cache_backend:
                    try:
                        cache_backend.set(
                            app_cache_key, cached_json, ttl_seconds=int(cache_ttl_minutes * 60)
                        )
                    except Exception as e:
                        logger.debug("Fast cache backfill failed (non-blocking): %s", e)
                return cached_results
            except Exception as e:
                logger.warning("Failed to parse cached results: %s", e)

        all_results: list[SubtitleResult] = []
        perfect_match_found = False

        # Parallel search with ThreadPoolExecutor
        from db.providers import (
            is_provider_auto_disabled,
            update_provider_stats,
        )

        # Batch-fetch provider stats for dynamic timeout computation (single DB query)
        _dyn_stats: dict = {}
        if getattr(self.settings, "provider_dynamic_timeout_enabled", True):
            try:
                from db.providers import get_all_provider_stats

                stats_list = get_all_provider_stats()
                _dyn_stats = {s["provider_name"]: s for s in stats_list if s.get("provider_name")}
            except Exception as e:
                logger.debug(
                    "Failed to fetch provider stats for dynamic timeout computation: %s", e
                )

        if not self._providers:
            return all_results

        with ThreadPoolExecutor(max_workers=len(self._providers)) as executor:
            futures = {}
            for name, provider in self._providers.items():
                # Check auto-disable status
                if is_provider_auto_disabled(name):
                    logger.debug("Skipping provider %s -- auto-disabled", name)
                    continue

                # Check circuit breaker
                cb = self._circuit_breakers.get(name)
                if cb and not cb.allow_request():
                    logger.debug("Skipping provider %s -- circuit breaker OPEN", name)
                    continue

                # Check rate limit
                if not self._check_rate_limit(name):
                    logger.debug("Skipping provider %s due to rate limit", name)
                    continue

                # Submit search task
                future = executor.submit(self._search_provider_with_retry, name, provider, query)
                futures[future] = name

            # Collect results as they complete
            # Use max timeout across all active providers + buffer
            active_names = {futures[f] for f in futures}
            max_timeout = (
                max(
                    (
                        self._get_timeout(n, _dyn_stats)
                        for n in self._providers
                        if n in active_names
                    ),
                    default=self.settings.provider_search_timeout,
                )
                + 3
            )
            for future in as_completed(futures, timeout=max_timeout):
                name = futures[future]
                try:
                    results, elapsed_ms = future.result()
                    all_results.extend(results)

                    # Update circuit breaker and stats
                    # NOTE: empty results are NOT a failure — the provider responded
                    # correctly, it just found nothing for this query.
                    cb = self._circuit_breakers.get(name)
                    if cb:
                        cb.record_success()
                    update_provider_stats(name, success=True, score=0, response_time_ms=elapsed_ms)

                    # Check for perfect match (early exit)
                    if early_exit and results:
                        # Score results immediately to check for perfect match
                        for result in results:
                            compute_score(result, query)
                            if result.score >= 400:
                                logger.info(
                                    "Perfect match found (score=%d) from provider %s, stopping search",
                                    result.score,
                                    name,
                                )
                                perfect_match_found = True
                                break

                        if perfect_match_found:
                            # Cancel remaining futures (they'll complete but we won't wait)
                            break

                except FutureTimeoutError:
                    logger.warning("Provider %s search timed out", name)
                    cb = self._circuit_breakers.get(name)
                    if cb:
                        cb.record_failure()
                    update_provider_stats(name, success=False, score=0)
                    self._check_auto_disable(name)
                except Exception as e:
                    logger.warning("Provider %s search failed: %s", name, e)
                    cb = self._circuit_breakers.get(name)
                    if cb:
                        cb.record_failure()
                    update_provider_stats(name, success=False, score=0)
                    self._check_auto_disable(name)

        # If early exit was triggered, we may have incomplete results, but that's OK
        # Score all results
        for result in all_results:
            if result.score == 0:  # Only score if not already scored
                compute_score(result, query)

        # Post-search forced classification: use forced_detection to classify
        # results from providers without native forced support (e.g., AnimeTosho,
        # Jimaku, SubDL). Single-pass: search once, classify results.
        for result in all_results:
            if not result.forced:
                forced_type = classify_forced_result(
                    result.filename,
                    result.provider_data if hasattr(result, "provider_data") else None,
                )
                if forced_type in ("forced", "signs"):
                    result.forced = True

        # Post-filter: if query requests forced_only, remove non-forced results
        if query.forced_only:
            all_results = [r for r in all_results if r.forced]

        # Filter by language (if query specifies languages)
        if query.languages:
            all_results = [r for r in all_results if r.language in query.languages]

        # Filter by format — include UNKNOWN since some providers omit format metadata
        if format_filter:
            all_results = [
                r
                for r in all_results
                if r.format == format_filter or r.format == SubtitleFormat.UNKNOWN
            ]

        # Filter by min score
        if min_score > 0:
            all_results = [r for r in all_results if r.score >= min_score]

        # Filter blacklisted subtitles
        from db.blacklist import is_blacklisted

        all_results = [r for r in all_results if not is_blacklisted(r.provider_name, r.subtitle_id)]

        # Release group filtering: exclude blocked groups, boost preferred groups
        from config import get_settings

        settings = get_settings()
        _exclude = [
            g.strip().lower() for g in settings.release_group_exclude.split(",") if g.strip()
        ]
        _prefer = [g.strip().lower() for g in settings.release_group_prefer.split(",") if g.strip()]

        if _exclude:
            before = len(all_results)
            all_results = [
                r for r in all_results if not any(g in r.release_info.lower() for g in _exclude)
            ]
            filtered = before - len(all_results)
            if filtered:
                logger.debug(
                    "Release group filter: excluded %d result(s) matching %s", filtered, _exclude
                )

        if _prefer:
            bonus = settings.release_group_prefer_bonus
            for r in all_results:
                if any(g in r.release_info.lower() for g in _prefer):
                    r.score += bonus
                    r.matches.add("release_group_prefer")

        # Sort by format preference (ASS first), then by score descending
        all_results.sort(
            key=lambda r: (
                0 if r.format == SubtitleFormat.ASS else 1,  # ASS first
                -r.score,  # Then by score descending
            )
        )

        # Cache results in both tiers
        try:
            cache_data = [
                {
                    "provider_name": r.provider_name,
                    "subtitle_id": r.subtitle_id,
                    "language": r.language,
                    "format": r.format.value,
                    "filename": r.filename,
                    "download_url": r.download_url,
                    "release_info": r.release_info,
                    "hearing_impaired": r.hearing_impaired,
                    "forced": r.forced,
                    "score": r.score,
                    "provider_data": r.provider_data,
                }
                for r in all_results
            ]
            cache_json = json.dumps(cache_data)
            # Tier 1: Fast cache (Redis or in-memory)
            if cache_backend:
                try:
                    cache_backend.set(
                        app_cache_key, cache_json, ttl_seconds=int(cache_ttl_minutes * 60)
                    )
                except Exception as e:
                    logger.debug("Fast cache write failed (non-blocking): %s", e)
            # Tier 2: Persistent DB cache (audit trail + UI stats)
            cache_provider_results(
                "combined", cache_key, cache_json, ttl_hours=cache_ttl_minutes / 60
            )
        except Exception as e:
            logger.debug("Failed to cache results: %s", e)

        return all_results

    def search_with_fallback(
        self,
        query: VideoQuery,
        format_filter: SubtitleFormat | None = None,
        min_score: int = 0,
        early_exit: bool = True,
    ) -> list[SubtitleResult]:
        """Search providers with fallback to embedded subtitles.

        Args:
            query: What to search for
            format_filter: Only return results of this format (e.g. ASS)
            min_score: Minimum score threshold
            early_exit: If True, stop searching when a perfect match is found

        Returns:
            List of SubtitleResult sorted by score (highest first)
        """
        return self.search(
            query, format_filter=format_filter, min_score=min_score, early_exit=early_exit
        )

    def download(self, result: SubtitleResult) -> bytes | None:
        """Download a subtitle from its provider.

        Args:
            result: A SubtitleResult from search()

        Returns:
            Raw subtitle file content, or None on failure
        """
        provider = self._providers.get(result.provider_name)
        if not provider:
            logger.error("Provider %s not available for download", result.provider_name)
            return None

        # Check rate limit before download
        if not self._check_rate_limit(result.provider_name):
            logger.debug(
                "Skipping download from provider %s due to rate limit", result.provider_name
            )
            return None

        try:
            content = provider.download(result)
            result.content = content
            # Rate limit tracking is already updated by _check_rate_limit() above
            return content
        except Exception as e:
            logger.error("Download from %s failed: %s", result.provider_name, e)
            # On failure, we should still track the rate limit attempt
            # The timestamp was already added by _check_rate_limit(), so we don't need to do anything
            return None

    def search_and_download_best(
        self,
        query: VideoQuery,
        format_filter: SubtitleFormat | None = None,
        min_score: int = 0,
    ) -> SubtitleResult | None:
        """Convenience: search with fallback, pick best, download it.

        Returns:
            SubtitleResult with content populated, or None
        """
        results = self.search_with_fallback(query, format_filter=format_filter, min_score=min_score)
        if not results:
            return None

        # Try results in order until one downloads successfully
        for result in results:
            # Track search attempt for stats
            from db.providers import update_provider_stats

            try:
                content = self.download(result)
                if content is not None:  # Empty bytes for embedded is OK
                    # Record successful download
                    update_provider_stats(result.provider_name, success=True, score=result.score)
                    # Trigger auto re-ranking (throttled to once/hour)
                    try:
                        from providers.reranker import apply_auto_reranking

                        apply_auto_reranking()
                    except Exception as _rr_err:
                        logger.debug("Re-ranking trigger skipped: %s", _rr_err)
                    return result
                else:
                    # Record failed download
                    update_provider_stats(result.provider_name, success=False, score=0)
            except Exception as e:
                logger.warning("Download failed for %s: %s", result.subtitle_id, e)
                update_provider_stats(result.provider_name, success=False, score=0)

        return None

    def save_subtitle(self, result: SubtitleResult, output_path: str) -> str:
        """Save a downloaded subtitle to disk.

        Args:
            result: SubtitleResult with content populated
            output_path: Base path (without extension — extension from format)

        Returns:
            Path to saved file

        Raises:
            ValueError: If result has no content
            OSError: If directory creation or file write fails
            RuntimeError: If disk space is insufficient
        """
        if not result.content:
            raise ValueError("SubtitleResult has no content (download first)")

        # Determine extension — detect from content if format is unknown
        if result.format == SubtitleFormat.UNKNOWN and result.content:
            result.format = _detect_format_from_content(result.content)
        ext = result.format.value if result.format != SubtitleFormat.UNKNOWN else "srt"
        if not output_path.endswith(f".{ext}"):
            # If output_path already has an extension, replace it
            base, _ = os.path.splitext(output_path)
            output_path = f"{base}.{ext}"

        # Check disk space before writing (defensive guard)
        try:
            import shutil

            stat = shutil.disk_usage(os.path.dirname(output_path))
            free_mb = stat.free / (1024 * 1024)
            MIN_FREE_SPACE_MB = 100  # Same as translator.py
            if free_mb < MIN_FREE_SPACE_MB:
                raise RuntimeError(
                    f"Insufficient disk space: {free_mb:.0f}MB free, "
                    f"need at least {MIN_FREE_SPACE_MB}MB"
                )
        except OSError as e:
            logger.warning("Failed to check disk space for %s: %s", output_path, e)
            # Continue anyway - disk space check is best-effort

        # Validate output path is within allowed media directory (path traversal guard)
        try:
            from config import get_settings as _get_settings
            from security_utils import is_safe_path as _is_safe_path

            _settings = _get_settings()
            _media_path = getattr(_settings, "media_path", "/media")
            if not _is_safe_path(output_path, _media_path):
                raise ValueError(
                    f"save_subtitle: output_path {output_path!r} is outside media_path"
                )
        except ValueError:
            raise
        except Exception as e:
            logger.debug("Path validation skipped (config unavailable, likely in tests): %s", e)

        # Sanitize subtitle content before writing to disk
        try:
            from subtitle_sanitizer import sanitize_subtitle

            result.content = sanitize_subtitle(result.content, result.format)
        except ValueError as e:
            raise RuntimeError(f"Subtitle failed security check: {e}") from e
        except Exception as e:
            logger.warning("Subtitle sanitization failed (skipping): %s", e)
            # Non-fatal: log and continue on unexpected errors to preserve availability

        # Duplicate detection: skip write if identical content already exists on disk
        try:
            from config import get_settings as _get_settings_dedup
            from db.repositories.cleanup import CleanupRepository
            from dedup_engine import compute_content_hash_from_bytes
            from error_handler import DuplicateSubtitleError

            _dedup_settings = _get_settings_dedup()
            if getattr(_dedup_settings, "dedup_on_download", True):
                content_hash = compute_content_hash_from_bytes(result.content)
                _output_dir = os.path.dirname(os.path.abspath(output_path))

                repo = CleanupRepository()
                matches = repo.find_by_content_hash(content_hash)
                stale_paths = []
                duplicate_path = None

                for match in matches:
                    match_path = match["file_path"]
                    if not os.path.isfile(match_path):
                        stale_paths.append(match_path)
                        continue
                    if os.path.dirname(os.path.abspath(match_path)) == _output_dir:
                        duplicate_path = match_path
                        break

                if stale_paths:
                    repo.delete_hashes_by_paths(stale_paths)
                    logger.debug("Cleaned %d stale hash entries", len(stale_paths))

                if duplicate_path:
                    logger.info(
                        "Duplicate subtitle skipped: hash %s already at %s",
                        content_hash[:12],
                        duplicate_path,
                    )
                    raise DuplicateSubtitleError(content_hash, duplicate_path, output_path)
        except DuplicateSubtitleError:
            raise
        except Exception as e:
            logger.debug("Dedup check skipped: %s", e)

        # Create directory with error handling
        try:
            dir_path = os.path.dirname(output_path)
            if dir_path:  # Only create if there's a directory component
                os.makedirs(dir_path, exist_ok=True)
        except OSError as e:
            logger.error("Failed to create directory for %s: %s", output_path, e)
            raise RuntimeError(f"Cannot create directory for subtitle: {e}") from e

        # Write file with error handling
        try:
            with open(output_path, "wb") as f:
                f.write(result.content)
        except OSError as e:
            logger.error("Failed to write subtitle to %s: %s", output_path, e)
            raise RuntimeError(f"Cannot write subtitle file: {e}") from e

        # Register hash in dedup DB after successful write
        try:
            from db.repositories.cleanup import CleanupRepository as CleanupRepo
            from dedup_engine import compute_content_hash_from_bytes as _chfb

            _hash = _chfb(result.content)
            _ext = result.format.value if result.format.value != "unknown" else "srt"
            CleanupRepo().upsert_hash(
                file_path=output_path,
                content_hash=_hash,
                file_size=len(result.content),
                format=_ext,
                language=result.language,
            )
        except Exception as e:
            logger.debug("Failed to register subtitle hash after write: %s", e)

        logger.info(
            "Saved subtitle: %s (%s, %s, score=%d)",
            output_path,
            result.provider_name,
            result.language,
            result.score,
        )

        # Fire subtitle_downloaded event for post-processing hooks
        try:
            from events import emit_event

            emit_event(
                "subtitle_downloaded",
                {
                    "subtitle_path": output_path,
                    "provider_name": result.provider_name or "",
                    "language": result.language or "",
                    "format": result.format.value if result.format else "",
                    "score": result.score or 0,
                },
            )
        except Exception as _ev_err:
            logger.debug("subtitle_downloaded event skipped: %s", _ev_err)

        return output_path

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
