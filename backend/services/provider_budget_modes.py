"""Pacing-mode gate mixin for ProviderBudgetManager.

Extracted from services/provider_budget.py. Provides the three pacing
strategies the manager can apply on top of raw hour/day caps:

- ``_stretch_allowed`` — even-paced (``day_limit * (hour+1) / 24``)
- ``_burst_allowed``   — allow all bursts inside the first N hours,
  pace the remainder across the remaining hours
- ``_adaptive_allowed`` — threshold from the demand histogram's
  cumulative share up to the current hour

All three read ``self._get_count`` + ``self._seconds_until_next_window``
from the host class's counter-store mixin — they do not otherwise
touch instance state.
"""

from __future__ import annotations

import math
from datetime import datetime


class _BudgetPacingModesMixin:
    """Pacing-mode gate helpers mixed into ProviderBudgetManager."""

    def _stretch_allowed(self, provider: str, day_limit: int, now: datetime):
        """Stretch gate: reject when hourly pace exceeds the evenly-paced quota.

        Returns ``BudgetDecision(allow=True)`` when pace is OK or ``day_limit``
        is 0. Returns ``BudgetDecision(allow=False, wait_seconds=<until next
        hour>, reason=...)`` when the caller is ahead of schedule.

        For a day limit ``D``, the threshold at the end of hour ``H`` (0-based,
        0..23) is ``ceil(D * (H+1) / 24)``. The test uses ``>=`` so at the
        exact threshold we block and start pacing against the next hour's
        quota.
        """
        from services.provider_budget import BudgetDecision, BudgetWindow

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
    ):
        """Burst gate: raw-cap-only inside the window; paced afterwards.

        Inside hours [0, burst_window_hours): always allow (raw caps already
        enforced before this method runs — do not rely on that for correctness
        here: this gate must be safe to call from any caller order).

        After the window: paces the REMAINING budget across the REMAINING hours.
        The burst-end consumption is not persisted anywhere; we estimate it by
        scaling current usage linearly (``day_used * burst_window_hours / now.hour``).
        Coarse but stateless — the estimate is constant within a single clock hour
        (only depends on ``now.hour``), so the threshold cannot oscillate within
        an hour. It self-corrects at each hour boundary as later hours tick.

        Degenerate configs (``burst_window_hours`` <=0 or >= 24) skip pacing
        entirely — the field is documented as 1..23; anything outside falls back
        to "no pacing" rather than crashing.
        """
        from services.provider_budget import BudgetDecision, BudgetWindow

        # Clamp the config to the valid range [1, 23]. Outside this range the
        # pacing math degenerates (div-by-zero at 24; nonsensical estimate at 0).
        if burst_window_hours <= 0 or burst_window_hours >= 24:
            return BudgetDecision(allow=True)

        if now.hour < burst_window_hours:
            return BudgetDecision(allow=True)

        day_used = self._get_count(provider, BudgetWindow.DAY, now)
        elapsed_post_burst_hours = now.hour - burst_window_hours + 1
        hours_remaining_in_day = 24 - burst_window_hours
        estimated_burst_used = min(
            day_used,
            int(day_used * burst_window_hours / max(1, now.hour)),
        )
        remaining_budget = max(0, day_limit - estimated_burst_used)
        paced_share = math.ceil(
            remaining_budget * elapsed_post_burst_hours / hours_remaining_in_day
        )
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

    def _adaptive_allowed(self, provider: str, day_limit: int, now: datetime):
        """Adaptive gate: threshold at end of hour H = day_limit * cumulative_share[0..H].

        Falls back to uniform distribution (same behaviour as 'stretch') when
        history is empty.
        """
        # Look up via provider_budget module so tests can patch
        # services.provider_budget.get_demand_shares at call time.
        from services.provider_budget import BudgetDecision, BudgetWindow, get_demand_shares

        shares = get_demand_shares(now=now)
        cumulative = 0.0
        for h in range(now.hour + 1):
            cumulative += shares[h]
        # Floor at 1 so an hour with zero historical demand doesn't lock out a
        # genuinely-quiet system forever. Allow at least a trickle.
        threshold = max(1, math.ceil(day_limit * cumulative))
        day_used = self._get_count(provider, BudgetWindow.DAY, now)
        if day_used >= threshold:
            return BudgetDecision(
                allow=False,
                wait_seconds=self._seconds_until_next_window(BudgetWindow.HOUR, now),
                reason=(
                    f"adaptive pace ({day_used}/{threshold} at hour {now.hour} UTC, "
                    f"cumulative demand share {cumulative:.2f})"
                ),
            )
        return BudgetDecision(allow=True)
