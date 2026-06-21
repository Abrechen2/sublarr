"""Detect embedded subtitle streams whose language tag disagrees with content."""

from __future__ import annotations

from services.subtitle_health.checkers.language_mislabel import _detect_language, _to2
from services.subtitle_health.models import Issue, IssueType, Severity, TargetKind

_HIGH_CONF = 0.90
_MED_CONF = 0.70


def detect(ctx) -> list[Issue]:
    issues: list[Issue] = []
    for t in ctx.targets:
        if t.kind != TargetKind.EMBEDDED or not t.raw:
            continue
        declared = _to2(t.lang)
        detected, conf = _detect_language(t.raw)
        if detected is None or declared == "und":
            continue
        if detected != declared and conf >= _MED_CONF:
            issues.append(
                Issue(
                    type=IssueType.CONTAINER_METADATA_DRIFT,
                    severity=Severity.CONFIRMED if conf >= _HIGH_CONF else Severity.SUSPICIOUS,
                    episode_id=ctx.episode_id,
                    target_kind=t.kind,
                    target_path=t.path,
                    stream_index=t.stream_index,
                    lang=declared,
                    count=1,
                    snippets=[
                        f"stream tagged {declared!r}, content detected {detected!r} (conf {conf:.2f})"
                    ],
                    raw_hash="",
                    fixable=True,
                    suggested_fix="metadata_correction",
                )
            )
    return issues
