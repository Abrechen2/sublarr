"""Per-hour demand histogram for adaptive budget pacing.

Bucket wanted_items by the UTC hour of their ``added_at`` over the last 30
days. Normalise to shares summing to 1.0. Cache for 1h to keep the hot path
cheap. Fall back to a uniform (1/24) distribution when history is empty or
the DB is unreachable — adaptive mode must never harden into a denial-of-
service against itself.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from threading import Lock

logger = logging.getLogger(__name__)

DEMAND_UNIFORM: list[float] = [1.0 / 24] * 24
_CACHE_TTL = timedelta(hours=1)
_HISTORY_DAYS = 30

_cache_shares: list[float] | None = None
_cache_at: datetime | None = None
_cache_lock = Lock()


def invalidate_demand_cache() -> None:
    """Test helper — drop the cached shares so the next call recomputes."""
    global _cache_shares, _cache_at
    with _cache_lock:
        _cache_shares = None
        _cache_at = None


def _fetch_added_at_hours(cutoff: datetime) -> list[int]:
    """Return UTC hours (0..23) for every wanted_item added after ``cutoff``.

    Isolated so tests can patch it. Requires a Flask app context.
    """
    from sqlalchemy import func, select

    from db.models.core import WantedItem
    from extensions import db

    stmt = select(func.extract("hour", WantedItem.added_at)).where(WantedItem.added_at >= cutoff)
    return [int(h) for h in db.session.execute(stmt).scalars().all()]


def get_demand_shares(now: datetime | None = None) -> list[float]:
    """Return 24 floats summing to 1.0 — share of historical demand per UTC hour.

    Cached 1h. Uniform when no history available.
    """
    if now is None:
        now = datetime.now(UTC)
    global _cache_shares, _cache_at
    with _cache_lock:
        if _cache_shares is not None and _cache_at is not None:
            if (now - _cache_at) < _CACHE_TTL:
                return _cache_shares
    try:
        cutoff = now - timedelta(days=_HISTORY_DAYS)
        hours = _fetch_added_at_hours(cutoff)
    except Exception as exc:  # noqa: BLE001
        logger.debug("demand histogram fetch failed, using uniform: %s", exc)
        hours = []
    if not hours:
        # Copy so callers mutating the result (or the cache being mutated via its
        # reference) cannot corrupt the module-level constant.
        result = list(DEMAND_UNIFORM)
    else:
        counts = [0] * 24
        for h in hours:
            if 0 <= h < 24:
                counts[h] += 1
        total = sum(counts) or 1
        result = [c / total for c in counts]
    with _cache_lock:
        _cache_shares = result
        _cache_at = now
    return result
