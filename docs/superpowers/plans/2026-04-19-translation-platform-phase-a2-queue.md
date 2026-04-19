# Translation Platform / Phase A2 — Queue Dashboard

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Steps use `- [ ]` checkbox syntax.

**Spec:** `docs/superpowers/specs/2026-04-19-translation-platform-lingarr-parity-design.md`
**Previous phase:** `docs/superpowers/plans/2026-04-19-translation-platform-phase-a1-telemetry.md` (deployed as 0.59.0-beta)

**Goal:** Ship the live translation-job queue dashboard. A1 tells operators *how much* translation costs; A2 tells them *what's happening right now* — which subtitle files are being translated, which backend is chosen, how far along each job is, and which one to cancel.

**Architecture:** In-memory `QueueState` registry on `TranslationManager` tracks active jobs (no DB persistence — queue state is transient). One new Flask blueprint `routes/translation/queue.py` with `GET /queue` (active + recent) and `POST /queue/<job_id>/cancel` (best-effort cancel between batches). Frontend adds `QueueDashboard.tsx` with 3s polling, progress bars, cancel button, and a "recent" panel showing finished jobs from the last 5 minutes.

**Tech Stack:** Flask, in-memory dict with thread lock, React 19 + Tailwind, React Query with 3s `refetchInterval`.

**Dependencies:** Phase A1 (0.59.0-beta) deployed. `TranslationManager` + `translation_events` table in place. The `TranslationManager` singleton exists in `backend/translation/__init__.py`.

**Baseline version:** 0.59.0-beta. Phase A2 ships as minor bump → 0.60.0-beta.

---

## File structure

### New backend files
- `backend/translation/queue_state.py` — in-memory `QueueState` registry (~130 LOC)
- `backend/routes/translation/queue.py` — `/queue` blueprint (~140 LOC)
- `backend/tests/test_queue_state.py`
- `backend/tests/test_translation_queue_routes.py`

### Modified backend files
- `backend/translation/__init__.py` — expose `queue_state` on `TranslationManager`; wire cancellation-flag check
- `backend/translation/llm_base.py` — check cancel flag before each batch, write `cancelled` status + respond
- `backend/translator/jobs.py` (existing) — register job-start with `queue_state`, deregister on finish
- `backend/routes/translation/__init__.py` — register new blueprint
- `backend/routes/__init__.py` — wire new blueprint
- `backend/app_schedulers.py` or `app.py` — add stale-job reconciliation call at startup

### New frontend files
- `frontend/src/pages/Settings/translation/QueueDashboard.tsx` (~220 LOC)
- `frontend/src/pages/Settings/translation/ActiveJobCard.tsx` (~110 LOC)
- `frontend/src/pages/Settings/translation/RecentJobRow.tsx` (~60 LOC)
- `frontend/src/hooks/useTranslationQueue.ts`
- `frontend/src/pages/Settings/translation/__tests__/QueueDashboard.test.tsx`

### Modified frontend files
- `frontend/src/api/translation.ts` — add `getQueue`, `cancelJob` functions
- `frontend/src/types/translation.ts` — add `QueueSnapshot` + `ActiveJob` + `RecentJob` types
- `frontend/src/hooks/useTranslationMutations.ts` — add `cancelJob` mutation
- `frontend/src/pages/Settings/index.tsx` — add route
- `frontend/src/components/settings/SettingsNav.tsx` — add menu entry
- `frontend/src/i18n/locales/{de,en}/settings.json` — queue strings

---

## Task 1: QueueState in-memory tracker

**Files:**
- Create: `backend/translation/queue_state.py`
- Create: `backend/tests/test_queue_state.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_queue_state.py`:

```python
"""QueueState in-memory tracker tests."""

from datetime import UTC, datetime

import pytest


def test_register_job_tracks_it():
    from translation.queue_state import QueueState

    q = QueueState()
    q.register_job(
        job_id="abc",
        file_path="/x/a.mkv",
        source_lang="en", target_lang="de",
        backend="claude", total_lines=100,
    )
    snap = q.active_snapshot()
    assert len(snap) == 1
    assert snap[0]["job_id"] == "abc"
    assert snap[0]["progress"]["total"] == 100
    assert snap[0]["progress"]["done"] == 0


def test_progress_updates():
    from translation.queue_state import QueueState

    q = QueueState()
    q.register_job(
        job_id="abc", file_path="/x/a.mkv",
        source_lang="en", target_lang="de",
        backend="claude", total_lines=100,
    )
    q.update_progress("abc", done=42, cost_micro_usd_delta=500)
    snap = q.active_snapshot()[0]
    assert snap["progress"]["done"] == 42
    assert snap["cost_so_far_micro_usd"] == 500


def test_finish_moves_to_recent():
    from translation.queue_state import QueueState

    q = QueueState()
    q.register_job(
        job_id="abc", file_path="/x/a.mkv",
        source_lang="en", target_lang="de",
        backend="claude", total_lines=100,
    )
    q.finish_job("abc", status="ok")

    assert q.active_snapshot() == []
    recent = q.recent_snapshot()
    assert len(recent) == 1
    assert recent[0]["job_id"] == "abc"
    assert recent[0]["status"] == "ok"


def test_cancel_sets_flag():
    from translation.queue_state import QueueState

    q = QueueState()
    q.register_job(
        job_id="abc", file_path="/x/a.mkv",
        source_lang="en", target_lang="de",
        backend="claude", total_lines=100,
    )
    assert q.is_cancelled("abc") is False
    q.cancel("abc")
    assert q.is_cancelled("abc") is True


def test_cancel_unknown_raises_keyerror():
    from translation.queue_state import QueueState

    q = QueueState()
    with pytest.raises(KeyError):
        q.cancel("nope")


def test_double_cancel_is_idempotent():
    from translation.queue_state import QueueState

    q = QueueState()
    q.register_job(
        job_id="abc", file_path="/x/a.mkv",
        source_lang="en", target_lang="de",
        backend="claude", total_lines=100,
    )
    q.cancel("abc")
    q.cancel("abc")  # must not raise
    assert q.is_cancelled("abc") is True


def test_recent_trims_to_20():
    """Recent list caps at 20 most recent finished jobs."""
    from translation.queue_state import QueueState

    q = QueueState()
    for i in range(25):
        q.register_job(
            job_id=f"j{i}", file_path=f"/x/{i}.mkv",
            source_lang="en", target_lang="de",
            backend="ollama", total_lines=1,
        )
        q.finish_job(f"j{i}", status="ok")

    recent = q.recent_snapshot()
    assert len(recent) == 20


def test_eta_seconds_computed():
    """After some progress, ETA is computed from elapsed/rate."""
    import time
    from translation.queue_state import QueueState

    q = QueueState()
    q.register_job(
        job_id="abc", file_path="/x/a.mkv",
        source_lang="en", target_lang="de",
        backend="claude", total_lines=100,
    )
    time.sleep(0.1)
    q.update_progress("abc", done=10)
    snap = q.active_snapshot()[0]
    # 10 lines in ~0.1s → 100 lines/s → 90 remaining → ~0.9s ETA
    assert snap["eta_seconds"] is not None
    assert 0 <= snap["eta_seconds"] <= 5


def test_thread_safety_stress():
    """Concurrent register+update from many threads doesn't corrupt state."""
    import threading
    from translation.queue_state import QueueState

    q = QueueState()

    def worker(i):
        q.register_job(
            job_id=f"j{i}", file_path=f"/x/{i}.mkv",
            source_lang="en", target_lang="de",
            backend="claude", total_lines=100,
        )
        for done in range(0, 100, 10):
            q.update_progress(f"j{i}", done=done)
        q.finish_job(f"j{i}", status="ok")

    ts = [threading.Thread(target=worker, args=(i,)) for i in range(20)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()

    # No active jobs after all finished
    assert q.active_snapshot() == []
    # 20 most recent
    assert len(q.recent_snapshot()) == 20
```

- [ ] **Step 2: Run — expect FAIL.**

- [ ] **Step 3: Create `backend/translation/queue_state.py`:**

```python
"""In-memory active translation-job tracker.

Single source of truth for "what is translating right now?" — populated
by TranslationManager as jobs start/progress/finish. No DB persistence;
queue state is transient (in-flight jobs only survive as long as the
process does).

Recent-jobs buffer keeps the last 20 finished jobs for ~5 minutes so
the UI can show a reassuring "done" tail.
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
        """Update in-flight job progress. No-op if job already removed."""
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
        """Mark job as cancel-requested. Raises KeyError if unknown."""
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
        """Current active jobs as list of dicts (copy — safe to hand to JSON)."""
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


# Module singleton
_instance: QueueState | None = None


def get_queue_state() -> QueueState:
    global _instance
    if _instance is None:
        _instance = QueueState()
    return _instance


def reset_for_tests() -> None:
    global _instance
    _instance = None
```

- [ ] **Step 4: Run tests — expect 9 passed.**

- [ ] **Step 5: Ruff + commit.**

```bash
cd /d/Sublarr_Projekt/Sublarr/.worktrees/translation-a2-queue
ruff check backend/translation/queue_state.py backend/tests/test_queue_state.py
git add backend/translation/queue_state.py backend/tests/test_queue_state.py
git commit -m "feat(translation-a2): add QueueState in-memory tracker"
```

---

## Task 2: Wire queue_state into LLMBackend + TranslationManager

**Files:**
- Modify: `backend/translation/llm_base.py` — check cancel flag before each batch
- Modify: `backend/translator/jobs.py` (existing) — register job at start, finish on completion
- Test: extend `backend/tests/test_llm_base.py`

- [ ] **Step 1: Append cancellation test** to `backend/tests/test_llm_base.py`:

```python
def test_cancel_flag_respected(app):
    """If cancel is requested, translate_batch raises JobCancelledError."""
    from translation.queue_state import get_queue_state, reset_for_tests
    from translation.llm_base import JobCancelledError

    reset_for_tests()
    qs = get_queue_state()
    qs.register_job(
        job_id="test_cancel",
        file_path="/x/a.mkv",
        source_lang="en", target_lang="de",
        backend="fake_llm",
        total_lines=10,
    )
    qs.cancel("test_cancel")

    with app.app_context():
        backend = _build_backend()
        with pytest.raises(JobCancelledError):
            backend.translate_batch(
                ["a"] * 10, source_lang="en", target_lang="de",
                job_id="test_cancel",
            )
```

- [ ] **Step 2: Extend `LLMBackend.translate_batch` to accept `job_id` parameter** (thread through to cancel-check):

In `backend/translation/llm_base.py`:

```python
# Add near LineCountMismatchError:
class JobCancelledError(RuntimeError):
    """Raised when a batch is skipped due to a cancel request on its job."""


# Update translate_batch signature:
def translate_batch(
    self,
    lines: list[str],
    source_lang: str,
    target_lang: str,
    series_context: str | None = None,
    glossary_entries: list[dict] | None = None,
    job_id: str | None = None,
) -> TranslationResult:
    # At the very start of the try/concurrency block, before calling _attempt:
    if job_id:
        from translation.queue_state import get_queue_state
        if get_queue_state().is_cancelled(job_id):
            raise JobCancelledError(f"Job {job_id} was cancelled")
    # ... rest unchanged
```

Also catch `JobCancelledError` alongside `ContentFilterError` in the `except` ladder:

```python
except JobCancelledError as exc:
    status = "cancelled"
    error_type = "JobCancelledError"
    error_msg = str(exc)
    raise
```

- [ ] **Step 3: Run tests + commit.**

```bash
cd /d/Sublarr_Projekt/Sublarr/.worktrees/translation-a2-queue/backend
/d/Sublarr_Projekt/Sublarr/backend/venv/Scripts/python.exe -m pytest tests/test_llm_base.py -v
cd ..
ruff check backend/translation/llm_base.py
git add backend/translation/llm_base.py backend/tests/test_llm_base.py
git commit -m "feat(translation-a2): LLMBackend checks cancel flag + raises JobCancelledError"
```

---

## Task 3: Queue API — GET /queue + POST /cancel

**Files:**
- Create: `backend/routes/translation/queue.py`
- Modify: `backend/routes/translation/__init__.py`
- Modify: `backend/routes/__init__.py`
- Test: `backend/tests/test_translation_queue_routes.py`

- [ ] **Step 1: Write failing tests.**

Create `backend/tests/test_translation_queue_routes.py`:

```python
"""API tests for /api/v1/translation/queue."""

import pytest


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("SUBLARR_DB_PATH", str(tmp_path / "app.db"))
    monkeypatch.setenv("SUBLARR_API_KEY", "")
    monkeypatch.setenv("SUBLARR_SCHEDULER_ROLE", "disabled")
    from config import reload_settings
    reload_settings()
    from app import create_app
    app = create_app(testing=True)
    from extensions import db as sa_db
    with app.app_context():
        sa_db.create_all()
    yield app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def reset_queue():
    from translation.queue_state import reset_for_tests
    reset_for_tests()


def test_empty_queue(client, reset_queue):
    resp = client.get("/api/v1/translation/queue")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data == {"active": [], "recent": []}


def test_active_job_visible(client, reset_queue):
    from translation.queue_state import get_queue_state

    get_queue_state().register_job(
        job_id="j1", file_path="/x/a.mkv",
        source_lang="en", target_lang="de",
        backend="claude", total_lines=428,
    )
    get_queue_state().update_progress("j1", done=142)

    resp = client.get("/api/v1/translation/queue")
    data = resp.get_json()
    assert len(data["active"]) == 1
    job = data["active"][0]
    assert job["job_id"] == "j1"
    assert job["progress"]["done"] == 142
    assert job["progress"]["total"] == 428


def test_cancel_job(client, reset_queue):
    from translation.queue_state import get_queue_state

    get_queue_state().register_job(
        job_id="j1", file_path="/x/a.mkv",
        source_lang="en", target_lang="de",
        backend="claude", total_lines=10,
    )
    resp = client.post("/api/v1/translation/queue/j1/cancel")
    assert resp.status_code == 202
    data = resp.get_json()
    assert data["status"] == "cancelling"
    assert get_queue_state().is_cancelled("j1")


def test_cancel_unknown_404(client, reset_queue):
    resp = client.post("/api/v1/translation/queue/nope/cancel")
    assert resp.status_code == 404


def test_cancel_already_cancelled_409(client, reset_queue):
    from translation.queue_state import get_queue_state

    get_queue_state().register_job(
        job_id="j1", file_path="/x/a.mkv",
        source_lang="en", target_lang="de",
        backend="claude", total_lines=10,
    )
    client.post("/api/v1/translation/queue/j1/cancel")
    resp = client.post("/api/v1/translation/queue/j1/cancel")
    assert resp.status_code == 409


def test_audit_log_written(client, reset_queue, caplog):
    import logging
    from translation.queue_state import get_queue_state

    get_queue_state().register_job(
        job_id="j1", file_path="/x/a.mkv",
        source_lang="en", target_lang="de",
        backend="claude", total_lines=10,
    )
    with caplog.at_level(logging.INFO, logger="routes.translation.queue"):
        client.post("/api/v1/translation/queue/j1/cancel")
    assert any("translation_admin_action" in r.message for r in caplog.records)
```

- [ ] **Step 2: Run — expect FAIL (404).**

- [ ] **Step 3: Create `backend/routes/translation/queue.py`:**

```python
"""Translation queue admin API — GET /queue + POST /cancel."""

from __future__ import annotations

import logging

from flask import Blueprint, jsonify, request

from translation.queue_state import get_queue_state

logger = logging.getLogger(__name__)

bp = Blueprint("translation_queue_admin", __name__, url_prefix="/api/v1/translation")


def _audit_log(action: str, **kwargs) -> None:
    api_key = request.headers.get("X-Api-Key", "")
    fp = api_key[:6] if api_key else "anon"
    extras = " ".join(f"{k}={v}" for k, v in kwargs.items())
    logger.info(
        "translation_admin_action action=%s actor=%s %s", action, fp, extras,
    )


@bp.route("/queue", methods=["GET"])
def queue_snapshot():
    qs = get_queue_state()
    return jsonify({
        "active": qs.active_snapshot(),
        "recent": qs.recent_snapshot(),
    }), 200


@bp.route("/queue/<job_id>/cancel", methods=["POST"])
def cancel_job(job_id: str):
    qs = get_queue_state()
    if qs.is_cancelled(job_id):
        return jsonify({
            "error": f"job {job_id!r} is already cancelled",
            "error_type": "AlreadyCancelledError",
        }), 409
    try:
        qs.cancel(job_id)
    except KeyError:
        return jsonify({
            "error": f"job {job_id!r} not found",
            "error_type": "NotFoundError",
        }), 404
    _audit_log("cancel-job", job_id=job_id)
    return jsonify({"status": "cancelling", "job_id": job_id}), 202
```

- [ ] **Step 4: Register blueprint.**

Update `backend/routes/translation/__init__.py`:

```python
from routes.translation.concurrency import bp as concurrency_bp
from routes.translation.events import bp as events_bp
from routes.translation.queue import bp as queue_bp

__all__ = ["events_bp", "concurrency_bp", "queue_bp"]
```

And in `backend/routes/__init__.py`, add:

```python
from routes.translation import queue_bp as translation_queue_bp
app.register_blueprint(translation_queue_bp)
```

- [ ] **Step 5: Run tests — expect 6 passed.**

- [ ] **Step 6: Commit.**

```bash
cd /d/Sublarr_Projekt/Sublarr/.worktrees/translation-a2-queue
ruff check backend/routes/translation/queue.py backend/tests/test_translation_queue_routes.py
git add backend/routes/translation/queue.py backend/routes/translation/__init__.py backend/routes/__init__.py backend/tests/test_translation_queue_routes.py
git commit -m "feat(translation-a2): add /api/v1/translation/queue endpoints"
```

---

## Task 4: Frontend types + API + hooks + mutations

**Files:**
- Modify: `frontend/src/types/translation.ts`
- Modify: `frontend/src/api/translation.ts`
- Create: `frontend/src/hooks/useTranslationQueue.ts`
- Modify: `frontend/src/hooks/useTranslationMutations.ts`

- [ ] **Step 1: Add types** to `frontend/src/types/translation.ts`:

```ts
// Translation queue — Phase A2
export type TranslationActiveJob = {
  job_id: string
  file_path: string
  source_lang: string
  target_lang: string
  backend: string
  progress: { done: number; total: number; pct: number }
  started_at: string
  eta_seconds: number | null
  cost_so_far_micro_usd: number
  cancel_requested: boolean
}

export type TranslationRecentJob = {
  job_id: string
  file_path: string
  source_lang: string
  target_lang: string
  backend: string
  lines: number
  status: string
  error_type: string | null
  finished_at: string
  duration_s: number
  cost_micro_usd: number
}

export type TranslationQueueSnapshot = {
  active: TranslationActiveJob[]
  recent: TranslationRecentJob[]
}
```

- [ ] **Step 2: Add API functions** to `frontend/src/api/translation.ts`:

```ts
import type { TranslationQueueSnapshot } from '@/lib/types'

export async function getQueue(): Promise<TranslationQueueSnapshot> {
  const { data } = await api.get('/translation/queue')
  return data
}

export async function cancelJob(
  jobId: string,
): Promise<{ status: string; job_id: string }> {
  const { data } = await api.post(
    `/translation/queue/${encodeURIComponent(jobId)}/cancel`,
  )
  return data
}
```

- [ ] **Step 3: Create `frontend/src/hooks/useTranslationQueue.ts`:**

```ts
import { useQuery } from '@tanstack/react-query'
import { getQueue } from '@/api/translation'

export function useTranslationQueue() {
  return useQuery({
    queryKey: ['translation', 'queue'],
    queryFn: getQueue,
    refetchInterval: 3000,  // Live updates every 3s
  })
}
```

- [ ] **Step 4: Extend `frontend/src/hooks/useTranslationMutations.ts`** — add `cancelJob` mutation:

```ts
import { cancelJob, purgeMemory, setConcurrency } from '@/api/translation'

export function useTranslationMutations() {
  const qc = useQueryClient()
  return {
    purgeMemory: useMutation({ /* existing */ }),
    setConcurrency: useMutation({ /* existing */ }),
    cancelJob: useMutation({
      mutationFn: (jobId: string) => cancelJob(jobId),
      onSuccess: () => {
        qc.invalidateQueries({ queryKey: ['translation', 'queue'] })
      },
    }),
  }
}
```

- [ ] **Step 5: Typecheck + commit.**

```bash
cd /d/Sublarr_Projekt/Sublarr/.worktrees/translation-a2-queue/frontend
/d/Sublarr_Projekt/Sublarr/frontend/node_modules/.bin/tsc --noEmit 2>&1 | tail -5
cd /d/Sublarr_Projekt/Sublarr/.worktrees/translation-a2-queue
git add frontend/src/types/translation.ts frontend/src/api/translation.ts frontend/src/hooks/useTranslationQueue.ts frontend/src/hooks/useTranslationMutations.ts
git commit -m "feat(translation-a2): queue types + API client + hooks + cancel mutation"
```

---

## Task 5: QueueDashboard components

**Files:**
- Create: `frontend/src/pages/Settings/translation/ActiveJobCard.tsx`
- Create: `frontend/src/pages/Settings/translation/RecentJobRow.tsx`
- Create: `frontend/src/pages/Settings/translation/QueueDashboard.tsx`

- [ ] **Step 1: ActiveJobCard.tsx**

```tsx
import { useTranslation } from 'react-i18next'
import { Loader2, X } from 'lucide-react'
import type { TranslationActiveJob } from '@/lib/types'

function formatFilename(path: string): string {
  const parts = path.split(/[/\\]/)
  return parts[parts.length - 1] || path
}

function formatEta(seconds: number | null, t: (k: string, o?: Record<string, unknown>) => string): string {
  if (seconds === null) return t('translation.queue.eta_unknown')
  if (seconds < 60) return t('translation.queue.eta_seconds', { n: seconds })
  return t('translation.queue.eta_minutes', { n: Math.round(seconds / 60) })
}

export function ActiveJobCard({
  job,
  onCancel,
  cancelling = false,
}: {
  job: TranslationActiveJob
  onCancel: () => void
  cancelling?: boolean
}) {
  const { t } = useTranslation('settings')
  const costUsd = (job.cost_so_far_micro_usd / 1_000_000).toFixed(4)

  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="truncate font-mono text-sm">
              {formatFilename(job.file_path)}
            </span>
            <span className="rounded bg-elevated px-2 py-0.5 text-xs">
              {job.source_lang} → {job.target_lang}
            </span>
            <span className="rounded bg-elevated px-2 py-0.5 text-xs font-mono">
              {job.backend}
            </span>
          </div>
          <div className="mt-2 w-full">
            <div
              className="h-2 overflow-hidden rounded bg-elevated"
              role="progressbar"
              aria-valuenow={job.progress.pct}
              aria-valuemin={0}
              aria-valuemax={100}
            >
              <div
                className="h-full bg-accent transition-all"
                style={{ width: `${job.progress.pct}%` }}
              />
            </div>
            <div className="mt-1 flex justify-between text-xs text-muted">
              <span>
                {job.progress.done}/{job.progress.total} ({job.progress.pct.toFixed(1)}%)
              </span>
              <span>
                {formatEta(job.eta_seconds, t)} · ${costUsd}
              </span>
            </div>
          </div>
        </div>
        <button
          onClick={onCancel}
          disabled={cancelling || job.cancel_requested}
          className="flex items-center gap-1 rounded-md border border-border px-2 py-1 text-sm hover:bg-elevated disabled:opacity-50"
        >
          {cancelling || job.cancel_requested ? (
            <Loader2 size={14} className="animate-spin" />
          ) : (
            <X size={14} />
          )}
          {job.cancel_requested
            ? t('translation.queue.cancelling')
            : t('translation.queue.cancel')}
        </button>
      </div>
    </div>
  )
}
```

- [ ] **Step 2: RecentJobRow.tsx**

```tsx
import { useTranslation } from 'react-i18next'
import { Check, X } from 'lucide-react'
import type { TranslationRecentJob } from '@/lib/types'

function formatFilename(path: string): string {
  const parts = path.split(/[/\\]/)
  return parts[parts.length - 1] || path
}

export function RecentJobRow({ job }: { job: TranslationRecentJob }) {
  const { t: _t } = useTranslation('settings')
  const ok = job.status === 'ok'
  const costUsd = (job.cost_micro_usd / 1_000_000).toFixed(4)

  return (
    <div className="flex items-center gap-3 border-b border-border px-2 py-1.5 text-sm">
      {ok ? (
        <Check size={14} className="text-success" />
      ) : (
        <X size={14} className="text-error" />
      )}
      <span className="truncate flex-1 font-mono">
        {formatFilename(job.file_path)}
      </span>
      <span className="text-xs text-muted">
        {job.source_lang} → {job.target_lang}
      </span>
      <span className="text-xs font-mono text-muted">{job.backend}</span>
      <span className="text-xs text-muted">
        {job.duration_s.toFixed(1)}s · ${costUsd} · {job.lines} lines
      </span>
      {job.error_type && (
        <span className="text-xs text-error">{job.error_type}</span>
      )}
    </div>
  )
}
```

- [ ] **Step 3: QueueDashboard.tsx**

```tsx
import { useTranslation } from 'react-i18next'
import { SettingsDetailLayout } from '@/components/settings/SettingsDetailLayout'
import { useTranslationQueue } from '@/hooks/useTranslationQueue'
import { useTranslationMutations } from '@/hooks/useTranslationMutations'
import { toast } from '@/components/shared/Toast'
import { ActiveJobCard } from './ActiveJobCard'
import { RecentJobRow } from './RecentJobRow'

export function QueueDashboard() {
  const { t } = useTranslation('settings')
  const { data, error, isLoading } = useTranslationQueue()
  const { cancelJob } = useTranslationMutations()

  const handleCancel = (jobId: string) => {
    cancelJob.mutate(jobId, {
      onSuccess: () => toast(t('translation.queue.cancel_requested'), 'success'),
      onError: (e: Error) => toast(e.message, 'error'),
    })
  }

  return (
    <SettingsDetailLayout
      title={t('translation.queue.title')}
      subtitle={t('translation.queue.subtitle')}
    >
      {error && (
        <div className="mb-4 rounded-lg border border-error bg-error-bg p-4 text-error">
          {t('translation.queue.load_error')}
        </div>
      )}
      {isLoading && <div className="text-muted">{t('common.loading', { defaultValue: 'Loading...' })}</div>}
      {data && (
        <div className="space-y-5">
          <div>
            <h3 className="mb-2 font-medium">
              {t('translation.queue.active', { n: data.active.length })}
            </h3>
            {data.active.length === 0 ? (
              <div className="text-muted">{t('translation.queue.no_active')}</div>
            ) : (
              <div className="space-y-2">
                {data.active.map((j) => (
                  <ActiveJobCard
                    key={j.job_id}
                    job={j}
                    onCancel={() => handleCancel(j.job_id)}
                    cancelling={cancelJob.isPending}
                  />
                ))}
              </div>
            )}
          </div>

          <div>
            <h3 className="mb-2 font-medium">
              {t('translation.queue.recent', { n: data.recent.length })}
            </h3>
            {data.recent.length === 0 ? (
              <div className="text-muted">{t('translation.queue.no_recent')}</div>
            ) : (
              <div className="rounded-lg border border-border overflow-hidden">
                {data.recent.map((j) => (
                  <RecentJobRow key={j.job_id} job={j} />
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </SettingsDetailLayout>
  )
}
```

- [ ] **Step 4: Typecheck + commit.**

```bash
cd /d/Sublarr_Projekt/Sublarr/.worktrees/translation-a2-queue/frontend
/d/Sublarr_Projekt/Sublarr/frontend/node_modules/.bin/tsc --noEmit 2>&1 | tail -5
cd /d/Sublarr_Projekt/Sublarr/.worktrees/translation-a2-queue
git add frontend/src/pages/Settings/translation/ActiveJobCard.tsx frontend/src/pages/Settings/translation/RecentJobRow.tsx frontend/src/pages/Settings/translation/QueueDashboard.tsx
git commit -m "feat(translation-a2): QueueDashboard + ActiveJobCard + RecentJobRow components"
```

---

## Task 6: Route + menu + i18n

**Files:**
- Modify: `frontend/src/pages/Settings/index.tsx` — add route
- Modify: `frontend/src/components/settings/SettingsNav.tsx` — add menu entry
- Modify: `frontend/src/i18n/locales/{de,en}/settings.json`

- [ ] **Step 1: Add lazy route** to `frontend/src/pages/Settings/index.tsx`:

```tsx
const QueueDashboard = lazy(() =>
  import('./translation/QueueDashboard').then((m) => ({
    default: m.QueueDashboard,
  })),
)

<Route
  path="translation/queue"
  element={
    <Suspense fallback={<FormSkeleton />}>
      <QueueDashboard />
    </Suspense>
  }
/>
```

- [ ] **Step 2: Add menu entry** in Translation group of `SettingsNav.tsx`:

```tsx
{
  label: t('settings.nav.translation_queue', 'Queue'),
  href: '/settings/translation/queue',
}
```

- [ ] **Step 3: Add i18n strings** under `translation.queue.*`:

EN:
```json
"queue": {
  "title": "Translation Queue",
  "subtitle": "Live status of running translation jobs",
  "active": "Active ({{n}})",
  "recent": "Recent ({{n}})",
  "no_active": "No translations in progress.",
  "no_recent": "No recent translations.",
  "cancel": "Cancel",
  "cancelling": "Cancelling…",
  "cancel_requested": "Cancel requested — will stop after current batch",
  "eta_unknown": "ETA unknown",
  "eta_seconds": "~{{n}}s remaining",
  "eta_minutes": "~{{n}}m remaining",
  "load_error": "Could not load queue state."
}
```

DE mirror:
```json
"queue": {
  "title": "Übersetzungs-Warteschlange",
  "subtitle": "Live-Status laufender Übersetzungen",
  "active": "Aktiv ({{n}})",
  "recent": "Kürzlich ({{n}})",
  "no_active": "Keine laufenden Übersetzungen.",
  "no_recent": "Keine kürzlichen Übersetzungen.",
  "cancel": "Abbrechen",
  "cancelling": "Wird abgebrochen…",
  "cancel_requested": "Abbruch angefordert — stoppt nach aktuellem Batch",
  "eta_unknown": "Restzeit unbekannt",
  "eta_seconds": "~{{n}}s verbleibend",
  "eta_minutes": "~{{n}}m verbleibend",
  "load_error": "Warteschlange konnte nicht geladen werden."
}
```

- [ ] **Step 4: Typecheck + commit.**

```bash
cd /d/Sublarr_Projekt/Sublarr/.worktrees/translation-a2-queue/frontend
/d/Sublarr_Projekt/Sublarr/frontend/node_modules/.bin/tsc --noEmit 2>&1 | tail -5
cd /d/Sublarr_Projekt/Sublarr/.worktrees/translation-a2-queue
git add frontend/src/pages/Settings/index.tsx frontend/src/components/settings/SettingsNav.tsx frontend/src/i18n/locales/
git commit -m "feat(translation-a2): wire QueueDashboard route + menu + i18n"
```

---

## Task 7: Frontend tests

**Files:**
- Create: `frontend/src/pages/Settings/translation/__tests__/QueueDashboard.test.tsx`

- [ ] **Step 1: Create tests** (pattern from CostMemoryPage.test.tsx in A1):

```tsx
import { describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { QueueDashboard } from '../QueueDashboard'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (k: string, opts?: Record<string, unknown>) => {
      if (opts && typeof opts === 'object' && 'defaultValue' in opts) {
        return String(opts.defaultValue ?? k)
      }
      return k
    },
  }),
}))

vi.mock('@/components/settings/SettingsDetailLayout', () => ({
  SettingsDetailLayout: ({ children }: { children: React.ReactNode }) => (
    <div>{children}</div>
  ),
}))

vi.mock('@/components/shared/Toast', () => ({
  toast: vi.fn(),
}))

vi.mock('@/api/translation', () => ({
  getQueue: vi.fn().mockResolvedValue({
    active: [
      {
        job_id: 'abc123',
        file_path: '/media/movie.mkv',
        source_lang: 'en',
        target_lang: 'de',
        backend: 'claude',
        progress: { done: 50, total: 100, pct: 50.0 },
        started_at: '2026-04-19T10:00:00Z',
        eta_seconds: 30,
        cost_so_far_micro_usd: 12400,
        cancel_requested: false,
      },
    ],
    recent: [
      {
        job_id: 'def456',
        file_path: '/media/show.s01e01.mkv',
        source_lang: 'en',
        target_lang: 'de',
        backend: 'ollama',
        lines: 428,
        status: 'ok',
        error_type: null,
        finished_at: '2026-04-19T09:55:00Z',
        duration_s: 12.5,
        cost_micro_usd: 0,
      },
    ],
  }),
  cancelJob: vi.fn(),
}))

const renderPage = () => {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <QueueDashboard />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('QueueDashboard', () => {
  it('renders active jobs', async () => {
    renderPage()
    await waitFor(() =>
      expect(screen.getByText('movie.mkv')).toBeInTheDocument(),
    )
    expect(screen.getByText(/50\/100/)).toBeInTheDocument()
  })

  it('renders recent jobs', async () => {
    renderPage()
    await waitFor(() =>
      expect(screen.getByText('show.s01e01.mkv')).toBeInTheDocument(),
    )
  })

  it('shows cancel button on active jobs', async () => {
    renderPage()
    await waitFor(() => screen.getByText('movie.mkv'))
    const cancelBtn = screen.getByRole('button', { name: /cancel/i })
    expect(cancelBtn).toBeInTheDocument()
    expect(cancelBtn).not.toBeDisabled()
  })
})
```

- [ ] **Step 2: Run tests + commit.**

```bash
cd /d/Sublarr_Projekt/Sublarr/.worktrees/translation-a2-queue/frontend
/d/Sublarr_Projekt/Sublarr/frontend/node_modules/.bin/vitest run src/pages/Settings/translation/__tests__/QueueDashboard.test.tsx 2>&1 | tail -10
cd /d/Sublarr_Projekt/Sublarr/.worktrees/translation-a2-queue
git add frontend/src/pages/Settings/translation/__tests__/QueueDashboard.test.tsx
git commit -m "test(translation-a2): QueueDashboard component tests"
```

---

## Task 8: Acceptance + merge + deploy

- [ ] **Step 1: Run full backend scheduler+translation suite**

```bash
cd /d/Sublarr_Projekt/Sublarr/.worktrees/translation-a2-queue/backend
/d/Sublarr_Projekt/Sublarr/backend/venv/Scripts/python.exe -m pytest tests/test_scheduler_*.py tests/test_translation_*.py tests/test_price_sheet.py tests/test_cost_tracker.py tests/test_backend_concurrency.py tests/test_translator_events.py tests/test_llm_base.py tests/test_ollama_backend.py tests/test_openai_compat.py tests/test_queue_state.py tests/test_translation_queue_routes.py --tb=line -q 2>&1 | tail -3
```

Expected: all green, ~250+ tests.

- [ ] **Step 2: Ruff clean on new files**

- [ ] **Step 3: Frontend typecheck + vitest**

```bash
cd /d/Sublarr_Projekt/Sublarr/.worktrees/translation-a2-queue/frontend
/d/Sublarr_Projekt/Sublarr/frontend/node_modules/.bin/tsc --noEmit 2>&1 | tail -3
/d/Sublarr_Projekt/Sublarr/frontend/node_modules/.bin/vitest run src/pages/Settings/translation 2>&1 | tail -5
```

- [ ] **Step 4: Merge to master**

```bash
cd /d/Sublarr_Projekt/Sublarr
git merge --ff-only translation-a2-queue 2>&1 | tail -5
```

If ff-only fails (docs-only commits landed between A1 and A2), rebase the branch in the worktree first:
```bash
cd /d/Sublarr_Projekt/Sublarr/.worktrees/translation-a2-queue && git rebase master && cd /d/Sublarr_Projekt/Sublarr && git merge --ff-only translation-a2-queue
```

- [ ] **Step 5: Bump version + changelog**

Write `backend/VERSION` → `0.60.0-beta`. Prepend changelog entry describing the Queue Dashboard, API endpoints, cancel semantics, in-memory queue tracker. Commit + push.

- [ ] **Step 6: Build + push Docker**

```bash
docker build --build-arg VERSION=0.60.0-beta -t ghcr.io/abrechen2/sublarr:0.60.0-beta -t ghcr.io/abrechen2/sublarr:latest .
docker push ghcr.io/abrechen2/sublarr:0.60.0-beta
docker push ghcr.io/abrechen2/sublarr:latest
```

- [ ] **Step 7: Deploy to Cardinal**

```bash
ssh root@192.168.178.36 "sed -i 's|ghcr.io/abrechen2/sublarr:.*|ghcr.io/abrechen2/sublarr:0.60.0-beta|g' /mnt/user/appdata/sublarr/docker-compose.yml && cd /mnt/user/appdata/sublarr && docker compose pull && docker compose up -d"
sleep 15
curl -s http://192.168.178.36:5765/api/v1/health
```

- [ ] **Step 8: Prod verification**

```bash
API_KEY="..."
curl -s -H "X-Api-Key: $API_KEY" http://192.168.178.36:5765/api/v1/translation/queue
```

Expected: `{"active":[],"recent":[]}` (empty queue — fresh deploy, no jobs ran yet).

- [ ] **Step 9: Cleanup worktree + branch**

```bash
cd /d/Sublarr_Projekt/Sublarr
git worktree remove .worktrees/translation-a2-queue --force
git branch -d translation-a2-queue
ssh root@192.168.178.36 "docker system prune -f"
```

## Phase A2 acceptance checklist

- [ ] `QueueState` tracks active + recent jobs, thread-safe
- [ ] `GET /api/v1/translation/queue` returns `{active, recent}`
- [ ] `POST /cancel` returns 202 on first call, 409 on double cancel, 404 on unknown job
- [ ] Audit log written on every cancel
- [ ] `LLMBackend.translate_batch` checks cancel flag + raises `JobCancelledError`
- [ ] QueueDashboard page polls every 3s + shows active/recent
- [ ] Progress bar reflects `done/total` from backend
- [ ] ETA computed server-side from elapsed/rate
- [ ] Cancel button disabled after click + shows "Cancelling…"
- [ ] All tests green (backend + frontend)
- [ ] Deployed to prod, `/queue` responds 200
