"""ASS karaoke syllable parser (Plan B8 Task 9).

Walks the raw text of an ASS dialogue event looking for `\\k<cs>`,
`\\K<cs>`, `\\kf<cs>`, and `\\ko<cs>` override tags. Each tag opens a
new syllable whose duration is the tag's centisecond value (1 cs = 10
ms); the text that follows the closing brace until the next karaoke
tag is the syllable's visible text.

Pure module — no pysubs2 dependency, no I/O. Imported by
``routes.tools.validation.parse_cues`` which calls it for every ASS
event so the frontend's ``AssKaraokeOverlay`` can paint per-syllable
ticks on the active waveform region.

Note: we DISPLAY syllable structure, we don't re-time it. Editing
karaoke remains Aegisub's domain.
"""

from __future__ import annotations

import re
from typing import TypedDict

# Match any karaoke variant ( \k / \K / \kf / \ko ) followed by an integer
# duration in centiseconds. The variant letters are captured for forward
# compatibility, even though we treat them all identically for timing.
_KARAOKE_TAG_RE = re.compile(r"\\(k[fo]?|K)(\d+)")

# Strip any remaining override block once we've extracted karaoke timings.
# ASS override blocks are wrapped in `{...}` and may contain anything from
# `\b1` (bold) to `\pos(50,200)`. We just remove the whole block.
_OVERRIDE_BLOCK_RE = re.compile(r"\{[^}]*\}")


class Syllable(TypedDict):
    text: str
    start: float
    end: float


def parse_ass_syllables(raw_text: str) -> list[Syllable]:
    """Return the karaoke syllables encoded in ``raw_text``.

    ``raw_text`` is the ASS event's raw text WITH override tags intact
    (i.e. ``event.text`` from pysubs2, NOT ``event.plaintext``).

    Returns an empty list when the event has no ``\\k`` / ``\\K`` /
    ``\\kf`` / ``\\ko`` tags. Otherwise each syllable carries:
      * ``text``: the visible characters of the syllable, with any
        non-karaoke override blocks stripped.
      * ``start``: offset from the cue start, in seconds.
      * ``end``: ``start + duration``.

    Pre-tag content (text before the first karaoke tag, e.g. a leading
    inline comment) is dropped because ASS doesn't render it as part of
    any syllable.
    """
    if not raw_text:
        return []

    # Split the text on karaoke tag boundaries. Each match yields one
    # `(variant, cs_str)` pair plus the chunk of text that follows it
    # until the next karaoke match (or end of string).
    matches = list(_KARAOKE_TAG_RE.finditer(raw_text))
    if not matches:
        return []

    syllables: list[Syllable] = []
    cursor_ms = 0.0

    for i, match in enumerate(matches):
        duration_cs = int(match.group(2))
        duration_ms = duration_cs * 10.0  # centiseconds → milliseconds

        # The visible text for this syllable starts AFTER the override
        # block this karaoke tag lived in (i.e. after the next `}` we
        # find at-or-after the tag). It runs until the start of the next
        # karaoke tag's override block — or end of text.
        block_close = raw_text.find("}", match.end())
        text_start = block_close + 1 if block_close != -1 else match.end()

        if i + 1 < len(matches):
            # Find the override block that holds the NEXT karaoke tag,
            # so we don't include its `{...}` in this syllable's text.
            next_match = matches[i + 1]
            next_block_open = raw_text.rfind("{", 0, next_match.start())
            text_end = next_block_open if next_block_open != -1 else next_match.start()
        else:
            text_end = len(raw_text)

        chunk = raw_text[text_start:text_end] if text_start <= text_end else ""
        # Strip any non-karaoke override blocks that may have been written
        # mid-syllable (e.g. `Bold{\b1}er`).
        text = _OVERRIDE_BLOCK_RE.sub("", chunk)

        syllables.append(
            {
                "text": text,
                "start": cursor_ms / 1000.0,
                "end": (cursor_ms + duration_ms) / 1000.0,
            }
        )
        cursor_ms += duration_ms

    return syllables
