"""Detect broken cue timing (suspicious only — never auto-fixed)."""

from __future__ import annotations

from services.subtitle_health.models import Issue, IssueType, Severity
from services.subtitle_health.text_utils import decode_with_confidence

_MAX_CPS = 45  # characters per second above this is implausible

# ASS/SSA legitimately overlaps cues (layers, signs, styled dialogue).
# Only SRT-like line-sequential formats treat overlap as an error.
_OVERLAP_CODECS = frozenset({"srt", "subrip", "webvtt", "text"})


def _events(raw: bytes):
    import pysubs2

    text, _enc, _conf = decode_with_confidence(raw)
    try:
        subs = pysubs2.SSAFile.from_string(text)
    except Exception:
        return None
    return [ev for ev in subs.events if not ev.is_comment and ev.plaintext.strip()]


def detect(ctx) -> list[Issue]:
    issues: list[Issue] = []
    for t in ctx.targets:
        if not t.raw:
            continue
        events = _events(t.raw)
        if not events:
            continue
        problems: list[str] = []
        check_overlap = (t.codec or "").lower() in _OVERLAP_CODECS
        max_end = None
        for ev in events:
            dur_ms = ev.end - ev.start
            if dur_ms <= 0:
                problems.append(f"non-positive duration at {ev.start}ms")
            else:
                cps = len(ev.plaintext) / (dur_ms / 1000.0)
                if cps > _MAX_CPS:
                    problems.append(f"CPS {cps:.0f} at {ev.start}ms")
            if check_overlap and max_end is not None and ev.start < max_end:
                problems.append(f"overlap at {ev.start}ms")
            max_end = ev.end if max_end is None else max(max_end, ev.end)
        if not problems:
            continue
        issues.append(
            Issue(
                type=IssueType.TIMING_SANITY,
                severity=Severity.SUSPICIOUS,
                episode_id=ctx.episode_id,
                target_kind=t.kind,
                target_path=t.path,
                stream_index=t.stream_index,
                lang=t.lang,
                count=len(problems),
                snippets=problems[:3],
                raw_hash="",
                fixable=False,
                suggested_fix=None,
            )
        )
    return issues
