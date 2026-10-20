"""Text decoding and cue-text extraction for health analysis (read-only)."""

from __future__ import annotations

import re

# ASS override blocks and escape codes (used for ANALYSIS stripping only).
# ASS_ESCAPE_RE is also imported by checkers/ass_escape_leak.py — single source of truth.
_ASS_TAG_RE = re.compile(r"\{\\[^}]*\}")
ASS_ESCAPE_RE = re.compile(r"(?<!\\)\\[Nnh]")
_SRT_TS_RE = re.compile(r"^\d+\s*$|-->")

# How far a decode can be trusted, by what picked its encoding. The re-encoder
# rewrites a file only at 0.5 or more, so a chardet guess (which reads a short
# German file as Big5) is reported but never written back.
_CONFIDENCE_BY_BASIS = {"hint": 0.8, "language": 0.8, "chardet": 0.4, "fallback": 0.2}


def decode_with_confidence(data: bytes, language: str | None = None) -> tuple[str, str, float]:
    """Decode bytes, returning (text, encoding, confidence in [0,1]).

    Same detection as the download path (``subtitle_encoding``): BOM, UTF-8,
    the codepages of ``language``, then chardet. Confidence reflects both the
    evidence and how clean the decode was (replacement-char rate).
    """
    from subtitle_encoding import detect_encoding

    text, encoding, basis = detect_encoding(data, language=language)
    clean = max(0.0, 1.0 - text.count("\ufffd") / max(1, len(text)))
    return text, encoding, clean * _CONFIDENCE_BY_BASIS.get(basis, 1.0)


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
