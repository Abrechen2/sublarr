"""Counter-store mixin for ProviderBudgetManager.

Extracted from services/provider_budget.py. Provides the low-level
``(provider, window, start)`` counter accessor / incrementer pair used
by the manager's public check/consume/refund API — either backed by
Redis (shared across processes) or an in-memory ``defaultdict`` (single
process / tests).

All instance state — ``_redis``, ``_lock``, ``_in_memory_counts``,
``_in_memory_counts_per_key``, ``_safety``, ``_factors`` — lives on
:class:`ProviderBudgetManager`; this mixin only accesses it via
``self``.
"""

from __future__ import annotations

import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class _BudgetCounterStoreMixin:
    """Backing-store methods for ProviderBudgetManager.

    Windowed counters are keyed on (provider, window_value, window_start).
    The in-memory dict is the durable fallback; Redis is consulted first
    when available and failures never raise — Redis outages degrade to
    the in-memory counter without breaking search.
    """

    def _effective_limit(
        self,
        raw: int,
        *,
        provider: str | None = None,
        window=None,
    ) -> int:
        """Return raw * factor * (100 - safety) / 100, rounded down to int.

        ``provider``/``window`` are optional to preserve the old no-factor API
        for tests that predate Phase 3 — pass them to apply learned adjustments.

        A positive ``raw`` never scales below 1: the margin and the learned
        factor exist to THROTTLE a provider, not to disable it. Plain rounding
        floors ``raw=1`` to 0 for any margin >= 1%, and ``check()`` then denies
        the first call outright ("second limit reached (0/0)") — which stalled
        every provider declaring ``"second": 1`` (see #181). ``raw=0`` keeps
        meaning "no calls allowed" and is passed through untouched.
        """
        factor = 1.0
        if provider is not None and window is not None:
            factor = self._factors.get((provider, window.value), 1.0)
        scaled = raw * factor
        if self._safety > 0:
            scaled = scaled * (100 - self._safety) / 100
        if raw > 0:
            return max(1, int(scaled))
        return max(0, int(scaled))

    def _key(self, provider: str, window, now: datetime) -> tuple[str, str, datetime]:
        from services.provider_budget import window_start_for

        return provider, window.value, window_start_for(window, now)

    def _redis_key(self, provider: str, window, now: datetime) -> str:
        from services.provider_budget import window_start_for

        start = window_start_for(window, now)
        return f"budget:{provider}:{window.value}:{start.isoformat()}"

    def _get_count(self, provider: str, window, now: datetime) -> int:
        if self._redis is not None:
            try:
                raw = self._redis.get(self._redis_key(provider, window, now))
                if raw is not None:
                    return int(raw)
            except Exception as exc:  # noqa: BLE001 — Redis must never break search
                logger.debug("Redis get failed for %s/%s: %s", provider, window.value, exc)
        return self._in_memory_counts.get(self._key(provider, window, now), 0)

    def _increment(self, provider: str, window, now: datetime) -> None:
        from services.provider_budget import _WINDOW_TTL_SECONDS

        # In-memory always wins as the durable fallback.
        with self._lock:
            self._in_memory_counts[self._key(provider, window, now)] += 1
        if self._redis is not None:
            try:
                key = self._redis_key(provider, window, now)
                self._redis.incr(key)
                self._redis.expire(key, _WINDOW_TTL_SECONDS[window])
            except Exception as exc:  # noqa: BLE001
                logger.debug("Redis incr failed for %s/%s: %s", provider, window.value, exc)

    def _increment_per_key(
        self,
        provider: str,
        key_id: int,
        window,
        now: datetime,
    ) -> None:
        from services.provider_budget import window_start_for

        start = window_start_for(window, now)
        key = (provider, key_id, window.value, start)
        with self._lock:
            self._in_memory_counts_per_key[key] += 1

    def _decrement(self, provider: str, window, now: datetime) -> None:
        with self._lock:
            key = self._key(provider, window, now)
            # Floor at zero — do not go negative if somehow a refund is double-called
            current = self._in_memory_counts.get(key, 0)
            if current > 0:
                self._in_memory_counts[key] = current - 1
        if self._redis is not None:
            try:
                redis_key = self._redis_key(provider, window, now)
                # Use decr; it is fine if it takes the key below zero temporarily —
                # the next consume will bring it back up.
                self._redis.decr(redis_key)
            except Exception as exc:  # noqa: BLE001
                logger.debug("Redis decr failed for %s/%s: %s", provider, window.value, exc)

    def _decrement_per_key(
        self,
        provider: str,
        key_id: int,
        window,
        now: datetime,
    ) -> None:
        from services.provider_budget import window_start_for

        start = window_start_for(window, now)
        key = (provider, key_id, window.value, start)
        with self._lock:
            current = self._in_memory_counts_per_key.get(key, 0)
            if current > 0:
                self._in_memory_counts_per_key[key] = current - 1

    @staticmethod
    def _seconds_until_next_window(window, now: datetime) -> int:
        from services.provider_budget import BudgetWindow

        if window is BudgetWindow.SECOND:
            return 1
        if window is BudgetWindow.HOUR:
            return 3600 - (now.minute * 60 + now.second)
        if window is BudgetWindow.DAY:
            return 86400 - (now.hour * 3600 + now.minute * 60 + now.second)
        raise ValueError(window)
