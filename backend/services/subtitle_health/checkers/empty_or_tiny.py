"""Detect empty or suspiciously small full-subtitle targets."""

from __future__ import annotations

import logging

from services.subtitle_health.models import Issue, IssueType, Severity, TargetKind
from services.subtitle_health.text_utils import decode_with_confidence

logger = logging.getLogger(__name__)

#: Fix action for a sparse full sidecar: no file is touched, the episode is
#: queued for a fresh search and the sparse file stays until a validated
#: replacement overwrites it.
REQUEUE_ACTION = "requeue_search"


def _count_cues(raw: bytes) -> int:
    import pysubs2

    text, _enc, _conf = decode_with_confidence(raw)
    try:
        subs = pysubs2.SSAFile.from_string(text)
    except Exception:
        return 0
    return sum(1 for ev in subs.events if not ev.is_comment and ev.text.strip())


def _sparse(raw: bytes, ctx, duration: list):
    """The sparse DialogueAssessment of ``raw``, or None.

    The verdict is ``subtitle_dialogue``'s, the same one the scanners, the
    search and the translator use. ``duration`` is a one-slot memo, so the
    video length is only looked up when the count leaves the verdict open.
    """
    from subtitle_dialogue import RATED_DIALOGUE_EVENTS, assess_content

    first = assess_content(raw, None)
    if first is None:
        return None
    if first.sparse_reason is None and first.dialogue_events < RATED_DIALOGUE_EVENTS:
        if not duration:
            import subtitle_plausibility

            duration.append(subtitle_plausibility.video_duration_s(ctx.video_path))
        if duration[0]:
            first = assess_content(raw, duration[0])
    return first if first is not None and first.sparse_reason else None


def detect(ctx) -> list[Issue]:
    issues: list[Issue] = []
    duration: list = []
    for t in ctx.targets:
        if t.forced:
            continue
        n = _count_cues(t.raw) if t.raw else 0
        sparse = None
        if n == 0:
            severity = Severity.CONFIRMED
        else:
            sparse = _sparse(t.raw, ctx, duration)
            if sparse is None:
                continue
            severity = Severity.SUSPICIOUS
            n = sparse.dialogue_events
        fix = None
        if sparse is None and t.kind == TargetKind.SIDECAR:
            fix = "trash_sidecar"
        elif sparse is not None and t.kind == TargetKind.SIDECAR:
            fix = REQUEUE_ACTION
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
                snippets=[sparse.sparse_reason if sparse else f"{n} cues"],
                raw_hash="",
                fixable=False,
                suggested_fix=fix,
            )
        )
    return issues
