"""Subtitle-sidecar + trash helpers used across the subtitles package.

These helpers are also public: several other modules (routes.tracks,
routes.video_sync, routes.subtitle_processor, routes.remux, routes.trash,
cleanup_scheduler) import `scan_subtitle_sidecars`, `_auto_purge_old_trash`,
`_get_trash_root`, or `_read_manifest` from `routes.subtitles`.
"""

from __future__ import annotations

import glob as _glob
import json
import logging
import os
import shutil
import uuid
from datetime import UTC, datetime

from security_utils import is_safe_path
from subtitle_filename import SUBTITLE_EXTS, parse_subtitle_filename

logger = logging.getLogger(__name__)

# Backwards-compat alias — older code in this module imported the local set
_SUBTITLE_EXTS = SUBTITLE_EXTS


# ─── Filesystem helpers ────────────────────────────────────────────────────────


def scan_subtitle_sidecars(video_path: str) -> list[dict]:
    """Scan filesystem for all subtitle sidecar files next to video_path.

    Returns a list of dicts with path, language, format, modifier (optional),
    size_bytes, modified_at. Backup files (``.bak``) are excluded — they are
    restore artefacts produced by ``subtitle_processor.apply_mods`` and are
    not playable subs. Modifier-suffixed files (``.hi``, ``.forced``,
    ``.sdh``, ``.cc``) keep their underlying language and surface the
    modifier in the response so the UI can render a small badge.
    """
    base, _ = os.path.splitext(video_path)
    result = []
    try:
        for fpath in _glob.glob(_glob.escape(base) + ".*"):
            if fpath == video_path:
                continue
            parsed = parse_subtitle_filename(fpath)
            if parsed is None:
                continue
            if parsed.is_backup:
                # .bak files belong to the backup-management UI, not the
                # active sidecar list.
                continue
            try:
                stat = os.stat(fpath)
            except OSError:
                continue
            entry: dict = {
                "path": fpath,
                "language": parsed.language,
                "format": parsed.extension,
                "size_bytes": stat.st_size,
                "modified_at": stat.st_mtime,
            }
            primary = parsed.primary_modifier
            if primary is not None:
                entry["modifier"] = primary
            result.append(entry)
    except Exception as exc:
        logger.warning("scan_subtitle_sidecars failed for %s: %s", video_path, exc)
    return result


# ─── Trash helpers ─────────────────────────────────────────────────────────────


def _get_trash_root(media_path: str) -> str:
    return os.path.join(media_path, ".sublarr_trash")


def _get_batch_dir(media_path: str, batch_id: str) -> str:
    return os.path.join(_get_trash_root(media_path), batch_id)


def _derive_series_name(path: str) -> str:
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


def _derive_language(files: list[dict]) -> str:
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


def _write_manifest(
    batch_dir: str,
    batch_id: str,
    files: list[dict],
    series_name: str = "",
    language: str = "",
) -> None:
    """Write a manifest.json recording original paths for a trash batch."""
    # Auto-derive context from files if not explicitly provided
    if not series_name and files:
        series_name = _derive_series_name(files[0].get("original", ""))
    if not language and files:
        language = _derive_language(files)

    manifest = {
        "batch_id": batch_id,
        "created_at": datetime.now(UTC).isoformat(),
        "files": files,  # [{"original": "...", "trashed": "..."}]
        "series_name": series_name,
        "language": language,
    }
    manifest_path = os.path.join(batch_dir, "manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2)


def _read_manifest(batch_dir: str) -> dict | None:
    manifest_path = os.path.join(batch_dir, "manifest.json")
    try:
        with open(manifest_path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return None


def _auto_purge_old_trash(media_path: str, retention_days: int) -> int:
    """Permanently remove trash batches older than retention_days. 0 = keep forever."""
    if retention_days <= 0:
        return 0
    trash_root = _get_trash_root(media_path)
    if not os.path.isdir(trash_root):
        return 0

    cutoff = datetime.now(UTC).timestamp() - retention_days * 86400
    purged = 0
    for entry in os.scandir(trash_root):
        if not entry.is_dir():
            continue
        manifest = _read_manifest(entry.path)
        if manifest is None:
            continue
        created_at_str = manifest.get("created_at", "")
        try:
            created_ts = datetime.fromisoformat(created_at_str).timestamp()
        except (ValueError, TypeError):
            continue
        if created_ts < cutoff:
            try:
                shutil.rmtree(entry.path)
                purged += 1
                logger.info(
                    "auto-purge: removed trash batch %s (age > %dd)",
                    manifest["batch_id"],
                    retention_days,
                )
            except OSError as exc:
                logger.warning("auto-purge: could not remove %s: %s", entry.path, exc)
    return purged


def _trash_sidecar(path: str, media_path: str, batch_dir: str) -> tuple[str, str | None]:
    """Move a subtitle file into the trash batch directory.

    Returns (trashed_path_or_original, error_or_None).
    """
    if not is_safe_path(path, media_path):
        return path, "Path outside media directory"
    ext = os.path.splitext(path)[1].lstrip(".").lower()
    if ext not in _SUBTITLE_EXTS:
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
