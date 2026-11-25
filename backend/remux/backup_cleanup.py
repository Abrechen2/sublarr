"""Backup (.bak) retention cleanup for remuxed video files.

Scans all watched media directories for *.bak files older than
`remux_backup_retention_days` and deletes them.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time

logger = logging.getLogger(__name__)

#: ``<video>.<epoch>.bak``, or ``<video>.<epoch>.<uuid8>.bak`` when a second
#: backup lands in the same second (``_make_backup`` collision suffix, #46).
_STAMP_SUFFIX_RE = re.compile(r"\.(\d{7,})(?:\.[0-9a-f]{8})?\.bak$")


#: Suffix of the record ``_make_backup`` writes next to each backup (#47).
ORIGIN_SUFFIX = ".origin.json"


def origin_path_for(bak_path: str) -> str:
    """Path of the origin record that belongs to ``bak_path``."""
    return bak_path + ORIGIN_SUFFIX


def write_origin(bak_path: str, video_path: str) -> None:
    """Record the full original path of a backup next to it.

    The central trash keeps only the basename, so without this record the
    origin of a backup from a series subfolder is unknown (#47).
    """
    from utils.atomic_write import atomic_write_bytes

    atomic_write_bytes(
        origin_path_for(bak_path), json.dumps({"original": video_path}).encode("utf-8")
    )


def read_origin(bak_path: str) -> str | None:
    """The recorded original path of ``bak_path``, or None without a usable record."""
    try:
        with open(origin_path_for(bak_path), encoding="utf-8") as fh:
            original = json.load(fh).get("original")
    except FileNotFoundError:
        return None
    except (OSError, ValueError, AttributeError) as exc:
        logger.warning("Unreadable origin record for %s: %s", bak_path, exc)
        return None
    return original if isinstance(original, str) and original else None


def remove_origin(bak_path: str) -> None:
    """Delete the origin record of a backup that is gone; a missing one is fine."""
    try:
        os.unlink(origin_path_for(bak_path))
    except FileNotFoundError:
        pass


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
    stem = _STAMP_SUFFIX_RE.sub("", filename)
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


def backup_created_at(bak_path: str) -> float:
    """Return the epoch seconds at which this backup was created.

    ``_make_backup`` writes ``<basename>.<epoch>.bak`` and copies with
    ``shutil.copy2``, which preserves the *source* file's mtime. For a video
    that has been in the library for months the resulting .bak is therefore
    months "old" the moment it is written, and a plain mtime check expires it
    on the very next sweep. The epoch in the filename is the only trustworthy
    creation time, so prefer it.

    Falls back to mtime when the stamp is missing (legacy ``*.bak`` names) or
    implausible — a corrupt far-future stamp must not pin a backup forever.

    Raises OSError if the file cannot be stat'ed and carries no usable stamp.
    """
    match = _STAMP_SUFFIX_RE.search(os.path.basename(bak_path))
    if match:
        stamp = float(match.group(1))
        # Allow a day of clock skew; anything beyond that is not a real stamp.
        if stamp <= time.time() + 86400:
            return stamp
    return os.path.getmtime(bak_path)


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
            created = backup_created_at(bak_path)
            if created < cutoff:
                os.unlink(bak_path)
                remove_origin(bak_path)
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
            # Only the recorded origin counts. Rebuilding it from the trash
            # layout offered an unrelated same-named video for restore (#47);
            # a legacy backup without a record stays unassigned.
            video_path = read_origin(bak_path)
            # Only expose video_path if it exists on disk
            if video_path and not os.path.isfile(video_path):
                video_path = None

            expires_at = None
            if retention_days > 0:
                from datetime import UTC, datetime, timedelta

                # Same clock as the sweep — otherwise the UI promises a
                # retention window the cleanup does not honour.
                expires_dt = datetime.fromtimestamp(
                    backup_created_at(bak_path), tz=UTC
                ) + timedelta(days=retention_days)
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
