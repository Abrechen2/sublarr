"""Video subtitle synchronization service.

Wraps ffsubsync and alass CLI tools. Both are optional dependencies —
SyncUnavailableError is raised when an engine is not installed.
"""

import os
import re
import shutil
import logging
import subprocess
import tempfile

logger = logging.getLogger(__name__)


def _check_module(name: str) -> bool:
    try:
        __import__(name)
        return True
    except ImportError:
        return False


FFSUBSYNC_AVAILABLE = bool(shutil.which("ffsubsync") or _check_module("ffsubsync"))
ALASS_AVAILABLE = bool(shutil.which("alass"))


class SyncUnavailableError(Exception):
    """Raised when the requested sync engine is not installed."""


def sync_with_ffsubsync(subtitle_path: str, video_path: str) -> dict:
    """Sync subtitle to video using ffsubsync (speech-detection based).

    Creates a .bak copy before modifying the subtitle in-place.

    Returns:
        dict with keys: output_path, shift_ms, engine, backup_path

    Raises:
        SyncUnavailableError: ffsubsync is not installed
        RuntimeError: ffsubsync exited with a non-zero status
    """
    if not FFSUBSYNC_AVAILABLE:
        raise SyncUnavailableError(
            "ffsubsync is not installed. Install with: pip install ffsubsync"
        )

    backup = _make_backup(subtitle_path)
    logger.info("ffsubsync: syncing %s against %s (backup: %s)", subtitle_path, video_path, backup)

    ext = os.path.splitext(subtitle_path)[1]
    fd, out_path = tempfile.mkstemp(suffix=ext)
    os.close(fd)

    cmd = ["ffsubsync", video_path, "-i", subtitle_path, "-o", out_path]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    except subprocess.TimeoutExpired:
        _safe_remove(out_path)
        raise RuntimeError("ffsubsync timed out after 600s")

    if result.returncode != 0:
        _safe_remove(out_path)
        raise RuntimeError(f"ffsubsync failed: {result.stderr.strip()}")

    shutil.move(out_path, subtitle_path)
    shift_ms = _parse_ffsubsync_shift(result.stderr + result.stdout)
    logger.info("ffsubsync: done, estimated shift %dms", shift_ms)

    return {
        "output_path": subtitle_path,
        "shift_ms": shift_ms,
        "engine": "ffsubsync",
        "backup_path": backup,
    }


def sync_with_alass(subtitle_path: str, reference_path: str) -> dict:
    """Sync subtitle to a reference subtitle using alass.

    Creates a .bak copy before modifying the subtitle in-place.

    Returns:
        dict with keys: output_path, engine, backup_path

    Raises:
        SyncUnavailableError: alass is not installed
        RuntimeError: alass exited with a non-zero status
    """
    if not ALASS_AVAILABLE:
        raise SyncUnavailableError(
            "alass is not installed. Download from: https://github.com/kaegi/alass/releases"
        )

    backup = _make_backup(subtitle_path)
    logger.info("alass: syncing %s against %s", subtitle_path, reference_path)

    ext = os.path.splitext(subtitle_path)[1]
    fd, out_path = tempfile.mkstemp(suffix=ext)
    os.close(fd)

    cmd = ["alass", reference_path, subtitle_path, out_path]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    except subprocess.TimeoutExpired:
        _safe_remove(out_path)
        raise RuntimeError("alass timed out after 300s")

    if result.returncode != 0:
        _safe_remove(out_path)
        raise RuntimeError(f"alass failed: {result.stderr.strip()}")

    shutil.move(out_path, subtitle_path)
    logger.info("alass: sync complete")

    return {
        "output_path": subtitle_path,
        "engine": "alass",
        "backup_path": backup,
    }


def get_available_engines() -> dict:
    """Return which sync engines are currently available."""
    return {
        "ffsubsync": FFSUBSYNC_AVAILABLE,
        "alass": ALASS_AVAILABLE,
    }


def _make_backup(file_path: str) -> str:
    """Copy file_path to <base>.bak<ext> and return the backup path."""
    base, ext = os.path.splitext(file_path)
    backup = f"{base}.bak{ext}"
    shutil.copy2(file_path, backup)
    return backup


def _safe_remove(path: str) -> None:
    try:
        os.unlink(path)
    except OSError:
        pass


def _parse_ffsubsync_shift(output: str) -> int:
    """Extract timing offset in milliseconds from ffsubsync output. Returns 0 if not parseable."""
    m = re.search(r"offset.*?([-\d.]+)\s*s", output, re.IGNORECASE)
    if m:
        try:
            return int(float(m.group(1)) * 1000)
        except ValueError:
            pass
    return 0
