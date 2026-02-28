"""Content-hash based subtitle deduplication engine.

Provides SHA-256 hashing of subtitle files, duplicate group detection,
safe batch deletion with keep-at-least-one guard, orphan detection,
and disk space analysis.

All file operations are validated against the configured media_path
for security. Background scanning uses ThreadPoolExecutor for parallelism.
"""

import hashlib
import json
import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed

from security_utils import is_safe_path

logger = logging.getLogger(__name__)

# Subtitle file extensions to scan
SUBTITLE_EXTENSIONS = {".srt", ".ass", ".ssa"}

# Language pattern in subtitle filenames: .en.srt, .de.ass, .ja.ssa
_LANG_PATTERN = re.compile(r"\.([a-z]{2,3})\.[a-z]{2,3}$", re.IGNORECASE)

# Common media file extensions
MEDIA_EXTENSIONS = {".mkv", ".mp4", ".avi", ".m4v", ".wmv", ".flv", ".webm", ".ts"}


def compute_subtitle_hash(file_path: str) -> dict:
    """Compute SHA-256 content hash for a subtitle file.

    Normalizes content (strip whitespace, normalize line endings) before
    hashing to detect duplicates regardless of line ending differences.

    Args:
        file_path: Absolute path to the subtitle file.

    Returns:
        Dict with file_path, content_hash, file_size, format, language, line_count.

    Raises:
        FileNotFoundError: If file does not exist.
        OSError: If file cannot be read.
    """
    if not os.path.isfile(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    # Read content
    with open(file_path, encoding="utf-8", errors="replace") as f:
        content = f.read()

    # Normalize: strip, replace \r\n with \n
    normalized = content.strip().replace("\r\n", "\n")

    # Compute SHA-256
    content_hash = hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    # File metadata
    file_size = os.path.getsize(file_path)
    ext = os.path.splitext(file_path)[1].lower()
    format_name = ext.lstrip(".")  # "srt", "ass", "ssa"

    # Extract language from filename pattern (e.g., .en.srt -> "en")
    language = None
    lang_match = _LANG_PATTERN.search(os.path.basename(file_path))
    if lang_match:
        language = lang_match.group(1).lower()

    line_count = len(normalized.splitlines())

    return {
        "file_path": file_path,
        "content_hash": content_hash,
        "file_size": file_size,
        "format": format_name,
        "language": language,
        "line_count": line_count,
    }


def scan_for_duplicates(media_path: str, socketio=None) -> dict:
    """Scan a media path recursively for duplicate subtitles.

    Walks the directory tree, hashes all subtitle files, stores hashes
    in the database, and identifies duplicate groups.

    Args:
        media_path: Root directory to scan.
        socketio: Optional SocketIO instance for progress events.

    Returns:
        Dict with total_scanned, duplicates_found, groups.
    """
    from db.repositories.cleanup import CleanupRepository

    if not os.path.isdir(media_path):
        return {
            "error": f"Path not found or not a directory: {media_path}",
            "total_scanned": 0,
            "duplicates_found": 0,
            "groups": [],
        }

    # Collect all subtitle file paths
    subtitle_files = []
    for root, _dirs, files in os.walk(media_path):
        for filename in files:
            ext = os.path.splitext(filename)[1].lower()
            if ext in SUBTITLE_EXTENSIONS:
                subtitle_files.append(os.path.join(root, filename))

    total = len(subtitle_files)
    logger.info("Dedup scan: found %d subtitle files in %s", total, media_path)

    if total == 0:
        return {"total_scanned": 0, "duplicates_found": 0, "groups": []}

    # Process files in parallel
    processed = 0
    errors = []
    hash_results = []

    def _process_file(fp):
        """Hash a single file (runs in thread pool)."""
        try:
            return compute_subtitle_hash(fp)
        except Exception as e:
            logger.warning("Failed to hash %s: %s", fp, e)
            return {"error": str(e), "file_path": fp}

    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {executor.submit(_process_file, fp): fp for fp in subtitle_files}

        for future in as_completed(futures):
            result = future.result()
            processed += 1

            if "error" in result:
                errors.append(result)
            else:
                hash_results.append(result)

            # Emit progress via WebSocket
            if socketio and processed % 10 == 0:
                socketio.emit(
                    "scan_progress",
                    {
                        "current": processed,
                        "total": total,
                        "percent": round(processed / total * 100, 1),
                    },
                )

    # Final progress emit
    if socketio:
        socketio.emit(
            "scan_progress",
            {
                "current": total,
                "total": total,
                "percent": 100.0,
            },
        )

    # Store hashes in database
    repo = CleanupRepository()
    for hr in hash_results:
        try:
            repo.upsert_hash(
                file_path=hr["file_path"],
                content_hash=hr["content_hash"],
                file_size=hr["file_size"],
                format=hr["format"],
                language=hr["language"],
                line_count=hr["line_count"],
            )
        except Exception as e:
            logger.warning("Failed to store hash for %s: %s", hr["file_path"], e)

    # Query duplicate groups
    groups = repo.get_duplicate_groups()

    duplicates_found = sum(g["count"] for g in groups)

    logger.info(
        "Dedup scan complete: %d files scanned, %d duplicates in %d groups, %d errors",
        processed,
        duplicates_found,
        len(groups),
        len(errors),
    )

    return {
        "total_scanned": processed,
        "duplicates_found": duplicates_found,
        "groups": groups,
        "errors": errors if errors else [],
    }


def delete_duplicates(file_paths: list[str], keep_path: str) -> dict:
    """Safely delete duplicate files, keeping exactly one.

    CRITICAL SAFETY: Refuses to proceed if keep_path is in file_paths
    or if keep_path does not exist.

    Args:
        file_paths: List of file paths to delete.
        keep_path: Path to the file that must be kept (safety guard).

    Returns:
        Dict with deleted count, bytes_freed, and any errors.
    """
    from config import get_settings
    from db.repositories.cleanup import CleanupRepository

    media_path = get_settings().media_path

    # Safety guard: keep_path must NOT be in deletion list
    if keep_path in file_paths:
        return {
            "deleted": 0,
            "bytes_freed": 0,
            "errors": ["SAFETY: keep_path is in the deletion list -- refusing to proceed"],
        }

    # Safety guard: keep_path must exist
    if not os.path.isfile(keep_path):
        return {
            "deleted": 0,
            "bytes_freed": 0,
            "errors": [f"SAFETY: keep_path does not exist: {keep_path}"],
        }

    deleted = 0
    bytes_freed = 0
    errors = []
    deleted_paths = []

    for fp in file_paths:
        try:
            if os.path.islink(fp):
                errors.append(f"Skipping symlink (not deleted for safety): {fp}")
                logger.warning("Skipping symlink during dedup deletion: %s", fp)
                continue

            if not is_safe_path(fp, media_path):
                errors.append(f"Skipping path outside media_path: {fp}")
                logger.warning("Dedup deletion refused for path outside media_path: %s", fp)
                continue

            if not os.path.isfile(fp):
                errors.append(f"File not found: {fp}")
                continue

            file_size = os.path.getsize(fp)
            os.remove(fp)
            deleted += 1
            bytes_freed += file_size
            deleted_paths.append(fp)
            logger.info("Deleted duplicate: %s (%d bytes)", fp, file_size)

        except Exception as e:
            errors.append(f"Failed to delete {fp}: {e}")
            logger.error("Failed to delete %s: %s", fp, e)

    # Remove hashes from DB for deleted files
    if deleted_paths:
        try:
            repo = CleanupRepository()
            repo.delete_hashes_by_paths(deleted_paths)
            repo.log_cleanup(
                action_type="dedup_delete",
                files_processed=len(file_paths),
                files_deleted=deleted,
                bytes_freed=bytes_freed,
                details_json=json.dumps(
                    {
                        "kept": keep_path,
                        "deleted": deleted_paths,
                    }
                ),
            )
        except Exception as e:
            logger.warning("Failed to update DB after deletion: %s", e)

    return {
        "deleted": deleted,
        "bytes_freed": bytes_freed,
        "errors": errors,
    }


def scan_orphaned_subtitles(media_path: str) -> list[dict]:
    """Find subtitle files where the parent media file no longer exists.

    A subtitle is orphaned if no media file (.mkv/.mp4/.avi etc.) shares
    its base name in the same directory.

    Args:
        media_path: Root directory to scan.

    Returns:
        List of dicts with path and size for orphaned files.
    """
    if not os.path.isdir(media_path):
        return []

    orphaned = []

    for root, _dirs, files in os.walk(media_path):
        # Build set of media base names in this directory
        media_bases = set()
        for filename in files:
            ext = os.path.splitext(filename)[1].lower()
            if ext in MEDIA_EXTENSIONS:
                # Get base name without extension and language tag
                base = os.path.splitext(filename)[0]
                media_bases.add(base.lower())

        # Check subtitle files against media base names
        for filename in files:
            ext = os.path.splitext(filename)[1].lower()
            if ext not in SUBTITLE_EXTENSIONS:
                continue

            # Strip subtitle extensions and language tags to get base name
            # e.g., "Episode.01.en.srt" -> "Episode.01"
            base = os.path.splitext(filename)[0]
            # Remove language tag if present
            lang_stripped = _LANG_PATTERN.sub("", base + ext)
            base_name = os.path.splitext(lang_stripped)[0]

            # Check if any media file matches this base
            if base_name.lower() not in media_bases:
                full_path = os.path.join(root, filename)
                try:
                    size = os.path.getsize(full_path)
                except OSError:
                    size = 0

                orphaned.append(
                    {
                        "path": full_path,
                        "size": size,
                        "filename": filename,
                        "directory": root,
                    }
                )

    logger.info("Orphan scan: found %d orphaned subtitle files in %s", len(orphaned), media_path)
    return orphaned


def get_disk_space_analysis(media_path: str) -> dict:
    """Get comprehensive disk space analysis for subtitles.

    Combines data from subtitle_hashes table with cleanup_history trends.

    Args:
        media_path: Root media directory (for context, actual data comes from DB).

    Returns:
        Dict with total_files, total_size_bytes, by_format, duplicate stats, trends.
    """
    from db.repositories.cleanup import CleanupRepository

    repo = CleanupRepository()
    return repo.get_disk_stats()
