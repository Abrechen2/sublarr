"""Does a subtitle file hold any subtitle line?

One answer for every place that asks — the wanted scan, extraction coverage
and the format cleanup each had their own copy (audit #61 A21): an empty or
header-only ``.de.ass`` counted as an existing subtitle for the wanted scan,
so the episode was never searched, while the cleanup already called the same
file unusable.
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

_CHUNK_BYTES = 65536
#: The marker may straddle two chunks; keep this many bytes of the previous one.
_OVERLAP = 32
#: Subtitles arrive as UTF-8/ANSI or UTF-16 (with or without BOM); the marker
#: is searched in each, so a valid UTF-16 file is not taken for empty (#63).
_ENCODINGS = ("utf-8", "utf-16-le", "utf-16-be")


def has_subtitle_lines(path: str, *, unreadable: bool = False) -> bool:
    """True when ``path`` holds at least one subtitle line.

    ASS/SSA need a ``Dialogue:`` event, SRT/VTT (and anything else) a cue
    arrow. The whole file is read if needed: embedded ``[Fonts]`` can push
    the first event far past any fixed sample. ``unreadable`` is the answer
    for a file that cannot be opened — callers that would delete or replace
    on "no lines" keep the default False, callers that would re-download on
    it pass True.
    """
    ext = os.path.splitext(path)[1].lower()
    text = "Dialogue:" if ext in (".ass", ".ssa") else "-->"
    markers = [text.encode(encoding) for encoding in _ENCODINGS]
    try:
        with open(path, "rb") as fh:
            tail = b""
            while chunk := fh.read(_CHUNK_BYTES):
                window = tail + chunk
                if any(marker in window for marker in markers):
                    return True
                tail = chunk[-_OVERLAP:]
    except OSError as exc:
        logger.warning("Cannot read %s to check for subtitle lines: %s", path, exc)
        return unreadable
    return False
