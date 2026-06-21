"""Detect empty or suspiciously small full-subtitle targets."""

from __future__ import annotations

import logging

from services.subtitle_health.models import Issue, IssueType, Severity
from services.subtitle_health.text_utils import decode_with_confidence

logger = logging.getLogger(__name__)

_MIN_CUES = 10  # below this, a track tagged as a full sub is suspect


def _count_cues(raw: bytes) -> int:
    import pysubs2

    text, _enc, _conf = decode_with_confidence(raw)
    try:
        subs = pysubs2.SSAFile.from_string(text)
    except Exception:
        return 0
    return sum(1 for ev in subs.events if not ev.is_comment and ev.text.strip())


def detect(ctx) -> list[Issue]:
    issues: list[Issue] = []
    for t in ctx.targets:
        if t.forced:
            continue
        n = _count_cues(t.raw) if t.raw else 0
        if n == 0:
            severity = Severity.CONFIRMED
        elif n < _MIN_CUES:
            severity = Severity.SUSPICIOUS
        else:
            continue
        issues.append(
            Issue(
                type=IssueType.EMPTY_OR_TINY,
                severity=severity,
                episode_id=ctx.episode_id,
                target_kind=t.kind,
                target_path=t.path,
                stream_index=t.stream_index,
                lang=t.lang,
                count=n,
                snippets=[f"{n} cues"],
                raw_hash="",
                fixable=False,
                suggested_fix="trash_sidecar" if n == 0 else None,
            )
        )
    return issues
