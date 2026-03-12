"""Staff credit line detection and removal for subtitle files.

Detects credits-only subtitle events using four independent heuristics:
1. Role marker annotations: (Translator), (QC), OP Theme, ED Theme, etc.
2. Credit prefix patterns: Credits:, Staff:, Translation:, etc.
3. Duration heuristic: events in the final N seconds (configurable via
   SUBLARR_CREDIT_THRESHOLD_SEC, default 90) without conversational punctuation.
4. Isolated capitalized names: exactly two title-case words, ≤40 chars.

Inspired by hi_remover.py — same structure, pure text transformation, no DB access.
"""

import re

# ─── Compiled patterns ────────────────────────────────────────────────────────

# Heuristic 1a: parenthetical role annotations anywhere in text
_ROLE_MARKERS = re.compile(
    r"\((Translator|TLC|Timer|QC|Encoder|Raw Provider|TS|KFX)\)",
    re.IGNORECASE,
)

# Heuristic 1b: standalone thematic labels (full line match)
_THEME_LABELS = re.compile(
    r"^(OP|ED|OP Theme|ED Theme|Staff Roll)$",
    re.IGNORECASE,
)

# Heuristic 2: credit prefix patterns (line starts with these)
_CREDIT_PREFIXES = re.compile(
    r"^(Credits|Staff|Translation|Timing|Quality Check|Cast)\s*:",
    re.IGNORECASE,
)

# Heuristic 4: exactly two title-case words, no other characters, ≤40 chars
_ISOLATED_NAME = re.compile(r"^[A-Z][a-z]+\s[A-Z][a-z]+$")


def _get_credit_threshold_ms() -> int:
    """Return the credits region threshold in milliseconds."""
    import os
    # Try environment variable first (for test flexibility)
    env_val = os.environ.get("SUBLARR_CREDIT_THRESHOLD_SEC")
    if env_val:
        try:
            threshold_sec = int(env_val)
        except ValueError:
            threshold_sec = 90
    else:
        # Fall back to config (once credit_threshold_sec field is added in Task 3)
        try:
            from config import get_settings
            threshold_sec = getattr(get_settings(), "credit_threshold_sec", 90)
        except Exception:
            threshold_sec = 90
    return int(threshold_sec) * 1000


def _is_credit_line(text: str, total_end_ms: int, event_start_ms: int) -> bool:
    """Return True if a subtitle line is a credits-only line.

    Args:
        text: The plain text content of the subtitle event (no ASS tags).
        total_end_ms: End time of the last dialogue event in the file (ms).
        event_start_ms: Start time of this event (ms).
    """
    stripped = text.strip()
    if not stripped:
        return False

    # Heuristic 1a: role marker annotation
    if _ROLE_MARKERS.search(stripped):
        return True

    # Heuristic 1b: standalone thematic label
    if _THEME_LABELS.match(stripped):
        return True

    # Heuristic 2: credit prefix
    if _CREDIT_PREFIXES.match(stripped):
        return True

    # Heuristic 3: duration region — but NOT if line has ? or ! (dialogue guard)
    threshold_ms = _get_credit_threshold_ms()
    if total_end_ms > 0 and event_start_ms >= (total_end_ms - threshold_ms):
        if "?" not in stripped and "!" not in stripped:
            # Combined with heuristic 4 check below to reduce false positives.
            # In the credits region, isolated names are very likely credits.
            if len(stripped) <= 40 and not re.search(r"[,\.;:\(\)\[\]]", stripped):
                return True

    # Heuristic 4: isolated capitalized names (outside credits region too)
    if len(stripped) <= 40 and _ISOLATED_NAME.match(stripped):
        return True

    return False


def remove_credits_from_srt(content: str) -> tuple[str, int]:
    """Remove credit events from SRT content.

    Returns:
        (cleaned_content, removed_count)
    """
    blocks = content.strip().split("\n\n")
    kept: list[str] = []
    removed = 0

    # Determine total_end_ms from last block's end timestamp
    total_end_ms = _parse_srt_last_end_ms(content)

    for block in blocks:
        lines = block.strip().split("\n")
        if len(lines) < 3:
            kept.append(block)
            continue

        # SRT: line 0 = index, line 1 = timestamps, lines 2+ = text
        timestamp_line = lines[1]
        text = "\n".join(lines[2:])
        event_start_ms = _parse_srt_start_ms(timestamp_line)

        if _is_credit_line(text, total_end_ms, event_start_ms):
            removed += 1
        else:
            kept.append(block)

    return "\n\n".join(kept), removed


def remove_credits_from_ass(content: str) -> tuple[str, int]:
    """Remove credit Dialogue lines from ASS/SSA content.

    Returns:
        (cleaned_content, removed_count)
    """
    try:
        import pysubs2
    except ImportError:
        return content, 0

    subs = pysubs2.SSAFile.from_string(content)
    total_end_ms = max((e.end for e in subs if not e.is_comment), default=0)

    original_count = len(subs)
    kept = []
    for event in subs:
        if event.is_comment:
            kept.append(event)
            continue
        plain_text = event.plaintext.strip()
        if _is_credit_line(plain_text, total_end_ms, event.start):
            pass  # drop this event
        else:
            kept.append(event)

    subs.events = kept
    removed = original_count - len(kept)
    return subs.to_string(subs.format), removed


# ─── Helpers ──────────────────────────────────────────────────────────────────

_SRT_TIMESTAMP_RE = re.compile(
    r"(\d{2}):(\d{2}):(\d{2}),(\d{3})\s*-->\s*(\d{2}):(\d{2}):(\d{2}),(\d{3})"
)


def _parse_srt_start_ms(timestamp_line: str) -> int:
    m = _SRT_TIMESTAMP_RE.match(timestamp_line.strip())
    if not m:
        return 0
    h, min_, s, ms = int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4))
    return h * 3_600_000 + min_ * 60_000 + s * 1_000 + ms


def _parse_srt_last_end_ms(content: str) -> int:
    """Return the end time of the last SRT timestamp in the file."""
    last_ms = 0
    for m in _SRT_TIMESTAMP_RE.finditer(content):
        h = int(m.group(5))
        min_ = int(m.group(6))
        s = int(m.group(7))
        ms = int(m.group(8))
        end_ms = h * 3_600_000 + min_ * 60_000 + s * 1_000 + ms
        if end_ms > last_ms:
            last_ms = end_ms
    return last_ms
