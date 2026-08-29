"""Give exhausted wanted items a bounded second chance.

Attempt exhaustion is permanent and provider-blind: an item that burned its
attempts while a provider was broken, misconfigured or down stays parked
forever, and fixing that provider afterwards does nothing for it (#199, #197).

Two triggers, one mechanism:

* **Time** — items exhausted for longer than
  ``wanted_revive_exhausted_after_days`` come back on a schedule. Off by
  default; reviving on its own is a behaviour change nobody asked for on
  upgrade.
* **A provider became usable again** — enabling one, storing credentials for
  one, or one recovering makes the earlier verdict stale for every item that
  gave up while it was unavailable.

Both funnel through ``reset_search_attempts``, which already owns the full set
of fields that gate eligibility. Selecting here and resetting there keeps one
definition of "put this back in rotation".
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

logger = logging.getLogger(__name__)


def _revive(*, idle_since, limit: int, reason: str) -> int:
    from config import peek_settings
    from db.repositories.wanted import WantedRepository

    settings = peek_settings()
    repo = WantedRepository()
    ids = repo.find_exhausted_ids(
        max_attempts=getattr(settings, "wanted_max_search_attempts", 3),
        adaptive=getattr(settings, "wanted_adaptive_backoff_enabled", True),
        idle_since=idle_since,
        limit=limit,
    )
    if not ids:
        return 0
    revived = repo.reset_search_attempts(ids)
    logger.info("wanted revive (%s): %d item(s) put back in rotation", reason, revived)
    return revived


def revive_exhausted_by_age() -> int:
    """Scheduler tick — module level and free of closures so it can be pickled
    into the APScheduler job store."""
    from config import peek_settings

    settings = peek_settings()
    days = getattr(settings, "wanted_revive_exhausted_after_days", 0) or 0
    if days <= 0:
        logger.debug("wanted revive: disabled (wanted_revive_exhausted_after_days=0)")
        return 0
    return _revive(
        idle_since=datetime.now(UTC) - timedelta(days=days),
        limit=getattr(settings, "wanted_revive_max_per_run", 200),
        reason=f"idle for more than {days} days",
    )


def revive_after_provider_change(provider_names: list[str] | None = None) -> int:
    """A provider became usable again, so the earlier "no result" verdicts are
    stale (#197).

    No age restriction: the whole point is that fixing a provider should have
    retroactive effect. The per-run cap still applies, so a large parked
    backlog returns in slices rather than flooding the next cycle.
    """
    from config import peek_settings

    settings = peek_settings()
    names = ", ".join(provider_names or []) or "provider configuration changed"
    return _revive(
        idle_since=None,
        limit=getattr(settings, "wanted_revive_max_per_run", 200),
        reason=names,
    )
