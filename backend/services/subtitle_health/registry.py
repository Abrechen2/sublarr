"""Registry of active checkers. Plan 1 ships two; later plans append more."""

from services.subtitle_health.checkers import ass_escape_leak, language_mislabel

CHECKERS = [
    ass_escape_leak.detect,
    language_mislabel.detect,
]
