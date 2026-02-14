"""Hearing-impaired tag removal for subtitle files.

Removes HI markers like [music], (gasps), SPEAKER LABELS:, and music symbols
from subtitle text. Inspired by Bazarr/SubZero HI-removal patterns.
"""

import re

# Compiled HI patterns for performance
_HI_PATTERNS = [
    # Square brackets: [music], [door slams], [laughing]
    re.compile(r'\[(?:music|♪|♫)[^\]]*\]', re.IGNORECASE),
    re.compile(r'\[[A-Z][A-Z\s,.\'\-]+\]'),           # [DOOR SLAMS]
    re.compile(r'\[[a-z][a-z\s,.\'\-]+\]'),            # [laughing]

    # Round brackets: (gasps), (music playing)
    re.compile(r'\((?:music|♪|♫)[^\)]*\)', re.IGNORECASE),
    re.compile(r'\([A-Z][A-Z\s,.\'\-]+\)'),            # (GASPS)
    re.compile(r'\([a-z][a-z\s,.\'\-]+\)'),            # (sighs)

    # Music symbols: ♪ text ♪
    re.compile(r'♪[^♪]*♪'),
    re.compile(r'♫[^♫]*♫'),
    re.compile(r'^♪.*$', re.MULTILINE),
    re.compile(r'^♫.*$', re.MULTILINE),

    # Speaker labels: JOHN:, MAN 1:
    re.compile(r'^[A-Z][A-Z\s]{1,20}:\s*', re.MULTILINE),

    # Standalone music symbols
    re.compile(r'^[\s]*[♪♫]+[\s]*$', re.MULTILINE),
]


def remove_hi_markers(text: str) -> str:
    """Remove HI markers from subtitle text.

    Applies all HI patterns, then cleans up leftover whitespace.
    """
    result = text
    for pattern in _HI_PATTERNS:
        result = pattern.sub('', result)

    # Clean up: collapse multiple spaces, strip lines
    result = re.sub(r'  +', ' ', result)
    # Remove blank lines
    lines = [line.strip() for line in result.split('\n')]
    lines = [line for line in lines if line]
    return '\n'.join(lines)


def remove_hi_from_srt(content: str) -> str:
    """Process entire SRT content, removing HI markers from dialog text.

    Preserves SRT structure (sequence numbers, timestamps) but removes
    HI markers from the text portions.
    """
    blocks = content.strip().split('\n\n')
    cleaned_blocks = []

    for block in blocks:
        lines = block.split('\n')
        if len(lines) < 3:
            cleaned_blocks.append(block)
            continue

        # First line = sequence number, second = timestamp, rest = text
        seq = lines[0]
        timestamp = lines[1]
        text = '\n'.join(lines[2:])

        cleaned_text = remove_hi_markers(text)
        if cleaned_text.strip():
            cleaned_blocks.append(f"{seq}\n{timestamp}\n{cleaned_text}")
        # If text is empty after removal, skip the entire block

    return '\n\n'.join(cleaned_blocks)


def remove_hi_from_ass_events(texts: list[str]) -> list[str]:
    """Process ASS dialog texts (tags already extracted), removing HI markers.

    Args:
        texts: List of clean text strings (ASS tags already extracted)

    Returns:
        List of cleaned text strings with HI markers removed
    """
    return [remove_hi_markers(text) for text in texts]
