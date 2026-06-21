"""Repair leaked ASS escape codes/tags in SRT/VTT subtitle bytes."""

from __future__ import annotations

import re
from datetime import UTC, datetime

from services.subtitle_health.fixers.common import (
    atomic_write_bytes,
    backup_sidecar,
    validate_cue_count,
)
from services.subtitle_health.raw_io import md5_bytes
from services.subtitle_health.text_utils import decode_with_confidence

_SRT_LIKE = frozenset({"srt", "subrip", "webvtt", "vtt"})
_NL_RE = re.compile(r"(?<!\\)\\[Nn]")
_H_RE = re.compile(r"(?<!\\)\\h")
_TAG_RE = re.compile(r"\{\\[^}\r\n]{1,200}\}")


def repair_text(text: str, codec: str) -> str:
    text = _NL_RE.sub("\n", text)
    text = _H_RE.sub(" ", text)
    if (codec or "").lower() in _SRT_LIKE:
        text = _TAG_RE.sub("", text)
    return text


def repair_bytes(raw: bytes, codec: str) -> bytes:
    text, _enc, _conf = decode_with_confidence(raw)
    fixed = repair_text(text, codec)
    return fixed.encode("utf-8")


def apply_to_sidecar(path: str, codec: str, *, finding_id=None) -> dict:
    """Repair a sidecar in place (atomic, backed up, validated). Returns manifest."""
    from services.subtitle_health import store

    with open(path, "rb") as fh:
        original = fh.read()
    fixed = repair_bytes(original, codec)
    if fixed == original:
        return {"changed": False, "reason": "already clean"}
    validate_cue_count(original, fixed)
    trashed = backup_sidecar(path)
    atomic_write_bytes(path, fixed)
    fix_id = store.record_fix(
        finding_id=finding_id,
        fixer="repair_escapes",
        action="repair_escapes",
        target_path=path,
        trashed_original_path=trashed,
        original_hash=md5_bytes(original),
        fixed_hash=md5_bytes(fixed),
        reversible=True,
    )
    return {"changed": True, "fix_id": fix_id, "applied_at": datetime.now(UTC).isoformat()}
