"""Detect a provider that has quietly stopped working, and say so once.

Sublarr has had circuit breakers and notification channels for a long time and
no bridge between them. A provider could fail permanently — an expired token, a
dead key, a gate misconfiguration — and the only symptom was a wanted queue
that stopped moving, which looks exactly like a library with nothing left to
find. On the install that prompted this the primary provider was dead for three
days, and the evidence was in `provider_stats` the entire time.

The detection is easy. Not crying wolf is the hard part, and it decides whether
the feature is worth having: on a healthy install most providers legitimately
never download, because they lose the scoring race. Alerting on "no downloads"
alone would bury the one provider that genuinely broke under a dozen that are
fine, and an alert channel people learn to ignore is worse than no channel.

So `downloads_stopped` fires only for a provider that is *demonstrably still
being used* — searching recently, and with downloads in its history. That
narrows it to the shape actually observed: the search path works, the download
path does not.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

logger = logging.getLogger(__name__)

# How long a provider that is still searching may go without a successful
# download before it counts as broken. Long enough to sit out a quiet night;
# short enough that a dead credential does not cost three days.
DOWNLOAD_SILENCE_H = 24

# A provider that has not searched in this long is not a download problem —
# nothing is reaching it at all, which is a different fault with a different
# fix.
SEARCH_SILENCE_H = 6

# One alert per provider per condition per day: the point is the first ping.
# In memory on purpose — a restart re-arming the alert is the safer error,
# since the operator may never have seen the first one.
_alerted: dict[tuple[str, str], str] = {}


def _as_utc(value):
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def _should_alert(provider: str, condition: str, now: datetime) -> bool:
    day = now.date().isoformat()
    if _alerted.get((provider, condition)) == day:
        return False
    _alerted[(provider, condition)] = day
    return True


def check_provider_degradation(now: datetime | None = None) -> list[dict]:
    """Evaluate every provider and return the alerts raised this run.

    Returns the payloads rather than only emitting them, so a caller can log
    what it found and a test can assert on it without reaching into the event
    bus.
    """
    from db.models.providers import ProviderStats
    from extensions import db

    now = now or datetime.now(UTC)
    alerts: list[dict] = []

    rows = db.session.query(ProviderStats).all()
    for row in rows:
        name = row.provider_name
        last_search = _as_utc(row.last_search_at)
        last_download = _as_utc(row.last_download_at)

        if row.auto_disabled and _should_alert(name, "auto_disabled", now):
            alerts.append(
                {
                    "provider_name": name,
                    "condition": "auto_disabled",
                    "detail": "The provider was auto-disabled after repeated failures.",
                    "since": _as_utc(row.disabled_until).isoformat() if row.disabled_until else "",
                }
            )

        # Every clause below is a reason NOT to alert, and each one is a false
        # positive that would otherwise be shipped:
        #   - never downloaded: normal, it loses the scoring race
        #   - not searching: a different fault, wrong advice
        #   - recent download: working
        searching = last_search is not None and (now - last_search) < timedelta(
            hours=SEARCH_SILENCE_H
        )
        used_to_download = (row.successful_downloads or 0) > 0 and last_download is not None
        gone_quiet = used_to_download and (now - last_download) >= timedelta(
            hours=DOWNLOAD_SILENCE_H
        )

        if searching and gone_quiet and _should_alert(name, "downloads_stopped", now):
            hours = int((now - last_download).total_seconds() // 3600)
            alerts.append(
                {
                    "provider_name": name,
                    "condition": "downloads_stopped",
                    "detail": (
                        f"Searches are still succeeding but nothing has downloaded for "
                        f"{hours}h. Search and download use different credentials, so this "
                        f"is usually an expired or rejected download credential."
                    ),
                    "since": last_download.isoformat(),
                }
            )

    for alert in alerts:
        logger.warning("provider degraded: %s — %s", alert["provider_name"], alert["condition"])

    if alerts and _alerts_enabled():
        from events import emit_event

        for alert in alerts:
            emit_event("provider_degraded", alert)

    return alerts


def _alerts_enabled() -> bool:
    """Off unless the operator asked for it.

    A notification that arrives unbidden on an install nobody asked to be
    watched is a support ticket, not a service — and the conditions here are
    heuristics about a fleet whose shape varies enormously between installs.
    The detection still runs and still logs, so the evidence is in the log
    either way.
    """
    from config import get_settings

    return bool(getattr(get_settings(), "provider_degradation_alerts_enabled", False))


def provider_degradation_tick() -> None:
    """Scheduler entry point. Module-level and argument-free so the job store
    can pickle it (SQLAlchemyJobStore pickles the callable)."""
    found = check_provider_degradation()
    if not found:
        logger.debug("provider degradation check: nothing to report")
