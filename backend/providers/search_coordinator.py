"""Search coordination logic for ProviderManager.

Extracted from providers/__init__.py — contains the parallel search
orchestration, caching, retry logic, and result scoring.

Not instantiated directly — used as mixin by ProviderManager.
"""

import hashlib
import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from concurrent.futures import TimeoutError as FutureTimeoutError

try:
    import metrics as _metrics_module

    _METRICS_AVAILABLE = getattr(_metrics_module, "METRICS_AVAILABLE", False)
except ImportError:
    _metrics_module = None  # type: ignore[assignment]
    _METRICS_AVAILABLE = False

from providers.base import (
    ProviderAuthError,
    ProviderRateLimitError,
    ProviderTimeoutError,
    SubtitleFormat,
    SubtitleResult,
    VideoQuery,
    compute_score,
)

logger = logging.getLogger(__name__)


class SearchCoordinatorMixin:
    """Mixin providing parallel search orchestration, caching, and retry logic.

    Expects the host class to provide:
    - self.settings
    - self._providers
    - self._circuit_breakers
    - self._check_rate_limit(name) -> bool
    - self._get_timeout(name, stats) -> int
    - self._get_retries(name) -> int
    - self._check_auto_disable(name)
    """

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
            str(query.anidb_id) if query.anidb_id else "",
        ]
        key_str = "|".join(key_parts)
        return hashlib.md5(key_str.encode(), usedforsecurity=False).hexdigest()  # noqa: S324

    def _search_provider_with_retry(
        self, name: str, provider, query: VideoQuery
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

        import requests as _requests

        for attempt in range(retries + 1):
            # Re-check CB and server rate limit INSIDE the thread — between
            # submission and the actual HTTP request, other threads may have
            # tripped the breaker or received a 429.
            cb = self._circuit_breakers.get(name)
            if cb and not cb.allow_request():
                logger.info("Provider %s circuit breaker OPEN, aborting search", name)
                raise ProviderTimeoutError(f"Provider {name} circuit breaker open")
            until = self._server_rate_limit_until.get(name, 0)
            if _time.time() < until:
                logger.info(
                    "Provider %s server-rate-limited (%.0fs left), skipping",
                    name,
                    until - _time.time(),
                )
                raise ProviderRateLimitError(
                    f"Provider {name} server-rate-limited",
                    retry_after=int(until - _time.time()),
                )
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
                raise  # Propagate to caller for circuit breaker recording
            except ProviderRateLimitError as e:
                logger.warning("Provider %s rate limit exceeded: %s", name, e)
                # Set shared rate limit so concurrent threads skip this provider
                retry_after = getattr(e, "retry_after", 60)
                self._server_rate_limit_until[name] = _time.time() + retry_after
                raise  # Don't retry — server limit far exceeds backoff budget
            except _requests.Timeout:
                # Timeouts are not transient — the server is slow or unreachable.
                # Retrying will just waste the full timeout budget again. Raise so
                # the caller records a circuit breaker failure.
                elapsed_ms = (_time.monotonic() - start) * 1000
                logger.warning(
                    "Provider %s timed out after %.0fms (attempt %d/%d), not retrying",
                    name,
                    elapsed_ms,
                    attempt + 1,
                    retries + 1,
                )
                raise ProviderTimeoutError(f"Provider {name} timed out after {elapsed_ms:.0f}ms")
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
                    raise

        return [], 0.0

    @staticmethod
    def _emit_provider_state(name: str, state: str, reason: str, remaining_seconds: int = 0):
        """Emit a provider_state_changed WebSocket event."""
        try:
            from events import emit_event

            emit_event(
                "provider_state_changed",
                {
                    "provider": name,
                    "state": state,
                    "reason": reason,
                    "remaining_seconds": remaining_seconds,
                },
            )
        except Exception:
            pass

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
        must_contain: list[str] | None = None,
        must_not_contain: list[str] | None = None,
    ) -> list[SubtitleResult]:
        """Search all providers in parallel and return scored, sorted results.

        Args:
            query: What to search for
            format_filter: Only return results of this format (e.g. ASS)
            min_score: Minimum score threshold
            early_exit: If True, stop searching when a perfect match (score >= 400) is found
            must_contain: Release title must contain all of these strings (case-insensitive)
            must_not_contain: Release title must not contain any of these strings (case-insensitive)

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
                try:
                    if _METRICS_AVAILABLE:
                        _metrics_module.PROVIDER_CACHE_HITS_TOTAL.labels(layer="db").inc()
                except Exception:
                    pass
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

        # Both cache tiers missed — record cache miss metrics
        try:
            if _METRICS_AVAILABLE:
                _metrics_module.PROVIDER_CACHE_MISSES_TOTAL.labels(layer="fast").inc()
                _metrics_module.PROVIDER_CACHE_MISSES_TOTAL.labels(layer="db").inc()
        except Exception:
            pass

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

        # Use manual executor management (no context manager) so that a provider
        # timeout does NOT block the Flask request waiting for slow/hung threads.
        # ThreadPoolExecutor.__exit__ calls shutdown(wait=True) which would stall
        # until every provider thread returns — even if as_completed() already timed
        # out.  Instead we call shutdown(wait=False, cancel_futures=True) in a
        # finally block so pending futures are cancelled and running ones finish as
        # daemon threads without blocking the response.
        executor = ThreadPoolExecutor(max_workers=max(1, len(self._providers)))
        try:
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

                # Budget gate — skip silently when exhausted (same pattern as
                # auto-disable/CB). Consume BEFORE submitting the future so a
                # provider timeout still costs budget (accurate accounting).
                if getattr(self.settings, "provider_budget_enabled", True):
                    from services.provider_budget import get_budget_manager

                    budget = get_budget_manager()
                    tier = getattr(provider, "tier", "free")
                    # Use class-level lookup so the ClassVar on the real provider
                    # class wins; fall back to instance attr for unusual stubs.
                    rate_limits = getattr(
                        type(provider), "rate_limits", getattr(provider, "rate_limits", None)
                    )
                    limits = {}
                    if isinstance(rate_limits, dict):
                        limits = rate_limits.get(tier) or rate_limits.get("free") or {}
                    if limits:
                        decision = budget.check(name, limits)
                        if not decision.allow:
                            logger.debug(
                                "Skipping provider %s -- budget: %s (wait %ds)",
                                name,
                                decision.reason,
                                decision.wait_seconds,
                            )
                            continue
                        budget.consume(name)

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
            try:
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
                        update_provider_stats(
                            name, success=True, score=0, response_time_ms=elapsed_ms
                        )

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
                            if cb.is_open:  # just transitioned to OPEN
                                try:
                                    from db.providers import auto_disable_provider

                                    auto_disable_provider(
                                        name,
                                        cooldown_minutes=max(1, cb.cooldown_seconds // 60),
                                    )
                                except Exception as _pe:
                                    logger.debug("CB persistence failed: %s", _pe)
                                self._emit_provider_state(
                                    name, "circuit_open", "timeout", cb.cooldown_seconds
                                )
                        update_provider_stats(name, success=False, score=0)
                        self._check_auto_disable(name)
                    except Exception as e:
                        logger.warning("Provider %s search failed: %s", name, e)
                        cb = self._circuit_breakers.get(name)
                        if cb:
                            cb.record_failure()
                            if cb.is_open:  # just transitioned to OPEN
                                try:
                                    from db.providers import auto_disable_provider

                                    auto_disable_provider(
                                        name,
                                        cooldown_minutes=max(1, cb.cooldown_seconds // 60),
                                    )
                                except Exception as _pe:
                                    logger.debug("CB persistence failed: %s", _pe)
                                self._emit_provider_state(
                                    name, "circuit_open", "failures", cb.cooldown_seconds
                                )
                        # Rate-limit exception → extended throttle (Bazarr throttle_map parity)
                        if isinstance(e, ProviderRateLimitError):
                            throttle_min = getattr(
                                self.settings, "provider_rate_limit_throttle_minutes", 60
                            )
                            try:
                                from db.providers import auto_disable_provider

                                auto_disable_provider(name, cooldown_minutes=throttle_min)
                                logger.info(
                                    "Provider %s rate-limited: extended throttle for %d min",
                                    name,
                                    throttle_min,
                                )
                                try:
                                    from events import emit_event

                                    emit_event(
                                        "provider_state_changed",
                                        {
                                            "provider": name,
                                            "state": "throttled",
                                            "reason": "rate_limited",
                                            "remaining_seconds": throttle_min * 60,
                                        },
                                    )
                                except Exception:
                                    pass
                            except Exception as _te:
                                logger.debug("Rate-limit throttle persistence failed: %s", _te)
                        update_provider_stats(name, success=False, score=0)
                        self._check_auto_disable(name)
            except FutureTimeoutError:
                # as_completed() overall timeout expired — some providers did not finish.
                # Return the partial results already collected rather than raising.
                unfinished = [futures[f] for f in futures if not f.done()]
                logger.warning(
                    "Search timed out after %ss: %d provider(s) still running (%s);"
                    " returning %d partial results",
                    max_timeout,
                    len(unfinished),
                    ", ".join(unfinished),
                    len(all_results),
                )
        finally:
            # cancel_futures=True cancels any queued-but-not-started futures immediately.
            # Already-running threads are released as daemon threads — we do NOT wait
            # for them (wait=False), so slow/hung providers never block the response.
            executor.shutdown(wait=False, cancel_futures=True)

        # If early exit was triggered, we may have incomplete results, but that's OK
        # Score all results
        for result in all_results:
            if result.score == 0:  # Only score if not already scored
                compute_score(result, query)

        # Post-search forced classification: use forced_detection to classify
        # results from providers without native forced support (e.g., AnimeTosho,
        # Jimaku, SubDL). Single-pass: search once, classify results.
        from forced_detection import classify_forced_result

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

        # mustContain / mustNotContain filtering (language profile)
        if must_contain:
            from wanted_search.profile_filters import apply_must_contain

            all_results = apply_must_contain(all_results, must_contain)
        if must_not_contain:
            from wanted_search.profile_filters import apply_must_not_contain

            all_results = apply_must_not_contain(all_results, must_not_contain)

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
        must_contain: list[str] | None = None,
        must_not_contain: list[str] | None = None,
    ) -> list[SubtitleResult]:
        """Search providers with fallback to embedded subtitles.

        Args:
            query: What to search for
            format_filter: Only return results of this format (e.g. ASS)
            min_score: Minimum score threshold
            early_exit: If True, stop searching when a perfect match is found
            must_contain: Release title must contain all of these strings (case-insensitive)
            must_not_contain: Release title must not contain any of these strings (case-insensitive)

        Returns:
            List of SubtitleResult sorted by score (highest first)
        """
        return self.search(
            query,
            format_filter=format_filter,
            min_score=min_score,
            early_exit=early_exit,
            must_contain=must_contain,
            must_not_contain=must_not_contain,
        )
