# backend/common_fixes.py
"""Common subtitle fix functions. Stub — full implementation in Task 3."""

import re

from subtitle_types import Change, _ms_to_str

_WATERMARK = re.compile(
    r"downloaded\s+from|opensubtitles|subscene|synced\s+by|subtitles\s+by|www\.",
    re.IGNORECASE,
)


def apply_common_fixes(subs, options: dict) -> list[Change]:
    """Stub with minimal watermark detection for Task 1 tests.

    Full implementation added in Task 3.
    """
    changes = []
    to_remove = []
    for i, event in enumerate(subs.events):
        text = event.plaintext.strip()
        if options.get("watermark_removal", True) and _WATERMARK.search(text):
            ts = f"{_ms_to_str(event.start)} --> {_ms_to_str(event.end)}"
            changes.append(Change(i, ts, text, "", "common_fixes"))
            to_remove.append(i)
    for i in sorted(to_remove, reverse=True):
        del subs.events[i]
    return changes
