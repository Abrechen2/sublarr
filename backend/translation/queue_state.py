"""In-memory active translation-job tracker.

Single source of truth for 'what is translating right now?' — populated
by TranslationManager as jobs start/progress/finish. No DB persistence.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, datetime

_MAX_RECENT = 20


@dataclass
class _JobState:
    job_id: str
    file_path: str
    source_lang: str
    target_lang: str
    backend: str
    total_lines: int
    done_lines: int = 0
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    started_mono: float = field(default_factory=time.monotonic)
    cancel_requested: bool = False
    cost_micro_usd: int = 0


@dataclass
class _RecentJob:
    job_id: str
    file_path: str
    source_lang: str
    target_lang: str
    backend: str
    lines: int
    status: str
    finished_at: datetime
    duration_s: float
    cost_micro_usd: int
    error_type: str | None = None


class QueueState:
    """Thread-safe in-memory translation queue registry."""

    def __init__(self) -> None:
        self._active: dict[str, _JobState] = {}
        self._recent: deque[_RecentJob] = deque(maxlen=_MAX_RECENT)
        self._lock = threading.Lock()

    def register_job(
        self,
        *,
        job_id: str,
        file_path: str,
        source_lang: str,
        target_lang: str,
        backend: str,
        total_lines: int,
    ) -> None:
        with self._lock:
            self._active[job_id] = _JobState(
                job_id=job_id,
                file_path=file_path,
                source_lang=source_lang,
                target_lang=target_lang,
                backend=backend,
                total_lines=total_lines,
            )

    def update_progress(
        self,
        job_id: str,
        *,
        done: int | None = None,
        cost_micro_usd_delta: int = 0,
        backend: str | None = None,
    ) -> None:
        with self._lock:
            state = self._active.get(job_id)
            if state is None:
                return
            if done is not None:
                state.done_lines = done
            if cost_micro_usd_delta:
                state.cost_micro_usd += cost_micro_usd_delta
            if backend:
                state.backend = backend

    def cancel(self, job_id: str) -> None:
        with self._lock:
            state = self._active.get(job_id)
            if state is None:
                raise KeyError(job_id)
            state.cancel_requested = True

    def is_cancelled(self, job_id: str) -> bool:
        with self._lock:
            state = self._active.get(job_id)
            return bool(state and state.cancel_requested)

    def finish_job(
        self,
        job_id: str,
        *,
        status: str,
        error_type: str | None = None,
    ) -> None:
        with self._lock:
            state = self._active.pop(job_id, None)
            if state is None:
                return
            finished_at = datetime.now(UTC)
            self._recent.appendleft(
                _RecentJob(
                    job_id=state.job_id,
                    file_path=state.file_path,
                    source_lang=state.source_lang,
                    target_lang=state.target_lang,
                    backend=state.backend,
                    lines=state.total_lines,
                    status=status,
                    finished_at=finished_at,
                    duration_s=time.monotonic() - state.started_mono,
                    cost_micro_usd=state.cost_micro_usd,
                    error_type=error_type,
                )
            )

    def active_snapshot(self) -> list[dict]:
        with self._lock:
            return [self._serialize_active(s) for s in self._active.values()]

    def recent_snapshot(self) -> list[dict]:
        with self._lock:
            return [self._serialize_recent(r) for r in self._recent]

    def _serialize_active(self, state: _JobState) -> dict:
        pct = (state.done_lines / state.total_lines * 100.0) if state.total_lines else 0.0
        elapsed = time.monotonic() - state.started_mono
        eta = None
        if state.done_lines > 0 and elapsed > 0.05:
            rate = state.done_lines / elapsed
            remaining = state.total_lines - state.done_lines
            if rate > 0:
                eta = max(0, int(remaining / rate))
        return {
            "job_id": state.job_id,
            "file_path": state.file_path,
            "source_lang": state.source_lang,
            "target_lang": state.target_lang,
            "backend": state.backend,
            "progress": {
                "done": state.done_lines,
                "total": state.total_lines,
                "pct": round(pct, 1),
            },
            "started_at": state.started_at.isoformat(),
            "eta_seconds": eta,
            "cost_so_far_micro_usd": state.cost_micro_usd,
            "cancel_requested": state.cancel_requested,
        }

    def _serialize_recent(self, job: _RecentJob) -> dict:
        return {
            "job_id": job.job_id,
            "file_path": job.file_path,
            "source_lang": job.source_lang,
            "target_lang": job.target_lang,
            "backend": job.backend,
            "lines": job.lines,
            "status": job.status,
            "error_type": job.error_type,
            "finished_at": job.finished_at.isoformat(),
            "duration_s": round(job.duration_s, 2),
            "cost_micro_usd": job.cost_micro_usd,
        }


_instance: QueueState | None = None


def get_queue_state() -> QueueState:
    global _instance
    if _instance is None:
        _instance = QueueState()
    return _instance


def reset_for_tests() -> None:
    global _instance
    _instance = None
