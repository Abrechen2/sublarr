"""Two-tier result caching for the search coordinator.

Extracted from providers/search_coordinator.py — the fast (Redis/memory)
+ persistent (DB) cache lookup/write helpers plus the (de)serialisation and
cache-key helpers. Pure mixin: used by ``SearchCoordinatorMixin``.
"""

import hashlib
import json
import logging

try:
    import metrics as _metrics_module

    _METRICS_AVAILABLE = getattr(_metrics_module, "METRICS_AVAILABLE", False)
except ImportError:
    _metrics_module = None  # type: ignore[assignment]
    _METRICS_AVAILABLE = False

from providers.base import SubtitleFormat, SubtitleResult, VideoQuery

logger = logging.getLogger(__name__)


class SearchCacheMixin:
    """Mixin providing the two-tier search-result cache and key helpers."""

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

    def _try_cached_search_results(
        self,
        cache_key: str,
        format_filter,
        app_cache_key: str,
        cache_backend,
        cache_ttl_minutes: float,
    ) -> list | None:
        """Two-tier cache lookup. Returns cached results or None to fall through.

        Tier 1: in-process/Redis fast cache keyed by ``app_cache_key``. Tier 2:
        persistent DB cache populated by every search. On a Tier-2 hit the
        value is backfilled into Tier 1 so the next call is cheaper.

        Records PROVIDER_CACHE_HITS_TOTAL / PROVIDER_CACHE_MISSES_TOTAL metrics
        when the ``metrics`` module is available.
        """
        # Tier 1
        if cache_backend:
            try:
                fast_cached = cache_backend.get(app_cache_key)
                if fast_cached:
                    try:
                        cached_data = json.loads(fast_cached)
                        cached_results = self._deserialize_results(cached_data)
                        logger.info("Returning %d results from fast cache", len(cached_results))
                        try:
                            if _METRICS_AVAILABLE:
                                _metrics_module.PROVIDER_CACHE_HITS_TOTAL.labels(layer="fast").inc()
                        except Exception:
                            pass
                        return cached_results
                    except Exception as e:
                        logger.debug("Failed to parse fast cached results: %s", e)
            except Exception as e:
                logger.debug("Fast cache lookup failed (non-blocking): %s", e)

        # Tier 2
        from db.providers import get_cached_results

        cached_json = get_cached_results(
            "combined", cache_key, format_filter.value if format_filter else None
        )
        if cached_json:
            try:
                cached_data = json.loads(cached_json)
                cached_results = self._deserialize_results(cached_data)
                logger.info("Returning %d cached results from DB", len(cached_results))
                try:
                    if _METRICS_AVAILABLE:
                        _metrics_module.PROVIDER_CACHE_HITS_TOTAL.labels(layer="db").inc()
                except Exception:
                    pass
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

        # Both tiers missed
        try:
            if _METRICS_AVAILABLE:
                _metrics_module.PROVIDER_CACHE_MISSES_TOTAL.labels(layer="fast").inc()
                _metrics_module.PROVIDER_CACHE_MISSES_TOTAL.labels(layer="db").inc()
        except Exception:
            pass
        return None

    def _write_search_cache(
        self,
        all_results: list,
        app_cache_key: str,
        cache_key: str,
        cache_ttl_minutes: float,
        cache_backend,
    ) -> None:
        """Serialise scored results and write both cache tiers.

        Never raises — cache failures degrade to a debug log so downstream
        scoring/filtering still returns results.
        """
        from db.providers import cache_provider_results

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
            if cache_backend:
                try:
                    cache_backend.set(
                        app_cache_key, cache_json, ttl_seconds=int(cache_ttl_minutes * 60)
                    )
                except Exception as e:
                    logger.debug("Fast cache write failed (non-blocking): %s", e)
            cache_provider_results(
                "combined", cache_key, cache_json, ttl_hours=cache_ttl_minutes / 60
            )
        except Exception as e:
            logger.debug("Failed to cache results: %s", e)

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
            str(query.anidb_id) if query.anidb_id else "",
        ]
        key_str = "|".join(key_parts)
        return hashlib.md5(key_str.encode(), usedforsecurity=False).hexdigest()  # noqa: S324
