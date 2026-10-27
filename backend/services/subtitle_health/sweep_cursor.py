"""Resume point of the nightly subtitle-health sweep.

The sweep ffprobes every episode of the library, ~30 s each on a network
share, so one night covers a few hundred episodes of tens of thousands. Without
a resume point every run restarted at the first series and the rest of the
library was never scanned.

The cursor is the last episode the sweep finished, as ``(source, series id,
episode id)``. Items are walked in that order, and a run resumes at the first
item greater than the cursor, so series or episodes added or removed since the
last run never derail it.

Lives in ``config_entries``, like ``services/foreign_tracks/state.py`` and
``services/repair/resume.py``: a small piece of job state that must survive
restarts.
"""

from __future__ import annotations

import json
import logging

logger = logging.getLogger(__name__)

CURSOR_KEY = "subtitle_health_sweep_cursor"

# Walk order of the sources; part of the cursor.
SOURCE_SONARR = 0
SOURCE_STANDALONE = 1

Cursor = tuple[int, int, int]


def load_cursor() -> Cursor | None:
    """The stored resume point, or None to start at the beginning."""
    from db.repositories.config import ConfigRepository

    try:
        raw = ConfigRepository().get_config_entry(CURSOR_KEY)
    except Exception:  # noqa: BLE001 — a missing cursor only costs a restart at the top
        logger.warning("subtitle_health sweep: resume point unavailable", exc_info=True)
        return None
    if not raw:
        return None
    try:
        value = json.loads(raw)
        if isinstance(value, list) and len(value) == 3:
            return (int(value[0]), int(value[1]), int(value[2]))
    except (ValueError, TypeError):
        pass
    logger.warning("subtitle_health sweep: unreadable resume point %r, starting at the top", raw)
    return None


def save_cursor(cursor: Cursor | None) -> None:
    """Store the resume point; None clears it (the next run starts at the top)."""
    from db.repositories.config import ConfigRepository

    value = json.dumps(list(cursor)) if cursor is not None else ""
    try:
        ConfigRepository().save_config_entry(CURSOR_KEY, value)
    except Exception:  # noqa: BLE001 — never fail the sweep over its bookmark
        logger.warning("subtitle_health sweep: could not save the resume point", exc_info=True)
