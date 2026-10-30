"""Hearing-impaired tag removal for subtitle files.

Removes HI markers like [music], (gasps), SPEAKER LABELS:, and music symbols
from subtitle text. Inspired by Bazarr/SubZero HI-removal patterns.
"""

import re

# Square brackets hold no dialogue in a subtitle: whatever is inside is a
# marker, in any language and any case ("[HERMES stöhnt]", "[Gelächter]").
_SQUARE_BRACKETS = re.compile(r"\[[^\[\]\n]{1,80}\]")
# Round brackets also carry asides, so only a lowercase or all-caps content
# is a marker; decided per match so umlauts and accents count as letters.
_ROUND_BRACKETS = re.compile(r"\(([^()\n]{1,80})\)")
_SPEAKER_LABEL = re.compile(r"^([^\W\d_][^\W\d_ ]*(?: [^\W\d_]+){0,2}):\s+", re.MULTILINE)


def _round_marker(match: re.Match) -> str:
    inner = match.group(1).strip()
    letters = [c for c in inner if c.isalpha()]
    if letters and (letters[0].islower() or all(c.isupper() for c in letters)):
        return ""
    return match.group(0)


def _speaker_label(match: re.Match) -> str:
    return "" if match.group(1).isupper() else match.group(0)


# Compiled HI patterns for performance
_HI_PATTERNS = [
    # Square brackets: [music], [door slams], [laughing]
    re.compile(r"\[(?:music|♪|♫)[^\]]*\]", re.IGNORECASE),
    re.compile(r"\[[A-Z][A-Z\s,.\'\-]+\]"),  # [DOOR SLAMS]
    re.compile(r"\[[a-z][a-z\s,.\'\-]+\]"),  # [laughing]
    # Round brackets: (gasps), (music playing)
    re.compile(r"\((?:music|♪|♫)[^\)]*\)", re.IGNORECASE),
    re.compile(r"\([A-Z][A-Z\s,.\'\-]+\)"),  # (GASPS)
    re.compile(r"\([a-z][a-z\s,.\'\-]+\)"),  # (sighs)
    # Music symbols: ♪ text ♪
    re.compile(r"♪[^♪]*♪"),
    re.compile(r"♫[^♫]*♫"),
    re.compile(r"^♪.*$", re.MULTILINE),
    re.compile(r"^♫.*$", re.MULTILINE),
    # Speaker labels: JOHN:, MAN 1:
    re.compile(r"^[A-Z][A-Z\s]{1,20}:\s*", re.MULTILINE),
    # Standalone music symbols
    re.compile(r"^[\s]*[♪♫]+[\s]*$", re.MULTILINE),
]


def remove_hi_markers(text: str) -> str:
    """Remove HI markers from subtitle text.

    Applies all HI patterns, then cleans up leftover whitespace.
    """
    result = text
    for pattern in _HI_PATTERNS:
        result = pattern.sub("", result)
    result = _SQUARE_BRACKETS.sub("", result)
    result = _ROUND_BRACKETS.sub(_round_marker, result)
    result = _SPEAKER_LABEL.sub(_speaker_label, result)
    if re.fullmatch(r"\s*\([^()\n]{1,80}\)\s*", result):
        result = ""  # a cue that is nothing but an aside: "(Seufzt)"

    # Clean up: collapse multiple spaces, strip lines
    result = re.sub(r"  +", " ", result)
    # Remove blank lines
    lines = [line.strip() for line in result.split("\n")]
    lines = [line for line in lines if line]
    return "\n".join(lines)


def remove_hi_from_srt(content: str) -> str:
    """Process entire SRT content, removing HI markers from dialog text.

    Preserves SRT structure (sequence numbers, timestamps) but removes
    HI markers from the text portions.
    """
    blocks = content.strip().split("\n\n")
    cleaned_blocks = []

    for block in blocks:
        lines = block.split("\n")
        if len(lines) < 3:
            cleaned_blocks.append(block)
            continue

        # First line = sequence number, second = timestamp, rest = text
        seq = lines[0]
        timestamp = lines[1]
        text = "\n".join(lines[2:])

        cleaned_text = remove_hi_markers(text)
        if cleaned_text.strip():
            cleaned_blocks.append(f"{seq}\n{timestamp}\n{cleaned_text}")
        # If text is empty after removal, skip the entire block

    return "\n\n".join(cleaned_blocks)


def remove_hi_from_ass_events(texts: list[str]) -> list[str]:
    """Process ASS dialog texts (tags already extracted), removing HI markers.

    Args:
        texts: List of clean text strings (ASS tags already extracted)

    Returns:
        List of cleaned text strings with HI markers removed
    """
    return [remove_hi_markers(text) for text in texts]
