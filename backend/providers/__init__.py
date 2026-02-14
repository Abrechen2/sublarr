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
)

logger = logging.getLogger(__name__)

# Provider registry — maps name to class
_PROVIDER_CLASSES: dict[str, type[SubtitleProvider]] = {}

# Singleton manager
_manager: Optional["ProviderManager"] = None


def register_provider(cls: type[SubtitleProvider]) -> type[SubtitleProvider]:
    """Decorator to register a provider class."""
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
        self._init_providers()

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
            from database import get_provider_stats, get_provider_success_rate
            
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
        for name in priority_list:
            if name not in _PROVIDER_CLASSES:
                continue
            if name not in enabled_set:
                continue

            try:
                config = self._get_provider_config(name)
                provider = _PROVIDER_CLASSES[name](**config)
                provider.initialize()
                self._providers[name] = provider
                logger.info("Provider initialized: %s", name)
            except Exception as e:
                logger.warning("Failed to initialize provider %s: %s", name, e)

        # Add any enabled providers not in priority list
        for name in enabled_set:
            if name in self._providers:
                continue
            if name not in _PROVIDER_CLASSES:
                continue
            try:
                config = self._get_provider_config(name)
                provider = _PROVIDER_CLASSES[name](**config)
                provider.initialize()
                self._providers[name] = provider
                logger.info("Provider initialized: %s", name)
            except Exception as e:
                logger.warning("Failed to initialize provider %s: %s", name, e)

        logger.info("Active providers: %s", list(self._providers.keys()))

    def _get_provider_config(self, name: str) -> dict:
        """Get provider-specific config from settings."""
        config = {}

        if name == "opensubtitles":
            config["api_key"] = getattr(self.settings, "opensubtitles_api_key", "")
            config["username"] = getattr(self.settings, "opensubtitles_username", "")
            config["password"] = getattr(self.settings, "opensubtitles_password", "")
        elif name == "jimaku":
            config["api_key"] = getattr(self.settings, "jimaku_api_key", "")
        elif name == "animetosho":
            pass  # No auth needed
        elif name == "subdl":
            config["api_key"] = getattr(self.settings, "subdl_api_key", "")

        # Strip whitespace from all credential values (防 paste artifacts)
        for key in config:
            if isinstance(config[key], str):
                config[key] = config[key].strip()

        return config

    def _check_rate_limit(self, provider_name: str) -> bool:
        """Check if provider is within rate limit.

        Returns:
            True if request is allowed, False if rate limited
        """
        if not getattr(self.settings, "provider_rate_limit_enabled", True):
            return True

        if provider_name not in self.PROVIDER_RATE_LIMITS:
            return True  # No rate limit configured

        max_requests, window_seconds = self.PROVIDER_RATE_LIMITS[provider_name]
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
                                    query: VideoQuery) -> list[SubtitleResult]:
        """Search a single provider with retries."""
        retries = self.PROVIDER_RETRIES.get(name, 2)
        last_error = None
        
        for attempt in range(retries + 1):
            try:
                results = provider.search(query)
                logger.info("Provider %s returned %d results (attempt %d/%d)", 
                          name, len(results), attempt + 1, retries + 1)
                return results
            except Exception as e:
                last_error = e
                if attempt < retries:
                    logger.debug("Provider %s search failed (attempt %d/%d), retrying: %s",
                               name, attempt + 1, retries + 1, e)
                else:
                    logger.warning("Provider %s search failed after %d attempts: %s",
                                 name, retries + 1, e)
        
        return []

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
        
        from database import get_cached_results, cache_provider_results
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
        with ThreadPoolExecutor(max_workers=len(self._providers)) as executor:
            futures = {}
            for name, provider in self._providers.items():
                # Check rate limit
                if not self._check_rate_limit(name):
                    logger.debug("Skipping provider %s due to rate limit", name)
                    continue

                # Get provider-specific timeout
                timeout = self.PROVIDER_TIMEOUTS.get(name, self.settings.provider_search_timeout)
                
                # Submit search task
                future = executor.submit(self._search_provider_with_retry, name, provider, query)
                futures[future] = name

            # Collect results as they complete
            for future in as_completed(futures, timeout=max(self.PROVIDER_TIMEOUTS.values(), 
                                                           default=self.settings.provider_search_timeout) + 5):
                name = futures[future]
                try:
                    results = future.result()
                    all_results.extend(results)
                    
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
                except Exception as e:
                    logger.warning("Provider %s search failed: %s", name, e)

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
        from database import is_blacklisted
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
            from database import update_provider_stats
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
        from database import get_provider_download_stats, get_provider_stats, get_provider_success_rate

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
                    "stats": {
                        "total_searches": perf_stats.get("total_searches", 0),
                        "successful_downloads": perf_stats.get("successful_downloads", 0),
                        "failed_downloads": perf_stats.get("failed_downloads", 0),
                        "success_rate": success_rate,
                        "avg_score": perf_stats.get("avg_score", 0),
                        "consecutive_failures": perf_stats.get("consecutive_failures", 0),
                        "last_success_at": perf_stats.get("last_success_at"),
                        "last_failure_at": perf_stats.get("last_failure_at"),
                    },
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
                    "stats": {
                        "total_searches": perf_stats.get("total_searches", 0),
                        "successful_downloads": perf_stats.get("successful_downloads", 0),
                        "failed_downloads": perf_stats.get("failed_downloads", 0),
                        "success_rate": success_rate,
                        "avg_score": perf_stats.get("avg_score", 0),
                        "consecutive_failures": perf_stats.get("consecutive_failures", 0),
                        "last_success_at": perf_stats.get("last_success_at"),
                        "last_failure_at": perf_stats.get("last_failure_at"),
                    },
                })

        # Sort by priority
        statuses.sort(key=lambda s: s["priority"])
        return statuses

    @staticmethod
    def _get_provider_config_fields(name: str) -> list[dict]:
        """Return config field definitions for a provider (for dynamic UI forms)."""
        fields_map = {
            "opensubtitles": [
                {"key": "opensubtitles_api_key", "label": "API Key", "type": "password", "required": True},
                {"key": "opensubtitles_username", "label": "Username", "type": "text", "required": False},
                {"key": "opensubtitles_password", "label": "Password", "type": "password", "required": False},
            ],
            "jimaku": [
                {"key": "jimaku_api_key", "label": "API Key", "type": "password", "required": True},
            ],
            "animetosho": [],  # No auth needed
            "subdl": [
                {"key": "subdl_api_key", "label": "API Key", "type": "password", "required": True},
            ],
        }
        return fields_map.get(name, [])

    def shutdown(self):
        """Terminate all providers."""
        for name, provider in self._providers.items():
            try:
                provider.terminate()
            except Exception as e:
                logger.warning("Error terminating provider %s: %s", name, e)
        self._providers.clear()
