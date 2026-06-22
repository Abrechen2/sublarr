"""Non-destructive alternative to trashing: move a sidecar to quarantine."""

from __future__ import annotations

import os
import shutil

from services.subtitle_health.raw_io import md5_bytes


def _quarantine_dir(path: str) -> str:
    d = os.path.join(os.path.dirname(path), ".subtitle_health_quarantine")
    os.makedirs(d, exist_ok=True)
    return d


def apply(path: str, *, finding_id=None) -> dict:
    from config import get_settings
    from security_utils import is_safe_path
    from services.subtitle_health import store

    if not is_safe_path(path, getattr(get_settings(), "media_path", "/media")):
        return {"changed": False, "reason": "unsafe path"}

    with open(path, "rb") as fh:
        original = fh.read()
    qdir = _quarantine_dir(path)
    dest = os.path.join(qdir, os.path.basename(path))
    if os.path.exists(dest):
        import uuid

        dest = os.path.join(qdir, f"{uuid.uuid4().hex[:8]}_{os.path.basename(path)}")
    shutil.move(path, dest)
    fix_id = store.record_fix(
        finding_id=finding_id,
        fixer="quarantine_sidecar",
        action="quarantine_sidecar",
        target_path=path,
        trashed_original_path=dest,
        original_hash=md5_bytes(original),
        fixed_hash="",
        reversible=True,
    )
    return {"changed": True, "fix_id": fix_id, "quarantined_path": dest}
