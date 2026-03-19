# backend/common_fixes.py
"""All common subtitle fix functions.

apply_common_fixes(subs, options) applies enabled fixes in sequence and returns
a list of Change objects. subs is a pysubs2.SSAFile modified in place.
"""

from __future__ import annotations

import re
import textwrap

import pysubs2

from subtitle_types import Change, _ms_to_str

_WATERMARK_PATTERNS = [
    re.compile(r"downloaded\s+from", re.IGNORECASE),
    re.compile(r"synced\s+by", re.IGNORECASE),
    re.compile(r"subtitles\s+by", re.IGNORECASE),
    re.compile(r"www\.", re.IGNORECASE),
    re.compile(r"opensubtitles", re.IGNORECASE),
    re.compile(r"subscene", re.IGNORECASE),
    re.compile(r"subf2m", re.IGNORECASE),
    re.compile(r"yifysubtitles", re.IGNORECASE),
]


def apply_common_fixes(subs: pysubs2.SSAFile, options: dict) -> list[Change]:
    """Apply all enabled common fixes to subs (in place). Return list of Changes."""
    defaults = {
        "utf8_conversion": True,
        "linebreak_normalization": True,
        "whitespace_cleanup": True,
        "empty_event_removal": True,
        "ocr_fixes": False,
        "fix_uppercase": False,
        "watermark_removal": True,
        "quote_normalization": True,
        "apostrophe_normalization": True,
        "em_dash_correction": True,
        "crocodile_brackets": True,
        "multiple_spaces": True,
        "interpunction_spacing": True,
        "consecutive_dots": True,
        "long_line_wrap": False,
        "wrap_chars": 42,
        "short_line_merge": False,
        "overlap_fix": True,
        "min_display_time": False,
        "min_ms": 800,
    }
    opts = {**defaults, **options}
    changes: list[Change] = []

    # Determine if fix_uppercase should apply: >60% of non-empty lines are all-caps
    _should_fix_uppercase = False
    if opts["fix_uppercase"]:
        non_empty = [e.plaintext.strip() for e in subs.events if e.plaintext.strip()]
        if non_empty:
            caps_count = sum(1 for t in non_empty if t == t.upper() and any(c.isalpha() for c in t))
            _should_fix_uppercase = (caps_count / len(non_empty)) > 0.6

    to_remove: list[int] = []

    for i, event in enumerate(subs.events):
        if event.is_comment:
            continue

        original = event.text
        text = original

        # Watermark removal
        if opts["watermark_removal"]:
            plain = event.plaintext.strip()
            if any(p.search(plain) for p in _WATERMARK_PATTERNS):
                ts = f"{_ms_to_str(event.start)} --> {_ms_to_str(event.end)}"
                changes.append(Change(i, ts, plain, "", "common_fixes"))
                to_remove.append(i)
                continue

        # Em-dash correction: -- → —
        if opts["em_dash_correction"]:
            text = text.replace("--", "\u2014")

        # Quote normalization: curly → straight
        if opts["quote_normalization"]:
            text = text.replace("\u201c", '"').replace("\u201d", '"')
            text = text.replace("\u2018", "'").replace("\u2019", "'")

        # Apostrophe normalization: '' → "
        if opts["apostrophe_normalization"]:
            text = text.replace("''", '"')

        # Crocodile brackets: >> at line start
        if opts["crocodile_brackets"]:
            text = re.sub(r"^>>\s*", "", text, flags=re.MULTILINE)

        # Multiple spaces
        if opts["multiple_spaces"]:
            text = re.sub(r"  +", " ", text)

        # Consecutive dots: .... → ...
        if opts["consecutive_dots"]:
            text = re.sub(r"\.{4,}", "...", text)

        # Interpunction spacing: remove space before , . ! ?
        if opts["interpunction_spacing"]:
            text = re.sub(r" ([,\.!\?])", r"\1", text)

        # Fix uppercase: apply sentence case
        if _should_fix_uppercase:
            plain = event.plaintext.strip()
            if plain and plain == plain.upper() and any(c.isalpha() for c in plain):
                text = ". ".join(s.strip().capitalize() for s in plain.split(". "))

        # Long line wrap
        if opts["long_line_wrap"]:
            wrap_chars = opts["wrap_chars"]
            plain = event.plaintext.strip()
            if len(plain) > wrap_chars:
                wrapped = textwrap.fill(plain, width=wrap_chars, break_long_words=False)
                # Use \n as line separator (works for both SRT and ASS)
                text = wrapped.replace("\n", "\n")

        # Record ONE change per event with the final modified_text
        if text != original:
            ts = f"{_ms_to_str(event.start)} --> {_ms_to_str(event.end)}"
            plain_original = event.plaintext.strip()
            event.text = text
            plain_modified = event.plaintext.strip()
            changes.append(Change(i, ts, plain_original, plain_modified, "common_fixes"))

    # Remove watermarked events in reverse order
    for i in sorted(to_remove, reverse=True):
        del subs.events[i]

    # Short line merge: combine adjacent short events (within 500ms gap, both under 20 chars)
    if opts["short_line_merge"]:
        i = 0
        while i < len(subs.events) - 1:
            a = subs.events[i]
            b = subs.events[i + 1]
            gap = b.start - a.end
            if gap <= 500 and len(a.plaintext.strip()) < 20 and len(b.plaintext.strip()) < 20:
                ts = f"{_ms_to_str(a.start)} --> {_ms_to_str(a.end)}"
                merged_text = a.text.rstrip() + "\n" + b.text.lstrip()
                changes.append(Change(i, ts, a.plaintext.strip(), merged_text, "common_fixes"))
                a.text = merged_text
                a.end = b.end
                del subs.events[i + 1]
            else:
                i += 1

    # Overlap fix: adjust end time of event[i] when it overlaps event[i+1]
    if opts["overlap_fix"]:
        for i in range(len(subs.events) - 1):
            if subs.events[i].end > subs.events[i + 1].start:
                original_end = subs.events[i].end
                subs.events[i].end = subs.events[i + 1].start - 1
                ts = f"{_ms_to_str(subs.events[i].start)} --> {_ms_to_str(original_end)}"
                changes.append(
                    Change(
                        i,
                        ts,
                        f"end={original_end}ms",
                        f"end={subs.events[i].end}ms",
                        "common_fixes",
                    )
                )

    # Minimum display time
    if opts["min_display_time"]:
        min_ms = opts["min_ms"]
        for i, event in enumerate(subs.events):
            duration = event.end - event.start
            if duration < min_ms:
                ts = f"{_ms_to_str(event.start)} --> {_ms_to_str(event.end)}"
                changes.append(
                    Change(
                        i,
                        ts,
                        f"duration={duration}ms",
                        f"duration={min_ms}ms",
                        "common_fixes",
                    )
                )
                event.end = event.start + min_ms

    return changes
