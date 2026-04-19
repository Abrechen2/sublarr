"""Pure subtitle repair functions.

Called by every save path (provider download, embedded extract, post-translate)
to normalize content before writing to disk. Pure — no I/O, no DB, no side
effects. Any defect it can't repair returns the input unchanged (caller
decides whether to fall back to the unrepaired bytes).

Five defect classes handled:
  1. BOM at file start (UTF-8 BOM 0xEF 0xBB 0xBF)
  2. Wrong newline encoding (CRLFCRLF, lone CR)
  3. Invalid decimals in timestamps (e.g. `00:00:01,4`)
  4. Overlapping cues in SRT
  5. Encoding mis-detection (content labeled UTF-8 but actually Windows-1252)

Public API:
  - repair_bytes(data: bytes, fmt: str) -> bytes
  - repair_srt(text: str) -> str
  - repair_ass(text: str) -> str
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

_UTF8_BOM = b"\xef\xbb\xbf"


def repair_bytes(data: bytes, fmt: str) -> bytes:
    """Entry point for byte-level repair (decode, repair, re-encode).

    Strips BOM, detects encoding with fallbacks, normalizes newlines, then
    dispatches to format-specific text repair.
    """
    if not data:
        return data

    # Strip UTF-8 BOM
    if data.startswith(_UTF8_BOM):
        data = data[len(_UTF8_BOM) :]

    # Decode — try UTF-8 first, then Windows-1252 (common SRT encoding),
    # then chardet as last resort.
    text = _decode_robust(data)

    # Normalize newlines to LF
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    # Collapse duplicated blank lines that the newline fix may have introduced
    text = re.sub(r"\n{3,}", "\n\n", text)

    # Format-specific repair
    fmt_lower = (fmt or "").lower()
    if fmt_lower in ("srt", "vtt"):
        text = repair_srt(text)
    elif fmt_lower in ("ass", "ssa"):
        text = repair_ass(text)

    return text.encode("utf-8")


def _decode_robust(data: bytes) -> str:
    """Decode bytes to str with fallback strategy."""
    for encoding in ("utf-8-sig", "utf-8"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            pass

    # Try chardet as last resort
    try:
        import chardet  # vendored transitive dep from B1

        detected = chardet.detect(data) or {}
        encoding = detected.get("encoding")
        if encoding:
            try:
                return data.decode(encoding, errors="replace")
            except (LookupError, UnicodeDecodeError):
                pass
    except ImportError:
        pass

    # Ultimate fallback
    return data.decode("windows-1252", errors="replace")


_SRT_TIMESTAMP_RE = re.compile(r"(\b\d{2}:\d{2}:\d{2}),(\d{1,3})\b")

_CUE_LINE_RE = re.compile(
    r"(\d{2}):(\d{2}):(\d{2}),(\d{3})\s*-->\s*(\d{2}):(\d{2}):(\d{2}),(\d{3})"
)


def _pad_decimals(match: re.Match[str]) -> str:
    hms = match.group(1)
    ms = match.group(2)
    return f"{hms},{ms.ljust(3, '0')}"


def _ts_to_ms(h: int, m: int, s: int, ms: int) -> int:
    return h * 3600000 + m * 60000 + s * 1000 + ms


def _ms_to_ts(ms_total: int) -> str:
    if ms_total < 0:
        ms_total = 0
    h, rem = divmod(ms_total, 3600000)
    m, rem = divmod(rem, 60000)
    s, ms = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _fix_overlaps_srt(text: str) -> str:
    """Scan cue lines in document order; clamp overlapping ends."""
    matches = list(_CUE_LINE_RE.finditer(text))
    if len(matches) < 2:
        return text

    replacements: list[tuple[int, int, str]] = []  # (start, end, replacement)
    for i, match in enumerate(matches[:-1]):
        h1, m1, s1, ms1, h2, m2, s2, ms2 = map(int, match.groups())
        next_match = matches[i + 1]
        nh1, nm1, ns1, nms1 = map(int, next_match.groups()[:4])

        cur_end_ms = _ts_to_ms(h2, m2, s2, ms2)
        next_start_ms = _ts_to_ms(nh1, nm1, ns1, nms1)

        if cur_end_ms <= next_start_ms:
            continue  # no overlap

        new_end_ms = next_start_ms - 1
        cur_start_ms = _ts_to_ms(h1, m1, s1, ms1)
        if new_end_ms <= cur_start_ms:
            continue  # Would produce zero/negative duration — skip fix

        new_ts = f"{_ms_to_ts(cur_start_ms)} --> {_ms_to_ts(new_end_ms)}"
        replacements.append((match.start(), match.end(), new_ts))

    # Apply replacements back-to-front to preserve earlier offsets
    for start, end, repl in reversed(replacements):
        text = text[:start] + repl + text[end:]

    return text


def repair_srt(text: str) -> str:
    """Repair SRT-specific defects.

    - Pad 1- and 2-digit millisecond decimals.
    - Clamp overlapping cue ends to (next_start - 1ms).
    """
    text = _SRT_TIMESTAMP_RE.sub(_pad_decimals, text)
    text = _fix_overlaps_srt(text)
    return text


def repair_ass(text: str) -> str:
    """Repair ASS/SSA-specific defects."""
    # Currently no ASS-specific repairs needed beyond byte-level.
    return text
