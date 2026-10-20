"""Parsing of ffsubsync's console output, shared by every ffsubsync caller.

The legacy wrapper (``services.video_sync``), the preview (``sync_preview``)
and the engine class (``sync_engines.ffsubsync_engine``) used to carry their
own parsers with different patterns, and each returned 0 when no offset line
was found — so a run whose output could not be read "succeeded" with no shift.
"""

from __future__ import annotations

import re

# Formats seen in the wild:
#   ffsubsync >= 0.4 (rich logger): ``INFO     offset seconds: 22.960``
#   legacy:                         ``offset: 1.234 s applied`` / ``Offset: -0.5 s``
#   older engine output:            ``estimated shift: 0.42s`` (colon optional)
# ``\b`` keeps ``max_offset_seconds: 60`` (an argument echo) from matching.
_SHIFT_RE = re.compile(
    r"\b(?:estimated\s+shift|offset)(?:\s+seconds)?\s*:?\s*(-?\d+(?:\.\d+)?)",
    re.IGNORECASE,
)

#: Reason / message used when ffsubsync exited 0 but reported no offset.
NO_OFFSET_MESSAGE = "ffsubsync reported no offset"


def parse_ffsubsync_shift(output: str) -> int | None:
    """Return ffsubsync's measured shift in ms, or None when no offset line is found.

    A real ``offset seconds: 0.000`` returns 0; None means the output could
    not be read and the run must be treated as a failed sync.
    """
    match = _SHIFT_RE.search(output or "")
    if not match:
        return None
    try:
        return round(float(match.group(1)) * 1000)
    except ValueError:
        return None
