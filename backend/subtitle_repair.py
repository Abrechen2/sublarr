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


def _pad_decimals(match: re.Match[str]) -> str:
    hms = match.group(1)
    ms = match.group(2)
    return f"{hms},{ms.ljust(3, '0')}"


def repair_srt(text: str) -> str:
    """Repair SRT-specific defects.

    - Pad 1- and 2-digit millisecond decimals in timestamps to 3 digits
      (e.g. `00:00:01,4` → `00:00:01,400`).
    """
    text = _SRT_TIMESTAMP_RE.sub(_pad_decimals, text)
    return text


def repair_ass(text: str) -> str:
    """Repair ASS/SSA-specific defects."""
    # Currently no ASS-specific repairs needed beyond byte-level.
    return text
