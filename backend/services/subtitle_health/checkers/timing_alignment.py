"""Detect full sidecars whose timing does not fit the video (see subtitle_timing).

A constant delay is repaired by shifting the file; a track for another cut or
episode is quarantined and searched again. Both only on a trusted verdict:
an embedded text track as the reference, or — against another sidecar — a
mismatching file that also runs past the end of the video (prod 2026-11:
Mushoku Tensei S01E21's English track ended 81 s after the episode).
"""

from __future__ import annotations

import logging

from services.subtitle_health.models import Issue, IssueType, Severity, TargetKind

logger = logging.getLogger(__name__)

SHIFT_ACTION = "shift_timing"
QUARANTINE_ACTION = "quarantine_wrong_sidecar"
_SKIP_NAME_PARTS = (".forced.", ".signs.", ".sdh.forced.")


def _is_full_sidecar(target) -> bool:
    if target.kind != TargetKind.SIDECAR or target.forced or not target.raw:
        return False
    name = target.path.lower()
    return not any(part in name for part in _SKIP_NAME_PARTS)


def detect(ctx) -> list[Issue]:
    import subtitle_timing
    from subtitle_dialogue import dialogue_starts

    issues: list[Issue] = []
    references: dict[str, object] = {}
    for t in ctx.targets:
        if not _is_full_sidecar(t):
            continue
        try:
            if t.lang not in references:
                references[t.lang] = subtitle_timing.find_reference(ctx.video_path, t.lang)
            reference = references[t.lang]
            if reference is None:
                continue
            starts = dialogue_starts(t.raw)
            alignment = subtitle_timing.align(reference.starts, starts) if starts else None
        except Exception as exc:  # noqa: BLE001 — no verdict, never a failed scan
            logger.debug("Timing alignment skipped for %s: %s", t.path, exc)
            continue
        if alignment is None or alignment.verdict not in (
            subtitle_timing.SHIFT,
            subtitle_timing.MISMATCH,
        ):
            continue
        is_shift = alignment.verdict == subtitle_timing.SHIFT
        trusted = reference.trusted or (not is_shift and _overruns(t.path, ctx.video_path))
        if is_shift:
            snippet = f"{alignment.offset_s:+.1f} s against {reference.source}"
            action = SHIFT_ACTION if trusted else None
        else:
            snippet = (
                f"{alignment.match:.0%} of lines start with {reference.source} "
                f"(best offset {alignment.offset_s:+.1f} s)"
            )
            action = QUARANTINE_ACTION if trusted else None
        issues.append(
            Issue(
                type=IssueType.TIMING_OFFSET if is_shift else IssueType.TIMING_MISMATCH,
                severity=Severity.CONFIRMED if trusted else Severity.SUSPICIOUS,
                episode_id=ctx.episode_id,
                target_kind=t.kind,
                target_path=t.path,
                stream_index=t.stream_index,
                lang=t.lang,
                count=round(alignment.offset_s * 10) if is_shift else round(alignment.match * 100),
                snippets=[snippet],
                raw_hash="",
                fixable=action == SHIFT_ACTION,
                suggested_fix=action,
            )
        )
    return issues


def _overruns(subtitle_path: str, video_path: str) -> bool:
    try:
        import subtitle_plausibility

        return bool(subtitle_plausibility.file_overruns_video(subtitle_path, video_path))
    except Exception:  # noqa: BLE001
        return False
