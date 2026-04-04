"""Cleanup rule executors — one function per rule_type.

Each executor takes (media_path, config, dry_run) and returns a result dict.
NFO files (.nfo) are never deleted by any executor.

Rule types:
  language_filter  — delete sidecars in non-allowed languages
  format_upgrade   — delete SRT when ASS exists for same episode+language
  orphan_files     — delete subtitle sidecars with no matching video on disk
  orphan_db        — remove DB entries whose file no longer exists
"""

import logging
import os

logger = logging.getLogger(__name__)

# Module-level import seam so tests can monkeypatch SubtitleRepository.
# Wrapped in try/except to allow importing this module outside a Flask app context.
try:
    from db.repositories.subtitles import SubtitleRepository  # noqa: F401
except ImportError:  # pragma: no cover
    SubtitleRepository = None  # type: ignore[assignment,misc]

SUBTITLE_EXTENSIONS = {".ass", ".ssa", ".srt", ".vtt", ".sub"}
VIDEO_EXTENSIONS = {".mkv", ".mp4", ".avi", ".mov", ".m4v", ".ts", ".wmv"}


def _subtitle_files(root: str) -> list[str]:
    """Walk root recursively, return paths of all subtitle files (never NFO)."""
    found = []
    for dirpath, _, filenames in os.walk(root):
        for fname in filenames:
            ext = os.path.splitext(fname)[1].lower()
            if ext in SUBTITLE_EXTENSIONS:
                found.append(os.path.join(dirpath, fname))
    return found


def _parse_lang_from_filename(filename: str) -> str | None:
    """Extract language tag from sidecar filename.

    Expects pattern: <basename>.<lang>.<ext>
    e.g. "Movie.de.ass" -> "de", "Show.S01E01.en.srt" -> "en"
    Returns None if filename doesn't match the pattern.
    """
    parts = filename.rsplit(".", 2)
    if len(parts) == 3:
        return parts[1].lower()
    return None


def execute_language_filter(media_path: str, config: dict, dry_run: bool = False) -> dict:
    """Delete subtitle sidecars in languages not in keep_languages list.

    Args:
        media_path: Root directory to scan recursively.
        config: {"keep_languages": ["de", "en"]}
        dry_run: If True, return counts without deleting.

    Returns:
        {"deleted": int, "kept": int, "bytes_freed": int} or
        {"would_delete": int, "would_keep": int} in dry_run mode.
    """
    keep_languages = {lang.lower() for lang in config.get("keep_languages", [])}
    deleted = 0
    kept = 0
    bytes_freed = 0
    would_delete = 0
    would_keep = 0

    for path in _subtitle_files(media_path):
        fname = os.path.basename(path)
        lang = _parse_lang_from_filename(fname)

        if lang is None or lang in keep_languages:
            kept += 1
            would_keep += 1
            continue

        file_size = os.path.getsize(path)
        if dry_run:
            would_delete += 1
            logger.debug("Would delete (language_filter): %s", path)
        else:
            try:
                os.remove(path)
                deleted += 1
                bytes_freed += file_size
                logger.info("Deleted (language_filter): %s", path)
            except OSError as e:
                logger.warning("Failed to delete %s: %s", path, e)

    if dry_run:
        return {"would_delete": would_delete, "would_keep": would_keep}
    return {"deleted": deleted, "kept": kept, "bytes_freed": bytes_freed}


def execute_format_upgrade(media_path: str, config: dict, dry_run: bool = False) -> dict:
    """Delete lower-quality format when higher-quality exists for same base+language.

    Args:
        media_path: Root directory to scan recursively.
        config: {"keep_format": "ass"} — "ass" deletes SRT when ASS exists;
                "srt" vice versa; "any" is a no-op.
        dry_run: If True, return counts without deleting.

    Returns:
        {"deleted": int, "bytes_freed": int} or {"would_delete": int} in dry_run mode.
    """
    keep_format = config.get("keep_format", "any").lower()
    if keep_format == "any":
        return {"deleted": 0, "bytes_freed": 0}

    if keep_format == "ass":
        preferred_ext, inferior_ext = ".ass", ".srt"
    else:
        preferred_ext, inferior_ext = ".srt", ".ass"

    from collections import defaultdict

    # index: (dirpath, base_without_ext) -> set of extensions present
    index: dict[tuple[str, str], set[str]] = defaultdict(set)
    path_map: dict[tuple[str, str, str], str] = {}

    for path in _subtitle_files(media_path):
        dirpath = os.path.dirname(path)
        fname = os.path.basename(path)
        base, ext = os.path.splitext(fname)
        key = (dirpath, base)
        index[key].add(ext.lower())
        path_map[(dirpath, base, ext.lower())] = path

    deleted = 0
    bytes_freed = 0
    would_delete = 0

    for (dirpath, base), exts in index.items():
        if preferred_ext in exts and inferior_ext in exts:
            inferior_path = path_map.get((dirpath, base, inferior_ext))
            if inferior_path:
                file_size = os.path.getsize(inferior_path)
                if dry_run:
                    would_delete += 1
                    logger.debug("Would delete (format_upgrade): %s", inferior_path)
                else:
                    try:
                        os.remove(inferior_path)
                        deleted += 1
                        bytes_freed += file_size
                        logger.info("Deleted (format_upgrade): %s", inferior_path)
                    except OSError as e:
                        logger.warning("Failed to delete %s: %s", inferior_path, e)

    if dry_run:
        return {"would_delete": would_delete}
    return {"deleted": deleted, "bytes_freed": bytes_freed}


def execute_orphan_files(media_path: str, config: dict, dry_run: bool = False) -> dict:
    """Delete subtitle sidecars with no matching video file in the same directory.

    A subtitle is considered orphaned when its directory contains no video files.

    Args:
        media_path: Root directory to scan recursively.
        config: {} (no configuration needed)
        dry_run: If True, return counts without deleting.

    Returns:
        {"deleted": int, "bytes_freed": int} or {"would_delete": int} in dry_run mode.
    """
    deleted = 0
    bytes_freed = 0
    would_delete = 0

    for path in _subtitle_files(media_path):
        dirpath = os.path.dirname(path)
        try:
            siblings = os.listdir(dirpath)
        except OSError:
            continue
        has_video = any(os.path.splitext(s)[1].lower() in VIDEO_EXTENSIONS for s in siblings)
        if not has_video:
            file_size = os.path.getsize(path)
            if dry_run:
                would_delete += 1
                logger.debug("Would delete (orphan_files): %s", path)
            else:
                try:
                    os.remove(path)
                    deleted += 1
                    bytes_freed += file_size
                    logger.info("Deleted (orphan_files): %s", path)
                except OSError as e:
                    logger.warning("Failed to delete %s: %s", path, e)

    if dry_run:
        return {"would_delete": would_delete}
    return {"deleted": deleted, "bytes_freed": bytes_freed}


def execute_orphan_db(config: dict, dry_run: bool = False) -> dict:
    """Remove DB subtitle entries whose file no longer exists on disk.

    Args:
        config: {} (no configuration needed)
        dry_run: If True, return counts without deleting.

    Returns:
        {"deleted": int} or {"would_delete": int} in dry_run mode.
    """
    import services.cleanup_executors as _self

    repo = _self.SubtitleRepository()
    paths = repo.get_all_subtitle_paths()
    deleted = 0
    would_delete = 0

    for path in paths:
        if not os.path.exists(path):
            if dry_run:
                would_delete += 1
                logger.debug("Would remove DB entry (orphan_db): %s", path)
            else:
                repo.delete_by_path(path)
                deleted += 1
                logger.info("Removed DB entry (orphan_db): %s", path)

    if dry_run:
        return {"would_delete": would_delete}
    return {"deleted": deleted}
