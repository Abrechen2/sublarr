"""ffsubsync engine — speech-detection sync against video (Plan B7).

Refactored from services/video_sync.py::sync_with_ffsubsync.
"""

from __future__ import annotations

import importlib.util
import logging
import re
import shutil
import subprocess
import time
from pathlib import Path

from services.sync_engines.base import BaseSyncEngine, SyncResult

logger = logging.getLogger(__name__)


def _check_module(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


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
        backup = src.with_suffix(src.suffix + ".bak")
        try:
            shutil.copy2(src, backup)
        except Exception:
            pass

        out_path = str(src)
        cmd = ["ffsubsync", video_path, "-i", subtitle_path, "-o", out_path]
        logger.info("ffsubsync: syncing %s against %s", subtitle_path, video_path)

        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=self.timeout_s)
        except subprocess.TimeoutExpired:
            return SyncResult(
                engine=self.name,
                ok=False,
                offset_ms=0,
                duration_ms=int((time.monotonic() - start) * 1000),
                reason=f"timeout {self.timeout_s}s",
            )

        if proc.returncode != 0:
            return SyncResult(
                engine=self.name,
                ok=False,
                offset_ms=0,
                duration_ms=int((time.monotonic() - start) * 1000),
                reason=(proc.stderr or "").strip()[:64] or "non-zero exit",
            )

        offset_ms = _parse_ffsubsync_shift((proc.stderr or "") + (proc.stdout or ""))
        _fire_after_sync_trigger(subtitle_path, video_path, self.name)

        return SyncResult(
            engine=self.name,
            ok=True,
            offset_ms=offset_ms,
            duration_ms=int((time.monotonic() - start) * 1000),
            output_path=out_path,
        )
