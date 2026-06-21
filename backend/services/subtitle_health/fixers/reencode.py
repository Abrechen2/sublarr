"""Re-encode a subtitle file to clean UTF-8 (no BOM, consistent newlines)."""

from __future__ import annotations

from services.subtitle_health.fixers.common import atomic_write_bytes, backup_sidecar
from services.subtitle_health.raw_io import md5_bytes
from services.subtitle_health.text_utils import decode_with_confidence

_MIN_CONF = 0.5  # refuse to rewrite if we cannot decode confidently


def reencode_bytes(raw: bytes) -> bytes:
    text, _enc, _conf = decode_with_confidence(raw)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return text.encode("utf-8")


def apply_to_sidecar(path: str, *, finding_id=None) -> dict:
    from services.subtitle_health import store

    with open(path, "rb") as fh:
        original = fh.read()
    _text, _enc, conf = decode_with_confidence(original)
    if conf < _MIN_CONF:
        return {"changed": False, "reason": "decode confidence too low"}
    fixed = reencode_bytes(original)
    if fixed == original:
        return {"changed": False, "reason": "already clean utf-8"}
    trashed = backup_sidecar(path)
    if trashed is None:
        return {"changed": False, "reason": "backup failed; not overwriting"}
    atomic_write_bytes(path, fixed)
    fix_id = store.record_fix(
        finding_id=finding_id,
        fixer="reencode",
        action="reencode",
        target_path=path,
        trashed_original_path=trashed,
        original_hash=md5_bytes(original),
        fixed_hash=md5_bytes(fixed),
        reversible=True,
    )
    return {"changed": True, "fix_id": fix_id}
