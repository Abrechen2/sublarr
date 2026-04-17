"""Budget-aware API key selector (Phase 4a).

Caches enabled pool rows per provider for 60s. On each ``pick()``:
  1. Filter rows whose ``last_429_at`` falls within ``retry_after_seconds``.
  2. Compute remaining day-budget per row using per-key usage from the
     ProviderBudgetManager + tier-specific rate_limits.
  3. Return the row with the highest remaining day-budget (or None if
     no usable row).
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from threading import Lock

from db.repositories.provider_account_pool import ProviderAccountPoolRepository
from services.provider_budget import get_budget_manager

logger = logging.getLogger(__name__)

_CACHE_TTL = timedelta(seconds=60)


class KeySelector:
    def __init__(self) -> None:
        self._cache: dict[str, tuple[list[dict], datetime]] = {}
        self._lock = Lock()

    def invalidate(self, provider: str | None = None) -> None:
        with self._lock:
            if provider is None:
                self._cache.clear()
            else:
                self._cache.pop(provider, None)

    def _load(self, provider: str, now: datetime) -> list[dict]:
        with self._lock:
            cached = self._cache.get(provider)
            if cached is not None and now - cached[1] < _CACHE_TTL:
                return cached[0]
        # Out of lock for the DB read (may be slow).
        rows = ProviderAccountPoolRepository().get_enabled_for(provider)
        with self._lock:
            self._cache[provider] = (rows, now)
        return rows

    def pick(
        self,
        provider: str,
        *,
        provider_rate_limits: dict[str, dict[str, int]],
        retry_after_seconds: int = 60,
        now: datetime | None = None,
    ) -> dict | None:
        if now is None:
            now = datetime.now(UTC)
        rows = self._load(provider, now)
        if not rows:
            return None

        cooldown = timedelta(seconds=retry_after_seconds)
        fresh: list[dict] = []
        for r in rows:
            if r["last_429_at"] is not None and (now - r["last_429_at"]) < cooldown:
                continue
            fresh.append(r)
        if not fresh:
            return None

        usage_per_key = get_budget_manager().get_usage_per_key(provider, now=now)

        def remaining(row: dict) -> int:
            tier_limits = (
                provider_rate_limits.get(row["tier"]) or provider_rate_limits.get("free") or {}
            )
            day_limit = tier_limits.get("day", 0)
            used = usage_per_key.get(row["id"], {}).get("day", 0)
            return day_limit - used

        return max(fresh, key=remaining)


_singleton_lock = Lock()
_singleton: KeySelector | None = None


def get_key_selector() -> KeySelector:
    global _singleton
    if _singleton is None:
        with _singleton_lock:
            if _singleton is None:
                _singleton = KeySelector()
    return _singleton


def reset_key_selector_for_tests() -> None:
    global _singleton
    with _singleton_lock:
        _singleton = None
