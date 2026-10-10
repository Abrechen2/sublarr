"""ffsubsync engine — speech-detection sync against video (Plan B7).

Refactored from services/video_sync.py::sync_with_ffsubsync.
"""

from __future__ import annotations

import importlib.util
import logging
import os
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from services.sync_engines.base import BaseSyncEngine, SyncResult

logger = logging.getLogger(__name__)


def _remove(path: str) -> None:
    try:
        os.unlink(path)
    except OSError:
        pass


def _check_module(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


def _backup_before_sync(subtitle_path: str) -> None:
    """Safety backup into the hidden single-slot ``.sublarr/backups/`` bak.

    Delegates to ``subtitle_restore.create_or_get_bak`` — an existing bak is
    the undo point of the original text and stays untouched. A failed backup
    is logged, not raised: the engine's contract is to sync regardless.
    """
    try:
        from services.subtitle_restore import create_or_get_bak

        create_or_get_bak(subtitle_path)
    except OSError as exc:
        logger.warning("sync backup failed for %s: %s", subtitle_path, exc)


def _parse_ffsubsync_shift(output: str) -> int:
    """Extract estimated shift in milliseconds from ffsubsync stdout/stderr.

    Handles both legacy and current ffsubsync output formats:
        legacy: ``estimated shift: 1.234s`` / ``offset: 1.234 s applied``
        modern (≥0.4.x): ``INFO     offset seconds: 22.960``
    """
    match = re.search(
        r"(?:estimated\s+shift|offset)(?:\s+seconds)?\s*:?\s*(-?\d+(?:\.\d+)?)",
        output,
        re.IGNORECASE,
    )
    if not match:
        return 0
    try:
        return int(float(match.group(1)) * 1000)
    except ValueError:
        return 0


def _fire_after_sync_trigger(subtitle_path: str, video_or_ref: str, engine: str) -> None:
    """Fire Plan B6 post-processing after_sync trigger. Local import to avoid circular deps."""
    try:
        from post_processing.config_store import get_trigger_ops
        from post_processing.pipeline import run_trigger

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
        logger.debug("after_sync trigger skipped: %s", exc)


class FfsubsyncEngine(BaseSyncEngine):
    name = "ffsubsync"
    timeout_s = 600

    def is_available(self) -> bool:
        return bool(shutil.which("ffsubsync") or _check_module("ffsubsync"))

    def sync(self, subtitle_path: str, video_path: str) -> SyncResult:
        start = time.monotonic()

        if not self.is_available():
            return SyncResult(
                engine=self.name,
                ok=False,
                offset_ms=0,
                duration_ms=int((time.monotonic() - start) * 1000),
                reason="ffsubsync not installed",
            )

        src = Path(subtitle_path)
        _backup_before_sync(str(src))

        from security_utils import safe_subprocess_arg
        from services.sync_engines.concurrency import nice_prefix, sync_subprocess_lock

        # ffsubsync writes to a temp file: its output caps every event at 10 s,
        # so only its measured shift is used, applied to the original below.
        fd, tmp_path = tempfile.mkstemp(suffix=src.suffix)
        os.close(fd)
        out_path = str(src)
        cmd = [
            *nice_prefix(),
            "ffsubsync",
            safe_subprocess_arg(video_path),
            "-i",
            safe_subprocess_arg(subtitle_path),
            "-o",
            safe_subprocess_arg(tmp_path),
        ]
        logger.info("ffsubsync: syncing %s against %s", subtitle_path, video_path)

        # ffsubsync reads + analyses audio from the full video; a large
        # remux needs far more than the fixed floor. Scale by file size,
        # never dropping below the engine's class default (self.timeout_s).
        from utils.io_timeout import compute_io_timeout

        effective_timeout = compute_io_timeout(video_path, floor=self.timeout_s)

        try:
            with sync_subprocess_lock:
                proc = subprocess.run(
                    cmd, capture_output=True, text=True, timeout=effective_timeout
                )
        except subprocess.TimeoutExpired:
            _remove(tmp_path)
            return SyncResult(
                engine=self.name,
                ok=False,
                offset_ms=0,
                duration_ms=int((time.monotonic() - start) * 1000),
                reason=f"timeout {effective_timeout}s",
            )

        if proc.returncode != 0:
            _remove(tmp_path)
            return SyncResult(
                engine=self.name,
                ok=False,
                offset_ms=0,
                duration_ms=int((time.monotonic() - start) * 1000),
                reason=(proc.stderr or "").strip()[:64] or "non-zero exit",
            )

        from services.video_sync import (
            _parse_ffsubsync_scale,
            framerate_scale_is_insane,
            framerate_scale_message,
            shift_original_into,
        )

        output = (proc.stderr or "") + (proc.stdout or "")
        offset_ms = _parse_ffsubsync_shift(output)
        scale = _parse_ffsubsync_scale(output)
        if framerate_scale_is_insane(scale):
            _remove(tmp_path)
            return SyncResult(
                engine=self.name,
                ok=False,
                offset_ms=offset_ms,
                duration_ms=int((time.monotonic() - start) * 1000),
                reason=framerate_scale_message(scale),
            )
        shift_original_into(subtitle_path, tmp_path, offset_ms)
        shutil.copyfile(tmp_path, out_path)
        _remove(tmp_path)
        _fire_after_sync_trigger(subtitle_path, video_path, self.name)

        return SyncResult(
            engine=self.name,
            ok=True,
            offset_ms=offset_ms,
            duration_ms=int((time.monotonic() - start) * 1000),
            output_path=out_path,
        )
