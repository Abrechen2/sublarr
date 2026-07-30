"""Per-series subtitle format requirement lookup.

``subtitle_format_requirement`` on SeriesSettings:
  - NULL / unset — inherit the global behavior (ASS preferred, SRT fallback)
  - "require_ass" — the wanted pipeline never falls back to SRT provider
    results for this series

Best-effort accessor in the style of ``services.foreign_track_cleanup``:
never raises, returns None when the series has no explicit requirement.
"""

import logging

logger = logging.getLogger(__name__)

REQUIRE_ASS = "require_ass"
ALLOWED_REQUIREMENTS = (REQUIRE_ASS,)


def get_series_format_requirement(sonarr_series_id: int | None) -> str | None:
    """Return "require_ass" or None for the given series (None on any error)."""
    if not sonarr_series_id:
        return None
    try:
        from db.models.core import SeriesSettings
        from extensions import db

        ss = db.session.get(SeriesSettings, sonarr_series_id)
        if ss is None:
            return None
        value = ss.subtitle_format_requirement
        return value if value in ALLOWED_REQUIREMENTS else None
    except Exception:
        logger.debug("format requirement: series lookup failed", exc_info=True)
        return None
