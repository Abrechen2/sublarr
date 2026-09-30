"""Sidecar trash primitives — trash root/batch resolution + move-to-trash.

Moved from ``routes/subtitles/helpers.py`` (``_get_trash_root``,
``_get_batch_dir``, ``_trash_sidecar``) on 2026-07-02 so services (e.g.
``services.subtitle_health.fixers.common``) no longer import from the
routes layer. ``routes/subtitles/helpers.py`` keeps thin delegating shims
under the old names for the routes-side callers and tests.

``write_manifest`` (and the two helpers it derives its labels with) moved
here on 2026-09-30: "Wanted -> Cleanup sidecars" is a service that trashes
sidecars too, and a batch without a manifest never appears in the trash page.
``_read_manifest`` / ``_auto_purge_old_trash`` stay in the routes helper.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import uuid
from datetime import UTC, datetime

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


def derive_series_name(path: str) -> str:
    """Derive a human-readable series name from a subtitle file path.

    Walks up the directory tree skipping 'Season N' folders.
    Strips trailing (YEAR) suffix.
    """
    import re as _re

    parts = os.path.normpath(path).split(os.sep)
    # Drop the filename itself, then walk backwards
    for part in reversed(parts[:-1]):
        if _re.match(r"^(season|staffel)\s*\d+$", part, _re.IGNORECASE):
            continue
        if part in ("", ".", ".."):
            continue
        # Strip trailing (YEAR)
        name = _re.sub(r"\s*\(\d{4}\)\s*$", "", part).strip()
        return name
    return ""


def derive_language(files: list[dict]) -> str:
    """Return the most common language code found in the trashed file names."""
    import re as _re
    from collections import Counter

    counts: Counter = Counter()
    for f in files:
        basename = os.path.basename(f.get("original", ""))
        # Match .lang. or .lang.ext patterns, e.g. episode.de.srt -> de
        m = _re.search(r"\.([a-z]{2,3})\.[a-z]+$", basename, _re.IGNORECASE)
        if m:
            counts[m.group(1).lower()] += 1
    return counts.most_common(1)[0][0] if counts else ""


def write_manifest(
    batch_dir: str,
    batch_id: str,
    files: list[dict],
    series_name: str = "",
    language: str = "",
) -> None:
    """Write a manifest.json recording original paths for a trash batch."""
    # Auto-derive context from files if not explicitly provided
    if not series_name and files:
        series_name = derive_series_name(files[0].get("original", ""))
    if not language and files:
        language = derive_language(files)

    manifest = {
        "batch_id": batch_id,
        "created_at": datetime.now(UTC).isoformat(),
        "files": files,  # [{"original": "...", "trashed": "..."}]
        "series_name": series_name,
        "language": language,
    }
    os.makedirs(batch_dir, exist_ok=True)
    manifest_path = os.path.join(batch_dir, "manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2)
