# Phase 5 / Rollout Phase 3 — Write Endpoints + CRUD UI

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Steps use `- [ ]` checkboxes.

**Spec:** `docs/superpowers/specs/2026-04-18-phase5-scheduler-hardening-design.md`
**Prior phase:** `docs/superpowers/plans/2026-04-19-phase5-scheduler-hardening-phase2-readonly-api-ui.md` (deployed as 0.56.0-beta)

**Goal:** Unlock the disabled action buttons in the SchedulerPage by adding `POST /run-now`, `POST /pause`, `POST /resume`, `PATCH /jobs/<id>` (modify trigger), `POST /reset-default` endpoints, plus a `TriggerEditModal` with interval + cron editors and a "next 3 fires" preview. Every mutation logs an admin audit line. Wraps up the user-facing scheduler feature — after Phase 3 the operator has full lifecycle control over the one registered job; Phase 4 will migrate the 4 legacy Timer sites.

**Architecture:** Five new Flask routes on the existing `routes/system/scheduler.py` blueprint, input-validated via the existing `IntervalTriggerModel` / `CronTriggerModel` Pydantic schemas from Phase 2. Frontend adds mutation hooks (React Query `useMutation`), `TriggerEditModal` component, and enables all disabled buttons in `JobCard`. Toast notifications via Sublarr's existing Toast primitive. E2E Playwright spec covers the golden path.

**Tech Stack:** Flask, Pydantic, APScheduler, React 19, Tailwind, React Query mutations, Playwright.

**Dependencies:** Phase 2 (0.56.0-beta) deployed. The `SublarrScheduler` facade already implements `run_now`, `pause_job`, `resume_job`, `modify_trigger`, `reset_to_default` with correct `JobNotRegisteredError` / `OneshotAlreadyPendingError` exceptions.

---

## File Structure

### New backend files
- `backend/tests/test_scheduler_write_routes.py` — route tests for mutations (~320 LOC)

### Modified backend files
- `backend/routes/system/scheduler.py` — add 5 mutation routes (~180 LOC added)
- `backend/routes/system/scheduler_serializers.py` — add `trigger_model_to_apscheduler_trigger` converter (~50 LOC added)
- `backend/tests/test_scheduler_serializers.py` — tests for converter (~60 LOC added)

### New frontend files
- `frontend/src/pages/Settings/scheduler/TriggerEditModal.tsx` (~220 LOC)
- `frontend/src/pages/Settings/scheduler/IntervalEditor.tsx` (~60 LOC)
- `frontend/src/pages/Settings/scheduler/CronEditor.tsx` (~140 LOC)
- `frontend/src/hooks/useSchedulerMutations.ts` (~80 LOC)
- `frontend/src/pages/Settings/scheduler/__tests__/TriggerEditModal.test.tsx` (~100 LOC)
- `frontend/e2e/scheduler.spec.ts` — Playwright golden-path spec (~80 LOC)

### Modified frontend files
- `frontend/src/api/scheduler.ts` — add `runNow`, `pauseJob`, `resumeJob`, `modifyTrigger`, `resetDefault` functions
- `frontend/src/pages/Settings/scheduler/JobCard.tsx` — enable disabled buttons, wire mutations + toast
- `frontend/src/i18n/locales/{de,en}/settings.json` — add new mutation i18n keys
- `frontend/package.json` — add `cron-parser` dev dep for client-side next-fires preview

---

## Task 1: Trigger converter (TriggerModel → APScheduler trigger)

**Files:**
- Modify: `backend/routes/system/scheduler_serializers.py`
- Modify: `backend/tests/test_scheduler_serializers.py`

- [ ] **Step 1: Append failing tests to existing `test_scheduler_serializers.py`:**

```python
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from routes.system.scheduler_serializers import (
    IntervalTriggerModel,
    CronTriggerModel,
    trigger_model_to_apscheduler,
    InvalidTriggerError,
)


def test_interval_model_to_aps_seconds():
    m = IntervalTriggerModel(type="interval", seconds=90)
    trig = trigger_model_to_apscheduler(m)
    assert isinstance(trig, IntervalTrigger)
    assert trig.interval.total_seconds() == 90


def test_interval_model_to_aps_minutes():
    m = IntervalTriggerModel(type="interval", minutes=15)
    trig = trigger_model_to_apscheduler(m)
    assert trig.interval.total_seconds() == 900


def test_cron_model_to_aps_hour_minute():
    m = CronTriggerModel(type="cron", hour=3, minute=0)
    trig = trigger_model_to_apscheduler(m)
    assert isinstance(trig, CronTrigger)
    # get_next_fire_time returns None iff trigger is unreachable; 03:00 is reachable
    import datetime
    next_fire = trig.get_next_fire_time(None, datetime.datetime.now(datetime.UTC))
    assert next_fire is not None


def test_cron_expression_shorthand():
    m = CronTriggerModel(type="cron", expression="0 3 * * *")
    trig = trigger_model_to_apscheduler(m)
    assert isinstance(trig, CronTrigger)


def test_unreachable_cron_raises():
    import pytest
    # day_of_week="xyz" is invalid — APScheduler raises on build, we re-wrap
    m = CronTriggerModel(type="cron", day_of_week="xyz", hour=3)
    with pytest.raises(InvalidTriggerError):
        trigger_model_to_apscheduler(m)
```

- [ ] **Step 2: Run — expect FAIL (ImportError).**

- [ ] **Step 3: Append to `backend/routes/system/scheduler_serializers.py`:**

```python
class InvalidTriggerError(ValueError):
    """Raised when a TriggerModel can't be converted to an APScheduler trigger."""


def trigger_model_to_apscheduler(model: TriggerModel) -> BaseTrigger:
    """Convert a validated TriggerModel into an APScheduler BaseTrigger.

    Raises InvalidTriggerError if the resulting trigger would never fire
    (e.g. day_of_week of an unknown value) or if APScheduler's own
    validation rejects the parameters.
    """
    try:
        if isinstance(model, IntervalTriggerModel):
            kwargs: dict[str, int] = {}
            if model.seconds is not None:
                kwargs["seconds"] = model.seconds
            if model.minutes is not None:
                kwargs["minutes"] = model.minutes
            if model.hours is not None:
                kwargs["hours"] = model.hours
            return IntervalTrigger(**kwargs, timezone="UTC")

        # Cron
        if model.expression:
            # Accept "m h dom mon dow" five-field cron shorthand
            parts = model.expression.strip().split()
            if len(parts) == 5:
                minute, hour, day, month, dow = parts
                return CronTrigger(
                    minute=minute, hour=hour, day=day,
                    month=month, day_of_week=dow,
                    timezone="UTC",
                )
            if len(parts) == 6:
                second, minute, hour, day, month, dow = parts
                return CronTrigger(
                    second=second, minute=minute, hour=hour, day=day,
                    month=month, day_of_week=dow,
                    timezone="UTC",
                )
            raise InvalidTriggerError(
                f"expression must have 5 or 6 fields, got {len(parts)}"
            )

        fields = {
            k: getattr(model, k)
            for k in (
                "year", "month", "day", "week",
                "day_of_week", "hour", "minute", "second",
            )
            if getattr(model, k) is not None
        }
        trig = CronTrigger(**fields, timezone="UTC")

        # Reachability guard: if the first call returns None, the trigger
        # will never fire — reject at save time rather than silently
        # persisting a dead schedule.
        import datetime
        if trig.get_next_fire_time(None, datetime.datetime.now(datetime.UTC)) is None:
            raise InvalidTriggerError("cron trigger is unreachable (no next fire time)")
        return trig
    except (ValueError, TypeError) as exc:
        if isinstance(exc, InvalidTriggerError):
            raise
        raise InvalidTriggerError(str(exc)) from exc
```

- [ ] **Step 4: Run tests — 5 new passed + 4 prior still green (9 total).**

- [ ] **Step 5: Ruff + commit:**

```bash
cd /d/Sublarr_Projekt/Sublarr/.worktrees/phase5-p3-write-endpoints
git add backend/routes/system/scheduler_serializers.py backend/tests/test_scheduler_serializers.py
git commit -m "feat(phase5-p3): add trigger_model_to_apscheduler converter + InvalidTriggerError"
```

---

## Task 2: Write endpoints (run-now, pause, resume, PATCH, reset-default)

**Files:**
- Modify: `backend/routes/system/scheduler.py`
- Create: `backend/tests/test_scheduler_write_routes.py`

- [ ] **Step 1: Write failing tests.**

Create `backend/tests/test_scheduler_write_routes.py`:

```python
"""Write-endpoint tests for /api/v1/scheduler/*."""

import time

import pytest


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("SUBLARR_DB_PATH", str(tmp_path / "app.db"))
    monkeypatch.setenv("SUBLARR_SCHEDULER_ROLE", "primary")
    monkeypatch.setenv("SUBLARR_API_KEY", "")
    from config import reload_settings
    reload_settings()
    from app import create_app
    app = create_app(testing=True)
    from extensions import db as sa_db
    with app.app_context():
        sa_db.create_all()
    yield app
    scheduler = app.extensions.get("scheduler")
    if scheduler and scheduler.running:
        scheduler.shutdown(timeout_s=2)


@pytest.fixture
def client(app):
    from services.scheduler import bootstrap_scheduler
    with app.app_context():
        if app.extensions.get("scheduler") is None:
            bootstrap_scheduler(app)
    return app.test_client()


def test_run_now_queues_oneshot(client):
    resp = client.post("/api/v1/scheduler/jobs/scheduler_history_cleanup/run-now")
    assert resp.status_code == 202
    data = resp.get_json()
    assert data["status"] == "queued"
    assert data["oneshot_id"].startswith("scheduler_history_cleanup_oneshot_")


def test_run_now_404_unknown(client):
    resp = client.post("/api/v1/scheduler/jobs/nope/run-now")
    assert resp.status_code == 404


def test_pause_and_resume(client):
    r = client.post("/api/v1/scheduler/jobs/scheduler_history_cleanup/pause")
    assert r.status_code == 200
    assert r.get_json()["status"] == "paused"

    r = client.post("/api/v1/scheduler/jobs/scheduler_history_cleanup/resume")
    assert r.status_code == 200
    assert r.get_json()["status"] == "running"


def test_pause_404_unknown(client):
    r = client.post("/api/v1/scheduler/jobs/nope/pause")
    assert r.status_code == 404


def test_patch_trigger_interval(client):
    r = client.patch(
        "/api/v1/scheduler/jobs/scheduler_history_cleanup",
        json={"trigger": {"type": "interval", "minutes": 30}},
    )
    assert r.status_code == 200
    data = r.get_json()
    assert data["trigger"]["type"] == "interval"
    assert data["trigger"]["seconds"] == 1800
    assert data["trigger_is_default"] is False


def test_patch_trigger_cron(client):
    r = client.patch(
        "/api/v1/scheduler/jobs/scheduler_history_cleanup",
        json={"trigger": {"type": "cron", "hour": 4, "minute": 30}},
    )
    assert r.status_code == 200
    data = r.get_json()
    assert data["trigger"]["type"] == "cron"
    assert data["trigger"]["hour"] == "4"


def test_patch_invalid_payload(client):
    r = client.patch(
        "/api/v1/scheduler/jobs/scheduler_history_cleanup",
        json={"trigger": {"type": "interval"}},  # missing unit
    )
    assert r.status_code == 400


def test_patch_unreachable_cron(client):
    r = client.patch(
        "/api/v1/scheduler/jobs/scheduler_history_cleanup",
        json={"trigger": {"type": "cron", "day_of_week": "xyz"}},
    )
    assert r.status_code == 400


def test_patch_404_unknown(client):
    r = client.patch(
        "/api/v1/scheduler/jobs/nope",
        json={"trigger": {"type": "interval", "minutes": 1}},
    )
    assert r.status_code == 404


def test_reset_default(client):
    # First modify
    client.patch(
        "/api/v1/scheduler/jobs/scheduler_history_cleanup",
        json={"trigger": {"type": "interval", "minutes": 30}},
    )
    # Then reset
    r = client.post("/api/v1/scheduler/jobs/scheduler_history_cleanup/reset-default")
    assert r.status_code == 200
    data = r.get_json()
    assert data["trigger_is_default"] is True


def test_reset_default_404(client):
    r = client.post("/api/v1/scheduler/jobs/nope/reset-default")
    assert r.status_code == 404


def test_admin_action_audit_logged(client, caplog):
    import logging
    with caplog.at_level(logging.INFO, logger="routes.system.scheduler"):
        client.post("/api/v1/scheduler/jobs/scheduler_history_cleanup/pause")
    assert any("scheduler_admin_action" in r.message for r in caplog.records)


def test_503_when_scheduler_down(app, client):
    with app.app_context():
        app.extensions["scheduler"] = None
    r = client.post("/api/v1/scheduler/jobs/scheduler_history_cleanup/run-now")
    assert r.status_code == 503
```

- [ ] **Step 2: Run — expect failures (endpoints don't exist).**

- [ ] **Step 3: Add routes to `backend/routes/system/scheduler.py`.** Append after the existing GET routes:

```python
from pydantic import ValidationError

from routes.system.scheduler_serializers import (
    CronTriggerModel,
    InvalidTriggerError,
    IntervalTriggerModel,
    trigger_model_to_apscheduler,
)
from services.scheduler import (
    JobNotRegisteredError,
    OneshotAlreadyPendingError,
)


def _audit_log(job_id: str, action: str) -> None:
    """Log admin action for audit trail."""
    # Fingerprint the API key (first 6 chars) without storing full value
    api_key = request.headers.get("X-Api-Key", "")
    fp = api_key[:6] if api_key else "anon"
    logger.info(
        "scheduler_admin_action job_id=%s action=%s actor=%s",
        job_id, action, fp,
    )


def _parse_trigger_model(data: dict) -> object:
    """Parse an incoming trigger dict into IntervalTriggerModel or CronTriggerModel."""
    t = (data or {}).get("type")
    if t == "interval":
        return IntervalTriggerModel.model_validate(data)
    if t == "cron":
        return CronTriggerModel.model_validate(data)
    raise ValueError(f"unknown trigger type: {t!r}")


@bp.route("/jobs/<job_id>/run-now", methods=["POST"])
def run_now(job_id: str):
    s = _get_scheduler()
    if s is None:
        return _scheduler_down_response()
    if job_id not in s._registered_ids:
        return jsonify({
            "error": f"Job {job_id!r} not found",
            "error_type": "NotFoundError",
        }), 404
    try:
        oneshot_id = s.run_now(job_id)
    except OneshotAlreadyPendingError as exc:
        return jsonify({
            "error": str(exc),
            "error_type": "OneshotAlreadyPendingError",
        }), 409
    _audit_log(job_id, "run-now")
    return jsonify({"status": "queued", "oneshot_id": oneshot_id}), 202


@bp.route("/jobs/<job_id>/pause", methods=["POST"])
def pause(job_id: str):
    s = _get_scheduler()
    if s is None:
        return _scheduler_down_response()
    if job_id not in s._registered_ids:
        return jsonify({
            "error": f"Job {job_id!r} not found",
            "error_type": "NotFoundError",
        }), 404
    job = s._scheduler.get_job(job_id)
    if job is not None and job.next_run_time is None:
        return jsonify({
            "error": f"{job_id} is already paused",
            "error_type": "ConflictError",
        }), 409
    s.pause_job(job_id)
    _audit_log(job_id, "pause")
    return jsonify({"status": "paused"}), 200


@bp.route("/jobs/<job_id>/resume", methods=["POST"])
def resume(job_id: str):
    s = _get_scheduler()
    if s is None:
        return _scheduler_down_response()
    if job_id not in s._registered_ids:
        return jsonify({
            "error": f"Job {job_id!r} not found",
            "error_type": "NotFoundError",
        }), 404
    job = s._scheduler.get_job(job_id)
    if job is not None and job.next_run_time is not None:
        return jsonify({
            "error": f"{job_id} is not paused",
            "error_type": "ConflictError",
        }), 409
    s.resume_job(job_id)
    _audit_log(job_id, "resume")
    return jsonify({"status": "running"}), 200


@bp.route("/jobs/<job_id>", methods=["PATCH"])
def modify(job_id: str):
    s = _get_scheduler()
    if s is None:
        return _scheduler_down_response()
    if job_id not in s._registered_ids:
        return jsonify({
            "error": f"Job {job_id!r} not found",
            "error_type": "NotFoundError",
        }), 404
    body = request.get_json(silent=True) or {}
    trigger_payload = body.get("trigger")
    if not isinstance(trigger_payload, dict):
        return jsonify({
            "error": "body must include {trigger: {...}}",
            "error_type": "ValidationError",
        }), 400
    try:
        model = _parse_trigger_model(trigger_payload)
        aps_trigger = trigger_model_to_apscheduler(model)
    except (ValidationError, ValueError, InvalidTriggerError) as exc:
        return jsonify({
            "error": str(exc),
            "error_type": "ValidationError",
        }), 400
    s.modify_trigger(job_id, aps_trigger)
    _audit_log(job_id, "patch-trigger")
    return jsonify(_job_to_dict(s, job_id)), 200


@bp.route("/jobs/<job_id>/reset-default", methods=["POST"])
def reset_default(job_id: str):
    s = _get_scheduler()
    if s is None:
        return _scheduler_down_response()
    if job_id not in s._registered_ids:
        return jsonify({
            "error": f"Job {job_id!r} not found",
            "error_type": "NotFoundError",
        }), 404
    s.reset_to_default(job_id)
    _audit_log(job_id, "reset-default")
    return jsonify(_job_to_dict(s, job_id)), 200
```

- [ ] **Step 4: Run tests — 12 new passed + 7 prior still green (19 total for routes).**

- [ ] **Step 5: Ruff + commit:**

```bash
git add backend/routes/system/scheduler.py backend/tests/test_scheduler_write_routes.py
git commit -m "feat(phase5-p3): add run-now/pause/resume/PATCH/reset-default endpoints with audit logging"
```

---

## Task 3: Frontend API client mutations

**Files:**
- Modify: `frontend/src/api/scheduler.ts`

- [ ] **Step 1: Append to `frontend/src/api/scheduler.ts`** (match existing axios-style from Phase 2):

```ts
import type { SchedulerJob, Trigger } from '@/lib/types'
// (existing imports kept)

export async function runNow(id: string): Promise<{ status: string; oneshot_id: string }> {
  const { data } = await api.post(`/scheduler/jobs/${encodeURIComponent(id)}/run-now`)
  return data
}

export async function pauseJob(id: string): Promise<{ status: string }> {
  const { data } = await api.post(`/scheduler/jobs/${encodeURIComponent(id)}/pause`)
  return data
}

export async function resumeJob(id: string): Promise<{ status: string }> {
  const { data } = await api.post(`/scheduler/jobs/${encodeURIComponent(id)}/resume`)
  return data
}

export async function modifyTrigger(id: string, trigger: Trigger): Promise<SchedulerJob> {
  const { data } = await api.patch(
    `/scheduler/jobs/${encodeURIComponent(id)}`,
    { trigger },
  )
  return data
}

export async function resetDefault(id: string): Promise<SchedulerJob> {
  const { data } = await api.post(
    `/scheduler/jobs/${encodeURIComponent(id)}/reset-default`,
  )
  return data
}
```

- [ ] **Step 2: Typecheck + commit:**

```bash
cd /d/Sublarr_Projekt/Sublarr/.worktrees/phase5-p3-write-endpoints/frontend
/d/Sublarr_Projekt/Sublarr/frontend/node_modules/.bin/tsc --noEmit 2>&1 | tail -5
cd /d/Sublarr_Projekt/Sublarr/.worktrees/phase5-p3-write-endpoints
git add frontend/src/api/scheduler.ts
git commit -m "feat(phase5-p3): scheduler API client mutations"
```

---

## Task 4: useSchedulerMutations hooks

**Files:**
- Create: `frontend/src/hooks/useSchedulerMutations.ts`

- [ ] **Step 1: Create the file:**

```ts
import { useMutation, useQueryClient } from '@tanstack/react-query'
import {
  modifyTrigger,
  pauseJob,
  resetDefault,
  resumeJob,
  runNow,
} from '@/api/scheduler'
import type { Trigger } from '@/lib/types'

export function useSchedulerMutations(jobId: string) {
  const qc = useQueryClient()
  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ['scheduler', 'jobs'] })
    qc.invalidateQueries({ queryKey: ['scheduler', 'jobs', jobId] })
  }

  return {
    runNow: useMutation({
      mutationFn: () => runNow(jobId),
      onSuccess: invalidate,
    }),
    pause: useMutation({
      mutationFn: () => pauseJob(jobId),
      onSuccess: invalidate,
    }),
    resume: useMutation({
      mutationFn: () => resumeJob(jobId),
      onSuccess: invalidate,
    }),
    patchTrigger: useMutation({
      mutationFn: (trigger: Trigger) => modifyTrigger(jobId, trigger),
      onSuccess: invalidate,
    }),
    resetDefault: useMutation({
      mutationFn: () => resetDefault(jobId),
      onSuccess: invalidate,
    }),
  }
}
```

- [ ] **Step 2: Typecheck + commit:**

```bash
cd /d/Sublarr_Projekt/Sublarr/.worktrees/phase5-p3-write-endpoints/frontend
/d/Sublarr_Projekt/Sublarr/frontend/node_modules/.bin/tsc --noEmit 2>&1 | tail -5
cd /d/Sublarr_Projekt/Sublarr/.worktrees/phase5-p3-write-endpoints
git add frontend/src/hooks/useSchedulerMutations.ts
git commit -m "feat(phase5-p3): useSchedulerMutations hooks"
```

---

## Task 5: IntervalEditor + CronEditor components

**Files:**
- Create: `frontend/src/pages/Settings/scheduler/IntervalEditor.tsx`
- Create: `frontend/src/pages/Settings/scheduler/CronEditor.tsx`

- [ ] **Step 1: IntervalEditor:**

```tsx
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { TriggerInterval } from '@/lib/types'

type Unit = 'seconds' | 'minutes' | 'hours'

export function IntervalEditor({
  value,
  onChange,
}: {
  value: TriggerInterval
  onChange: (v: TriggerInterval) => void
}) {
  const { t } = useTranslation('settings')
  const initialUnit: Unit = value.hours ? 'hours' : value.minutes ? 'minutes' : 'seconds'
  const initialN = value.hours ?? value.minutes ?? value.seconds ?? 1
  const [unit, setUnit] = useState<Unit>(initialUnit)
  const [n, setN] = useState(initialN)

  useEffect(() => {
    const base: TriggerInterval = { type: 'interval' }
    base[unit] = Math.max(1, n)
    onChange(base)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [n, unit])

  return (
    <div className="flex items-end gap-2">
      <label className="flex flex-col text-sm">
        <span className="mb-1 text-muted">{t('scheduler.interval_n')}</span>
        <input
          type="number"
          min={1}
          value={n}
          onChange={(e) => setN(Math.max(1, Number(e.target.value) || 1))}
          className="w-24 rounded-md border border-border bg-surface px-2 py-1"
        />
      </label>
      <label className="flex flex-col text-sm">
        <span className="mb-1 text-muted">{t('scheduler.interval_unit')}</span>
        <select
          value={unit}
          onChange={(e) => setUnit(e.target.value as Unit)}
          className="rounded-md border border-border bg-surface px-2 py-1"
        >
          <option value="seconds">{t('scheduler.unit_seconds')}</option>
          <option value="minutes">{t('scheduler.unit_minutes')}</option>
          <option value="hours">{t('scheduler.unit_hours')}</option>
        </select>
      </label>
    </div>
  )
}
```

- [ ] **Step 2: CronEditor** (with "next 3 fires" preview using `cron-parser`):

```tsx
import { useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { TriggerCron } from '@/lib/types'

type Mode = 'daily' | 'weekly' | 'advanced'

const DAYS = ['sun', 'mon', 'tue', 'wed', 'thu', 'fri', 'sat']

export function CronEditor({
  value,
  onChange,
}: {
  value: TriggerCron
  onChange: (v: TriggerCron) => void
}) {
  const { t } = useTranslation('settings')
  const [mode, setMode] = useState<Mode>(
    value.day_of_week ? 'weekly' : 'daily',
  )
  const [hour, setHour] = useState(Number(value.hour ?? '3'))
  const [minute, setMinute] = useState(Number(value.minute ?? '0'))
  const [days, setDays] = useState<string[]>(
    (value.day_of_week ?? '').split(',').filter(Boolean),
  )
  const [expression, setExpression] = useState('0 3 * * *')

  useEffect(() => {
    if (mode === 'daily') {
      onChange({ type: 'cron', hour: String(hour), minute: String(minute) })
    } else if (mode === 'weekly') {
      onChange({
        type: 'cron',
        hour: String(hour),
        minute: String(minute),
        day_of_week: days.join(',') || 'mon',
      })
    } else {
      // parse expression lazily below via preview; emit as-is
      onChange({ type: 'cron' }) // placeholder; TriggerEditModal validates on Save
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode, hour, minute, days])

  const nextFires = useMemo(() => {
    try {
      // dynamic import so the library isn't bundled on non-cron paths
      // eslint-disable-next-line @typescript-eslint/no-require-imports
      const parser = require('cron-parser')
      const expr =
        mode === 'advanced'
          ? expression
          : mode === 'daily'
            ? `${minute} ${hour} * * *`
            : `${minute} ${hour} * * ${days.join(',') || '*'}`
      const interval = parser.parseExpression(expr, { tz: 'UTC' })
      return [0, 1, 2].map(() => interval.next().toDate().toISOString())
    } catch {
      return []
    }
  }, [mode, hour, minute, days, expression])

  return (
    <div className="flex flex-col gap-3">
      <div className="flex gap-2">
        {(['daily', 'weekly', 'advanced'] as Mode[]).map((m) => (
          <button
            key={m}
            type="button"
            onClick={() => setMode(m)}
            className={`rounded-md px-3 py-1 text-sm ${
              mode === m ? 'bg-accent text-white' : 'border border-border'
            }`}
          >
            {t(`scheduler.cron_mode_${m}`)}
          </button>
        ))}
      </div>

      {mode !== 'advanced' && (
        <div className="flex items-center gap-2 text-sm">
          <input
            type="number"
            min={0}
            max={23}
            value={hour}
            onChange={(e) => setHour(Math.min(23, Math.max(0, Number(e.target.value))))}
            className="w-16 rounded-md border border-border bg-surface px-2 py-1"
          />
          <span>:</span>
          <input
            type="number"
            min={0}
            max={59}
            value={minute}
            onChange={(e) => setMinute(Math.min(59, Math.max(0, Number(e.target.value))))}
            className="w-16 rounded-md border border-border bg-surface px-2 py-1"
          />
          <span className="text-muted">UTC</span>
        </div>
      )}

      {mode === 'weekly' && (
        <div className="flex flex-wrap gap-1">
          {DAYS.map((d) => (
            <button
              key={d}
              type="button"
              onClick={() =>
                setDays((prev) =>
                  prev.includes(d) ? prev.filter((x) => x !== d) : [...prev, d],
                )
              }
              className={`rounded-full px-3 py-1 text-xs ${
                days.includes(d) ? 'bg-accent text-white' : 'border border-border'
              }`}
            >
              {t(`scheduler.dow_${d}`)}
            </button>
          ))}
        </div>
      )}

      {mode === 'advanced' && (
        <input
          type="text"
          value={expression}
          onChange={(e) => setExpression(e.target.value)}
          className="w-full rounded-md border border-border bg-surface px-2 py-1 font-mono text-sm"
          placeholder="0 3 * * *"
        />
      )}

      <div className="rounded-md bg-elevated p-2 text-xs text-muted">
        <div className="mb-1">{t('scheduler.next_fires')}</div>
        {nextFires.length === 0 ? (
          <div className="text-error">{t('scheduler.cron_invalid')}</div>
        ) : (
          <ul className="list-inside list-disc">
            {nextFires.map((ts) => (
              <li key={ts} className="font-mono">
                {new Date(ts).toLocaleString()}
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  )
}
```

**Note on `require('cron-parser')`:** if the project only allows ES modules, change to `import cronParser from 'cron-parser'` at top and drop the dynamic require. Check `frontend/package.json` + `tsconfig.json` — adapt.

- [ ] **Step 3: Add `cron-parser` to `frontend/package.json`:**

```bash
cd /d/Sublarr_Projekt/Sublarr/.worktrees/phase5-p3-write-endpoints/frontend
npm install --save cron-parser
```

- [ ] **Step 4: Typecheck + commit:**

```bash
/d/Sublarr_Projekt/Sublarr/frontend/node_modules/.bin/tsc --noEmit 2>&1 | tail -5
cd /d/Sublarr_Projekt/Sublarr/.worktrees/phase5-p3-write-endpoints
git add frontend/src/pages/Settings/scheduler/IntervalEditor.tsx frontend/src/pages/Settings/scheduler/CronEditor.tsx frontend/package.json frontend/package-lock.json
git commit -m "feat(phase5-p3): IntervalEditor + CronEditor with next-fires preview"
```

---

## Task 6: TriggerEditModal

**Files:**
- Create: `frontend/src/pages/Settings/scheduler/TriggerEditModal.tsx`

- [ ] **Step 1: Create the modal:**

```tsx
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { X } from 'lucide-react'
import type { SchedulerJob, Trigger, TriggerCron, TriggerInterval } from '@/lib/types'
import { IntervalEditor } from './IntervalEditor'
import { CronEditor } from './CronEditor'

type Tab = 'interval' | 'cron'

export function TriggerEditModal({
  job,
  open,
  onClose,
  onSubmit,
  isSubmitting = false,
  error = null,
}: {
  job: SchedulerJob
  open: boolean
  onClose: () => void
  onSubmit: (trigger: Trigger) => void
  isSubmitting?: boolean
  error?: string | null
}) {
  const { t } = useTranslation('settings')
  const initialTab: Tab = job.trigger.type
  const [tab, setTab] = useState<Tab>(initialTab)
  const [interval, setInterval] = useState<TriggerInterval>(
    job.trigger.type === 'interval' ? job.trigger : { type: 'interval', minutes: 15 },
  )
  const [cron, setCron] = useState<TriggerCron>(
    job.trigger.type === 'cron' ? job.trigger : { type: 'cron', hour: '3', minute: '0' },
  )

  if (!open) return null

  const payload: Trigger = tab === 'interval' ? interval : cron

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="w-full max-w-xl rounded-lg bg-surface p-5 shadow-xl">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="font-medium">
            {t('scheduler.edit_trigger_for', { job: job.id })}
          </h2>
          <button onClick={onClose} aria-label={t('common.close', { defaultValue: 'Close' })}>
            <X size={20} />
          </button>
        </div>

        <div className="mb-4 flex gap-2 border-b border-border">
          {(['interval', 'cron'] as Tab[]).map((tname) => (
            <button
              key={tname}
              type="button"
              onClick={() => setTab(tname)}
              className={`px-3 py-2 text-sm ${
                tab === tname
                  ? 'border-b-2 border-accent font-medium text-accent'
                  : 'text-muted'
              }`}
            >
              {t(`scheduler.tab_${tname}`)}
            </button>
          ))}
        </div>

        {tab === 'interval' ? (
          <IntervalEditor value={interval} onChange={setInterval} />
        ) : (
          <CronEditor value={cron} onChange={setCron} />
        )}

        {error && (
          <div className="mt-3 rounded-md bg-error-bg p-2 text-sm text-error">{error}</div>
        )}

        <div className="mt-5 flex justify-end gap-2">
          <button
            onClick={onClose}
            className="rounded-md border border-border px-3 py-1 text-sm"
          >
            {t('common.cancel', { defaultValue: 'Cancel' })}
          </button>
          <button
            onClick={() => onSubmit(payload)}
            disabled={isSubmitting}
            className="rounded-md bg-accent px-3 py-1 text-sm text-white disabled:opacity-50"
          >
            {isSubmitting
              ? t('common.saving', { defaultValue: 'Saving…' })
              : t('common.save', { defaultValue: 'Save' })}
          </button>
        </div>
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Typecheck + commit:**

```bash
cd /d/Sublarr_Projekt/Sublarr/.worktrees/phase5-p3-write-endpoints/frontend
/d/Sublarr_Projekt/Sublarr/frontend/node_modules/.bin/tsc --noEmit 2>&1 | tail -5
cd /d/Sublarr_Projekt/Sublarr/.worktrees/phase5-p3-write-endpoints
git add frontend/src/pages/Settings/scheduler/TriggerEditModal.tsx
git commit -m "feat(phase5-p3): TriggerEditModal with interval/cron tabs + submit handling"
```

---

## Task 7: Enable JobCard action buttons

**Files:**
- Modify: `frontend/src/pages/Settings/scheduler/JobCard.tsx`

- [ ] **Step 1: Update `JobCard.tsx`** to wire mutations + toast + TriggerEditModal. Replace the existing disabled-button block with:

```tsx
// near top of file:
import { useState } from 'react'
import { useSchedulerMutations } from '@/hooks/useSchedulerMutations'
import { TriggerEditModal } from './TriggerEditModal'
import { toast } from '@/components/shared/Toast'  // match existing toast API

// Inside JobCard:
const mut = useSchedulerMutations(job.id)
const [editOpen, setEditOpen] = useState(false)

const handleRunNow = () => {
  mut.runNow.mutate(undefined, {
    onSuccess: () => toast.success(t('scheduler.toast.queued')),
    onError: (e: Error) => toast.error(e.message),
  })
}

const handlePauseResume = () => {
  const fn = job.paused ? mut.resume : mut.pause
  fn.mutate(undefined, {
    onSuccess: () => toast.success(job.paused ? t('scheduler.toast.resumed') : t('scheduler.toast.paused')),
    onError: (e: Error) => toast.error(e.message),
  })
}

const handleReset = () => {
  if (!confirm(t('scheduler.confirm_reset'))) return
  mut.resetDefault.mutate(undefined, {
    onSuccess: () => toast.success(t('scheduler.toast.reset')),
    onError: (e: Error) => toast.error(e.message),
  })
}

const handleSaveTrigger = (trigger: Trigger) => {
  mut.patchTrigger.mutate(trigger, {
    onSuccess: () => {
      toast.success(t('scheduler.toast.updated'))
      setEditOpen(false)
    },
  })
}
```

Then replace each disabled button with an enabled version (remove `disabled`, remove `opacity-50`, remove the `title` tooltip, add the handler). The `[History]` button stays as-is (already enabled).

Pause/resume: conditionally render `Pause` or `Resume` icon based on `job.paused`.

At the end of the component's JSX (after the buttons, before the closing `</div>`), add:

```tsx
<TriggerEditModal
  job={job}
  open={editOpen}
  onClose={() => setEditOpen(false)}
  onSubmit={handleSaveTrigger}
  isSubmitting={mut.patchTrigger.isPending}
  error={mut.patchTrigger.error instanceof Error ? mut.patchTrigger.error.message : null}
/>
```

- [ ] **Step 2: Inspect existing toast API.**

Read `frontend/src/components/shared/Toast.tsx` (or wherever toast lives) — the API might be `toast({ type: 'success', ... })` instead of `toast.success(...)`. Adapt.

Also check the `confirm()` usage — if the project uses a custom confirm dialog component, use that instead.

- [ ] **Step 3: Typecheck + commit:**

```bash
cd /d/Sublarr_Projekt/Sublarr/.worktrees/phase5-p3-write-endpoints/frontend
/d/Sublarr_Projekt/Sublarr/frontend/node_modules/.bin/tsc --noEmit 2>&1 | tail -5
cd /d/Sublarr_Projekt/Sublarr/.worktrees/phase5-p3-write-endpoints
git add frontend/src/pages/Settings/scheduler/JobCard.tsx
git commit -m "feat(phase5-p3): enable JobCard action buttons — run-now/pause/resume/edit/reset"
```

---

## Task 8: i18n additions

**Files:**
- Modify: `frontend/src/i18n/locales/{de,en}/settings.json`

- [ ] **Step 1: Add these keys to both locale files** under `scheduler.*`:

DE:
```json
"interval_n": "Anzahl",
"interval_unit": "Einheit",
"unit_seconds": "Sekunden",
"unit_minutes": "Minuten",
"unit_hours": "Stunden",
"cron_mode_daily": "Täglich",
"cron_mode_weekly": "Wöchentlich",
"cron_mode_advanced": "Erweitert",
"dow_sun": "So", "dow_mon": "Mo", "dow_tue": "Di", "dow_wed": "Mi", "dow_thu": "Do", "dow_fri": "Fr", "dow_sat": "Sa",
"next_fires": "Nächste 3 Läufe",
"cron_invalid": "Cron-Ausdruck ungültig oder nicht erreichbar",
"edit_trigger_for": "Zeitplan für {{job}} bearbeiten",
"tab_interval": "Intervall",
"tab_cron": "Cron",
"confirm_reset": "Zeitplan auf Standard zurücksetzen?",
"toast": {
  "queued": "Auftrag eingereiht",
  "paused": "Pausiert",
  "resumed": "Fortgesetzt",
  "updated": "Zeitplan aktualisiert",
  "reset": "Auf Standard zurückgesetzt"
}
```

EN mirror:
```json
"interval_n": "Number",
"interval_unit": "Unit",
"unit_seconds": "seconds",
"unit_minutes": "minutes",
"unit_hours": "hours",
"cron_mode_daily": "Daily",
"cron_mode_weekly": "Weekly",
"cron_mode_advanced": "Advanced",
"dow_sun": "Sun", "dow_mon": "Mon", "dow_tue": "Tue", "dow_wed": "Wed", "dow_thu": "Thu", "dow_fri": "Fri", "dow_sat": "Sat",
"next_fires": "Next 3 fires",
"cron_invalid": "Cron expression invalid or unreachable",
"edit_trigger_for": "Edit trigger for {{job}}",
"tab_interval": "Interval",
"tab_cron": "Cron",
"confirm_reset": "Reset trigger to default?",
"toast": {
  "queued": "Run queued",
  "paused": "Paused",
  "resumed": "Resumed",
  "updated": "Trigger updated",
  "reset": "Reset to default"
}
```

Also add `common.cancel`, `common.save`, `common.saving` to `common.json` if not already present (English defaults baked into the code, but proper translations are preferred).

- [ ] **Step 2: Commit:**

```bash
git add frontend/src/i18n/locales/
git commit -m "feat(phase5-p3): i18n strings for TriggerEditModal + mutation toasts"
```

---

## Task 9: Frontend TriggerEditModal tests

**Files:**
- Create: `frontend/src/pages/Settings/scheduler/__tests__/TriggerEditModal.test.tsx`

- [ ] **Step 1: Create tests** (adapt the vitest/mock pattern from Phase 2's `SchedulerPage.test.tsx`):

```tsx
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { TriggerEditModal } from '../TriggerEditModal'
import type { SchedulerJob } from '@/lib/types'

const makeJob = (trigger: SchedulerJob['trigger']): SchedulerJob => ({
  id: 'test_job',
  description: '',
  owner_module: '',
  trigger,
  trigger_is_default: true,
  paused: false,
  next_run_time: null,
  last_run: null,
  stats_7d: { ok: 0, error: 0, timeout: 0, missed: 0, skipped_overlap: 0 },
})

describe('TriggerEditModal', () => {
  it('pre-selects interval tab when trigger is interval', () => {
    const onSubmit = vi.fn()
    render(
      <TriggerEditModal
        job={makeJob({ type: 'interval', minutes: 15 })}
        open
        onClose={() => {}}
        onSubmit={onSubmit}
      />,
    )
    // Both tabs are visible; the interval tab content ("Number" field) is the one shown
    const n = screen.getAllByRole('spinbutton')[0]
    expect(n).toBeInTheDocument()
  })

  it('pre-selects cron tab when trigger is cron', () => {
    render(
      <TriggerEditModal
        job={makeJob({ type: 'cron', hour: '3', minute: '0' })}
        open
        onClose={() => {}}
        onSubmit={vi.fn()}
      />,
    )
    // Daily / Weekly / Advanced mode buttons visible
    expect(screen.getByText(/Daily|Täglich/i)).toBeInTheDocument()
  })

  it('submits the current trigger on Save', () => {
    const onSubmit = vi.fn()
    render(
      <TriggerEditModal
        job={makeJob({ type: 'interval', minutes: 15 })}
        open
        onClose={() => {}}
        onSubmit={onSubmit}
      />,
    )
    fireEvent.click(screen.getByText(/Save|Speichern/i))
    expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({ type: 'interval' }))
  })

  it('does not render when open=false', () => {
    render(
      <TriggerEditModal
        job={makeJob({ type: 'interval', minutes: 15 })}
        open={false}
        onClose={() => {}}
        onSubmit={vi.fn()}
      />,
    )
    expect(screen.queryByText(/Edit trigger|Zeitplan/i)).not.toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run tests, expect 4 passed.** If i18n-mocking is needed to match labels, adapt following Phase 2's `SchedulerPage.test.tsx` pattern.

- [ ] **Step 3: Commit.**

---

## Task 10: E2E Playwright spec

**Files:**
- Create: `frontend/e2e/scheduler.spec.ts`

- [ ] **Step 1: Read existing e2e specs** for auth setup + API-key handling (likely via a shared `test.beforeEach` or an auth fixture).

- [ ] **Step 2: Create spec:**

```ts
import { expect, test } from '@playwright/test'

test.describe('Scheduler page', () => {
  test.beforeEach(async ({ page }) => {
    // Follow the project's login / API-key pattern — read an existing spec.
    await page.goto('/settings/system/scheduler')
  })

  test('renders registered jobs', async ({ page }) => {
    await expect(page.getByText('scheduler_history_cleanup')).toBeVisible()
  })

  test('run-now queues an execution and appears in history', async ({ page }) => {
    const runBtn = page.getByRole('button', { name: /run now|jetzt ausführen/i }).first()
    await runBtn.click()
    // Toast visible
    await expect(page.getByText(/queued|eingereiht/i)).toBeVisible({ timeout: 5000 })

    // Open history
    await page.getByRole('button', { name: /history|verlauf/i }).first().click()
    // Wait for new row (status 'ok') to appear
    await expect(page.getByText(/ok/i).first()).toBeVisible({ timeout: 10000 })
  })

  test('edit trigger → Edited pill appears, reset → pill disappears', async ({ page }) => {
    await page.getByRole('button', { name: /edit trigger|zeitplan ändern/i }).first().click()
    // Switch to interval tab, set minutes=30, save
    await page.getByRole('button', { name: /interval|intervall/i }).click()
    const nInput = page.getByRole('spinbutton').first()
    await nInput.fill('30')
    await page.getByRole('button', { name: /save|speichern/i }).click()
    await expect(page.getByText(/edited|geändert/i)).toBeVisible({ timeout: 5000 })

    // Reset
    page.once('dialog', (d) => d.accept())  // the confirm() dialog
    await page.getByRole('button', { name: /reset|standard/i }).first().click()
    await expect(page.getByText(/edited|geändert/i)).toHaveCount(0, { timeout: 5000 })
  })
})
```

- [ ] **Step 3: Run Playwright** (only if dev server is running or configured for CI):

```bash
cd /d/Sublarr_Projekt/Sublarr/.worktrees/phase5-p3-write-endpoints/frontend
npm run test:e2e -- scheduler.spec.ts 2>&1 | tail -20
```

This may require the dev server to be up. If the existing test config starts one automatically (`webServer` in `playwright.config.ts`), it should work. If not, the test is committed as-is but not run in this session — CI will exercise it.

- [ ] **Step 4: Commit.**

---

## Task 11: Full acceptance

- [ ] **Backend scheduler suite:**

```bash
cd /d/Sublarr_Projekt/Sublarr/.worktrees/phase5-p3-write-endpoints/backend
/d/Sublarr_Projekt/Sublarr/backend/venv/Scripts/python.exe -m pytest tests/test_scheduler_*.py -v --tb=short 2>&1 | tail -10
```

Expected: ~92 tests (80 from Phase 1+2 + 12 new from Phase 3).

- [ ] **Ruff clean:**

`cd backend && ruff check . && ruff format --check . 2>&1 | tail -3`

- [ ] **Frontend typecheck + vitest:**

```bash
cd /d/Sublarr_Projekt/Sublarr/.worktrees/phase5-p3-write-endpoints/frontend
/d/Sublarr_Projekt/Sublarr/frontend/node_modules/.bin/tsc --noEmit 2>&1 | tail -5
/d/Sublarr_Projekt/Sublarr/frontend/node_modules/.bin/vitest run src/pages/Settings/scheduler 2>&1 | tail -10
```

## Phase 3 acceptance

- [ ] POST /run-now returns 202 + oneshot_id
- [ ] POST /pause + /resume work with 409 on no-op
- [ ] PATCH /jobs/<id> accepts interval AND cron; 400 on invalid
- [ ] POST /reset-default restores code default + sets trigger_is_default=true
- [ ] Every mutation logs `scheduler_admin_action` at INFO with actor fingerprint
- [ ] TriggerEditModal opens with correct tab pre-selected
- [ ] Cron editor shows live "next 3 fires" preview
- [ ] JobCard buttons all enabled; clicking invokes the corresponding mutation
- [ ] Toast notifications on success/error
- [ ] DE + EN i18n populated
- [ ] All backend + frontend tests green
- [ ] E2E spec committed (optionally run)
