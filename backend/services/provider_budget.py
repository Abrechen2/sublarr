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
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from threading import Lock
from typing import Any

# Imported at module level (not deferred) so tests can patch
# ``services.provider_budget.get_settings`` directly. Audited 2026-04-17: no
# cycle — ``config`` does not import from ``services.*``.
from config import get_settings
from services.demand_histogram import get_demand_shares  # noqa: F401 — tests patch here
from services.provider_budget_counters import (  # noqa: F401 — re-exported for back-compat
    _BudgetCounterStoreMixin,
)
from services.provider_budget_modes import (  # noqa: F401 — re-exported for back-compat
    _BudgetPacingModesMixin,
)

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


class ProviderBudgetManager(_BudgetCounterStoreMixin, _BudgetPacingModesMixin):
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
        # Per-key counters: (provider, key_id, window_value, window_start) -> count.
        # Populated when ``consume`` is called with ``key_id=<int>``. Same TTL model
        # as ``_in_memory_counts`` — entries for past windows are never evicted,
        # but are filtered out by ``get_usage_per_key`` which checks the
        # current window start.
        self._in_memory_counts_per_key: dict[tuple[str, int, str, datetime], int] = defaultdict(int)
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
        if day_limit > 0 and stretch_mode in ("stretch", "burst", "adaptive"):
            if stretch_mode == "stretch":
                stretch_decision = self._stretch_allowed(provider, day_limit, now)
            elif stretch_mode == "burst":
                stretch_decision = self._burst_allowed(
                    provider,
                    day_limit,
                    now,
                    burst_window_hours=burst_window_hours,
                )
            else:  # adaptive
                stretch_decision = self._adaptive_allowed(provider, day_limit, now)
            if not stretch_decision.allow:
                return stretch_decision

        return BudgetDecision(allow=True)

    # _stretch_allowed / _burst_allowed / _adaptive_allowed live on
    # _BudgetPacingModesMixin — see services/provider_budget_modes.py.

    def consume(
        self,
        provider: str,
        now: datetime | None = None,
        *,
        key_id: int | None = None,
    ) -> None:
        """Record one call against ``provider`` — increments all three windows.

        If ``key_id`` is provided, also increments per-key counters alongside the
        aggregate. Callers without multi-key support can continue to omit it.
        """
        if now is None:
            now = datetime.now(UTC)
        for window in BudgetWindow:
            self._increment(provider, window, now)
            if key_id is not None:
                self._increment_per_key(provider, key_id, window, now)
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

    def get_usage_per_key(
        self,
        provider: str,
        now: datetime | None = None,
    ) -> dict[int, dict[str, int]]:
        """Return ``{key_id: {window: count}}`` for ``provider``.

        Only counts falling within the current window start are returned — stale
        entries from previous windows are filtered out so the returned numbers
        always match ``get_usage``.
        """
        if now is None:
            now = datetime.now(UTC)
        with self._lock:
            snapshot = list(self._in_memory_counts_per_key.items())
        out: dict[int, dict[str, int]] = {}
        for (p, kid, wname, wstart), cnt in snapshot:
            if p != provider:
                continue
            if wstart != window_start_for(BudgetWindow(wname), now):
                continue  # stale window
            out.setdefault(kid, {})[wname] = cnt
        return out

    def prune(self, cutoff: datetime | None = None) -> int:
        """Drop in-memory counters whose window ended before ``cutoff``.

        Redis entries expire via TTL and do not need pruning. Returns the number
        of keys removed (diagnostic for tests and long-running processes).

        Evicts from both ``_in_memory_counts`` (aggregate) and
        ``_in_memory_counts_per_key`` (Phase 4a per-key dimension) so neither
        leaks across window rollovers.
        """
        if cutoff is None:
            cutoff = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        removed = 0
        with self._lock:
            for key in list(self._in_memory_counts.keys()):
                if key[2] < cutoff:
                    del self._in_memory_counts[key]
                    removed += 1
            for key in list(self._in_memory_counts_per_key.keys()):
                if key[3] < cutoff:
                    del self._in_memory_counts_per_key[key]
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

    # Counter-store methods (_effective_limit, _key, _redis_key, _get_count,
    # _increment, _increment_per_key, _decrement, _seconds_until_next_window)
    # are provided by _BudgetCounterStoreMixin — see provider_budget_counters.py.


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
