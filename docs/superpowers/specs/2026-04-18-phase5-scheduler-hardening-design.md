# Phase 5 — Scheduler Hardening Design

**Date:** 2026-04-18
**Status:** Approved design, awaiting implementation plan
**Part of:** V1 competitive parity initiative (`docs/superpowers/specs/2026-04-18-v1-competitive-parity.md`)
**Baseline version:** 0.54.1-beta

## Summary

Replace the ad-hoc `threading.Timer`-based scheduler loops with a single
APScheduler-backed service, add persistent run history and an admin UI,
and separate the two filesystem-event debouncers from the recurring
schedulers. Removes the entire `threading.Timer` cancel-before-reassign
bug class (memory `feedback_scheduler_timer_leak`), gives operators
visibility into periodic work, and produces the reliable job-identity
foundation that Phase 9's audit log will build on.

## Decisions taken during brainstorming

| # | Question | Decision |
|---|---|---|
| 1 | Migration scope | **Full migration** — all recurring `threading.Timer` sites move to APScheduler in one phase |
| 2 | JobStore backend | **`SQLAlchemyJobStore`** — persist on Sublarr's existing DB |
| 3 | UI scope | **Full CRUD** — list, run-now, pause/resume, edit trigger, reset to default, history |
| 4 | Schedule expression types | **Interval and cron per-job** — each `JobSpec` declares its natural trigger type |
| 5 | Error handling & history | **Dedicated `scheduler_job_runs` table** — populated via APScheduler event listeners |
| — | Architectural approach | **Explicit registry list** in `services/scheduler.py` (no decorators, no abstract facade) |

Guiding principle adopted for this design (memory `feedback_no_shortcuts`):
design the full correctness surface up front — lifecycle, persistence,
error handling, observability, retention, security, tests — no
stripped-down MVPs.

## Scope

### In scope — recurring schedulers (migrate to APScheduler)

| Site | Current role | New JobSpec id |
|---|---|---|
| `anidb_sync.py` | Weekly AniDB dump sync | `anidb_sync` |
| `cleanup_scheduler.py` | Periodic DB/filesystem cleanup | `cleanup` |
| `upgrade_scheduler.py` | Periodic upgrade scan | `upgrade_scan` |
| `services/wanted_scanner_scheduler.py` | Two timers: scan tick + search tick | `wanted_scanner`, `wanted_search` |

### In scope — debouncers (NOT APScheduler — different primitive)

| Site | Pattern | New home |
|---|---|---|
| `providers/plugins/watcher.py` | FS event debounce | `utils/debouncer.py::DebouncedCallback` |
| `standalone/watcher.py` | Per-path FS event coalescing | `utils/debouncer.py::DebouncedCallback` |

### In scope — new jobs

| JobSpec id | Reason |
|---|---|
| `scheduler_history_cleanup` | Dogfooded retention cron for `scheduler_job_runs` |
| `provider_budget_tick` | Make budget recovery deterministic (currently request-triggered) |
| `metrics_flush` | Steady-beat Prometheus flush for idle instances |

### Out of scope

- Celery / Dramatiq / Redis Queue migrations.
- Multi-replica scheduler coordination (single-instance assumption documented).
- Phase 9 audit log (`translation_events`, `download_events`) — separate phase.

## Architecture

### Module layout

```
backend/
  services/
    scheduler.py           ~260 LOC
      JobSpec                        dataclass
      SCHEDULED_JOBS: list[JobSpec]  canonical registry, code defaults
      _scheduler: BackgroundScheduler module singleton
      class SublarrScheduler         facade
        .start(app)                  idempotent
        .shutdown(timeout_s=25)      bounded
        .register_job(spec)          no-op if row exists
        .reset_to_default(job_id)
        .purge_orphans()
        .run_now(job_id)             DateTrigger(now)
      _on_job_executed / _on_job_error / _on_job_missed
      _tick_wrapper(spec, fn)        app_context + timeout + capture + metrics
  routes/system/
    scheduler.py           ~160 LOC  Flask blueprint, 7 endpoints, admin-gated
  db/models/
    scheduler.py           ~40 LOC   JobRun ORM model
  db/migrations/versions/
    YYYYMMDD_scheduler_infrastructure.py
  utils/
    debouncer.py           ~60 LOC   DebouncedCallback

  # slimmed (tick function kept, Timer wiring removed)
  anidb_sync.py
  cleanup_scheduler.py                → deleted; logic moves to services/cleanup.py
  upgrade_scheduler.py                → deleted; logic moves to services/upgrade.py
  services/wanted_scanner_scheduler.py → _WantedSchedulerMixin removed
  providers/plugins/watcher.py         → uses DebouncedCallback
  standalone/watcher.py                → uses DebouncedCallback

frontend/src/
  pages/Settings/SchedulerPage.tsx
  pages/Settings/scheduler/
    JobCard.tsx
    TriggerEditModal.tsx
    JobHistoryDrawer.tsx
    IntervalEditor.tsx
    CronEditor.tsx
  api/scheduler.ts
  hooks/useSchedulerJobs.ts
  hooks/useSchedulerJobRuns.ts
```

### Startup procedure

`create_app()`, after DB init and before `socketio.run()`:

1. `scheduler = SublarrScheduler(db_url=app.config["SQLALCHEMY_DATABASE_URI"])`
2. `scheduler.attach_app(app)` — enables app_context wrap in tick wrapper.
3. `scheduler.attach_listeners()` — `EVENT_JOB_EXECUTED/ERROR/MISSED`.
4. For each `JobSpec` in `SCHEDULED_JOBS`: `scheduler.register_job(spec)`
   — adds to JobStore if no row with that id; if a row exists, leaves
   the user's trigger/paused state alone.
5. `scheduler.purge_orphans()` — deletes JobStore rows whose id is no
   longer in `SCHEDULED_JOBS`.
6. Stale-run reconciliation: `UPDATE scheduler_job_runs SET status='error',
   error_type='InterruptedByShutdown' WHERE finished_at IS NULL AND started_at
   < NOW() - INTERVAL '10 minutes'`.
7. `scheduler.start()` — idempotent.
8. `app.extensions["scheduler"] = scheduler` — routes retrieve via `current_app`.

The single-instance guard runs before step 1: if
`SUBLARR_SCHEDULER_ROLE` is anything other than `"primary"` (default),
steps 1–8 are skipped and a log line records that this replica will
not schedule.

### Shutdown procedure

Added to `app_shutdown.py`:

```python
scheduler = current_app.extensions.get("scheduler")
if scheduler:
    scheduler.shutdown(timeout_s=25)
```

Ordered: HTTP server stop → scheduler shutdown → DB pool close.
Docker `stop_grace_period=30` leaves 5s buffer. Bounded so runaway
ticks don't trigger SIGKILL-driven data loss.

### Source-of-truth rule

- `SCHEDULED_JOBS` in code is the *schema* of the scheduler (which ids
  exist, what function each one calls).
- The JobStore row is the *state* of each job (current trigger, paused
  flag, next fire time).
- On registration, code defaults fill in only when a JobStore row is
  missing. User edits via the UI persist and survive re-deploys.
- `reset_to_default(job_id)` is the explicit path back to the code
  default: remove the row, re-register from `SCHEDULED_JOBS`.

### Tick wrapper contract

Every job is invoked through `_tick_wrapper(spec, fn)` which:

- Enters `app.app_context()` (fixes the leaked-context class of bug,
  memory `feedback_flask_app_context_in_threads`).
- Runs `fn()` via `ThreadPoolExecutor.submit(fn).result(timeout=spec.timeout_s)`
  (cross-platform — avoids `signal.SIGALRM` which doesn't exist on
  Windows).
- Catches all exceptions, logs with `exc_info=True`, writes a
  `scheduler_job_runs` row with `status='error'`, and emits the
  corresponding Prometheus counter.
- Uses a fresh `db.create_scoped_session()` for the history write so
  a corrupted tick session cannot lose the error record.

### Concurrency defaults

Per `JobSpec`, defaulting to:
- `max_instances=1`
- `coalesce=True`
- `misfire_grace_time`: computed at registration from the trigger —
  `IntervalTrigger` → half of the interval in seconds;
  `CronTrigger` → `60` seconds. If `JobSpec.misfire_grace_time`
  is explicit, that value wins.

Overridable per-spec where semantics differ.

## Data model

### `scheduler_job_runs`

Columns:

| Column | Type | Notes |
|---|---|---|
| `id` | `Integer` PK autoincrement | |
| `job_id` | `String(64)` NOT NULL | indexed |
| `started_at` | `DateTime(timezone=True)` NOT NULL | indexed |
| `finished_at` | `DateTime(timezone=True)` | NULL while running |
| `duration_ms` | `Integer` | |
| `status` | `String(16)` NOT NULL | `ok` / `error` / `timeout` / `missed` / `skipped_overlap` |
| `triggered_by` | `String(16)` NOT NULL default `'schedule'` | `schedule` / `manual` / `startup` |
| `error_type` | `String(128)` | exception class name |
| `error_msg` | `Text` | truncated to 4KB before write |

Indexes:
- `(job_id, started_at)` — supports "last N runs of job X" queries.
- `started_at` — supports retention `DELETE WHERE started_at < cutoff`.
- `status` — supports Prometheus error-rate query.

### `apscheduler_jobs`

Explicit Alembic migration mirrors `SQLAlchemyJobStore`'s internal
schema so we own it:

| Column | Type |
|---|---|
| `id` | `Unicode(191)` PK |
| `next_run_time` | `Float(precision=25)` indexed |
| `job_state` | `LargeBinary` NOT NULL |

### Retention

- New config field: `scheduler_history_retention_days: int = Field(default=30, ge=1, le=365)`.
- JobSpec `scheduler_history_cleanup` runs daily at 03:15 UTC, deletes
  rows older than the current retention setting, logs the count.
- Upper bound at 30 days × ~8 jobs × pathological 1/min ≈ 345k rows
  — negligible.

## API contract

Blueprint `routes/system/scheduler.py`, prefix `/api/v1/scheduler`,
all endpoints admin-gated via existing `@require_api_key` + admin
check used by `routes/system/*`.

### Trigger payload schema (Pydantic `TriggerModel`)

```json
// Interval
{"type": "interval", "seconds": 900}
{"type": "interval", "minutes": 15}
{"type": "interval", "hours": 1}

// Cron
{"type": "cron", "hour": 3, "minute": 0}
{"type": "cron", "day_of_week": "sun", "hour": 5, "minute": 0}
{"type": "cron", "expression": "0 3 * * *"}
```

Validation rules:
- `type` required.
- Interval: exactly one of `seconds`/`minutes`/`hours` ≥ 1.
- Cron: `expression` shorthand is server-side-expanded to named fields
  before storage. `CronTrigger(**payload).get_next_fire_time(None, now())`
  must return non-None; otherwise `InvalidCronError` 400.
- Timezone: all cron triggers stored as UTC. UI converts for display.

### Endpoints

| Method | Path | Purpose | Status codes |
|---|---|---|---|
| `GET`  | `/jobs` | List jobs with live state | 200, 401, 503 |
| `GET`  | `/jobs/<id>` | Single job detail | 200, 401, 404 |
| `POST` | `/jobs/<id>/run-now` | Queue one-shot | 202, 401, 404, 409 |
| `POST` | `/jobs/<id>/pause` | Pause recurring | 200, 401, 404, 409 |
| `POST` | `/jobs/<id>/resume` | Resume recurring | 200, 401, 404, 409 |
| `PATCH`| `/jobs/<id>` | Modify trigger | 200, 400, 401, 404 |
| `POST` | `/jobs/<id>/reset-default` | Revert to code default | 200, 401, 404 |
| `GET`  | `/jobs/<id>/runs` | Paginated history | 200, 401, 404 |

### Job object shape (list + detail + post-mutation)

```json
{
  "id": "wanted_scanner",
  "description": "Scan Sonarr/Radarr/standalone for wanted subtitles",
  "owner_module": "services.wanted_scanner_core",
  "trigger": {"type": "interval", "minutes": 15},
  "trigger_is_default": false,
  "paused": false,
  "next_run_time": "2026-04-18T14:45:00Z",
  "last_run": {
    "started_at": "2026-04-18T14:30:00Z",
    "finished_at": "2026-04-18T14:30:12Z",
    "duration_ms": 12041,
    "status": "ok",
    "error_type": null,
    "error_msg": null
  },
  "stats_7d": {"ok": 672, "error": 3, "timeout": 0, "missed": 1}
}
```

`stats_7d` uses one grouped query per list call, cached 10s server-side.

### Run-now semantics

- Creates a one-shot job `<job_id>_oneshot_<ts>` with `DateTrigger(now)`.
- Own `max_instances=1` — spam returns 409 if another oneshot with the
  same prefix is pending/running.
- Main recurring job is untouched. Concurrent "schedule" + "manual"
  runs are possible; document this as intended.

### Admin audit logging

Every mutation endpoint logs at INFO:
`scheduler_admin_action job_id=X action=Y actor=<api_key_fingerprint>`.

Covers the admin audit trail this phase without needing Phase 9's
audit log.

## Frontend UI

### Navigation

Added to System settings group under `Settings → System → Scheduler`,
route `/settings/system/scheduler`, icon `Calendar`.

### Page layout

Card list, one card per registered job, showing: id, description,
trigger label, last run summary (relative time + status + duration),
next run label, 7-day stats, action row. Card variants for paused
(muted background), error-on-last-run (warning border), edited
trigger (small "Edited" pill).

### Trigger edit modal

Two tabs: **Interval** and **Cron**. Current trigger pre-selects the
matching tab; switching is scratch state (doesn't persist until Save).

- **Interval:** number input + unit dropdown (s/m/h), client-validates ≥ 1.
- **Cron:**
  - Mode picker: "Daily at…" / "Weekly on…" / "Advanced (expression)".
  - Daily: hour + minute inputs.
  - Weekly: day-of-week chips + hour + minute.
  - Advanced: free-text expression + client-side `cron-parser` "next
    3 fires" preview.

Save → `PATCH /api/v1/scheduler/jobs/<id>`. 400 errors surface inline.

### History drawer

Opens from `[History]` button, right-side drawer. Table columns:
`Time | Status badge | Duration | Triggered by | Error type`. Row
click expands to show `error_msg`. Pagination: 50 rows, infinite
scroll. Status filter chips at top.

### Polling

- Job list: React Query `refetchInterval=10000` (matches server cache).
- History drawer: 5s while open, cleared on close.
- Optimistic UI on `Run now` — pending row with spinner, reconciles
  on next poll.

### Empty / error states

- Scheduler down (GET /jobs → 503): red banner "Scheduler is not
  running. Check server logs." + disabled action buttons.
- No runs yet for a fresh job: "No runs yet. Next run in X min."

### Accessibility & styling

- All strings under `i18n/locales/{de,en}/settings.json`
  `scheduler.*` key (DE primary, EN mirror per CLAUDE.md).
- Status badges `aria-label="Status: OK"` etc.
- Focus trap in modal (reuse existing pattern from
  `ProviderEditModal`).
- Pure Tailwind per the A1 policy; dynamic inline style only for the
  optimistic progress indicator.

## Error handling — failure matrix

### Per-tick failures (handled in `_tick_wrapper`)

| Failure | Detection | History status |
|---|---|---|
| `fn()` raises | try/except | `error` |
| Timeout | future result(timeout=) | `timeout` |
| `EVENT_JOB_MISSED` | listener | `missed` |
| `MaxInstancesReachedError` | listener | `skipped_overlap` |
| DB session corrupt | fresh scoped session for history write | `error` |

### Startup failures

| Failure | Handling |
|---|---|
| JobStore.start() fails | Catch, log, set `extensions["scheduler"]=None`, routes 503 |
| Migration chain broken | Existing `MigrationsPendingError` escalation in `app_schedulers.py` |
| JobSpec id collision | `ConfigurationError` at process start (fail fast) |
| Orphan JobStore rows | `purge_orphans()` before `start()` |
| Circular imports | Lazy function references via `"module.path:fn"` string resolved inside tick wrapper |

### Cron edge cases

| Case | Handling |
|---|---|
| DST transitions | Storage always UTC; UI converts |
| Unreachable cron | Validator rejects at save time |
| NTP clock jump | `misfire_grace_time` absorbs |

### Run-now edge cases

| Case | Handling |
|---|---|
| Spam | 409 if pending oneshot exists |
| While recurring running | Both run independently; documented |
| Stale oneshots after crash | `purge_orphans` extended to sweep `*_oneshot_*` with past `next_run_time` |

### Shutdown edge cases

| Case | Handling |
|---|---|
| Tick runs >25s at SIGTERM | Row left with NULL `finished_at`; reconciler marks `InterruptedByShutdown` on next startup |
| SIGKILL | Same reconciler path |
| Double SIGTERM | `shutdown()` idempotent via `_shutting_down` flag |

### Runtime concerns

- PATCH during execution: APScheduler `reschedule_job` is thread-safe;
  current invocation finishes on old trigger, next fire uses new.
- Settings change (`scheduler_history_retention_days`): picked up on
  next cleanup fire (reads `get_settings()` at tick time); no restart.
- Settings save no longer restarts the scheduler (idempotent
  `start()`); removes one entire bug class documented in
  `feedback_scheduler_timer_leak`.

## Testing

Coverage goals: ≥ 80% line coverage on new modules; 100% of error
rows in the failure matrix have at least one dedicated test.

### Test harness additions

- `test_scheduler` fixture: SublarrScheduler bound to in-memory
  jobstore, autostart=False.
- `frozen_time` fixture: `freezegun(tick=False)` for cron assertions.
- Smoke test: real `SQLAlchemyJobStore` against throwaway SQLite URL
  so prod config instantiates without mocks.

### Unit test files

```
test_scheduler_facade.py                  ~40 tests
test_scheduler_tick_wrapper.py            ~25 tests
test_scheduler_listeners.py               ~12 tests
test_scheduler_routes.py                  ~35 tests
test_scheduler_cron_edge_cases.py         ~10 tests
test_scheduler_startup_reconciliation.py   ~8 tests
test_scheduler_migration.py                ~6 tests
test_scheduler_retention.py                ~6 tests
test_debouncer.py                         ~12 tests
test_scheduler_second_instance_guard.py    ~4 tests
```

Integration (guarded by `APS_TEST_REAL=1`, nightly CI):
`integration/test_scheduler_end_to_end.py` — 8 scenarios including
pause mid-loop, PATCH while running, run-now concurrency, shutdown
interruption reconciliation, full lifecycle.

### Regression tests tied to memory-documented pitfalls

| Memory | Regression test |
|---|---|
| `feedback_scheduler_timer_leak` | `test_debouncer::test_cancel_before_reassign`; `test_scheduler_facade::test_start_idempotent_on_settings_save` |
| `feedback_flask_app_context_in_threads` | `test_scheduler_tick_wrapper::test_app_context_entered_before_fn` |
| `feedback_alembic_pitfalls` | `test_scheduler_migration::test_upgrade_uses_if_not_exists_safe_ops` |
| `project_stability_session_2026_04_13` | `test_scheduler_retention::test_uses_session_begin` |

### Migration regression tests for retiring Timer sites

- `test_wanted_scanner_tick.py`
- `test_cleanup_tick.py`
- `test_upgrade_scan_tick.py`
- `test_anidb_sync_tick.py`

Same assertions as the old `test_*_scheduler.py` tests, invoked at
function level. Old Timer-level tests deleted once coverage confirmed.

### Frontend tests

```
pages/Settings/__tests__/SchedulerPage.test.tsx                  ~15 tests
pages/Settings/scheduler/__tests__/TriggerEditModal.test.tsx     ~12 tests
pages/Settings/scheduler/__tests__/JobHistoryDrawer.test.tsx     ~10 tests
```

### E2E (Playwright)

One `frontend/e2e/scheduler.spec.ts`: navigate to page, verify 8
jobs, run-now + observe history row, edit trigger + observe
"Edited" pill, reset-default + observe pill disappears.

### Runtime budget

- Unit suite: ~175 new tests, < 20s
- Integration suite: < 60s (APS `tick=True` time advancement)
- Frontend unit: ~37 new tests, < 15s
- E2E: ~30-45s for the single spec

## Canonical job registry (initial content)

```python
SCHEDULED_JOBS = [
    JobSpec(id='wanted_scanner',            func=wanted_scanner_tick,
            default_trigger=IntervalTrigger(minutes=15),
            timeout_s=600,  owner_module='services.wanted_scanner_core'),
    JobSpec(id='wanted_search',             func=wanted_search_tick,
            default_trigger=IntervalTrigger(minutes=5),
            timeout_s=900,  owner_module='services.wanted_scanner_core'),
    JobSpec(id='cleanup',                   func=cleanup_tick,
            default_trigger=CronTrigger(hour=3, minute=0),
            timeout_s=1800, owner_module='services.cleanup'),
    JobSpec(id='upgrade_scan',              func=upgrade_scan_tick,
            default_trigger=CronTrigger(hour=4, minute=0),
            timeout_s=3600, owner_module='services.upgrade'),
    JobSpec(id='anidb_sync',                func=anidb_sync_tick,
            default_trigger=CronTrigger(day_of_week='sun', hour=5, minute=0),
            timeout_s=1800, owner_module='anidb_sync'),
    JobSpec(id='scheduler_history_cleanup', func=delete_old_job_runs,
            default_trigger=CronTrigger(hour=3, minute=15),
            timeout_s=60,   owner_module='services.scheduler'),
    JobSpec(id='provider_budget_tick',      func=budget_recovery_tick,
            default_trigger=IntervalTrigger(minutes=1),
            timeout_s=30,   owner_module='services.provider_budget'),
    JobSpec(id='metrics_flush',             func=metrics_flush_tick,
            default_trigger=IntervalTrigger(seconds=30),
            timeout_s=10,   owner_module='monitoring.metrics'),
]
```

## Dependencies & prerequisites

- `apscheduler >= 3.10` added to `backend/requirements.txt`.
- `cron-parser` npm package added to `frontend/package.json`.
- No new Docker base-image packages.

## Risks & mitigations

| Risk | Mitigation |
|---|---|
| First deploy triggers stampede of "missed fires" | Explicit purge + startup reconciliation; `coalesce=True` on every JobSpec |
| Two scheduler instances run concurrently (new replica spun up) | `SUBLARR_SCHEDULER_ROLE` guard, default primary, documented |
| APScheduler library version upgrade breaks `apscheduler_jobs` shape | Explicit Alembic migration of that table — we control evolution |
| Test-patch breakage in the 4 retiring sites | Per-site regression test file deleted only after new test file matches coverage |
| Long-running tick vs Docker stop-grace-period | Bounded `shutdown(timeout_s=25)`; Docker grace 30s gives 5s buffer |
| Users misconfigure an unreachable cron | Validator rejects at save time; preview widget shows next 3 fires |

## Rollout plan (high-level)

Implementation plan is out of scope for this design doc; it will be
produced by the writing-plans skill in the next step. At a
high level, the natural phasing is:

1. **Infrastructure** — `services/scheduler.py` facade, `JobRun`
   model, migration, tick wrapper, listeners, Prometheus wiring.
   All tests green; no existing behaviour touched.
2. **API + UI (read-only)** — GET endpoints, SchedulerPage with
   disabled action buttons; deploy this and verify prod looks sane
   before enabling writes.
3. **Write endpoints + UI actions** — `run-now`, pause/resume,
   PATCH, reset-default.
4. **Migrations** — one commit per retiring Timer site, each
   removing the site's Timer plumbing and registering its JobSpec.
   Ship after each.
5. **Debouncer extraction** — `utils/debouncer.py` + migrate the two
   watcher sites.
6. **Cleanup** — delete legacy `*_scheduler.py` files, delete
   old Timer-level tests once regression file is green, update
   CLAUDE.md with single-instance guard docs.

## Acceptance criteria

- [ ] All 6 `threading.Timer` production sites are gone (4 migrated
      to APScheduler, 2 migrated to `DebouncedCallback`).
- [ ] `scheduler_job_runs` has rows for every scheduled execution
      since boot, with correct status / duration / triggered_by /
      error fields.
- [ ] `GET /api/v1/scheduler/jobs` returns the 8 JobSpec entries
      with live state.
- [ ] Admin can run-now, pause/resume, edit trigger, reset-default,
      view history from Settings → System → Scheduler.
- [ ] `SUBLARR_SCHEDULER_ROLE` env var gates scheduler startup
      correctly (primary starts, anything else skips).
- [ ] `scheduler.shutdown()` returns within `timeout_s` ≤ 25 seconds.
- [ ] Stale-run reconciler marks abandoned rows
      `InterruptedByShutdown` on startup.
- [ ] Prometheus endpoint exposes new scheduler metrics.
- [ ] Retention cron runs nightly and deletes rows older than
      `scheduler_history_retention_days`.
- [ ] Unit coverage ≥ 80% on new modules; all regression tests for
      documented pitfalls pass.
- [ ] E2E spec for the scheduler page passes in CI.

## Open questions

None at design time. Implementation questions deferred to the plan.
