# Phase 5 / Rollout Phase 2 — Read-only API + UI

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** `docs/superpowers/specs/2026-04-18-phase5-scheduler-hardening-design.md`
**Previous phase:** `docs/superpowers/plans/2026-04-18-phase5-scheduler-hardening-phase1-infrastructure.md` (deployed as 0.55.0-beta)

**Goal:** Expose the scheduler state that Phase 1 persists through a read-only HTTP API and a new Settings page. Operators can inspect registered jobs, their live state (next/last fire, 7-day stats), and per-job run history, but cannot modify anything yet. Write endpoints land in Phase 3.

**Architecture:** Flask blueprint `routes/system/scheduler.py` with three GET endpoints (`/jobs`, `/jobs/<id>`, `/jobs/<id>/runs`). Responses are serialized via a `TriggerModel` Pydantic schema shared with Phase 3. Frontend adds `pages/Settings/SchedulerPage.tsx` with `JobCard` + `JobHistoryDrawer` components; action buttons render but are disabled with a "coming in Phase 3" tooltip.

**Tech Stack:** Flask, Pydantic, SQLAlchemy, React 19, Tailwind, React Query, vitest.

**Dependencies:** Phase 1 (0.55.0-beta) deployed. `SublarrScheduler` facade exists with all introspection methods.

---

## File Structure

### New backend files
- `backend/routes/system/scheduler.py` — Flask blueprint (~220 LOC)
- `backend/routes/system/scheduler_serializers.py` — TriggerModel + job-object Pydantic schemas (~100 LOC)
- `backend/tests/test_scheduler_routes.py` — route tests (~280 LOC)
- `backend/tests/test_scheduler_serializers.py` — serializer tests (~80 LOC)

### New frontend files
- `frontend/src/api/scheduler.ts` — typed API client (~80 LOC)
- `frontend/src/hooks/useSchedulerJobs.ts` — React Query hooks (~40 LOC)
- `frontend/src/hooks/useSchedulerJobRuns.ts` — paginated history hook (~40 LOC)
- `frontend/src/pages/Settings/SchedulerPage.tsx` — page shell + list (~180 LOC)
- `frontend/src/pages/Settings/scheduler/JobCard.tsx` — single-job tile (~120 LOC)
- `frontend/src/pages/Settings/scheduler/JobHistoryDrawer.tsx` — right-side history drawer (~160 LOC)
- `frontend/src/pages/Settings/scheduler/StatusBadge.tsx` — tiny status pill (~30 LOC)
- `frontend/src/pages/Settings/__tests__/SchedulerPage.test.tsx` — component tests (~150 LOC)
- `frontend/src/pages/Settings/scheduler/__tests__/JobCard.test.tsx` (~80 LOC)

### Modified backend files
- `backend/routes/system/__init__.py` — register scheduler blueprint

### Modified frontend files
- `frontend/src/App.tsx` or wherever Settings routing lives — add `/settings/system/scheduler` route
- `frontend/src/pages/Settings/SystemSettings.tsx` (or equivalent menu) — add "Scheduler" entry
- `frontend/src/i18n/locales/de/settings.json` + `.../en/settings.json` — scheduler.* keys
- `frontend/src/lib/types.ts` — JobSpec / JobRun / Trigger type definitions

---

## Task 1: TriggerModel + job-object serializer

**Files:**
- Create: `backend/routes/system/scheduler_serializers.py`
- Test: `backend/tests/test_scheduler_serializers.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_scheduler_serializers.py`:

```python
"""Pydantic serializer tests for scheduler API."""

from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from routes.system.scheduler_serializers import serialize_trigger


def test_serialize_interval_seconds():
    assert serialize_trigger(IntervalTrigger(seconds=90)) == {
        "type": "interval", "seconds": 90,
    }


def test_serialize_interval_minutes():
    assert serialize_trigger(IntervalTrigger(minutes=15)) == {
        "type": "interval", "seconds": 900,
    }


def test_serialize_cron_hour_minute():
    out = serialize_trigger(CronTrigger(hour=3, minute=0))
    assert out["type"] == "cron"
    assert out["hour"] == "3"
    assert out["minute"] == "0"


def test_serialize_cron_day_of_week():
    out = serialize_trigger(CronTrigger(day_of_week="sun", hour=5))
    assert out["type"] == "cron"
    assert out["day_of_week"] == "sun"
    assert out["hour"] == "5"
```

- [ ] **Step 2: Run — expect FAIL (ImportError)**

`cd /d/Sublarr_Projekt/Sublarr/.worktrees/phase5-p2-api-readonly/backend && /d/Sublarr_Projekt/Sublarr/backend/venv/Scripts/python.exe -m pytest tests/test_scheduler_serializers.py -v`

- [ ] **Step 3: Create serializers module**

Create `backend/routes/system/scheduler_serializers.py`:

```python
"""Pydantic + plain dict serializers for the scheduler API.

TriggerModel is also shared with Phase 3's PATCH endpoint, where it is
used for INPUT validation. For Phase 2 (read-only) it is used only for
shape reference; serialisation itself is done via ``serialize_trigger``.
"""

from __future__ import annotations

from typing import Any, Literal

from apscheduler.triggers.base import BaseTrigger
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from pydantic import BaseModel, Field, model_validator


class IntervalTriggerModel(BaseModel):
    type: Literal["interval"]
    seconds: int | None = Field(default=None, ge=1)
    minutes: int | None = Field(default=None, ge=1)
    hours: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def exactly_one_unit(self) -> "IntervalTriggerModel":
        units = [self.seconds, self.minutes, self.hours]
        if sum(1 for u in units if u is not None) != 1:
            raise ValueError(
                "interval trigger requires exactly one of seconds/minutes/hours"
            )
        return self


class CronTriggerModel(BaseModel):
    type: Literal["cron"]
    year: str | int | None = None
    month: str | int | None = None
    day: str | int | None = None
    week: str | int | None = None
    day_of_week: str | int | None = None
    hour: str | int | None = None
    minute: str | int | None = None
    second: str | int | None = None
    expression: str | None = None


TriggerModel = IntervalTriggerModel | CronTriggerModel


def serialize_trigger(trigger: BaseTrigger) -> dict[str, Any]:
    """Convert APScheduler trigger to stable JSON-ready dict."""
    if isinstance(trigger, IntervalTrigger):
        return {
            "type": "interval",
            "seconds": int(trigger.interval.total_seconds()),
        }
    if isinstance(trigger, CronTrigger):
        out: dict[str, Any] = {"type": "cron"}
        for field in trigger.fields:
            if field.is_default:
                continue
            out[field.name] = str(field)
        return out
    return {"type": "unknown", "repr": repr(trigger)}
```

- [ ] **Step 4: Run tests — expect 4 passed**

- [ ] **Step 5: Ruff**

- [ ] **Step 6: Commit**

```bash
cd /d/Sublarr_Projekt/Sublarr/.worktrees/phase5-p2-api-readonly
git add backend/routes/system/scheduler_serializers.py backend/tests/test_scheduler_serializers.py
git commit -m "feat(phase5-p2): add TriggerModel + serialize_trigger"
```

---

## Task 2: Blueprint skeleton + auth check

**Files:**
- Create: `backend/routes/system/scheduler.py`
- Modify: `backend/routes/system/__init__.py` — register blueprint
- Test: `backend/tests/test_scheduler_routes.py`

- [ ] **Step 1: Write failing test for 503-when-scheduler-down**

Create `backend/tests/test_scheduler_routes.py`:

```python
"""Route tests for /api/v1/scheduler/*."""

import pytest


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("SUBLARR_DB_PATH", str(tmp_path / "app.db"))
    monkeypatch.setenv("SUBLARR_SCHEDULER_ROLE", "primary")
    from config import reload_settings
    reload_settings()
    from app import create_app
    app = create_app(testing=True)
    from extensions import db as sa_db
    with app.app_context():
        sa_db.create_all()
    yield app
    # teardown
    scheduler = app.extensions.get("scheduler")
    if scheduler and scheduler.running:
        scheduler.shutdown(timeout_s=2)


@pytest.fixture
def client(app):
    return app.test_client()


def test_jobs_list_returns_registered_jobs(app, client):
    """GET /api/v1/scheduler/jobs returns list including scheduler_history_cleanup."""
    from services.scheduler import bootstrap_scheduler

    with app.app_context():
        if app.extensions.get("scheduler") is None:
            bootstrap_scheduler(app)

    resp = client.get("/api/v1/scheduler/jobs")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "jobs" in data
    ids = [j["id"] for j in data["jobs"]]
    assert "scheduler_history_cleanup" in ids


def test_jobs_list_503_when_scheduler_disabled(client, monkeypatch):
    """When the scheduler failed to start, the endpoint returns 503."""
    from flask import current_app
    with client.application.app_context():
        current_app.extensions["scheduler"] = None

    resp = client.get("/api/v1/scheduler/jobs")
    assert resp.status_code == 503
    assert resp.get_json()["error_type"] == "SchedulerDownError"


def test_single_job_detail(app, client):
    from services.scheduler import bootstrap_scheduler

    with app.app_context():
        if app.extensions.get("scheduler") is None:
            bootstrap_scheduler(app)

    resp = client.get("/api/v1/scheduler/jobs/scheduler_history_cleanup")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["id"] == "scheduler_history_cleanup"
    assert "trigger" in data
    assert "paused" in data
    assert "trigger_is_default" in data


def test_single_job_404(app, client):
    from services.scheduler import bootstrap_scheduler

    with app.app_context():
        if app.extensions.get("scheduler") is None:
            bootstrap_scheduler(app)

    resp = client.get("/api/v1/scheduler/jobs/nope")
    assert resp.status_code == 404


def test_runs_list_paginates(app, client):
    from services.scheduler import bootstrap_scheduler

    with app.app_context():
        if app.extensions.get("scheduler") is None:
            bootstrap_scheduler(app)
        s = app.extensions["scheduler"]
        # Fire a few oneshots to populate history (each call uses a unique ts)
        import time
        for _ in range(3):
            s.run_now("scheduler_history_cleanup")
            time.sleep(1)

    resp = client.get("/api/v1/scheduler/jobs/scheduler_history_cleanup/runs?limit=2")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["limit"] == 2
    assert len(data["runs"]) <= 2
    assert "total" in data


def test_runs_status_filter(app, client):
    from services.scheduler import bootstrap_scheduler

    with app.app_context():
        if app.extensions.get("scheduler") is None:
            bootstrap_scheduler(app)

    resp = client.get(
        "/api/v1/scheduler/jobs/scheduler_history_cleanup/runs?status=ok"
    )
    assert resp.status_code == 200
    data = resp.get_json()
    for r in data["runs"]:
        assert r["status"] == "ok"


def test_stats_7d_present_on_list(app, client):
    from services.scheduler import bootstrap_scheduler

    with app.app_context():
        if app.extensions.get("scheduler") is None:
            bootstrap_scheduler(app)

    resp = client.get("/api/v1/scheduler/jobs")
    assert resp.status_code == 200
    for j in resp.get_json()["jobs"]:
        assert "stats_7d" in j
        assert set(j["stats_7d"].keys()) >= {"ok", "error", "timeout", "missed"}
```

- [ ] **Step 2: Run tests — expect 404/500 on the route (blueprint doesn't exist yet)**

- [ ] **Step 3: Create blueprint**

Create `backend/routes/system/scheduler.py`:

```python
"""Scheduler admin API — GET endpoints (Phase 2 read-only).

Phase 3 will add POST/PATCH write endpoints (run-now, pause/resume,
modify-trigger, reset-default) to this same blueprint.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

import sqlalchemy as sa
from flask import Blueprint, current_app, jsonify, request

from db.models.scheduler import JobRun
from extensions import db
from routes.system.scheduler_serializers import serialize_trigger

logger = logging.getLogger(__name__)

bp = Blueprint("scheduler_admin", __name__, url_prefix="/api/v1/scheduler")

_STATS_CACHE: dict[str, tuple[float, dict]] = {}
_STATS_CACHE_TTL_S = 10.0


def _get_scheduler():
    s = current_app.extensions.get("scheduler")
    if s is None:
        return None
    return s


def _scheduler_down_response():
    return jsonify({
        "error": "Scheduler is not running on this replica.",
        "error_type": "SchedulerDownError",
    }), 503


def _stats_7d_all() -> dict[str, dict[str, int]]:
    """Grouped count of ok/error/timeout/missed/skipped_overlap per job over last 7 days.

    Cached 10s to avoid hammering the DB on UI poll.
    """
    import time

    now = time.monotonic()
    cached = _STATS_CACHE.get("all")
    if cached and cached[0] > now:
        return cached[1]

    cutoff = datetime.now(UTC) - timedelta(days=7)
    rows = db.session.execute(
        sa.select(JobRun.job_id, JobRun.status, sa.func.count())
        .where(JobRun.started_at >= cutoff)
        .group_by(JobRun.job_id, JobRun.status)
    ).all()

    result: dict[str, dict[str, int]] = {}
    for job_id, status, count in rows:
        result.setdefault(job_id, {"ok": 0, "error": 0, "timeout": 0, "missed": 0, "skipped_overlap": 0})
        result[job_id][status] = count

    _STATS_CACHE["all"] = (now + _STATS_CACHE_TTL_S, result)
    return result


def _last_run_for(job_id: str) -> dict | None:
    row = db.session.execute(
        sa.select(JobRun)
        .where(JobRun.job_id == job_id)
        .order_by(JobRun.started_at.desc())
        .limit(1)
    ).scalar_one_or_none()
    if row is None:
        return None
    return {
        "started_at": row.started_at.isoformat() if row.started_at else None,
        "finished_at": row.finished_at.isoformat() if row.finished_at else None,
        "duration_ms": row.duration_ms,
        "status": row.status,
        "error_type": row.error_type,
        "error_msg": row.error_msg,
    }


def _job_to_dict(scheduler, spec_id: str) -> dict:
    aps_job = scheduler._scheduler.get_job(spec_id)
    spec = scheduler._spec_by_id(spec_id)
    stats = _stats_7d_all().get(
        spec_id,
        {"ok": 0, "error": 0, "timeout": 0, "missed": 0, "skipped_overlap": 0},
    )
    next_run = None
    paused = False
    if aps_job is not None:
        paused = aps_job.next_run_time is None
        next_run = aps_job.next_run_time.isoformat() if aps_job.next_run_time else None
    return {
        "id": spec.id,
        "description": spec.description,
        "owner_module": spec.owner_module,
        "trigger": serialize_trigger(aps_job.trigger) if aps_job else serialize_trigger(spec.default_trigger),
        "trigger_is_default": scheduler.trigger_is_default(spec.id),
        "paused": paused,
        "next_run_time": next_run,
        "last_run": _last_run_for(spec_id),
        "stats_7d": stats,
    }


@bp.route("/jobs", methods=["GET"])
def list_jobs():
    """List all registered jobs with live state."""
    s = _get_scheduler()
    if s is None:
        return _scheduler_down_response()
    jobs = [_job_to_dict(s, jid) for jid in sorted(s._registered_ids)]
    return jsonify({"jobs": jobs}), 200


@bp.route("/jobs/<job_id>", methods=["GET"])
def get_job(job_id: str):
    s = _get_scheduler()
    if s is None:
        return _scheduler_down_response()
    if job_id not in s._registered_ids:
        return jsonify({"error": f"Job {job_id!r} not found", "error_type": "NotFoundError"}), 404
    return jsonify(_job_to_dict(s, job_id)), 200


@bp.route("/jobs/<job_id>/runs", methods=["GET"])
def list_runs(job_id: str):
    s = _get_scheduler()
    if s is None:
        return _scheduler_down_response()
    if job_id not in s._registered_ids:
        return jsonify({"error": f"Job {job_id!r} not found", "error_type": "NotFoundError"}), 404

    try:
        limit = min(max(int(request.args.get("limit", "50")), 1), 500)
        offset = max(int(request.args.get("offset", "0")), 0)
    except ValueError:
        return jsonify({"error": "limit/offset must be integers", "error_type": "ValueError"}), 400

    status_filter = request.args.get("status")

    q = sa.select(JobRun).where(JobRun.job_id == job_id)
    count_q = sa.select(sa.func.count()).select_from(JobRun).where(JobRun.job_id == job_id)
    if status_filter:
        q = q.where(JobRun.status == status_filter)
        count_q = count_q.where(JobRun.status == status_filter)

    total = db.session.execute(count_q).scalar_one()
    rows = db.session.execute(
        q.order_by(JobRun.started_at.desc()).limit(limit).offset(offset)
    ).scalars().all()

    return jsonify({
        "total": total,
        "limit": limit,
        "offset": offset,
        "runs": [
            {
                "id": r.id,
                "started_at": r.started_at.isoformat() if r.started_at else None,
                "finished_at": r.finished_at.isoformat() if r.finished_at else None,
                "duration_ms": r.duration_ms,
                "status": r.status,
                "triggered_by": r.triggered_by,
                "error_type": r.error_type,
                "error_msg": r.error_msg,
            }
            for r in rows
        ],
    }), 200
```

- [ ] **Step 4: Register blueprint in `backend/routes/system/__init__.py`**

Read the existing file to find the right place, then add:

```python
from routes.system.scheduler import bp as scheduler_bp
```

And in the `register_blueprints` or similar helper, register `scheduler_bp`. If `routes/system/__init__.py` follows the marketplace/blacklist package pattern, the registration happens in `backend/app_routes_core.py`. Read that file to confirm and add the blueprint there.

- [ ] **Step 5: Run tests — expect 6 passed**

- [ ] **Step 6: Ruff**

- [ ] **Step 7: Commit**

```bash
git add backend/routes/system/scheduler.py backend/routes/system/__init__.py backend/tests/test_scheduler_routes.py backend/app_routes_core.py
git commit -m "feat(phase5-p2): add read-only /api/v1/scheduler/jobs endpoints"
```

---

## Task 3: Frontend types + API client

**Files:**
- Modify: `frontend/src/lib/types.ts` — add SchedulerJob / JobRun / Trigger types
- Create: `frontend/src/api/scheduler.ts` — typed fetch wrapper

- [ ] **Step 1: Add types to `frontend/src/lib/types.ts`:**

Find the type declarations section and append:

```ts
// Scheduler — Phase 5
export type TriggerInterval = {
  type: 'interval'
  seconds?: number
  minutes?: number
  hours?: number
}

export type TriggerCron = {
  type: 'cron'
  year?: string
  month?: string
  day?: string
  week?: string
  day_of_week?: string
  hour?: string
  minute?: string
  second?: string
}

export type Trigger = TriggerInterval | TriggerCron

export type SchedulerStatus = 'ok' | 'error' | 'timeout' | 'missed' | 'skipped_overlap'
export type SchedulerTriggeredBy = 'schedule' | 'manual' | 'startup'

export type SchedulerJobRun = {
  id: number
  started_at: string | null
  finished_at: string | null
  duration_ms: number | null
  status: SchedulerStatus
  triggered_by: SchedulerTriggeredBy
  error_type: string | null
  error_msg: string | null
}

export type SchedulerJob = {
  id: string
  description: string
  owner_module: string
  trigger: Trigger
  trigger_is_default: boolean
  paused: boolean
  next_run_time: string | null
  last_run: Omit<SchedulerJobRun, 'id' | 'triggered_by'> | null
  stats_7d: Record<SchedulerStatus, number>
}
```

- [ ] **Step 2: Create `frontend/src/api/scheduler.ts`:**

```ts
import { apiClient } from './client'
import type { SchedulerJob, SchedulerJobRun } from '@/lib/types'

export async function listJobs(): Promise<{ jobs: SchedulerJob[] }> {
  return apiClient.get('/scheduler/jobs')
}

export async function getJob(id: string): Promise<SchedulerJob> {
  return apiClient.get(`/scheduler/jobs/${encodeURIComponent(id)}`)
}

export async function listRuns(
  id: string,
  params?: { limit?: number; offset?: number; status?: string },
): Promise<{ total: number; limit: number; offset: number; runs: SchedulerJobRun[] }> {
  const search = new URLSearchParams()
  if (params?.limit) search.set('limit', String(params.limit))
  if (params?.offset) search.set('offset', String(params.offset))
  if (params?.status) search.set('status', params.status)
  const qs = search.toString()
  return apiClient.get(
    `/scheduler/jobs/${encodeURIComponent(id)}/runs${qs ? `?${qs}` : ''}`,
  )
}
```

The exact `apiClient.get` shape must match the existing client in `frontend/src/api/client.ts`. Read that file first. If it returns Promise<unknown> and requires a type assertion, add `as` casts. Adjust the import style to match existing API modules (e.g. `from './client'` vs `from '@/api/client'`).

- [ ] **Step 3: Typecheck**

`cd /d/Sublarr_Projekt/Sublarr/.worktrees/phase5-p2-api-readonly/frontend && npx tsc --noEmit 2>&1 | tail -10`

Expected: no new errors related to the new file.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/lib/types.ts frontend/src/api/scheduler.ts
git commit -m "feat(phase5-p2): scheduler types + typed API client"
```

---

## Task 4: React Query hooks

**Files:**
- Create: `frontend/src/hooks/useSchedulerJobs.ts`
- Create: `frontend/src/hooks/useSchedulerJobRuns.ts`

- [ ] **Step 1: Create `frontend/src/hooks/useSchedulerJobs.ts`:**

```ts
import { useQuery } from '@tanstack/react-query'
import { listJobs, getJob } from '@/api/scheduler'

export function useSchedulerJobs() {
  return useQuery({
    queryKey: ['scheduler', 'jobs'],
    queryFn: listJobs,
    refetchInterval: 10000,
    refetchOnWindowFocus: false,
  })
}

export function useSchedulerJob(id: string, enabled = true) {
  return useQuery({
    queryKey: ['scheduler', 'jobs', id],
    queryFn: () => getJob(id),
    enabled,
    refetchInterval: 10000,
  })
}
```

- [ ] **Step 2: Create `frontend/src/hooks/useSchedulerJobRuns.ts`:**

```ts
import { useQuery } from '@tanstack/react-query'
import { listRuns } from '@/api/scheduler'

export function useSchedulerJobRuns(
  id: string,
  params: { limit?: number; offset?: number; status?: string } = {},
  enabled = true,
) {
  return useQuery({
    queryKey: ['scheduler', 'jobs', id, 'runs', params],
    queryFn: () => listRuns(id, params),
    enabled,
    refetchInterval: 5000,
  })
}
```

- [ ] **Step 3: Typecheck + commit:**

```bash
cd /d/Sublarr_Projekt/Sublarr/.worktrees/phase5-p2-api-readonly/frontend && npx tsc --noEmit 2>&1 | tail -5
cd /d/Sublarr_Projekt/Sublarr/.worktrees/phase5-p2-api-readonly
git add frontend/src/hooks/useSchedulerJobs.ts frontend/src/hooks/useSchedulerJobRuns.ts
git commit -m "feat(phase5-p2): React Query hooks for scheduler jobs + runs"
```

---

## Task 5: JobCard component

**Files:**
- Create: `frontend/src/pages/Settings/scheduler/JobCard.tsx`
- Create: `frontend/src/pages/Settings/scheduler/StatusBadge.tsx`

- [ ] **Step 1: StatusBadge:**

Create `frontend/src/pages/Settings/scheduler/StatusBadge.tsx`:

```tsx
import type { SchedulerStatus } from '@/lib/types'
import { useTranslation } from 'react-i18next'

const STATUS_COLOR: Record<SchedulerStatus, string> = {
  ok: 'bg-success/20 text-success',
  error: 'bg-danger/20 text-danger',
  timeout: 'bg-warning/20 text-warning',
  missed: 'bg-warning/20 text-warning',
  skipped_overlap: 'bg-muted/20 text-muted',
}

export function StatusBadge({ status }: { status: SchedulerStatus }) {
  const { t } = useTranslation('settings')
  return (
    <span
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${STATUS_COLOR[status]}`}
      aria-label={`Status: ${status}`}
    >
      {t(`scheduler.status.${status}`, { defaultValue: status })}
    </span>
  )
}
```

- [ ] **Step 2: JobCard:**

Create `frontend/src/pages/Settings/scheduler/JobCard.tsx`:

```tsx
import type { SchedulerJob } from '@/lib/types'
import { useTranslation } from 'react-i18next'
import { StatusBadge } from './StatusBadge'
import { Play, Pause, Edit3, History, RotateCcw } from 'lucide-react'

function triggerLabel(job: SchedulerJob, t: (k: string, o?: Record<string, unknown>) => string): string {
  const trig = job.trigger
  if (trig.type === 'interval') {
    const s = trig.seconds ?? 0
    if (s >= 3600) return t('scheduler.every_hours', { n: Math.round(s / 3600) })
    if (s >= 60) return t('scheduler.every_minutes', { n: Math.round(s / 60) })
    return t('scheduler.every_seconds', { n: s })
  }
  const hour = trig.hour ?? '*'
  const minute = trig.minute ?? '*'
  const dow = trig.day_of_week
  if (dow) return t('scheduler.cron_weekly', { dow, hour, minute })
  return t('scheduler.cron_daily', { hour, minute })
}

function relativeTime(iso: string | null, t: (k: string, o?: Record<string, unknown>) => string): string {
  if (!iso) return t('scheduler.never', { defaultValue: '—' })
  const diff = (Date.now() - new Date(iso).getTime()) / 1000
  if (diff < 60) return t('scheduler.just_now')
  if (diff < 3600) return t('scheduler.minutes_ago', { n: Math.round(diff / 60) })
  return t('scheduler.hours_ago', { n: Math.round(diff / 3600) })
}

export function JobCard({
  job,
  onOpenHistory,
}: {
  job: SchedulerJob
  onOpenHistory: () => void
}) {
  const { t } = useTranslation('settings')

  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <h3 className="font-medium text-text-primary">{job.id}</h3>
            {!job.trigger_is_default && (
              <span className="rounded-full bg-muted/20 px-2 py-0.5 text-xs text-muted">
                {t('scheduler.edited')}
              </span>
            )}
            {job.paused && (
              <span className="rounded-full bg-warning/20 px-2 py-0.5 text-xs text-warning">
                {t('scheduler.paused')}
              </span>
            )}
          </div>
          <p className="mt-0.5 text-sm text-muted">
            {triggerLabel(job, t)} · {job.owner_module}
          </p>
          {job.description && (
            <p className="mt-1 text-sm text-text-secondary">{job.description}</p>
          )}
        </div>
        {job.last_run?.status && <StatusBadge status={job.last_run.status} />}
      </div>

      <div className="mt-3 grid grid-cols-2 gap-3 text-sm">
        <div>
          <div className="text-muted">{t('scheduler.last_run')}</div>
          <div>{relativeTime(job.last_run?.finished_at ?? null, t)}</div>
        </div>
        <div>
          <div className="text-muted">{t('scheduler.next_run')}</div>
          <div>{relativeTime(job.next_run_time, t)}</div>
        </div>
      </div>

      <div className="mt-3 text-xs text-muted">
        7d: {job.stats_7d.ok} ok · {job.stats_7d.error} err · {job.stats_7d.timeout} to ·{' '}
        {job.stats_7d.missed} miss
      </div>

      <div className="mt-3 flex flex-wrap gap-2">
        <button
          disabled
          title={t('scheduler.phase3_coming')}
          className="inline-flex items-center gap-1 rounded-md border border-border px-3 py-1 text-sm text-muted opacity-50 cursor-not-allowed"
        >
          <Play size={14} /> {t('scheduler.run_now')}
        </button>
        <button
          disabled
          title={t('scheduler.phase3_coming')}
          className="inline-flex items-center gap-1 rounded-md border border-border px-3 py-1 text-sm text-muted opacity-50 cursor-not-allowed"
        >
          <Pause size={14} /> {t('scheduler.pause')}
        </button>
        <button
          disabled
          title={t('scheduler.phase3_coming')}
          className="inline-flex items-center gap-1 rounded-md border border-border px-3 py-1 text-sm text-muted opacity-50 cursor-not-allowed"
        >
          <Edit3 size={14} /> {t('scheduler.edit_trigger')}
        </button>
        <button
          onClick={onOpenHistory}
          className="inline-flex items-center gap-1 rounded-md border border-border px-3 py-1 text-sm hover:bg-surface-hover"
        >
          <History size={14} /> {t('scheduler.history')}
        </button>
        <button
          disabled
          title={t('scheduler.phase3_coming')}
          className="inline-flex items-center gap-1 rounded-md border border-border px-3 py-1 text-sm text-muted opacity-50 cursor-not-allowed"
        >
          <RotateCcw size={14} /> {t('scheduler.reset_default')}
        </button>
      </div>
    </div>
  )
}
```

- [ ] **Step 3: Typecheck + commit:**

```bash
cd /d/Sublarr_Projekt/Sublarr/.worktrees/phase5-p2-api-readonly/frontend && npx tsc --noEmit 2>&1 | tail -5
cd /d/Sublarr_Projekt/Sublarr/.worktrees/phase5-p2-api-readonly
git add frontend/src/pages/Settings/scheduler/
git commit -m "feat(phase5-p2): JobCard + StatusBadge components (read-only actions)"
```

---

## Task 6: JobHistoryDrawer

**Files:**
- Create: `frontend/src/pages/Settings/scheduler/JobHistoryDrawer.tsx`

- [ ] **Step 1: Create the drawer:**

```tsx
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { X, ChevronRight } from 'lucide-react'
import { useSchedulerJobRuns } from '@/hooks/useSchedulerJobRuns'
import type { SchedulerStatus } from '@/lib/types'
import { StatusBadge } from './StatusBadge'

const STATUS_FILTERS: (SchedulerStatus | 'all')[] = [
  'all', 'ok', 'error', 'timeout', 'missed', 'skipped_overlap',
]

export function JobHistoryDrawer({
  jobId,
  open,
  onClose,
}: {
  jobId: string
  open: boolean
  onClose: () => void
}) {
  const { t } = useTranslation('settings')
  const [status, setStatus] = useState<SchedulerStatus | 'all'>('all')
  const [expanded, setExpanded] = useState<number | null>(null)
  const { data, isLoading } = useSchedulerJobRuns(
    jobId,
    { limit: 50, status: status === 'all' ? undefined : status },
    open,
  )

  if (!open) return null

  return (
    <div className="fixed inset-0 z-40 flex">
      <div
        className="flex-1 bg-black/40"
        onClick={onClose}
        role="presentation"
      />
      <div className="flex w-full max-w-2xl flex-col bg-surface shadow-xl">
        <div className="flex items-center justify-between border-b border-border p-4">
          <h2 className="font-medium">{t('scheduler.history_for', { job: jobId })}</h2>
          <button onClick={onClose} aria-label={t('common.close')}>
            <X size={20} />
          </button>
        </div>

        <div className="flex gap-1 overflow-x-auto border-b border-border p-2">
          {STATUS_FILTERS.map((s) => (
            <button
              key={s}
              onClick={() => setStatus(s)}
              className={`rounded-full px-3 py-1 text-xs ${
                status === s ? 'bg-primary text-primary-foreground' : 'hover:bg-surface-hover'
              }`}
            >
              {t(`scheduler.status.${s}`, { defaultValue: s })}
            </button>
          ))}
        </div>

        <div className="flex-1 overflow-y-auto">
          {isLoading && <div className="p-4 text-muted">{t('common.loading')}</div>}
          {data && data.runs.length === 0 && (
            <div className="p-4 text-muted">{t('scheduler.no_runs')}</div>
          )}
          {data && data.runs.map((r) => (
            <div key={r.id} className="border-b border-border">
              <button
                onClick={() => setExpanded(expanded === r.id ? null : r.id)}
                className="flex w-full items-center gap-3 px-4 py-2 text-left hover:bg-surface-hover"
              >
                <ChevronRight
                  size={14}
                  className={`transition-transform ${expanded === r.id ? 'rotate-90' : ''}`}
                />
                <StatusBadge status={r.status} />
                <span className="font-mono text-xs text-muted">
                  {r.started_at && new Date(r.started_at).toLocaleString()}
                </span>
                <span className="ml-auto text-xs text-muted">
                  {r.duration_ms != null ? `${r.duration_ms}ms` : '—'}
                </span>
              </button>
              {expanded === r.id && (r.error_msg || r.error_type) && (
                <div className="bg-surface-muted px-10 py-2 font-mono text-xs">
                  {r.error_type && <div className="font-semibold">{r.error_type}</div>}
                  {r.error_msg && (
                    <pre className="mt-1 whitespace-pre-wrap break-words text-muted">
                      {r.error_msg}
                    </pre>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Typecheck + commit:**

```bash
cd /d/Sublarr_Projekt/Sublarr/.worktrees/phase5-p2-api-readonly/frontend && npx tsc --noEmit 2>&1 | tail -5
cd /d/Sublarr_Projekt/Sublarr/.worktrees/phase5-p2-api-readonly
git add frontend/src/pages/Settings/scheduler/JobHistoryDrawer.tsx
git commit -m "feat(phase5-p2): JobHistoryDrawer with status filter + row expand"
```

---

## Task 7: SchedulerPage + route registration

**Files:**
- Create: `frontend/src/pages/Settings/SchedulerPage.tsx`
- Modify: `frontend/src/App.tsx` (or wherever routes live) — add `/settings/system/scheduler`
- Modify: the System settings menu component — add "Scheduler" entry

- [ ] **Step 1: SchedulerPage:**

```tsx
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { SettingsDetailLayout } from '@/components/settings/SettingsDetailLayout'
import { useSchedulerJobs } from '@/hooks/useSchedulerJobs'
import { JobCard } from './scheduler/JobCard'
import { JobHistoryDrawer } from './scheduler/JobHistoryDrawer'

export function SchedulerPage() {
  const { t } = useTranslation('settings')
  const { data, isLoading, error } = useSchedulerJobs()
  const [historyJob, setHistoryJob] = useState<string | null>(null)

  return (
    <SettingsDetailLayout
      title={t('scheduler.title')}
      subtitle={t('scheduler.subtitle')}
    >
      {error && (
        <div className="mb-4 rounded-lg border border-danger/50 bg-danger/10 p-4 text-danger">
          {t('scheduler.down_error')}
        </div>
      )}
      {isLoading && <div className="text-muted">{t('common.loading')}</div>}
      {data && (
        <div className="space-y-3">
          {data.jobs.map((j) => (
            <JobCard key={j.id} job={j} onOpenHistory={() => setHistoryJob(j.id)} />
          ))}
        </div>
      )}
      {historyJob && (
        <JobHistoryDrawer
          jobId={historyJob}
          open
          onClose={() => setHistoryJob(null)}
        />
      )}
    </SettingsDetailLayout>
  )
}
```

- [ ] **Step 2: Wire routing.** Read `frontend/src/App.tsx` (or equivalent) and add a lazy route for the scheduler page:

```tsx
const SchedulerPage = lazy(() =>
  import('./pages/Settings/SchedulerPage').then((m) => ({ default: m.SchedulerPage })),
)
```

And a Route entry under `/settings/system/scheduler`.

- [ ] **Step 3: Add menu entry** in the System settings index (whichever file renders the sidebar — likely `SystemSettings.tsx` or `SystemOverview.tsx`). Follow the pattern of existing entries.

- [ ] **Step 4: Typecheck + commit:**

```bash
cd /d/Sublarr_Projekt/Sublarr/.worktrees/phase5-p2-api-readonly/frontend && npx tsc --noEmit 2>&1 | tail -5
cd /d/Sublarr_Projekt/Sublarr/.worktrees/phase5-p2-api-readonly
git add frontend/src/pages/Settings/SchedulerPage.tsx frontend/src/App.tsx
# Plus whatever menu file was modified
git commit -m "feat(phase5-p2): SchedulerPage route + System menu entry"
```

---

## Task 8: i18n strings

**Files:**
- Modify: `frontend/src/i18n/locales/de/settings.json`
- Modify: `frontend/src/i18n/locales/en/settings.json`

- [ ] **Step 1: Add scheduler.* keys to both locale files.**

Add (adjust structure to match existing file conventions — may need to nest under `scheduler`):

```json
{
  "scheduler": {
    "title": "Scheduler",
    "subtitle": "Geplante Hintergrund-Jobs verwalten",
    "every_seconds": "Alle {{n}} Sekunden",
    "every_minutes": "Alle {{n}} Minuten",
    "every_hours": "Alle {{n}} Stunden",
    "cron_daily": "Täglich {{hour}}:{{minute}}",
    "cron_weekly": "Wöchentlich {{dow}} {{hour}}:{{minute}}",
    "last_run": "Letzter Lauf",
    "next_run": "Nächster Lauf",
    "never": "—",
    "just_now": "gerade eben",
    "minutes_ago": "vor {{n}} min",
    "hours_ago": "vor {{n}} h",
    "edited": "Geändert",
    "paused": "Pausiert",
    "run_now": "Jetzt ausführen",
    "pause": "Pausieren",
    "resume": "Fortsetzen",
    "edit_trigger": "Zeitplan ändern",
    "history": "Verlauf",
    "reset_default": "Standard",
    "phase3_coming": "Verfügbar in Phase 3",
    "history_for": "Verlauf von {{job}}",
    "no_runs": "Noch keine Läufe.",
    "down_error": "Scheduler läuft auf dieser Instanz nicht.",
    "status": {
      "all": "Alle",
      "ok": "OK",
      "error": "Fehler",
      "timeout": "Timeout",
      "missed": "Verpasst",
      "skipped_overlap": "Übersprungen"
    }
  }
}
```

English version (EN must mirror DE):

```json
{
  "scheduler": {
    "title": "Scheduler",
    "subtitle": "Manage scheduled background jobs",
    "every_seconds": "Every {{n}} seconds",
    "every_minutes": "Every {{n}} minutes",
    "every_hours": "Every {{n}} hours",
    "cron_daily": "Daily at {{hour}}:{{minute}}",
    "cron_weekly": "Weekly {{dow}} {{hour}}:{{minute}}",
    "last_run": "Last run",
    "next_run": "Next run",
    "never": "—",
    "just_now": "just now",
    "minutes_ago": "{{n}} min ago",
    "hours_ago": "{{n}} h ago",
    "edited": "Edited",
    "paused": "Paused",
    "run_now": "Run now",
    "pause": "Pause",
    "resume": "Resume",
    "edit_trigger": "Edit trigger",
    "history": "History",
    "reset_default": "Reset default",
    "phase3_coming": "Available in Phase 3",
    "history_for": "History for {{job}}",
    "no_runs": "No runs yet.",
    "down_error": "Scheduler is not running on this replica.",
    "status": {
      "all": "All",
      "ok": "OK",
      "error": "Error",
      "timeout": "Timeout",
      "missed": "Missed",
      "skipped_overlap": "Skipped"
    }
  }
}
```

- [ ] **Step 2: Commit:**

```bash
git add frontend/src/i18n/locales/de/settings.json frontend/src/i18n/locales/en/settings.json
git commit -m "feat(phase5-p2): i18n strings for scheduler page"
```

---

## Task 9: Frontend component tests

**Files:**
- Create: `frontend/src/pages/Settings/__tests__/SchedulerPage.test.tsx`

- [ ] **Step 1: Basic rendering test** — matches existing project pattern (read another Settings page test first; follow its setup):

```tsx
import { describe, it, expect, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { SchedulerPage } from '../SchedulerPage'

vi.mock('@/api/scheduler', () => ({
  listJobs: vi.fn().mockResolvedValue({
    jobs: [
      {
        id: 'scheduler_history_cleanup',
        description: 'Delete old rows',
        owner_module: 'services.scheduler',
        trigger: { type: 'cron', hour: '3', minute: '15' },
        trigger_is_default: true,
        paused: false,
        next_run_time: '2026-04-19T03:15:00Z',
        last_run: null,
        stats_7d: { ok: 0, error: 0, timeout: 0, missed: 0, skipped_overlap: 0 },
      },
    ],
  }),
  listRuns: vi.fn().mockResolvedValue({ total: 0, limit: 50, offset: 0, runs: [] }),
  getJob: vi.fn(),
}))

const renderPage = () => {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <SchedulerPage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('SchedulerPage', () => {
  it('renders job cards', async () => {
    renderPage()
    await waitFor(() =>
      expect(screen.getByText('scheduler_history_cleanup')).toBeInTheDocument(),
    )
  })

  it('disables write action buttons', async () => {
    renderPage()
    await waitFor(() => screen.getByText('scheduler_history_cleanup'))
    const runBtn = screen.getByRole('button', { name: /run now/i })
    expect(runBtn).toBeDisabled()
  })
})
```

- [ ] **Step 2: Run tests:**

`cd /d/Sublarr_Projekt/Sublarr/.worktrees/phase5-p2-api-readonly/frontend && npm run test -- --run src/pages/Settings/__tests__/SchedulerPage.test.tsx 2>&1 | tail -20`

Expected: 2 passed.

- [ ] **Step 3: Commit:**

```bash
git add frontend/src/pages/Settings/__tests__/SchedulerPage.test.tsx
git commit -m "test(phase5-p2): SchedulerPage component tests"
```

---

## Task 10: Final acceptance & regression check

- [ ] **Backend full suite:**

`cd /d/Sublarr_Projekt/Sublarr/.worktrees/phase5-p2-api-readonly/backend && /d/Sublarr_Projekt/Sublarr/backend/venv/Scripts/python.exe -m pytest tests/test_scheduler_routes.py tests/test_scheduler_serializers.py tests/test_scheduler_*.py -v --tb=short 2>&1 | tail -15`

Expected: all scheduler tests green. Compare count to Phase 1 baseline (68) + Phase 2 new tests (~11) ≈ 79+.

- [ ] **Frontend lint + typecheck + tests:**

```bash
cd /d/Sublarr_Projekt/Sublarr/.worktrees/phase5-p2-api-readonly/frontend
npm run lint 2>&1 | tail -10
npx tsc --noEmit 2>&1 | tail -5
npm run test -- --run 2>&1 | tail -20
```

Expected: no new failures; only regressions would be concerning.

- [ ] **Ruff check on backend:**

`cd /d/Sublarr_Projekt/Sublarr/.worktrees/phase5-p2-api-readonly/backend && ruff check . && ruff format --check . 2>&1 | tail -5`

- [ ] **Final commit count:**

`cd /d/Sublarr_Projekt/Sublarr/.worktrees/phase5-p2-api-readonly && git log master..HEAD --oneline | wc -l`

Expected: ~10 commits.

---

## Phase 2 acceptance checklist

- [ ] `/api/v1/scheduler/jobs` returns all registered JobSpecs with live state
- [ ] `/api/v1/scheduler/jobs/<id>` returns single job detail or 404
- [ ] `/api/v1/scheduler/jobs/<id>/runs` paginates with status filter
- [ ] 503 `SchedulerDownError` when scheduler not running
- [ ] Settings → System → Scheduler menu entry renders
- [ ] SchedulerPage lists all jobs with card layout
- [ ] JobHistoryDrawer opens + paginates + filters by status
- [ ] All action buttons visible but disabled with "Phase 3 coming" tooltip
- [ ] Error banner when GET /jobs returns 503
- [ ] i18n DE + EN both populated
- [ ] All scheduler tests green (backend + frontend)
- [ ] Ruff + typecheck clean

---

## Phase 3 preview

Phase 3 unlocks the disabled buttons: adds `POST /run-now`, `POST /pause`, `POST /resume`, `PATCH /jobs/<id>` (with TriggerEditModal), `POST /reset-default`. Tests: 409 conflicts, audit log, optimistic UI. Separate plan file.
