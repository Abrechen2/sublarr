"""Learning/429-handling mixin for ProviderBudgetManager.

Extracted from services/provider_budget.py. Groups the three methods
that deal with feedback (429 events) and recovery (ramping learned
factors back to 1.0), plus the 1-Hz-rate-limited websocket emitter:

- ``record_429`` — multiplies the learned adjustment_factor by 0.9
  (floor 0.1) when a provider returns 429; persists via the
  ``provider_learned_limits`` repo (with in-memory fallback on DB
  failure) and emits ``provider_state_changed`` on the event bus.
- ``tick_recovery`` — once-per-wanted-scheduler-tick nudge: every row
  whose factor is still below 1.0 gets ramped back up via
  ``ProviderLearnedLimitsRepository.ramp_recovery``.
- ``_emit_update`` — fires ``provider_budget_updated`` with the
  current usage snapshot; rate-limited to 1 event/sec per provider
  via ``_LAST_EMIT_AT``.

Module-level helpers live on ``services.provider_budget`` — tests
patch them at that exact path (``_persist_429``, ``_ramp_all``,
``_emit_event``) so we look them up via call-time ``import
services.provider_budget as _pb`` to honour patches.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

logger = logging.getLogger(__name__)


class _BudgetLearningMixin:
    """Learning + event-emission methods mixed into ProviderBudgetManager."""

    def record_429(
        self,
        provider: str,
        window,
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
        import services.provider_budget as _pb

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
                new_factor = _pb._persist_429(
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
            _pb._emit_event(
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
        import services.provider_budget as _pb

        if now is None:
            now = datetime.now(UTC)
        try:
            new_factors = _pb._ramp_all(now)
        except Exception as exc:  # noqa: BLE001
            logger.warning("tick_recovery failed, keeping existing factors: %s", exc)
            return
        if not new_factors:
            return
        with self._lock:
            self._factors.update(new_factors)

    def _emit_update(self, provider: str, now: datetime) -> None:
        """Emit a provider_budget_updated event; rate-limited to 1/sec per provider.

        Best-effort — a failing event bus must never break budget accounting.
        Payload includes the NEW usage snapshot so the frontend can render without
        a follow-up HTTP call.
        """
        import services.provider_budget as _pb

        last = _pb._LAST_EMIT_AT.get(provider)
        if last is not None and (now - last).total_seconds() < _pb._EMIT_MIN_INTERVAL_SECONDS:
            return
        _pb._LAST_EMIT_AT[provider] = now
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
