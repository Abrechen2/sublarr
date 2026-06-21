"""Text decoding and cue-text extraction for health analysis (read-only)."""

from __future__ import annotations

import re

# ASS override blocks and escape codes (used for ANALYSIS stripping only).
# ASS_ESCAPE_RE is also imported by checkers/ass_escape_leak.py — single source of truth.
_ASS_TAG_RE = re.compile(r"\{\\[^}]*\}")
ASS_ESCAPE_RE = re.compile(r"(?<!\\)\\[Nnh]")
_SRT_TS_RE = re.compile(r"^\d+\s*$|-->")

# Decode candidates in priority order after UTF-8.
_FALLBACK_ENCODINGS = ("cp1252", "latin-1")


def decode_with_confidence(data: bytes) -> tuple[str, str, float]:
    """Decode bytes, returning (text, encoding, confidence in [0,1]).

    BOM -> UTF-8 -> fallback codecs. Confidence reflects how clean the decode
    was (replacement-char rate). Mojibake/encoding checks build on this.
    """
    if data.startswith(b"\xef\xbb\xbf"):
        text = data[3:].decode("utf-8", errors="replace")
        rep = text.count("�")
        conf = max(0.0, 1.0 - rep / max(1, len(text)))
        return text, "utf-8-sig", conf
    try:
        return data.decode("utf-8"), "utf-8", 1.0
    except UnicodeDecodeError:
        pass
    for enc in _FALLBACK_ENCODINGS:
        try:
            return data.decode(enc), enc, 0.6
        except UnicodeDecodeError:
            continue
    text = data.decode("utf-8", errors="replace")
    rep = text.count("�")
    conf = max(0.0, 1.0 - rep / max(1, len(text)))
    return text, "utf-8-replace", conf


def strip_ass_tags(text: str) -> str:
    """Remove ASS override blocks and convert escape codes to spaces (analysis)."""
    text = _ASS_TAG_RE.sub("", text)
    text = ASS_ESCAPE_RE.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip()


def extract_cue_text_srt(raw_text: str) -> str:
    """Return just the spoken text of an SRT/VTT: drop indices and timestamps."""
    lines = []
    for line in raw_text.splitlines():
        s = line.strip()
        if not s or _SRT_TS_RE.search(s) or s.upper().startswith("WEBVTT"):
            continue
        lines.append(s)
    return "\n".join(lines)
