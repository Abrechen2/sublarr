"""Shift a sidecar by the constant offset its timing check found (reversible)."""

from __future__ import annotations

from services.subtitle_health.fixers.common import atomic_write_bytes, backup_sidecar
from services.subtitle_health.raw_io import md5_bytes


def apply_to_sidecar(path: str, video_path: str, *, finding_id=None) -> dict:
    """Re-measure against the video's reference and shift; never trusts a stale finding."""
    import subtitle_timing
    from services.subtitle_health import store
    from subtitle_dialogue import dialogue_starts
    from subtitle_filename import parse_subtitle_filename

    with open(path, "rb") as fh:
        original = fh.read()
    parsed = parse_subtitle_filename(path)
    reference = subtitle_timing.find_reference(video_path, parsed.language if parsed else "")
    if reference is None or not reference.trusted:
        return {"changed": False, "reason": "no trusted timing reference"}
    starts = dialogue_starts(original)
    alignment = subtitle_timing.align(reference.starts, starts) if starts else None
    if alignment is None or alignment.verdict != subtitle_timing.SHIFT:
        return {"changed": False, "reason": "timing no longer off by a constant offset"}
    fixed = subtitle_timing.shift_content(original, alignment.offset_s)
    if fixed is None:
        return {"changed": False, "reason": "subtitle could not be read"}
    trashed = backup_sidecar(path)
    if trashed is None:
        return {"changed": False, "reason": "backup failed; not overwriting"}
    atomic_write_bytes(path, fixed)
    fix_id = store.record_fix(
        finding_id=finding_id,
        fixer="shift_timing",
        action="shift_timing",
        target_path=path,
        trashed_original_path=trashed,
        original_hash=md5_bytes(original),
        fixed_hash=md5_bytes(fixed),
        reversible=True,
    )
    return {"changed": True, "fix_id": fix_id, "shifted_s": -alignment.offset_s}
