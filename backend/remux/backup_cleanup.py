"""Backup (.bak) retention cleanup for remuxed video files.

Scans all watched media directories for *.bak files older than
`remux_backup_retention_days` and deletes them.
"""

from __future__ import annotations

import logging
import os
import time

logger = logging.getLogger(__name__)


def _iter_bak_files(media_paths: list[str]):
    """Yield absolute paths of all .bak files found under the given directories."""
    for base_dir in media_paths:
        if not os.path.isdir(base_dir):
            continue
        for dirpath, _dirs, files in os.walk(base_dir):
            for fname in files:
                if fname.endswith(".bak"):
                    yield os.path.join(dirpath, fname)


def cleanup_old_backups(media_paths: list[str], retention_days: int) -> dict:
    """Delete .bak files older than `retention_days`.

    Returns
    -------
    dict
        {"deleted": [...], "errors": [...], "skipped": int}
    """
    if retention_days <= 0:
        return {"deleted": [], "errors": [], "skipped": 0}

    cutoff = time.time() - retention_days * 86400
    deleted, errors, skipped = [], [], 0

    for bak_path in _iter_bak_files(media_paths):
        try:
            mtime = os.path.getmtime(bak_path)
            if mtime < cutoff:
                os.unlink(bak_path)
                deleted.append(bak_path)
                logger.info("Remux backup deleted (age > %d days): %s", retention_days, bak_path)
            else:
                skipped += 1
        except OSError as exc:
            logger.warning("Could not process backup %s: %s", bak_path, exc)
            errors.append({"path": bak_path, "error": str(exc)})

    return {"deleted": deleted, "errors": errors, "skipped": skipped}


def list_backups(media_paths: list[str]) -> list[dict]:
    """Return metadata for all .bak files found under the given directories."""
    result = []
    for bak_path in _iter_bak_files(media_paths):
        try:
            stat = os.stat(bak_path)
            result.append(
                {
                    "path": bak_path,
                    "size_bytes": stat.st_size,
                    "mtime": stat.st_mtime,
                }
            )
        except OSError:
            pass
    return result
