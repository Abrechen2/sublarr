"""Auto-resume for quota-interrupted repair runs.

A sharp repair run over a damaged library spans several provider-quota days
(OpenSubtitles allows ~1000 downloads/day). Requiring a human to restart the
run every morning is how libraries stay broken — so a run that stops on quota
exhaustion persists a pending resume, and the ``repair_resume`` scheduler tick
starts the next pass once the allowance is back. The chain repeats until a
pass finishes without hitting the quota.

The pending entry survives restarts (it lives in ``config_entries``) and is
claimed — cleared — by the sharp run itself when it starts, not by the tick:
if ``job.start()`` loses a race against a manually started run, the entry must
stay so a later tick can retry.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta

logger = logging.getLogger(__name__)

RESUME_KEY = "repair_auto_resume"

# Fire a little after the reset moment — provider clocks are not our clocks.
_RESET_BUFFER = timedelta(minutes=5)

# A reset time in the past (clock skew, stale header) must never produce an
# immediate re-fire loop against the provider.
_STALE_RESET_DELAY = timedelta(hours=1)


def parse_reset_time(value: object) -> datetime | None:
    """Parse an ISO-8601 timestamp (``Z`` suffix tolerated) into aware UTC."""
    if not value or not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _next_utc_midnight(now: datetime) -> datetime:
    """OpenSubtitles resets its allowance at midnight UTC."""
    return (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)


def schedule_resume(
    *, language: str | None, reset_at: datetime | None, now: datetime | None = None
) -> datetime:
    """Persist a pending resume and return the moment it becomes due."""
    from db.config import save_config_entry

    now = now or datetime.now(UTC)
    if reset_at is None:
        resume_at = _next_utc_midnight(now) + _RESET_BUFFER
    elif reset_at <= now:
        resume_at = now + _STALE_RESET_DELAY
    else:
        resume_at = reset_at + _RESET_BUFFER

    save_config_entry(
        RESUME_KEY,
        json.dumps({"language": language, "resume_at": resume_at.isoformat()}),
    )
    logger.info(
        "repair: quota exhausted — run will auto-resume at %s (language=%s)",
        resume_at.isoformat(),
        language,
    )
    return resume_at


def pending_resume() -> dict | None:
    """The persisted pending resume, or None. Corrupt state reads as None."""
    from db.config import get_config_entry

    raw = get_config_entry(RESUME_KEY)
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except ValueError:
        logger.warning("repair: pending-resume state is corrupt — ignoring it")
        return None
    resume_at = parse_reset_time(data.get("resume_at"))
    if resume_at is None:
        return None
    return {"language": data.get("language"), "resume_at": resume_at}


def clear_resume() -> None:
    from db.config import save_config_entry

    save_config_entry(RESUME_KEY, "")


def repair_resume_tick() -> None:
    """Scheduler tick: start the next sharp pass once the allowance is back.

    No-op unless a resume is pending, due, and no pass is currently running.
    Deliberately does NOT clear the pending entry — the sharp run claims it
    when it actually starts, so a lost ``job.start()`` race is retried on the
    next tick instead of silently dropping the resume.
    """
    from flask import current_app

    from services.repair import job

    pending = pending_resume()
    if pending is None:
        return
    if job.is_running():
        return
    if datetime.now(UTC) < pending["resume_at"]:
        return

    started = job.start(
        current_app._get_current_object(), language=pending["language"], dry_run=False
    )
    if started:
        logger.info("repair: auto-resumed the interrupted run (language=%s)", pending["language"])
