"""Extract an embedded track, repair it, and write an external sidecar."""

from __future__ import annotations

import os

from services.subtitle_health.fixers.common import atomic_write_bytes
from services.subtitle_health.fixers.repair_escapes import repair_bytes
from services.subtitle_health.raw_io import extract_track_raw, md5_bytes

_LANG3 = {"ger": "de", "deu": "de", "eng": "en"}


def _lang2(lang: str) -> str:
    n = (lang or "und").lower().split("-")[0]
    return _LANG3.get(n, n)


def apply(video_path: str, *, sub_index: int, codec: str, lang: str, finding_id=None) -> dict:
    from services.subtitle_health import store

    lang2 = _lang2(lang)
    base, _ = os.path.splitext(video_path)
    out_path = f"{base}.{lang2}.srt"

    raw = extract_track_raw(video_path, sub_index, codec)
    fixed = repair_bytes(raw, codec)

    if os.path.exists(out_path):
        with open(out_path, "rb") as fh:
            existing_hash = md5_bytes(fh.read())
        if not _is_prior_artifact(out_path, existing_hash):
            return {
                "changed": False,
                "reason": "would overwrite foreign sidecar",
                "target_path": out_path,
            }

    atomic_write_bytes(out_path, fixed)
    fix_id = store.record_fix(
        finding_id=finding_id,
        fixer="extract_clean_sidecar",
        action="extract_clean_sidecar",
        target_path=out_path,
        trashed_original_path=None,
        original_hash="",
        fixed_hash=md5_bytes(fixed),
        reversible=False,
    )
    return {
        "changed": True,
        "fix_id": fix_id,
        "target_path": out_path,
        "status": "mitigated_by_sidecar",
    }


def _is_prior_artifact(path: str, current_hash: str) -> bool:
    """True if a prior extract_clean_sidecar manifest produced this exact file."""
    from db.models.core import SubtitleHealthFix
    from extensions import db

    try:
        rows = (
            db.session.query(SubtitleHealthFix)
            .filter_by(action="extract_clean_sidecar", target_path=path)
            .all()
        )
        return any(r.fixed_hash == current_hash for r in rows)
    except Exception:
        return False
