"""Shared helpers for the tools Blueprint package."""

import os
import shutil

from security_utils import is_safe_path

SUPPORTED_FORMATS = {"srt", "ass", "ssa", "vtt"}
PYSUBS2_EXT = {"srt": "srt", "ass": "ass", "ssa": "ssa", "vtt": "vtt"}


def _validate_file_path(file_path: str) -> tuple:
    """Validate that file_path exists, is a subtitle, and is under media_path.

    Returns:
        (None, None) if valid, otherwise (error_message, status_code).
        On success returns (None, file_path) -- normalized file_path.
    """
    from config import get_settings, map_path

    if not file_path:
        return ("file_path is required", 400)

    # Apply path mapping so Sonarr-style remote paths resolve to local container paths.
    file_path = map_path(file_path)

    s = get_settings()
    if not is_safe_path(file_path, s.media_path):
        return ("file_path must be under the configured media_path", 403)

    abs_path = os.path.realpath(file_path)

    if not os.path.exists(abs_path):
        return (f"File not found: {file_path}", 404)

    ext = os.path.splitext(abs_path)[1].lower()
    if ext not in (".srt", ".ass", ".ssa"):
        return ("Only .srt, .ass, and .ssa files are supported", 400)

    return (None, abs_path)


def _create_backup(file_path: str) -> str:
    """Create a .bak backup of a file before modifying it.

    Returns:
        Path to the backup file.
    """
    base, ext = os.path.splitext(file_path)
    bak_path = f"{base}.bak{ext}"
    shutil.copy2(file_path, bak_path)
    return bak_path
