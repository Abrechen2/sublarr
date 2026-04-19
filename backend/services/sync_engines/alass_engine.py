"""alass engine — reference-subtitle-based sync (Plan B7).

Refactored from services/video_sync.py::sync_with_alass.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import time
from pathlib import Path

from services.sync_engines.base import BaseSyncEngine, SyncResult

logger = logging.getLogger(__name__)


def _fire_after_sync_trigger(subtitle_path: str, video_or_ref: str, engine: str) -> None:
    """Fire Plan B6 post-processing after_sync trigger. Local import avoids circular deps."""
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


class AlassEngine(BaseSyncEngine):
    name = "alass"
    timeout_s = 300

    def is_available(self) -> bool:
        return bool(shutil.which("alass"))

    def sync(self, subtitle_path: str, reference_path: str) -> SyncResult:
        start = time.monotonic()

        if not self.is_available():
            return SyncResult(
                engine=self.name,
                ok=False,
                offset_ms=0,
                duration_ms=int((time.monotonic() - start) * 1000),
                reason="alass not installed",
            )

        src = Path(subtitle_path)
        backup = src.with_suffix(src.suffix + ".bak")
        try:
            shutil.copy2(src, backup)
        except Exception:
            pass

        out_path = str(src)
        cmd = ["alass", reference_path, subtitle_path, out_path]
        logger.info("alass: syncing %s against %s", subtitle_path, reference_path)

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

        _fire_after_sync_trigger(subtitle_path, reference_path, self.name)

        # alass does not report offset in stdout; callers that need a delta can diff timestamps.
        return SyncResult(
            engine=self.name,
            ok=True,
            offset_ms=0,
            duration_ms=int((time.monotonic() - start) * 1000),
            output_path=out_path,
        )
