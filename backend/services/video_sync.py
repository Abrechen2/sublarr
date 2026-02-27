"""Video subtitle synchronization service.

Wraps ffsubsync and alass CLI tools. Both are optional dependencies —
SyncUnavailableError is raised when an engine is not installed.
"""

import contextlib
import logging
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile

logger = logging.getLogger(__name__)


def _check_module(name: str) -> bool:
    try:
        __import__(name)
        return True
    except ImportError:
        return False


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
    if not (shutil.which("ffsubsync") or _check_module("ffsubsync")):
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
    if not shutil.which("alass"):
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
    """Return which sync engines are currently installed (checked at call time)."""
    return {
        "ffsubsync": bool(shutil.which("ffsubsync") or _check_module("ffsubsync")),
        "alass": bool(shutil.which("alass")),
    }


def _install_alass_binary() -> None:
    """Download and install the alass binary for the current platform."""
    import stat
    import urllib.request

    system = platform.system().lower()
    machine = platform.machine().lower()

    # Map platform to GitHub release asset name
    if system == "linux":
        asset = "alass-linux64" if "x86_64" in machine or "amd64" in machine else None
    elif system == "darwin":
        asset = "alass-osx"
    elif system == "windows":
        asset = "alass-win64.exe"
    else:
        asset = None

    if not asset:
        raise RuntimeError(f"No alass binary available for {system}/{machine}")

    url = f"https://github.com/kaegi/alass/releases/latest/download/{asset}"
    install_name = "alass.exe" if system == "windows" else "alass"

    # Install to ~/.local/bin (Linux/Mac) or next to Python (Windows)
    if system == "windows":
        install_dir = os.path.dirname(sys.executable)
    else:
        install_dir = os.path.expanduser("~/.local/bin")
        os.makedirs(install_dir, exist_ok=True)

    install_path = os.path.join(install_dir, install_name)
    logger.info("Downloading alass from %s → %s", url, install_path)

    with urllib.request.urlopen(url, timeout=60) as resp:  # noqa: S310
        data = resp.read()

    with open(install_path, "wb") as f:
        f.write(data)

    if system != "windows":
        os.chmod(
            install_path, os.stat(install_path).st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH
        )

    logger.info("alass installed to %s", install_path)


def install_engine(engine: str) -> dict:
    """Install a sync engine. Returns { success, message }.

    Supported engines:
        ffsubsync — installed via pip
        alass     — downloaded binary from GitHub releases
    """
    if engine == "ffsubsync":
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "ffsubsync"],
            capture_output=True,
            text=True,
            timeout=300,
        )
        if result.returncode != 0:
            raise RuntimeError(f"pip install ffsubsync failed: {result.stderr.strip()}")
        logger.info("ffsubsync installed successfully")
        return {"success": True, "message": "ffsubsync installed"}

    elif engine == "alass":
        _install_alass_binary()
        return {"success": True, "message": "alass installed"}

    else:
        raise ValueError(f"Unknown engine: {engine!r}")


def _make_backup(file_path: str) -> str:
    """Copy file_path to <base>.bak<ext> and return the backup path."""
    base, ext = os.path.splitext(file_path)
    backup = f"{base}.bak{ext}"
    shutil.copy2(file_path, backup)
    return backup


def _safe_remove(path: str) -> None:
    with contextlib.suppress(OSError):
        os.unlink(path)


def _parse_ffsubsync_shift(output: str) -> int:
    """Extract timing offset in milliseconds from ffsubsync output. Returns 0 if not parseable."""
    m = re.search(r"offset.*?([-\d.]+)\s*s", output, re.IGNORECASE)
    if m:
        try:
            return int(float(m.group(1)) * 1000)
        except ValueError:
            pass
    return 0
