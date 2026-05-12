"""Video subtitle synchronization service.

Wraps ffsubsync and alass CLI tools. Both are optional dependencies —
``SyncUnavailableError`` is raised when an engine is not installed.

**Plan B7 note:** These top-level functions remain the public legacy API
(used by ``routes/sync.py``, ``routes/video_sync.py``, ``wanted_search``,
and CLI ``backend/cli/commands/sync.py``) and keep their historic dict
return shape. The new engine-class pattern lives in
``services.sync_engines.*`` and is orchestrated via
``services.sync_engines.orchestrator.SyncOrchestrator`` — it does NOT
replace these wrappers, it runs alongside them so the orchestrator can
layer new engines on top without touching legacy callers. The module-level
``shutil``, ``subprocess``, ``_check_module``, ``_parse_ffsubsync_shift``,
``_make_backup`` and ``run_trigger`` symbols are intentionally preserved
because existing tests patch them.
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

# Plan B6 — post-processing pipeline trigger (module-level import so tests can
# patch("services.video_sync.run_trigger")).
from post_processing.pipeline import run_trigger

logger = logging.getLogger(__name__)


def _fire_after_sync_trigger(subtitle_path: str, video_or_ref: str, engine: str) -> None:
    """Fire the after_sync post-processing trigger. Never raises."""
    try:
        from post_processing.config_store import get_trigger_ops

        op_ids = get_trigger_ops("after_sync")
        if op_ids:
            run_trigger(
                trigger="after_sync",
                op_ids=op_ids,
                context={
                    "subtitle_path": subtitle_path,
                    "video_path": video_or_ref,
                    "lang": "",
                    "score": 0,
                    "trigger": "after_sync",
                    "engine": engine,
                },
            )
    except Exception as exc:  # pragma: no cover — defensive
        logger.warning("post_processing after_sync skipped: %s", exc)


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

    Plan B7.1 follow-up: writes a row to ``sync_job_runs`` on every call
    (success or failure) so legacy route callers get the same audit trail
    as orchestrator-based calls.

    Returns:
        dict with keys: output_path, shift_ms, engine, backup_path

    Raises:
        SyncUnavailableError: ffsubsync is not installed
        RuntimeError: ffsubsync exited with a non-zero status
    """
    import time as _time

    start = _time.monotonic()

    def _audit(status: str, offset_ms: int | None, reason: str = "") -> None:
        """Write an audit row; never raises."""
        try:
            from services.sync_engines.events import write_sync_job_run

            write_sync_job_run(
                engine="ffsubsync",
                status=status,
                offset_ms=offset_ms,
                duration_ms=int((_time.monotonic() - start) * 1000),
                subtitle_path=subtitle_path,
                video_path=video_path,
                reason=reason,
            )
        except Exception as _exc:  # pragma: no cover — defensive
            logger.debug("sync audit write failed: %s", _exc)

    if not (shutil.which("ffsubsync") or _check_module("ffsubsync")):
        _audit("skipped", None, "unavailable")
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
        _audit("error", None, "timeout 600s")
        raise RuntimeError("ffsubsync timed out after 600s") from None

    if result.returncode != 0:
        _safe_remove(out_path)
        _audit("error", None, (result.stderr or "").strip()[:64] or "non-zero exit")
        raise RuntimeError(f"ffsubsync failed: {result.stderr.strip()}")

    shutil.move(out_path, subtitle_path)
    shift_ms = _parse_ffsubsync_shift(result.stderr + result.stdout)
    logger.info("ffsubsync: done, estimated shift %dms", shift_ms)
    _audit("ok", shift_ms, "")

    # Plan B6 — fire after_sync post-processing trigger on the happy path.
    _fire_after_sync_trigger(subtitle_path, video_path, "ffsubsync")

    return {
        "output_path": subtitle_path,
        "shift_ms": shift_ms,
        "engine": "ffsubsync",
        "backup_path": backup,
    }


def sync_with_alass(subtitle_path: str, reference_path: str) -> dict:
    """Sync subtitle to a reference subtitle using alass.

    Creates a .bak copy before modifying the subtitle in-place.

    Plan B7.1 follow-up: writes a row to ``sync_job_runs`` on every call
    (success or failure) so legacy route callers get the same audit trail
    as orchestrator-based calls.

    Returns:
        dict with keys: output_path, engine, backup_path

    Raises:
        SyncUnavailableError: alass is not installed
        RuntimeError: alass exited with a non-zero status
    """
    import time as _time

    start = _time.monotonic()

    def _audit(status: str, reason: str = "") -> None:
        """Write an audit row; never raises."""
        try:
            from services.sync_engines.events import write_sync_job_run

            write_sync_job_run(
                engine="alass",
                status=status,
                offset_ms=None,  # alass doesn't report shift
                duration_ms=int((_time.monotonic() - start) * 1000),
                subtitle_path=subtitle_path,
                video_path=reference_path,
                reason=reason,
            )
        except Exception as _exc:  # pragma: no cover — defensive
            logger.debug("sync audit write failed: %s", _exc)

    if not shutil.which("alass"):
        _audit("skipped", "unavailable")
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
        _audit("error", "timeout 300s")
        raise RuntimeError("alass timed out after 300s") from None

    if result.returncode != 0:
        _safe_remove(out_path)
        _audit("error", (result.stderr or "").strip()[:64] or "non-zero exit")
        raise RuntimeError(f"alass failed: {result.stderr.strip()}")

    shutil.move(out_path, subtitle_path)
    logger.info("alass: sync complete")
    _audit("ok", "")

    # Plan B6 — fire after_sync post-processing trigger on the happy path.
    _fire_after_sync_trigger(subtitle_path, reference_path, "alass")

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
    """Extract timing offset in milliseconds from ffsubsync output. Returns 0 if not parseable.

    Handles both legacy and current ffsubsync output formats:
        legacy: ``offset: 1.234 s applied`` / ``Offset: -0.5 s``
        modern (≥0.4.x): ``INFO     offset seconds: 22.960``
    """
    m = re.search(
        r"offset(?:\s+seconds)?\s*:\s*(-?\d+(?:\.\d+)?)",
        output,
        re.IGNORECASE,
    )
    if m:
        try:
            return int(float(m.group(1)) * 1000)
        except ValueError:
            pass
    return 0
