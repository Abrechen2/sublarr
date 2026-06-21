"""Detect ASS-structured content inside an SRT/subrip-tagged target."""

from __future__ import annotations

import re

from services.subtitle_health.models import Issue, IssueType, Severity
from services.subtitle_health.text_utils import decode_with_confidence

_ASS_MARKERS = re.compile(r"^\s*(\[Script Info\]|\[V4\+? Styles\]|\[Events\]|Dialogue:)", re.M)
_SRT_CODECS = frozenset({"srt", "subrip"})


def detect(ctx) -> list[Issue]:
    issues: list[Issue] = []
    for t in ctx.targets:
        if not t.raw or (t.codec or "").lower() not in _SRT_CODECS:
            continue
        text, _enc, _conf = decode_with_confidence(t.raw)
        markers = _ASS_MARKERS.findall(text)
        if not markers:
            continue
        issues.append(
            Issue(
                type=IssueType.FORMAT_MISMATCH,
                severity=Severity.CONFIRMED,
                episode_id=ctx.episode_id,
                target_kind=t.kind,
                target_path=t.path,
                stream_index=t.stream_index,
                lang=t.lang,
                count=len(markers),
                snippets=[f"ASS structure in SRT-tagged target: {markers[0]!r}"],
                raw_hash="",
                fixable=True,
                suggested_fix="repair_escapes",
            )
        )
    return issues
