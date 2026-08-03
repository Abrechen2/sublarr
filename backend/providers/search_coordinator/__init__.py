"""Search coordination logic for ProviderManager.

Extracted from providers/__init__.py — contains the parallel search
orchestration, caching, retry logic, and result scoring.

Not instantiated directly — used as mixin by ProviderManager.

This package keeps the budget-gated execution core (``_submit_provider_searches``,
``_collect_provider_results``, ``_handle_rate_limit_exception``) and the public
``search`` entry points in this module so that tests which monkeypatch
``providers.search_coordinator.get_budget_manager`` /
``providers.search_coordinator.get_key_selector`` continue to bind correctly.
Cache, scoring and per-provider retry helpers live in sibling modules and are
mixed in below.
"""

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from concurrent.futures import TimeoutError as FutureTimeoutError

import decision_log
from db.repositories.provider_account_pool import ProviderAccountPoolRepository
from providers.base import (
    ProviderRateLimitError,
    SubtitleFormat,
    SubtitleResult,
    VideoQuery,
    compute_score,
)
from providers.search_coordinator.cache import SearchCacheMixin
from providers.search_coordinator.retry import SearchRetryMixin
from providers.search_coordinator.scoring import SearchScoringMixin
from services.key_selector import get_key_selector
from services.provider_budget import get_budget_manager

logger = logging.getLogger(__name__)

# Dedup set for one-time WARN emission per provider that ships without
# ``rate_limits`` metadata. Without this guard, new providers that forget to
# declare the ClassVar would silently bypass the budget gate — with the guard
# they show up in logs on first encounter (and only once per process).
_warned_missing_limits: set[str] = set()

# retry_after below this threshold is treated as a per-second burst; above, as
# a daily quota. Covers the observed provider behaviour where short waits
# (≤ 2 min) are transient bursts while longer waits indicate the daily window.
_RATE_LIMIT_WINDOW_THRESHOLD_S = 120

__all__ = ["SearchCoordinatorMixin"]


class SearchCoordinatorMixin(SearchRetryMixin, SearchScoringMixin, SearchCacheMixin):
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

    def _submit_provider_searches(
        self,
        executor,
        query,
        is_provider_auto_disabled,
    ) -> tuple[dict, dict]:
        """Gate every provider against auto-disable / CB / rate-limit / budget, then submit.

        For each provider that passes every gate we pick a pool key (if budget
        is on), consume one day-window call up front so timeouts still cost
        budget, and submit ``_search_provider_with_retry`` to the executor.
        Budget is refunded if the ``executor.submit`` itself fails (e.g. the
        executor is shutting down or OOM).

        Returns:
            Tuple of ``(futures, futures_to_key)`` where ``futures`` maps each
            submitted future to its provider name (for the as_completed loop)
            and ``futures_to_key`` maps the future to the key_id that was used
            (so the 429 handler can call ``ProviderAccountPoolRepository.mark_429``
            on the specific row).
        """
        futures: dict = {}
        futures_to_key: dict = {}

        # Provider profile: a language profile can restrict which providers a
        # search may query. Empty/absent = no restriction (global selection).
        allowed = set(getattr(query, "allowed_providers", None) or [])

        for name, provider in self._providers.items():
            # Reset per-iteration key tracking (Phase 4a).
            key: dict | None = None
            if allowed and name not in allowed:
                logger.debug("Skipping provider %s -- not in profile provider list", name)
                continue
            # Check auto-disable status
            if is_provider_auto_disabled(name):
                logger.debug("Skipping provider %s -- auto-disabled", name)
                decision_log.provider_skipped(name, "auto_disabled")
                continue

            # Check circuit breaker
            cb = self._circuit_breakers.get(name)
            if cb and not cb.allow_request():
                logger.debug("Skipping provider %s -- circuit breaker OPEN", name)
                decision_log.provider_skipped(name, "circuit_open")
                continue

            # Check rate limit
            if not self._check_rate_limit(name):
                logger.debug("Skipping provider %s due to rate limit", name)
                decision_log.provider_skipped(name, "rate_limited")
                continue

            # Budget gate — skip silently when exhausted (same pattern as
            # auto-disable/CB). Consume BEFORE submitting the future so a
            # provider timeout still costs budget (accurate accounting).
            if getattr(self.settings, "provider_budget_enabled", True):
                budget = get_budget_manager()
                tier = getattr(provider, "tier", "free")
                # Use class-level lookup so the ClassVar on the real provider
                # class wins; fall back to instance attr for unusual stubs.
                rate_limits = getattr(
                    type(provider), "rate_limits", getattr(provider, "rate_limits", None)
                )
                rate_limits_dict = rate_limits if isinstance(rate_limits, dict) else {}
                limits = {}
                if rate_limits_dict:
                    limits = rate_limits_dict.get(tier) or rate_limits_dict.get("free") or {}
                if not limits:
                    # Provider did not declare rate_limits (or none for this
                    # tier). The provider runs unthrottled — but the multi-key
                    # pool MUST still be consulted, otherwise enabling pool
                    # rows for a provider that lacks rate_limits silently
                    # falls back to singleton creds. WARN once so the missing
                    # metadata is visible.
                    if name not in _warned_missing_limits:
                        _warned_missing_limits.add(name)
                        logger.warning(
                            "Provider %s has no rate_limits[%r] defined — budget gate is "
                            "disabled for this provider. Add a 'rate_limits' ClassVar to "
                            "the provider class to enable throttling.",
                            name,
                            tier,
                        )
                    selected = get_key_selector().pick(name, provider_rate_limits=rate_limits_dict)
                    if selected is not None:
                        key = selected
                        budget.consume(name, key_id=key["id"])
                else:
                    decision = budget.check(name, limits)
                    if not decision.allow:
                        logger.debug(
                            "Skipping provider %s -- budget: %s (wait %ds)",
                            name,
                            decision.reason,
                            decision.wait_seconds,
                        )
                        decision_log.provider_skipped(
                            name, "budget_exhausted", detail=decision.reason
                        )
                        continue

                    # Phase 4a: pick a key from the pool before we commit the call.
                    key = get_key_selector().pick(
                        name,
                        provider_rate_limits=rate_limits_dict,
                    )
                    if key is None:
                        logger.warning(
                            "%s: no usable key in pool (all exhausted, 429-cooling, "
                            "or pool row deleted). Add a pool row via Settings → "
                            "Providers, or turn off Settings → Automation → "
                            "Provider budget to bypass the gate for this provider.",
                            name,
                        )
                        decision_log.provider_skipped(name, "no_pool_key")
                        continue

                    # Credential injection + mark_used happen INSIDE the worker
                    # thread (see _search_provider_with_retry) under a per-provider
                    # lock, so two concurrent search() calls cannot clobber the
                    # singleton provider's credentials.
                    budget.consume(name, key_id=key["id"])

            # Submit search task — refund budget if submit fails synchronously
            # (e.g. executor shut down, memory pressure). Without the refund the
            # just-consumed call leaks permanently.
            try:
                future = executor.submit(
                    self._search_provider_with_retry, name, provider, query, key
                )
                futures[future] = name
                # Phase 4a: track the key_id used for this future (if any),
                # so the rate-limit handler can mark_429 on the right row.
                if key is not None:
                    futures_to_key[future] = key["id"]
            except Exception as exc:  # noqa: BLE001
                logger.warning("submit failed for %s: %s -- refunding budget", name, exc)
                decision_log.provider_failed(name, "error", detail=f"submit failed: {exc}")
                if getattr(self.settings, "provider_budget_enabled", True):
                    try:
                        # Pass key_id so the per-key dimension is also rolled
                        # back; otherwise repeated submit failures drift the
                        # per-key counter while the aggregate stays correct.
                        refund_key_id = key["id"] if key is not None else None
                        get_budget_manager().refund(name, key_id=refund_key_id)
                    except Exception as refund_exc:  # noqa: BLE001
                        logger.debug("Budget refund failed for %s: %s", name, refund_exc)
                continue

        return futures, futures_to_key

    def _collect_provider_results(
        self,
        futures: dict,
        futures_to_key: dict,
        max_timeout: int,
        query,
        early_exit: bool,
        update_provider_stats,
    ) -> list:
        """Drain submitted futures, record CB/stats, handle 429s, return results.

        Walks ``as_completed(futures, timeout=max_timeout)`` once, dispatching
        each completion into one of three branches:

        - ``future.result()`` succeeded → extend accumulated results, record
          CB success + provider stats. If ``early_exit`` is on and any
          result scores ≥ 400, break the loop to skip still-running
          providers (they're cancelled in the caller's ``finally`` via
          ``executor.shutdown(wait=False, cancel_futures=True)``).
        - ``FutureTimeoutError`` on one future → record CB failure,
          auto-disable on CB transition to OPEN, update stats.
        - Generic exception → record CB failure, auto-disable on CB
          transition. For ``ProviderRateLimitError`` specifically,
          additionally apply an extended throttle (per
          ``provider_rate_limit_throttle_minutes``), emit the
          provider_state_changed event, call the budget manager's
          ``record_429`` learning hook, and mark the pool key as
          429-cooling so ``KeySelector`` skips it.

        An outer ``FutureTimeoutError`` on ``as_completed`` itself (not a
        single future) is swallowed: partial results are returned rather
        than raising, because dropping the whole search on one slow
        provider is worse than returning what we have.
        """
        all_results = []
        try:
            for future in as_completed(futures, timeout=max_timeout):
                name = futures[future]
                try:
                    results, elapsed_ms = future.result()
                    all_results.extend(results)
                    decision_log.provider_searched(name, len(results), elapsed_ms)

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
                        perfect_match_found = False
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
                            decision_log.early_exit(name, result.score)
                            break

                except FutureTimeoutError:
                    logger.warning("Provider %s search timed out", name)
                    decision_log.provider_failed(name, "timeout")
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
                    decision_log.provider_failed(
                        name,
                        "rate_limited" if isinstance(e, ProviderRateLimitError) else "error",
                        detail=str(e),
                    )
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
                        self._handle_rate_limit_exception(e, name, future, futures_to_key)
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
            decision_log.providers_unfinished(unfinished)
        return all_results

    def _handle_rate_limit_exception(self, e, name: str, future, futures_to_key: dict) -> None:
        """Apply the post-429 cascade: throttle, event emit, budget learn, pool-key cooldown."""
        throttle_min = getattr(self.settings, "provider_rate_limit_throttle_minutes", 60)
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
        # Phase 3 learning hook — tell the budget manager so future
        # calls throttle harder.
        if getattr(self.settings, "provider_budget_enabled", True):
            try:
                from services.provider_budget import BudgetWindow

                retry_after = getattr(e, "retry_after", 60)
                window = (
                    BudgetWindow.SECOND
                    if retry_after <= _RATE_LIMIT_WINDOW_THRESHOLD_S
                    else BudgetWindow.DAY
                )
                provider_obj = self._providers.get(name)
                if provider_obj is None:
                    logger.debug(
                        "record_429 hook: provider %s no longer registered, skipping",
                        name,
                    )
                else:
                    tier = getattr(provider_obj, "tier", "free")
                    rate_limits = getattr(type(provider_obj), "rate_limits", {}) or {}
                    limit = (rate_limits.get(tier) or rate_limits.get("free") or {}).get(
                        window.value, 0
                    )
                    if limit > 0:
                        get_budget_manager().record_429(
                            name,
                            window=window,
                            configured_limit=limit,
                        )
            except Exception as _le:  # noqa: BLE001
                logger.warning("record_429 hook failed for %s: %s", name, _le)
        # Phase 4a: per-key 429 cooldown — mark the pool row
        # used for this call so KeySelector skips it until the
        # retry_after window elapses.
        try:
            key_id = futures_to_key.get(future)
            if key_id is not None:
                ProviderAccountPoolRepository().mark_429(key_id)
        except Exception as _mke:  # noqa: BLE001
            logger.warning("mark_429 failed for %s: %s", name, _mke)

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
        # One decision-log search entry per search() call (no-op when inactive).
        decision_log.search_started(query.languages, format_filter, min_score)

        # Check cache first (two-tier: fast app cache, then persistent DB cache)
        cache_key = self._make_cache_key(query, format_filter)
        cache_ttl_minutes = getattr(self.settings, "provider_cache_ttl_minutes", 5)
        app_cache_key = f"provider:combined:{cache_key}"
        cache_backend = self._get_cache_backend()

        cached_results = self._try_cached_search_results(
            cache_key, format_filter, app_cache_key, cache_backend, cache_ttl_minutes
        )
        if cached_results is not None:
            decision_log.search_cache_hit(len(cached_results))
            return cached_results

        all_results: list[SubtitleResult] = []

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
            # Phase 4a: futures_to_key tracks which key_id each future used so
            # the rate-limit handler can call mark_429(key_id) later.
            futures, futures_to_key = self._submit_provider_searches(
                executor, query, is_provider_auto_disabled
            )

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
            all_results = self._collect_provider_results(
                futures, futures_to_key, max_timeout, query, early_exit, update_provider_stats
            )
        finally:
            # cancel_futures=True cancels any queued-but-not-started futures immediately.
            # Already-running threads are released as daemon threads — we do NOT wait
            # for them (wait=False), so slow/hung providers never block the response.
            executor.shutdown(wait=False, cancel_futures=True)

        # Score + classify + filter + sort — delegated to _finalise_search_results.
        _total_before_filters = len(all_results)
        all_results = self._finalise_search_results(
            all_results, query, format_filter, min_score, must_contain, must_not_contain
        )
        decision_log.search_finished(_total_before_filters, len(all_results))

        # Cache results in both tiers (delegated to _write_search_cache).
        self._write_search_cache(
            all_results, app_cache_key, cache_key, cache_ttl_minutes, cache_backend
        )

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
