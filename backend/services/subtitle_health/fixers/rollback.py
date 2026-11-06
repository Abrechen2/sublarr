"""Restore a prior fix from its manifest entry."""

from __future__ import annotations

import logging
import os
import shutil

logger = logging.getLogger(__name__)


def apply(fix_id: int) -> dict:
    from services.subtitle_health import store

    m = store.get_fix(fix_id)
    if not m:
        return {"restored": False, "reason": "fix not found"}
    if not m.get("reversible") or not m.get("trashed_original_path"):
        return {"restored": False, "reason": "not reversible"}
    src = m["trashed_original_path"]
    dst = m["target_path"]
    if not os.path.exists(src):
        return {"restored": False, "reason": "backup missing"}
    os.makedirs(os.path.dirname(dst) or ".", exist_ok=True)
    shutil.move(src, dst)
    fid = m.get("finding_id")
    if fid is not None:
        try:
            from services.subtitle_health import store

            store.mark_finding(fid, "open")
        except Exception:
            logger.debug("Could not mark finding %s as open after the rollback", fid, exc_info=True)
    return {"restored": True, "target_path": dst}
