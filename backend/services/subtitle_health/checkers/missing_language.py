"""Report configured target languages that have no subtitle present (info)."""

from __future__ import annotations

from services.subtitle_health.checkers.language_mislabel import _to2
from services.subtitle_health.models import Issue, IssueType, Severity, TargetKind


def detect(ctx) -> list[Issue]:
    wanted = {_to2(lang) for lang in (ctx.target_languages or []) if lang}
    if not wanted:
        return []
    present = {_to2(t.lang) for t in ctx.targets if t.raw}
    missing = sorted(wanted - present - {"und"})
    issues: list[Issue] = []
    for lang in missing:
        issues.append(
            Issue(
                type=IssueType.MISSING_LANGUAGE,
                severity=Severity.INFO,
                episode_id=ctx.episode_id,
                target_kind=TargetKind.SIDECAR,
                target_path=ctx.video_path,
                stream_index=None,
                lang=lang,
                count=1,
                snippets=[f"no {lang!r} subtitle present"],
                raw_hash="",
                fixable=False,
                suggested_fix=None,
            )
        )
    return issues
