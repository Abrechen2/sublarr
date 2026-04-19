"""SyncOrchestrator — iterate configured engine chain with fallback + audit (Plan B7)."""

from __future__ import annotations

import logging
import time

from services.sync_engines.base import BaseSyncEngine, SyncResult
from services.sync_engines.events import write_sync_job_run

logger = logging.getLogger(__name__)


class SyncOrchestrator:
    """Runs a sequence of engines, early-exiting on the first sane success.

    An engine's result is rejected (fall-through) if:
      - is_available() returns False
      - sync() raises an exception
      - abs(offset_ms) exceeds sanity_threshold_ms
      - result.ok is False
    """

    def __init__(self, engines: list[BaseSyncEngine], sanity_threshold_ms: int = 60_000) -> None:
        self.engines = engines
        self.sanity_threshold_ms = sanity_threshold_ms

    def sync(self, subtitle_path: str, video_path: str) -> SyncResult:
        last_reason = ""
        last_engine = "none"

        for engine in self.engines:
            name = getattr(engine, "name", engine.__class__.__name__)
            start = time.monotonic()

            if not engine.is_available():
                logger.debug("sync engine %s unavailable, skipping", name)
                last_engine = name
                last_reason = "unavailable"
                write_sync_job_run(
                    engine=name,
                    status="skipped",
                    offset_ms=None,
                    duration_ms=0,
                    subtitle_path=subtitle_path,
                    video_path=video_path,
                    reason="unavailable",
                )
                continue

            try:
                result = engine.sync(subtitle_path, video_path)
            except Exception as exc:
                elapsed = int((time.monotonic() - start) * 1000)
                logger.warning("sync engine %s raised: %s", name, exc)
                last_engine = name
                last_reason = f"exception: {exc}"[:64]
                write_sync_job_run(
                    engine=name,
                    status="error",
                    offset_ms=None,
                    duration_ms=elapsed,
                    subtitle_path=subtitle_path,
                    video_path=video_path,
                    reason=last_reason,
                )
                continue

            # Sanity check
            if result.ok and abs(result.offset_ms) > self.sanity_threshold_ms:
                logger.warning(
                    "sync engine %s returned insane offset %dms (>%dms), falling through",
                    name,
                    result.offset_ms,
                    self.sanity_threshold_ms,
                )
                last_engine = name
                last_reason = f"insanity:{result.offset_ms}"
                write_sync_job_run(
                    engine=name,
                    status="insanity_reject",
                    offset_ms=result.offset_ms,
                    duration_ms=result.duration_ms,
                    subtitle_path=subtitle_path,
                    video_path=video_path,
                    reason=last_reason,
                )
                continue

            # Success or engine-reported failure
            write_sync_job_run(
                engine=name,
                status="ok" if result.ok else "failure",
                offset_ms=result.offset_ms,
                duration_ms=result.duration_ms,
                subtitle_path=subtitle_path,
                video_path=video_path,
                reason=result.reason,
            )
            if result.ok:
                return result

            last_engine = name
            last_reason = result.reason or "engine failure"

        # All engines failed
        return SyncResult(
            engine=last_engine,
            ok=False,
            offset_ms=0,
            duration_ms=0,
            reason=last_reason or "all engines failed",
        )


_default_orchestrator: SyncOrchestrator | None = None


def get_default_orchestrator() -> SyncOrchestrator:
    """Lazy-initialize the default orchestrator with the configured engine chain."""
    global _default_orchestrator
    if _default_orchestrator is None:
        # Local imports avoid circular dependencies.
        from services.sync_engines.alass_engine import AlassEngine
        from services.sync_engines.ffsubsync_engine import FfsubsyncEngine

        _default_orchestrator = SyncOrchestrator(
            engines=[FfsubsyncEngine(), AlassEngine()],
            sanity_threshold_ms=60_000,
        )
    return _default_orchestrator
