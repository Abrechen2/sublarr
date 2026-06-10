"""Per-provider search-with-retry execution (worker-thread side).

Extracted from providers/search_coordinator.py — the credential-injection
wrapper and the core retry loop that run inside the ThreadPoolExecutor
worker. Pure mixin: used by ``SearchCoordinatorMixin``.
"""

import logging
import threading

from db.repositories.provider_account_pool import ProviderAccountPoolRepository
from providers.base import (
    ProviderAuthError,
    ProviderRateLimitError,
    ProviderTimeoutError,
    SubtitleResult,
    VideoQuery,
)

logger = logging.getLogger(__name__)


class SearchRetryMixin:
    """Mixin providing single-provider search execution with retries."""

    def _search_provider_with_retry(
        self, name: str, provider, query: VideoQuery, key: dict | None = None
    ) -> tuple[list[SubtitleResult], float]:
        """Search a single provider with retries.

        Credential injection (api_key/username/password from the pool row) is
        performed HERE inside the worker thread under a per-provider lock so
        two concurrent ``search()`` calls cannot clobber the singleton
        provider's credentials. Original values are restored in a finally
        block so provider state never leaks between calls.

        ``mark_used`` is also called here (worker thread) — previously it ran
        in the coordinator loop causing a DB commit per provider per tick.

        Args:
            key: pool row selected by KeySelector, or None for legacy callers
                that don't use the pool gate.

        Returns:
            Tuple of (results list, elapsed_ms). elapsed_ms is 0 if no successful search.
        """
        if key is None:
            return self._do_search_provider_with_retry(name, provider, query)

        # Lazy-init the per-provider lock dict (the mixin has no __init__).
        # setdefault is atomic on CPython dicts so a concurrent first call is
        # benign — both threads converge on the same RLock instance.
        if not hasattr(self, "_provider_call_locks"):
            self._provider_call_locks = {}
        lock = self._provider_call_locks.setdefault(name, threading.RLock())

        with lock:
            old = (
                getattr(provider, "api_key", None),
                getattr(provider, "username", None),
                getattr(provider, "password", None),
            )
            provider.api_key = key["api_key"]
            if key.get("username"):
                provider.username = key["username"]
            if key.get("password"):
                provider.password = key["password"]
            try:
                result = self._do_search_provider_with_retry(name, provider, query)
                # Phase 4a: record key usage on success (worker thread — parallel).
                try:
                    ProviderAccountPoolRepository().mark_used(key["id"])
                except Exception as _pe:  # noqa: BLE001
                    logger.debug(
                        "mark_used failed for %s key_id=%s: %s",
                        name,
                        key["id"],
                        _pe,
                    )
                return result
            finally:
                provider.api_key, provider.username, provider.password = old

    def _do_search_provider_with_retry(
        self, name: str, provider, query: VideoQuery
    ) -> tuple[list[SubtitleResult], float]:
        """Core search-with-retry loop (no credential injection).

        Factored out of :meth:`_search_provider_with_retry` so the injection
        wrapper and the legacy ``key=None`` path can share the same body.
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
