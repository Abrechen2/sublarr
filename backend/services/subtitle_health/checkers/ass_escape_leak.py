"""Detect literal ASS escape codes (\\N, \\n, \\h) and leaked override tags.

Runs on RAW bytes (never -f srt output). \\N at line end and consecutive \\N
are handled; doubly-escaped \\\\N is ignored.

Only SRT-like codecs are scanned: \\N is valid ASS/SSA syntax, so scanning
those codecs would produce false positives on every clean embedded track.
"""

from __future__ import annotations

import re

from services.subtitle_health.models import (
    Issue,
    IssueType,
    Severity,
    TargetKind,
)
from services.subtitle_health.text_utils import (
    ASS_ESCAPE_RE,
    decode_with_confidence,
    extract_cue_text_srt,
)

# Codecs where \\N is NOT valid syntax and therefore signals a leak.
_SRT_LIKE = frozenset({"srt", "subrip", "webvtt", "text"})
# Leaked ASS override block: only {\...}, never arbitrary {...}.
_TAG_RE = re.compile(r"\{\\[^}\r\n]{1,120}\}")


def detect(ctx) -> list[Issue]:
    issues: list[Issue] = []
    for t in ctx.targets:
        if not t.raw:
            continue
        if (t.codec or "").lower() not in _SRT_LIKE:
            continue
        text, _enc, _conf = decode_with_confidence(t.raw)
        cue_text = extract_cue_text_srt(text)

        escapes = ASS_ESCAPE_RE.findall(cue_text)
        tags = _TAG_RE.findall(cue_text)
        if not escapes and not tags:
            continue

        snippets = [m.group(0) for m in list(ASS_ESCAPE_RE.finditer(cue_text))[:3]]
        if not snippets:
            snippets = tags[:3]

        # Provide a little context around the first escape for the UI.
        first = ASS_ESCAPE_RE.search(cue_text)
        if first:
            lo = max(0, first.start() - 25)
            hi = min(len(cue_text), first.end() + 10)
            snippets = [cue_text[lo:hi]] + snippets[1:3]

        severity = Severity.CONFIRMED if escapes else Severity.SUSPICIOUS
        issues.append(
            Issue(
                type=IssueType.ASS_ESCAPE_LEAK,
                severity=severity,
                episode_id=ctx.episode_id,
                target_kind=t.kind,
                target_path=t.path,
                stream_index=t.stream_index,
                lang=t.lang,
                count=len(escapes) + len(tags),
                snippets=snippets,
                raw_hash="",  # filled by scan.py after hashing the raw bytes
                fixable=True,
                suggested_fix=(
                    "repair_escapes" if t.kind == TargetKind.SIDECAR else "extract_clean_sidecar"
                ),
            )
        )
    return issues
