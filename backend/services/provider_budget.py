"""Provider-budget manager — tracks per-provider API calls across three sliding windows.

Every subtitle provider declares its own rate limits via ``SubtitleProvider.rate_limits``.
This module is the enforcement surface: :class:`ProviderBudgetManager` keeps
per-provider usage counters for three windows (second, hour, day) and tells the
search coordinator whether another call is allowed.

Counters live in Redis when a client is supplied (shared across processes); they
fall back to an in-memory ``defaultdict`` for single-process runs and tests. Redis
failures never break search — every Redis call is wrapped in ``try/except`` and the
in-memory counter is always authoritative if Redis is unreachable.

Daemon-level window-expiry is provided by Redis TTL (``expire()``). The in-memory
store does not evict entries on its own; long-running single-process setups should
call :meth:`ProviderBudgetManager.prune` periodically (called from tests only today).
"""

from __future__ import annotations

import enum
import logging
import math
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from threading import Lock
from typing import Any

from config import get_settings

logger = logging.getLogger(__name__)

# Rate-limit state for the provider_budget_updated SocketIO event.
# Tracks last emission time per provider so we never flood the WebSocket
# channel with more than one update per second per provider.
_LAST_EMIT_AT: dict[str, datetime] = {}
_EMIT_MIN_INTERVAL_SECONDS = 1.0


class BudgetWindow(enum.StrEnum):
    """The three time windows tracked per provider."""

    SECOND = "second"
    HOUR = "hour"
    DAY = "day"


_WINDOW_TTL_SECONDS = {
    BudgetWindow.SECOND: 2,
    BudgetWindow.HOUR: 3700,
    BudgetWindow.DAY: 90_000,
}


def window_start_for(window: BudgetWindow, now: datetime | None = None) -> datetime:
    """Return the UTC start of the enclosing window for ``now``.

    Examples:
        >>> window_start_for(BudgetWindow.HOUR, datetime(2026, 4, 16, 12, 34, 56, tzinfo=timezone.utc))
        datetime.datetime(2026, 4, 16, 12, 0, tzinfo=datetime.timezone.utc)
    """
    if now is None:
        now = datetime.now(UTC)
    if window is BudgetWindow.SECOND:
        return now.replace(microsecond=0)
    if window is BudgetWindow.HOUR:
        return now.replace(minute=0, second=0, microsecond=0)
    if window is BudgetWindow.DAY:
        return now.replace(hour=0, minute=0, second=0, microsecond=0)
    raise ValueError(f"unknown window: {window!r}")


@dataclass(frozen=True)
class BudgetDecision:
    """Result of a budget check — allow/deny plus wait time and reason."""

    allow: bool
    wait_seconds: int = 0
    reason: str = ""


@dataclass
class _Counts:
    """Per-provider per-window counter map. Internal detail."""

    store: dict[tuple[str, str, datetime], int] = field(default_factory=lambda: defaultdict(int))


class ProviderBudgetManager:
    """Three-window rate-limit accountant for subtitle providers.

    Thread-safe in the in-memory path via an internal lock; Redis path is naturally
    atomic via ``INCR``. Construct via :func:`get_budget_manager` for the
    process-wide singleton, or instantiate directly for tests.

    Args:
        redis: Optional Redis client (duck-typed — needs ``incr``, ``expire``, ``get``).
        safety_margin_pct: Reserve this percentage below the declared limit to
            cushion against clock drift and under-counting. Applied to the raw
            limit: effective = raw * (100 - margin) / 100.
    """

    def __init__(self, redis: Any = None, safety_margin_pct: int = 20) -> None:
        self._redis = redis
        self._safety = max(0, min(100, safety_margin_pct))
        self._lock = Lock()
        self._in_memory_counts: dict[tuple[str, str, datetime], int] = defaultdict(int)
        # Learned adjustment factors keyed by (provider, window_value). Loaded from
        # provider_learned_limits on first access and refreshed after each
        # record_429()/tick_recovery() call. Default is 1.0 for any missing entry.
        self._factors: dict[tuple[str, str], float] = {}
        self._factors_loaded = False

    # ── Public API ────────────────────────────────────────────────────────

    def check(
        self,
        provider: str,
        limits: dict[str, int],
        now: datetime | None = None,
    ) -> BudgetDecision:
        """Return an allow/deny decision for the next call to ``provider``.

        Iterates the three windows in increasing granularity (second → hour → day).
        The first window that is at-or-over its effective limit blocks the call.

        Args:
            provider: Provider name (must match the key used in :meth:`consume`).
            limits: Mapping of window name → raw daily limit (from ``rate_limits``).
                Missing windows are not enforced.
            now: Override the current time — test-only.
        """
        if now is None:
            now = datetime.now(UTC)

        for window_name, raw_limit in limits.items():
            try:
                window = BudgetWindow(window_name)
            except ValueError:
                # Unknown window key in rate_limits — ignore defensively.
                continue
            effective = self._effective_limit(raw_limit, provider=provider, window=window)
            used = self._get_count(provider, window, now)
            if used >= effective:
                return BudgetDecision(
                    allow=False,
                    wait_seconds=self._seconds_until_next_window(window, now),
                    reason=f"{window.value} limit reached ({used}/{effective})",
                )

        # Stretch-mode gate — default 'stretch' (even pacing). 'burst' lets the first
        # N hours run at raw-cap pace, then paces the REMAINING quota across the
        # REMAINING hours. 'adaptive' is handled in Task 7. 'off' / disabled skip the gate.
        try:
            settings = get_settings()
            stretch_mode = getattr(settings, "provider_budget_stretch_mode", "stretch")
            burst_window_hours = int(getattr(settings, "provider_budget_burst_window_hours", 6))
        except Exception:  # noqa: BLE001
            stretch_mode, burst_window_hours = "stretch", 6

        day_limit = limits.get("day", 0)
        if day_limit > 0 and stretch_mode in ("stretch", "burst"):
            if stretch_mode == "stretch":
                stretch_decision = self._stretch_allowed(provider, day_limit, now)
            else:  # burst
                stretch_decision = self._burst_allowed(
                    provider,
                    day_limit,
                    now,
                    burst_window_hours=burst_window_hours,
                )
            if not stretch_decision.allow:
                return stretch_decision

        return BudgetDecision(allow=True)

    def _stretch_allowed(self, provider: str, day_limit: int, now: datetime) -> BudgetDecision:
        """Stretch gate: reject when hourly pace exceeds the evenly-paced quota.

        Returns ``BudgetDecision(allow=True)`` when pace is OK or ``day_limit``
        is 0. Returns ``BudgetDecision(allow=False, wait_seconds=<until next
        hour>, reason=...)`` when the caller is ahead of schedule.

        For a day limit ``D``, the threshold at the end of hour ``H`` (0-based,
        0..23) is ``ceil(D * (H+1) / 24)``. The test uses ``>=`` so at the
        exact threshold we block and start pacing against the next hour's
        quota.
        """
        if day_limit <= 0:
            return BudgetDecision(allow=True)
        day_used = self._get_count(provider, BudgetWindow.DAY, now)
        hour_plus_1 = now.hour + 1
        threshold = math.ceil(day_limit * hour_plus_1 / 24)
        if day_used >= threshold:
            wait = self._seconds_until_next_window(BudgetWindow.HOUR, now)
            return BudgetDecision(
                allow=False,
                wait_seconds=wait,
                reason=(
                    f"stretch pace ({day_used}/{threshold} at hour {now.hour} UTC, "
                    f"of {day_limit}/day)"
                ),
            )
        return BudgetDecision(allow=True)

    def _burst_allowed(
        self,
        provider: str,
        day_limit: int,
        now: datetime,
        burst_window_hours: int,
    ) -> BudgetDecision:
        """Burst gate: raw-cap-only inside the window; paced afterwards.

        Inside hours [0, burst_window_hours): always allow (raw caps already
        enforced before this method runs).

        After the window: paces the REMAINING budget across the REMAINING hours.
        The burst-end consumption is not persisted anywhere; we estimate it by
        scaling current usage linearly (``day_used * burst_window_hours / now.hour``).
        Coarse but stateless; self-corrects within minutes as later hours tick.
        """
        if now.hour < burst_window_hours:
            return BudgetDecision(allow=True)

        day_used = self._get_count(provider, BudgetWindow.DAY, now)
        hours_after_burst_end = now.hour - burst_window_hours + 1
        hours_remaining_in_day = 24 - burst_window_hours
        estimated_burst_used = min(
            day_used,
            int(day_used * burst_window_hours / max(1, now.hour)),
        )
        remaining_budget = max(0, day_limit - estimated_burst_used)
        paced_share = math.ceil(remaining_budget * hours_after_burst_end / hours_remaining_in_day)
        threshold = estimated_burst_used + paced_share
        if day_used >= threshold:
            wait = self._seconds_until_next_window(BudgetWindow.HOUR, now)
            return BudgetDecision(
                allow=False,
                wait_seconds=wait,
                reason=(
                    f"burst pace ({day_used}/{threshold} at hour {now.hour} UTC, "
                    f"burst window {burst_window_hours}h, {day_limit}/day)"
                ),
            )
        return BudgetDecision(allow=True)

    def consume(self, provider: str, now: datetime | None = None) -> None:
        """Record one call against ``provider`` — increments all three windows."""
        if now is None:
            now = datetime.now(UTC)
        for window in BudgetWindow:
            self._increment(provider, window, now)
        self._emit_update(provider, now)

    def refund(self, provider: str, now: datetime | None = None) -> None:
        """Undo one call against ``provider`` — decrements all three windows.

        Used by the search coordinator when submit() fails synchronously after
        consume(), so quota does not leak for calls that never actually happened.
        """
        if now is None:
            now = datetime.now(UTC)
        for window in BudgetWindow:
            self._decrement(provider, window, now)
        self._emit_update(provider, now)

    def get_usage(self, provider: str, now: datetime | None = None) -> dict[str, int]:
        """Return ``{'second': n, 'hour': n, 'day': n}`` for ``provider``."""
        if now is None:
            now = datetime.now(UTC)
        return {w.value: self._get_count(provider, w, now) for w in BudgetWindow}

    def prune(self, cutoff: datetime | None = None) -> int:
        """Drop in-memory counters whose window ended before ``cutoff``.

        Redis entries expire via TTL and do not need pruning. Returns the number
        of keys removed (diagnostic for tests and long-running processes).
        """
        if cutoff is None:
            cutoff = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        removed = 0
        with self._lock:
            for key in list(self._in_memory_counts.keys()):
                if key[2] < cutoff:
                    del self._in_memory_counts[key]
                    removed += 1
        return removed

    def seconds_until_next_window(self, window_name: str, now: datetime | None = None) -> int:
        """Public wrapper around :meth:`_seconds_until_next_window`.

        Accepts the window name as a plain string — used by the ``/api/v1/system/budget``
        endpoint to surface reset countdowns.
        """
        if now is None:
            now = datetime.now(UTC)
        return self._seconds_until_next_window(BudgetWindow(window_name), now)

    def record_429(
        self,
        provider: str,
        window: BudgetWindow,
        configured_limit: int,
        observed_limit: int | None = None,
        now: datetime | None = None,
    ) -> float:
        """Record a provider-reported rate-limit hit.

        Multiplies the learned ``adjustment_factor`` by 0.9 (floor 0.1) for
        ``(provider, window)``. Persists via the repo; if persistence fails we
        still update the in-memory cache so the next ``check()`` throttles.
        Returns the new factor.
        """
        if now is None:
            now = datetime.now(UTC)
        if (
            observed_limit is not None
            and configured_limit > 0
            and observed_limit >= configured_limit
        ):
            # Implausible value — a provider reporting an observed limit at or above the
            # configured limit is almost certainly a header parsing mishap. Drop it so
            # we don't persist nonsense.
            observed_limit = None
        key = (provider, window.value)
        with self._lock:
            current = self._factors.get(key, 1.0)
            fallback_factor = max(0.1, current * 0.9)
            try:
                new_factor = _persist_429(
                    provider=provider,
                    window=window,
                    configured_limit=configured_limit,
                    observed_limit=observed_limit,
                    now=now,
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "record_429 persistence failed for %s/%s (using in-memory fallback): %s",
                    provider,
                    window.value,
                    exc,
                )
                new_factor = fallback_factor
            self._factors[key] = new_factor
        try:
            _emit_event(
                "provider_state_changed",
                {
                    "provider": provider,
                    "state": "learning",
                    "reason": f"429_observed_{window.value}",
                    "adjustment_factor": new_factor,
                },
            )
        except Exception as exc:  # noqa: BLE001
            logger.info("provider_state_changed emit failed: %s", exc)
        return new_factor

    def tick_recovery(self, now: datetime | None = None) -> None:
        """Advance learned factors toward 1.0 for any row on a clean streak.

        Called once per wanted-scheduler tick (typically daily). Swallows all DB
        errors — recovery is best-effort and must not break the scheduler.
        """
        if now is None:
            now = datetime.now(UTC)
        try:
            new_factors = _ramp_all(now)
        except Exception as exc:  # noqa: BLE001
            logger.warning("tick_recovery failed, keeping existing factors: %s", exc)
            return
        if not new_factors:
            return
        with self._lock:
            self._factors.update(new_factors)

    # ── Internals ─────────────────────────────────────────────────────────

    def _emit_update(self, provider: str, now: datetime) -> None:
        """Emit a provider_budget_updated event; rate-limited to 1/sec per provider.

        Best-effort — a failing event bus must never break budget accounting.
        Payload includes the NEW usage snapshot so the frontend can render without
        a follow-up HTTP call.
        """
        last = _LAST_EMIT_AT.get(provider)
        if last is not None and (now - last).total_seconds() < _EMIT_MIN_INTERVAL_SECONDS:
            return
        _LAST_EMIT_AT[provider] = now
        try:
            from events import emit_event

            emit_event(
                "provider_budget_updated",
                {
                    "provider": provider,
                    "usage": self.get_usage(provider, now=now),
                },
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug("Failed to emit provider_budget_updated: %s", exc)

    def _effective_limit(
        self,
        raw: int,
        *,
        provider: str | None = None,
        window: BudgetWindow | None = None,
    ) -> int:
        """Return raw * factor * (100 - safety) / 100, rounded down to int.

        ``provider``/``window`` are optional to preserve the old no-factor API
        for tests that predate Phase 3 — pass them to apply learned adjustments.
        """
        factor = 1.0
        if provider is not None and window is not None:
            factor = self._factors.get((provider, window.value), 1.0)
        scaled = raw * factor
        if self._safety > 0:
            scaled = scaled * (100 - self._safety) / 100
        return max(0, int(scaled))

    def _key(self, provider: str, window: BudgetWindow, now: datetime) -> tuple[str, str, datetime]:
        return provider, window.value, window_start_for(window, now)

    def _redis_key(self, provider: str, window: BudgetWindow, now: datetime) -> str:
        start = window_start_for(window, now)
        return f"budget:{provider}:{window.value}:{start.isoformat()}"

    def _get_count(self, provider: str, window: BudgetWindow, now: datetime) -> int:
        if self._redis is not None:
            try:
                raw = self._redis.get(self._redis_key(provider, window, now))
                if raw is not None:
                    return int(raw)
            except Exception as exc:  # noqa: BLE001 — Redis must never break search
                logger.debug("Redis get failed for %s/%s: %s", provider, window.value, exc)
        return self._in_memory_counts.get(self._key(provider, window, now), 0)

    def _increment(self, provider: str, window: BudgetWindow, now: datetime) -> None:
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

    def _decrement(self, provider: str, window: BudgetWindow, now: datetime) -> None:
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

    @staticmethod
    def _seconds_until_next_window(window: BudgetWindow, now: datetime) -> int:
        if window is BudgetWindow.SECOND:
            return 1
        if window is BudgetWindow.HOUR:
            return 3600 - (now.minute * 60 + now.second)
        if window is BudgetWindow.DAY:
            return 86400 - (now.hour * 3600 + now.minute * 60 + now.second)
        raise ValueError(window)


# ── Module-level singleton ────────────────────────────────────────────────

_singleton: ProviderBudgetManager | None = None
_singleton_lock = Lock()


def get_budget_manager() -> ProviderBudgetManager:
    """Return the process-wide :class:`ProviderBudgetManager` singleton.

    Lazy-constructs on first call. Wires Redis if available (via
    ``extensions.get_redis_client``) and reads the safety margin from settings.
    Falls back to in-memory mode when either resource is missing — neither is
    a hard requirement.
    """
    global _singleton
    if _singleton is not None:
        return _singleton
    with _singleton_lock:
        if _singleton is not None:
            return _singleton
        redis_client = _try_get_redis()
        safety = _try_get_safety_margin()
        _singleton = ProviderBudgetManager(redis=redis_client, safety_margin_pct=safety)
        logger.info(
            "ProviderBudgetManager initialised (redis=%s, safety=%d%%)",
            "yes" if redis_client else "no",
            safety,
        )
    return _singleton


def _try_get_redis() -> Any | None:
    try:
        from extensions import get_redis_client

        return get_redis_client()
    except Exception as exc:  # noqa: BLE001
        logger.debug("Redis unavailable for budget manager: %s", exc)
        return None


def _try_get_safety_margin() -> int:
    try:
        from config import get_settings

        return int(getattr(get_settings(), "provider_budget_safety_margin_pct", 20))
    except Exception as exc:  # noqa: BLE001
        logger.debug("Settings unavailable for budget margin: %s", exc)
        return 20


def _persist_429(
    provider: str,
    window: BudgetWindow,
    configured_limit: int,
    observed_limit: int | None,
    now: datetime,
) -> float:
    """Thin wrapper around the repo. Returns the NEW adjustment_factor.

    Wrapped so tests can patch it with MagicMock without needing a DB session.
    Requires a Flask app context (``db.session`` is request-scoped); callers
    outside an app context will get an error logged by ``record_429``'s
    outer try/except.
    """
    from db.repositories.provider_learned_limits import ProviderLearnedLimitsRepository

    return ProviderLearnedLimitsRepository().upsert_on_429(
        provider=provider,
        window=window.value,
        configured_limit=configured_limit,
        observed_limit=observed_limit,
        now=now,
    )


def _ramp_all(now: datetime) -> dict[tuple[str, str], float]:
    """Run ramp_recovery for every row with factor < 1.0. Returns the new map.

    Requires a Flask app context; ``tick_recovery`` callers from outside one
    (tests) must push ``app_ctx`` or patch this function.
    """
    # Expected row count is tiny (providers × windows ≈ < 20 in practice), so N
    # sequential commits are acceptable on the scheduler thread. Revisit if the
    # learned-limits table ever grows large.
    from db.repositories.provider_learned_limits import ProviderLearnedLimitsRepository

    repo = ProviderLearnedLimitsRepository()
    new_factors: dict[tuple[str, str], float] = {}
    for key, row in repo.get_all().items():
        if row["adjustment_factor"] < 1.0:
            new_factor = repo.ramp_recovery(key[0], key[1], step=0.02, now=now)
            new_factors[key] = new_factor
    return new_factors


def _emit_event(name: str, payload: dict) -> None:
    """Thin wrapper around events.emit_event — test-patchable."""
    from events import emit_event

    emit_event(name, payload)


def reset_singleton_for_tests() -> None:
    """Test helper — clear the cached singleton so the next call rebuilds it."""
    global _singleton
    with _singleton_lock:
        _singleton = None
