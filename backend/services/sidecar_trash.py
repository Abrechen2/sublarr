"""Sidecar trash primitives — trash root/batch resolution + move-to-trash.

Moved from ``routes/subtitles/helpers.py`` (``_get_trash_root``,
``_get_batch_dir``, ``_trash_sidecar``) on 2026-07-02 so services (e.g.
``services.subtitle_health.fixers.common``) no longer import from the
routes layer. ``routes/subtitles/helpers.py`` keeps thin delegating shims
under the old names for the routes-side callers and tests.

Manifest handling (``_write_manifest`` / ``_read_manifest`` /
``_auto_purge_old_trash``) stays in the routes helper — it is only used
by route-level trash workflows.
"""

from __future__ import annotations

import logging
import os
import shutil
import uuid

from security_utils import is_safe_path
from subtitle_filename import SUBTITLE_EXTS

logger = logging.getLogger(__name__)


def get_trash_root(media_path: str) -> str:
    return os.path.join(media_path, ".sublarr_trash")


def get_batch_dir(media_path: str, batch_id: str) -> str:
    return os.path.join(get_trash_root(media_path), batch_id)


def trash_sidecar(path: str, media_path: str, batch_dir: str) -> tuple[str, str | None]:
    """Move a subtitle file into the trash batch directory.

    Returns (trashed_path_or_original, error_or_None).
    """
    if not is_safe_path(path, media_path):
        return path, "Path outside media directory"
    ext = os.path.splitext(path)[1].lstrip(".").lower()
    if ext not in SUBTITLE_EXTS:
        return path, f"Not a subtitle file: .{ext}"
    if not os.path.exists(path):
        return path, "File not found"

    os.makedirs(batch_dir, exist_ok=True)
    basename = os.path.basename(path)
    trash_path = os.path.join(batch_dir, basename)
    # Resolve name conflicts
    if os.path.exists(trash_path):
        trash_path = os.path.join(batch_dir, f"{uuid.uuid4().hex[:8]}_{basename}")
    try:
        shutil.move(path, trash_path)
    except OSError as exc:
        return path, str(exc)

    # Move .quality.json sidecar too if present
    quality_src = path + ".quality.json"
    if os.path.exists(quality_src):
        try:
            shutil.move(quality_src, trash_path + ".quality.json")
        except OSError:
            pass

    # Remove subtitle_downloads DB entry (best-effort)
    try:
        from db.library import delete_download_record

        delete_download_record(path)
    except Exception as exc:
        logger.debug("Could not remove subtitle_downloads entry for %s: %s", path, exc)

    return trash_path, None
