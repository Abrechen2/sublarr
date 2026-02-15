"""Subtitle provider system — search and download subtitles from multiple sources.

The ProviderManager orchestrates searches across enabled providers,
scores results, and returns the best match.

Usage:
    from providers import get_provider_manager

    manager = get_provider_manager()
    results = manager.search(query)
    if results:
        content = manager.download(results[0])
"""

import os
import logging
import hashlib
import json
from typing import Optional
from datetime import datetime, timedelta
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError as FutureTimeoutError

from providers.base import (
    SubtitleProvider,
    SubtitleResult,
    SubtitleFormat,
    VideoQuery,
    compute_score,
    ProviderAuthError,
    ProviderRateLimitError,
    ProviderTimeoutError,
)
from circuit_breaker import CircuitBreaker

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
            cls.name, _PROVIDER_CLASSES[cls.name].__name__, cls.__name__,
        )
        return cls
    _PROVIDER_CLASSES[cls.name] = cls
    return cls


def get_provider_manager() -> "ProviderManager":
    """Get or create the singleton ProviderManager."""
    global _manager
    if _manager is None:
        _manager = ProviderManager()
    return _manager


def invalidate_manager():
    """Reset the manager (call after config changes)."""
    global _manager
    if _manager:
        _manager.shutdown()
    _manager = None


class ProviderManager:
    """Manages multiple subtitle providers with priority ordering and scoring."""

    # Provider-specific rate limits: (max_requests, window_seconds)
    PROVIDER_RATE_LIMITS = {
        "opensubtitles": (40, 10),  # 40 requests per 10 seconds
        "jimaku": (100, 60),         # 100 requests per 60 seconds
        "animetosho": (50, 30),      # 50 requests per 30 seconds
        "subdl": (30, 10),           # 30 requests per 10 seconds
    }

    # Provider-specific timeouts (seconds)
    PROVIDER_TIMEOUTS = {
        "animetosho": 20,
        "opensubtitles": 15,
        "jimaku": 30,
        "subdl": 15,
    }

    # Provider-specific retry counts
    PROVIDER_RETRIES = {
        "animetosho": 2,
        "opensubtitles": 3,
        "jimaku": 2,
        "subdl": 2,
    }

    def __init__(self):
        from config import get_settings
        self.settings = get_settings()
        self._providers: dict[str, SubtitleProvider] = {}
        self._rate_limits: dict[str, list[datetime]] = defaultdict(list)
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
        priority_str = getattr(self.settings, "provider_priorities", "animetosho,jimaku,opensubtitles,subdl")
        manual_priority_list = [p.strip() for p in priority_str.split(",") if p.strip()]

        # Auto-prioritize based on success rate if enabled
        if getattr(self.settings, "provider_auto_prioritize", True):
            from db.providers import get_provider_stats, get_provider_success_rate
            
            # Get stats for all enabled providers
            provider_success_rates = {}
            for name in enabled_set:
                if name in _PROVIDER_CLASSES:
                    stats = get_provider_stats(name)
                    if stats and stats.get("total_searches", 0) >= 10:  # Minimum 10 searches for auto-prioritization
                        success_rate = get_provider_success_rate(name)
                        provider_success_rates[name] = success_rate
            
            # Sort by success rate (descending), then by manual priority
            if provider_success_rates:
                # Create priority list: high success rate first, then manual priority
                sorted_by_success = sorted(
                    provider_success_rates.items(),
                    key=lambda x: (-x[1], manual_priority_list.index(x[0]) if x[0] in manual_priority_list else 999)
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
                logger.debug("Initializing provider %s with config keys: %s", name, list(config.keys()))
                provider = _PROVIDER_CLASSES[name](**config)
                provider.initialize()
                
                # Check if provider was actually initialized
                if hasattr(provider, 'session') and provider.session is None:
                    logger.warning("Provider %s initialized but session is None (likely missing API key)", name)
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
                logger.debug("Initializing provider %s (fallback) with config keys: %s", name, list(config.keys()))
                provider = _PROVIDER_CLASSES[name](**config)
                provider.initialize()
                
                # Check if provider was actually initialized
                if hasattr(provider, 'session') and provider.session is None:
                    logger.warning("Provider %s initialized but session is None (likely missing API key)", name)
                else:
                    self._providers[name] = provider
                    self._circuit_breakers[name] = CircuitBreaker(
                        name=name,
                        failure_threshold=self.settings.circuit_breaker_failure_threshold,
                        cooldown_seconds=self.settings.circuit_breaker_cooldown_seconds,
                    )
                    logger.info("Provider initialized successfully (fallback): %s", name)
            except Exception as e:
                logger.error("Failed to initialize provider %s (fallback): %s", name, e, exc_info=True)

        if not self._providers:
            logger.warning("No providers were successfully initialized! Check API keys and configuration.")
        else:
            logger.info("Active providers (%d): %s", len(self._providers), list(self._providers.keys()))

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
                short_key = key[len(prefix):]
            mapped_config[short_key] = value

        # Strip whitespace from all credential values (prevent paste artifacts)
        for key in mapped_config:
            if isinstance(mapped_config[key], str):
                mapped_config[key] = mapped_config[key].strip()

        return mapped_config

    def _get_rate_limit(self, provider_name: str) -> tuple[int, int]:
        """Get rate limit for a provider: (max_requests, window_seconds).

        Prefers class attribute, falls back to hardcoded dict, then (0, 0).
        """
        cls = _PROVIDER_CLASSES.get(provider_name)
        if cls:
            class_limit = getattr(cls, "rate_limit", (0, 0))
            if class_limit != (0, 0):
                return class_limit
        return self.PROVIDER_RATE_LIMITS.get(provider_name, (0, 0))

    def _get_timeout(self, provider_name: str) -> int:
        """Get timeout for a provider (seconds).

        Prefers class attribute, falls back to hardcoded dict, then global setting.
        """
        cls = _PROVIDER_CLASSES.get(provider_name)
        if cls:
            class_timeout = getattr(cls, "timeout", 0)
            if class_timeout > 0:
                return class_timeout
        return self.PROVIDER_TIMEOUTS.get(provider_name, self.settings.provider_search_timeout)

    def _get_retries(self, provider_name: str) -> int:
        """Get retry count for a provider.

        Prefers class attribute, falls back to hardcoded dict, then default 2.
        """
        cls = _PROVIDER_CLASSES.get(provider_name)
        if cls:
            class_retries = getattr(cls, "max_retries", -1)
            if class_retries >= 0:
                return class_retries
        return self.PROVIDER_RETRIES.get(provider_name, 2)

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
        now = datetime.utcnow()
        timestamps = self._rate_limits[provider_name]

        # Remove old timestamps outside the window
        window = timedelta(seconds=window_seconds)
        timestamps[:] = [ts for ts in timestamps if now - ts < window]

        if len(timestamps) >= max_requests:
            logger.debug("Provider %s rate limited: %d/%d requests in %ds window",
                        provider_name, len(timestamps), max_requests, window_seconds)
            return False  # Rate limited

        # Record this request
        timestamps.append(now)
        return True

    def _make_cache_key(self, query: VideoQuery, format_filter: Optional[SubtitleFormat] = None) -> str:
        """Generate a cache key for a query."""
        key_parts = [
            query.file_path or "",
            ",".join(sorted(query.languages)) if query.languages else "",
            format_filter.value if format_filter else "",
        ]
        key_str = "|".join(key_parts)
        return hashlib.md5(key_str.encode()).hexdigest()

    def _search_provider_with_retry(self, name: str, provider: SubtitleProvider,
                                    query: VideoQuery) -> tuple[list[SubtitleResult], float]:
        """Search a single provider with retries.

        Returns:
            Tuple of (results list, elapsed_ms). elapsed_ms is 0 if no successful search.
        """
        import time as _time

        retries = self._get_retries(name)
        last_error = None
        elapsed_ms = 0.0

        # Check if provider is initialized
        if hasattr(provider, 'session') and provider.session is None:
            logger.warning("Provider %s not initialized (session is None), skipping search", name)
            return [], 0.0

        logger.debug("Searching provider %s for: %s (languages: %s)",
                    name, query.display_name, query.languages)

        for attempt in range(retries + 1):
            try:
                start = _time.monotonic()
                results = provider.search(query)
                elapsed_ms = (_time.monotonic() - start) * 1000

                logger.info("Provider %s returned %d results in %.0fms (attempt %d/%d)",
                          name, len(results), elapsed_ms, attempt + 1, retries + 1)
                if results:
                    logger.debug("Provider %s top result: %s (score: %d, format: %s)",
                               name, results[0].filename, results[0].score, results[0].format.value)
                return results, elapsed_ms
            except ProviderAuthError as e:
                logger.error("Provider %s authentication failed: %s", name, e)
                return [], 0.0  # Don't retry auth errors
            except ProviderRateLimitError as e:
                logger.warning("Provider %s rate limit exceeded: %s", name, e)
                if attempt < retries:
                    # Wait a bit longer for rate limits
                    wait_time = 2 ** attempt  # Exponential backoff: 1s, 2s, 4s
                    logger.debug("Waiting %ds before retry...", wait_time)
                    _time.sleep(wait_time)
                    last_error = e
                else:
                    return [], 0.0  # Don't retry indefinitely for rate limits
            except Exception as e:
                last_error = e
                if attempt < retries:
                    logger.debug("Provider %s search failed (attempt %d/%d), retrying: %s",
                               name, attempt + 1, retries + 1, e, exc_info=True)
                else:
                    logger.warning("Provider %s search failed after %d attempts: %s",
                                 name, retries + 1, e, exc_info=True)

        return [], 0.0

    def _check_auto_disable(self, name: str):
        """Check if a provider should be auto-disabled based on consecutive failures.

        Auto-disables when consecutive_failures >= 2x circuit_breaker_failure_threshold.
        """
        from db.providers import get_provider_stats as _get_stats, auto_disable_provider
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
        format_filter: Optional[SubtitleFormat] = None,
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
        # Check cache first
        cache_key = self._make_cache_key(query, format_filter)
        cache_ttl_minutes = getattr(self.settings, "provider_cache_ttl_minutes", 5)
        
        from db.providers import get_cached_results, cache_provider_results
        cached_json = get_cached_results("combined", cache_key, format_filter.value if format_filter else None)
        if cached_json:
            try:
                cached_data = json.loads(cached_json)
                cached_results = []
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
                    )
                    cached_results.append(result)
                logger.info("Returning %d cached results", len(cached_results))
                return cached_results
            except Exception as e:
                logger.warning("Failed to parse cached results: %s", e)

        all_results: list[SubtitleResult] = []
        perfect_match_found = False

        # Parallel search with ThreadPoolExecutor
        from db.providers import update_provider_stats, auto_disable_provider, is_provider_auto_disabled

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

                # Get provider-specific timeout (used for overall as_completed wait)
                timeout = self._get_timeout(name)

                # Submit search task
                future = executor.submit(self._search_provider_with_retry, name, provider, query)
                futures[future] = name

            # Collect results as they complete
            # Use max timeout across all active providers + buffer
            max_timeout = max(
                (self._get_timeout(n) for n in self._providers if n in {futures[f] for f in futures}),
                default=self.settings.provider_search_timeout,
            ) + 5
            for future in as_completed(futures, timeout=max_timeout):
                name = futures[future]
                try:
                    results, elapsed_ms = future.result()
                    all_results.extend(results)

                    # Update circuit breaker and stats
                    cb = self._circuit_breakers.get(name)
                    if cb:
                        if results:
                            cb.record_success()
                            update_provider_stats(name, success=True, score=0, response_time_ms=elapsed_ms)
                        else:
                            cb.record_failure()
                            update_provider_stats(name, success=False, score=0, response_time_ms=elapsed_ms)
                            # Auto-disable check: if consecutive failures >= 2x CB threshold
                            self._check_auto_disable(name)

                    # Check for perfect match (early exit)
                    if early_exit and results:
                        # Score results immediately to check for perfect match
                        for result in results:
                            compute_score(result, query)
                            if result.score >= 400:
                                logger.info("Perfect match found (score=%d) from provider %s, stopping search",
                                          result.score, name)
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

        # Filter by language (if query specifies languages)
        if query.languages:
            all_results = [r for r in all_results if r.language in query.languages]

        # Filter by format
        if format_filter:
            all_results = [r for r in all_results if r.format == format_filter]

        # Filter by min score
        if min_score > 0:
            all_results = [r for r in all_results if r.score >= min_score]

        # Filter blacklisted subtitles
        from db.blacklist import is_blacklisted
        all_results = [r for r in all_results if not is_blacklisted(r.provider_name, r.subtitle_id)]

        # Sort by format preference (ASS first), then by score descending
        all_results.sort(key=lambda r: (
            0 if r.format == SubtitleFormat.ASS else 1,  # ASS first
            -r.score  # Then by score descending
        ))

        # Cache results
        try:
            cache_data = [{
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
            } for r in all_results]
            cache_provider_results("combined", cache_key, json.dumps(cache_data), 
                                 ttl_hours=cache_ttl_minutes / 60)
        except Exception as e:
            logger.debug("Failed to cache results: %s", e)

        return all_results

    def search_with_fallback(
        self,
        query: VideoQuery,
        format_filter: Optional[SubtitleFormat] = None,
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
        # 1. Try provider search first
        results = self.search(query, format_filter=format_filter, min_score=min_score, early_exit=early_exit)
        if results:
            return results
        
        # 2. Fallback: Check embedded subtitles
        if not query.file_path or not os.path.exists(query.file_path):
            return []
        
        try:
            from ass_utils import run_ffprobe, has_target_language_stream
            from providers.base import SubtitleResult, SubtitleFormat
            
            probe_data = run_ffprobe(query.file_path)
            if not probe_data:
                return []
            
            # Check for target language embedded subtitle
            target_lang = query.languages[0] if query.languages else None
            embedded_format = has_target_language_stream(probe_data, target_language=target_lang)
            
            if embedded_format:
                # Create pseudo-result for embedded subtitle
                embedded_result = SubtitleResult(
                    provider_name="embedded",
                    subtitle_id="embedded",
                    language=target_lang or "unknown",
                    format=SubtitleFormat.ASS if embedded_format == "ass" else SubtitleFormat.SRT,
                    filename=os.path.basename(query.file_path),
                    score=100,  # Lower than provider results but still valid
                )
                logger.info("Found embedded %s subtitle in %s", embedded_format, query.file_path)
                return [embedded_result]
        except Exception as e:
            logger.debug("Fallback embedded subtitle check failed: %s", e)
        
        return []

    def download(self, result: SubtitleResult) -> Optional[bytes]:
        """Download a subtitle from its provider.

        Args:
            result: A SubtitleResult from search()

        Returns:
            Raw subtitle file content, or None on failure
        """
        # Handle embedded subtitles (no download needed, already in file)
        if result.provider_name == "embedded":
            logger.debug("Skipping download for embedded subtitle")
            return b""  # Return empty bytes, extraction happens elsewhere
        
        provider = self._providers.get(result.provider_name)
        if not provider:
            logger.error("Provider %s not available for download", result.provider_name)
            return None

        # Check rate limit before download
        if not self._check_rate_limit(result.provider_name):
            logger.debug("Skipping download from provider %s due to rate limit", result.provider_name)
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
        format_filter: Optional[SubtitleFormat] = None,
        min_score: int = 0,
    ) -> Optional[SubtitleResult]:
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
        """
        if not result.content:
            raise ValueError("SubtitleResult has no content (download first)")

        # Determine extension
        ext = result.format.value if result.format != SubtitleFormat.UNKNOWN else "srt"
        if not output_path.endswith(f".{ext}"):
            # If output_path already has an extension, replace it
            base, _ = os.path.splitext(output_path)
            output_path = f"{base}.{ext}"

        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        with open(output_path, "wb") as f:
            f.write(result.content)

        logger.info("Saved subtitle: %s (%s, %s, score=%d)",
                     output_path, result.provider_name, result.language, result.score)
        return output_path

    def get_provider_status(self) -> list[dict]:
        """Get status of all providers (for API/UI) with priority, downloads, config_fields, and stats."""
        from db.providers import get_provider_download_stats, get_provider_stats, get_provider_success_rate, is_provider_auto_disabled

        # Build priority order (use current priority list from _init_providers)
        priority_str = getattr(self.settings, "provider_priorities", "animetosho,jimaku,opensubtitles,subdl")
        priority_list = [p.strip() for p in priority_str.split(",") if p.strip()]

        # Get enabled set
        enabled_str = getattr(self.settings, "providers_enabled", "")
        if enabled_str:
            enabled_set = {p.strip() for p in enabled_str.split(",") if p.strip()}
        else:
            enabled_set = set(_PROVIDER_CLASSES.keys())

        # Download stats from DB
        download_stats = get_provider_download_stats()
        # Performance stats
        performance_stats = get_provider_stats()

        statuses = []
        for name, cls in _PROVIDER_CLASSES.items():
            priority = priority_list.index(name) if name in priority_list else len(priority_list)
            downloads = download_stats.get(name, {}).get("total", 0)
            config_fields = self._get_provider_config_fields(name)
            
            # Get performance stats
            perf_stats = performance_stats.get(name, {})
            success_rate = get_provider_success_rate(name)

            # Build common stats dict with response time and auto-disable info
            auto_disabled = is_provider_auto_disabled(name)
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
                try:
                    healthy, msg = provider.health_check()
                except Exception as e:
                    healthy, msg = False, str(e)
                statuses.append({
                    "name": name,
                    "enabled": True,
                    "initialized": True,
                    "healthy": healthy,
                    "message": msg,
                    "priority": priority,
                    "downloads": downloads,
                    "config_fields": config_fields,
                    "stats": stats_dict,
                })
            else:
                statuses.append({
                    "name": name,
                    "enabled": name in enabled_set,
                    "initialized": False,
                    "healthy": False,
                    "message": "Not initialized",
                    "priority": priority,
                    "downloads": downloads,
                    "config_fields": config_fields,
                    "stats": stats_dict,
                })

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
        """Terminate all providers."""
        for name, provider in self._providers.items():
            try:
                provider.terminate()
            except Exception as e:
                logger.warning("Error terminating provider %s: %s", name, e)
        self._providers.clear()
