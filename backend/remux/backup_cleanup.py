"""Backup (.bak) retention cleanup for remuxed video files.

Scans all watched media directories for *.bak files older than
`remux_backup_retention_days` and deletes them.
"""

from __future__ import annotations

import logging
import os
import re
import time

logger = logging.getLogger(__name__)


def _derive_video_path(bak_path: str) -> str | None:
    """Derive the original video path from a .bak file path.

    Example:
        /media/Show/Season 1/.sublarr/trash/2026-04-05/Episode.mkv.1775388610.bak
        → /media/Show/Season 1/Episode.mkv

    Returns None if the path structure doesn't match expectations or the
    reconstructed path is clearly wrong.
    """
    filename = os.path.basename(bak_path)
    # Strip .{timestamp}.bak suffix (timestamp = large integer)
    stem = re.sub(r"\.\d{7,}\.bak$", "", filename)
    if not stem or stem == filename:
        # Fallback: strip any .bak suffix
        stem = re.sub(r"\.bak$", "", filename)

    # Navigate out of .sublarr/trash/{date}/ → original video directory
    # bak_path: .../video_dir/.sublarr/trash/YYYY-MM-DD/filename.bak
    try:
        original_dir = os.path.normpath(os.path.join(os.path.dirname(bak_path), "..", "..", ".."))
    except Exception:
        return None

    candidate = os.path.join(original_dir, stem)
    return candidate


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


def list_backups(media_paths: list[str], retention_days: int = 0) -> list[dict]:
    """Return metadata for all .bak files found under the given directories.

    Args:
        media_paths: Directories to scan recursively.
        retention_days: If > 0, compute expires_at from mtime + retention_days.
    """
    result = []
    for bak_path in _iter_bak_files(media_paths):
        try:
            stat = os.stat(bak_path)
            video_path = _derive_video_path(bak_path)
            # Only expose video_path if it exists on disk
            if video_path and not os.path.isfile(video_path):
                video_path = None

            expires_at = None
            if retention_days > 0:
                from datetime import UTC, datetime, timedelta

                expires_dt = datetime.fromtimestamp(stat.st_mtime, tz=UTC) + timedelta(
                    days=retention_days
                )
                expires_at = expires_dt.isoformat()

            result.append(
                {
                    "path": bak_path,
                    "video_path": video_path,
                    "size_bytes": stat.st_size,
                    "mtime": stat.st_mtime,
                    "expires_at": expires_at,
                }
            )
        except OSError:
            pass
    return result
