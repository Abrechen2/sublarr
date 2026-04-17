"""Repository for the ``provider_learned_limits`` table.

Tracks observed rate-limit adjustments per (provider, window). A 429 from the
provider multiplies ``adjustment_factor`` by 0.9 (floored at 0.1). Clean days
ramp the factor back toward 1.0 in 0.02 steps after 7 consecutive days without
a 429.

All reads and writes against ``provider_learned_limits`` go through this
repository — direct SQL against the table is a contract violation.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from db.repositories.base import BaseRepository

logger = logging.getLogger(__name__)

_FACTOR_FLOOR = 0.1
_FACTOR_CEILING = 1.0
_RAMP_WAIT_HOURS = 24
_RAMP_GOOD_DAY_THRESHOLD = 7


def _as_utc(value: datetime | None) -> datetime | None:
    """SQLite drops tzinfo on read — restore UTC so math with aware datetimes works."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


class ProviderLearnedLimitsRepository(BaseRepository):
    """CRUD + learning operations for ``provider_learned_limits``."""

    def _row_to_dict(self, row) -> dict:
        return {
            "provider_name": row.provider_name,
            "window_type": row.window_type,
            "configured_limit": row.configured_limit,
            "observed_limit": row.observed_limit,
            "adjustment_factor": float(row.adjustment_factor),
            "last_429_at": _as_utc(row.last_429_at),
            "consecutive_good_days": row.consecutive_good_days,
            "updated_at": _as_utc(row.updated_at),
        }

    def get(self, provider: str, window: str) -> dict | None:
        from db.models.core import ProviderLearnedLimit  # noqa: PLC0415

        row = (
            self.session.execute(
                select(ProviderLearnedLimit).where(
                    ProviderLearnedLimit.provider_name == provider,
                    ProviderLearnedLimit.window_type == window,
                )
            )
            .scalars()
            .first()
        )
        return self._row_to_dict(row) if row else None

    def get_all(self) -> dict[tuple[str, str], dict]:
        from db.models.core import ProviderLearnedLimit  # noqa: PLC0415

        rows = self.session.execute(select(ProviderLearnedLimit)).scalars().all()
        return {(r.provider_name, r.window_type): self._row_to_dict(r) for r in rows}

    def upsert_on_429(
        self,
        provider: str,
        window: str,
        configured_limit: int,
        observed_limit: int | None,
        now: datetime,
    ) -> float:
        """Record a 429: multiply factor by 0.9 (floor 0.1), reset good-days."""
        from db.models.core import ProviderLearnedLimit  # noqa: PLC0415

        row = (
            self.session.execute(
                select(ProviderLearnedLimit).where(
                    ProviderLearnedLimit.provider_name == provider,
                    ProviderLearnedLimit.window_type == window,
                )
            )
            .scalars()
            .first()
        )
        if row is None:
            row = ProviderLearnedLimit(
                provider_name=provider,
                window_type=window,
                configured_limit=configured_limit,
                observed_limit=observed_limit,
                adjustment_factor=1.0,
                consecutive_good_days=0,
                last_429_at=now,
                updated_at=now,
            )
            self.session.add(row)
        new_factor = max(_FACTOR_FLOOR, float(row.adjustment_factor) * 0.9)
        row.adjustment_factor = new_factor
        row.consecutive_good_days = 0
        row.last_429_at = now
        row.updated_at = now
        if observed_limit is not None:
            row.observed_limit = observed_limit
        self.session.commit()
        logger.debug(
            "provider_learned_limits: 429 for %s/%s -> factor=%.3f",
            provider,
            window,
            new_factor,
        )
        return new_factor

    def ramp_recovery(
        self,
        provider: str,
        window: str,
        step: float,
        now: datetime,
    ) -> float:
        """Advance a (provider, window) toward factor=1.0 after a clean day.

        No-ops silently for unknown rows (nothing to ramp if never 429'd).
        """
        from db.models.core import ProviderLearnedLimit  # noqa: PLC0415

        row = (
            self.session.execute(
                select(ProviderLearnedLimit).where(
                    ProviderLearnedLimit.provider_name == provider,
                    ProviderLearnedLimit.window_type == window,
                )
            )
            .scalars()
            .first()
        )
        if row is None:
            return _FACTOR_CEILING

        # Must be a full 24h since the last 429 AND since the last ramp.
        # SQLite strips tzinfo on read — coerce to UTC before subtracting.
        last_429 = _as_utc(row.last_429_at)
        last_updated = _as_utc(row.updated_at)
        # "Since the last 429 OR the last ramp write, whichever is more recent."
        # Both are tracked: 429 resets consecutive_good_days, ramp writes updated_at.
        candidates = [d for d in (last_429, last_updated) if d is not None]
        if not candidates:
            return float(row.adjustment_factor)
        last = max(candidates)
        if (now - last) < timedelta(hours=_RAMP_WAIT_HOURS):
            return float(row.adjustment_factor)

        row.consecutive_good_days += 1
        row.updated_at = now
        if (
            row.consecutive_good_days >= _RAMP_GOOD_DAY_THRESHOLD
            and float(row.adjustment_factor) < _FACTOR_CEILING
        ):
            row.adjustment_factor = min(_FACTOR_CEILING, float(row.adjustment_factor) + step)
        self.session.commit()
        return float(row.adjustment_factor)

    def reset(self, provider: str, window: str) -> None:
        """Test-only: drop the row for (provider, window)."""
        from db.models.core import ProviderLearnedLimit  # noqa: PLC0415

        self.session.execute(
            ProviderLearnedLimit.__table__.delete().where(
                ProviderLearnedLimit.provider_name == provider,
                ProviderLearnedLimit.window_type == window,
            )
        )
        self.session.commit()
