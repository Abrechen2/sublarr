"""Shared archive extraction utilities with ZIP bomb and size protection.

All subtitle providers that handle archive downloads should use these helpers
instead of inline zipfile/rarfile calls, to ensure consistent security checks
across the entire download pipeline.
"""

import io
import logging
import os
import zipfile

logger = logging.getLogger(__name__)

_MAX_ARCHIVE_BYTES = 20 * 1024 * 1024  # 20 MB — reject before extraction
_MAX_EXTRACTED_BYTES = 50 * 1024 * 1024  # 50 MB — total extracted
_MAX_COMPRESSION_RATIO = 100  # 100:1 — ZIP bomb ratio
_SUBTITLE_EXTENSIONS = frozenset({".ass", ".srt", ".ssa", ".vtt"})


def extract_subtitles_from_zip(
    data: bytes,
    subtitle_exts: frozenset[str] = _SUBTITLE_EXTENSIONS,
) -> list[tuple[str, bytes]]:
    """In-memory ZIP extraction with ZIP bomb and size protection.

    Args:
        data: Raw ZIP archive bytes.
        subtitle_exts: Allowed subtitle file extensions (with leading dot).

    Returns:
        List of (basename, content) tuples for matching subtitle files.

    Raises:
        ValueError: If archive exceeds size limits or compression ratio.
    """
    if len(data) > _MAX_ARCHIVE_BYTES:
        raise ValueError(
            f"Archive too large: {len(data) // (1024 * 1024)} MB > "
            f"{_MAX_ARCHIVE_BYTES // (1024 * 1024)} MB limit"
        )

    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            total_compressed = sum(info.compress_size for info in zf.infolist())
            total_uncompressed = sum(info.file_size for info in zf.infolist())

            if total_uncompressed > _MAX_EXTRACTED_BYTES:
                raise ValueError(
                    f"Archive extraction too large: {total_uncompressed // (1024 * 1024)} MB > "
                    f"{_MAX_EXTRACTED_BYTES // (1024 * 1024)} MB limit"
                )

            # ZIP bomb ratio check (skip if nothing compressed — empty/stored zips)
            if total_compressed > 0:
                ratio = total_uncompressed / total_compressed
                if ratio > _MAX_COMPRESSION_RATIO:
                    raise ValueError(
                        f"ZIP bomb detected: compression ratio {ratio:.0f}:1 exceeds "
                        f"{_MAX_COMPRESSION_RATIO}:1 limit"
                    )

            results = []
            for info in zf.infolist():
                # Skip directory entries
                if info.filename.endswith("/"):
                    continue
                # Strip any path components to prevent ZIP slip
                basename = os.path.basename(info.filename)
                if not basename:
                    continue
                ext = os.path.splitext(basename)[1].lower()
                if ext not in subtitle_exts:
                    continue
                results.append((basename, zf.read(info.filename)))

            return results

    except zipfile.BadZipFile:
        logger.warning("archive_utils: bad ZIP archive, skipping")
        return []


def extract_subtitles_from_rar(
    data: bytes,
    subtitle_exts: frozenset[str] = _SUBTITLE_EXTENSIONS,
) -> list[tuple[str, bytes]]:
    """In-memory RAR extraction with size protection.

    Args:
        data: Raw RAR archive bytes.
        subtitle_exts: Allowed subtitle file extensions (with leading dot).

    Returns:
        List of (basename, content) tuples for matching subtitle files.

    Raises:
        ImportError: If the rarfile package is not installed.
        ValueError: If archive exceeds the size limit.
    """
    if len(data) > _MAX_ARCHIVE_BYTES:
        raise ValueError(
            f"Archive too large: {len(data) // (1024 * 1024)} MB > "
            f"{_MAX_ARCHIVE_BYTES // (1024 * 1024)} MB limit"
        )

    import rarfile  # optional dep — raises ImportError if absent

    results = []
    try:
        with rarfile.RarFile(io.BytesIO(data)) as rf:
            for info in rf.infolist():
                basename = os.path.basename(info.filename)
                if not basename:
                    continue
                ext = os.path.splitext(basename)[1].lower()
                if ext not in subtitle_exts:
                    continue
                results.append((basename, rf.read(info.filename)))
    except Exception as e:
        logger.warning("archive_utils: RAR extraction failed: %s", e)

    return results
