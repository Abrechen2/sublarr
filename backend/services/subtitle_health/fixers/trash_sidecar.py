"""Trash a mislabeled/bogus sidecar and optionally mark its language wanted."""

from __future__ import annotations

import logging

from services.subtitle_health.fixers.common import backup_sidecar
from services.subtitle_health.raw_io import md5_bytes

logger = logging.getLogger(__name__)


def apply(path: str, *, finding_id=None, mark_wanted: bool = True) -> dict:
    from services.subtitle_health import store

    with open(path, "rb") as fh:
        original = fh.read()
    trashed = backup_sidecar(path)
    if trashed is None:
        return {"changed": False, "reason": "trash failed"}
    fix_id = store.record_fix(
        finding_id=finding_id,
        fixer="trash_sidecar",
        action="trash_sidecar",
        target_path=path,
        trashed_original_path=trashed,
        original_hash=md5_bytes(original),
        fixed_hash="",
        reversible=True,
    )
    return {"changed": True, "fix_id": fix_id, "trashed_path": trashed, "mark_wanted": mark_wanted}
