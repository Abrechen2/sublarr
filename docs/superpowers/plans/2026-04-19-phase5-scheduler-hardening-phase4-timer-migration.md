# Phase 5 / Rollout Phase 4 — Timer Site Migration

**Spec:** `docs/superpowers/specs/2026-04-18-phase5-scheduler-hardening-design.md`
**Prior phase:** `docs/superpowers/plans/2026-04-19-phase5-scheduler-hardening-phase3-write-endpoints.md` (deployed as 0.57.0-beta)

**Goal:** Migrate the 4 legacy `threading.Timer` schedulers into `SCHEDULED_JOBS` so the Scheduler UI shows all 5 real recurring jobs instead of just the meta `scheduler_history_cleanup`. The legacy `start_xxx_scheduler()` entry points become thin adapters that re-apply the config-interval override on `SublarrScheduler` via `modify_trigger`.

**Architecture:** Each site keeps its tick function (the code that does work) but loses the `threading.Timer` wiring. New JobSpecs are added to `SCHEDULED_JOBS`. The legacy module-level entry points called by settings-save paths forward to `SublarrScheduler.modify_trigger(job_id, IntervalTrigger(...))`. No behaviour change — jobs still respect config settings — but the scheduling mechanics move to APScheduler.

---

## Migration sites

| Site | Current tick | New JobSpec id | Default trigger |
|---|---|---|---|
| `cleanup_scheduler.py` → `services/cleanup.py` | `CleanupScheduler._run_scheduled` | `cleanup` | `IntervalTrigger(hours=168)` (weekly, configurable) |
| `upgrade_scheduler.py` → `services/upgrade.py` | `UpgradeScheduler._run_scheduled` | `upgrade_scan` | `IntervalTrigger(hours=168)` (weekly, configurable) |
| `anidb_sync.py` | `run_sync(app)` | `anidb_sync` | `IntervalTrigger(hours=168)` (weekly) |
| `services/wanted_scanner_scheduler.py` (mixin) | `_scheduled_scan` + `_scheduled_search` | `wanted_scanner`, `wanted_search` | `IntervalTrigger(hours=6)` / `IntervalTrigger(hours=24)` |

5 total new JobSpecs (one site contributes two).

---

## Task 1: Cleanup + Upgrade migrations (simplest pattern)

Both files follow the same singleton+class pattern. Tick becomes a module-level `cleanup_tick()` / `upgrade_tick()` function that resolves `app.extensions['scheduler']._app` implicitly via current_app. Since tick wrapper enters app_context, the tick function can use `current_app` or grab settings directly.

**Pattern:**

1. Extract the worker logic from `_run_scheduled` into a module-level `cleanup_tick()` / `upgrade_tick()`.
2. Add JobSpec to `SCHEDULED_JOBS` in `services/scheduler.py::_build_default_jobs()`.
3. Keep `start_cleanup_scheduler(app, socketio)` as a no-op adapter that reads current config value and calls `scheduler.modify_trigger(id, IntervalTrigger(hours=value))` if scheduler is running.
4. Remove the `threading.Timer` loop; class remains as a container for `last_run_at` / `next_run_at` getters (UI endpoints still query these — check before deleting).
5. Commit each migration separately.

**Step-by-step (cleanup):**

- [ ] Read `backend/cleanup_scheduler.py` to understand the current `CleanupScheduler._run_scheduled` body — that's the tick logic.
- [ ] Add at the top of the file (or in a new `services/cleanup.py` module):
  ```python
  def cleanup_tick() -> None:
      """Run cleanup work once (callable by the APScheduler JobSpec)."""
      # Paste the body of CleanupScheduler._run_scheduled here but drop
      # the `self._schedule_next(new_interval)` line at the end —
      # rescheduling is now APScheduler's job.
  ```
- [ ] Import `IntervalTrigger` in `services/scheduler.py` (already there from Phase 3).
- [ ] Append to `_build_default_jobs()`:
  ```python
  from cleanup_scheduler import cleanup_tick
  from db.config import get_config_entry  # or wherever config lookup lives

  interval_hours = int(get_config_entry("cleanup_schedule_interval_hours") or 168)
  specs.append(JobSpec(
      id="cleanup",
      func=cleanup_tick,
      default_trigger=IntervalTrigger(hours=max(1, interval_hours)),
      timeout_s=3600,
      owner_module="services.cleanup",
      description="Periodic database + filesystem cleanup",
  ))
  ```
- [ ] Update `start_cleanup_scheduler(app, socketio)` to become:
  ```python
  def start_cleanup_scheduler(app, socketio):
      """Adapter: re-apply interval from config on the APScheduler job."""
      scheduler = app.extensions.get("scheduler")
      if scheduler is None:
          logger.warning("cleanup: SublarrScheduler not available")
          return
      try:
          repo = ... # however config is read
          interval = int(repo.get_config_entry("cleanup_schedule_interval_hours") or 168)
          scheduler.modify_trigger("cleanup", IntervalTrigger(hours=max(1, interval)))
          logger.info("cleanup interval updated to %dh", interval)
      except JobNotRegisteredError:
          logger.warning("cleanup JobSpec not registered; skipping")
  ```
- [ ] `stop_cleanup_scheduler()` becomes a no-op (the APScheduler manages shutdown).
- [ ] Delete the `CleanupScheduler` class body related to timers — but KEEP any getter methods that routes still read (grep `cleanup_scheduler.get_cleanup_scheduler()` to find callers).
- [ ] Run existing cleanup tests — they may need rewriting. If they hit the Timer directly they break; if they call the work fn they're fine.
- [ ] Commit: `refactor(phase5-p4): migrate cleanup_scheduler to SchedulerJobSpec`

Same pattern for `upgrade_scheduler.py`.

---

## Task 2: anidb_sync migration

`anidb_sync.py` already has a top-level `run_sync(app)` function that does the work. The JobSpec can wrap it:

```python
def anidb_sync_tick() -> None:
    from flask import current_app
    from anidb_sync import run_sync
    run_sync(current_app._get_current_object())
```

Add JobSpec with `IntervalTrigger(hours=168)` (weekly).

Remove the `AnidbSyncScheduler` class + `start_anidb_sync_scheduler` + `stop_anidb_sync_scheduler` — or keep them as adapter no-ops if anything imports them (grep first).

---

## Task 3: Wanted scanner migration

`services/wanted_scanner_scheduler.py` defines `_WantedSchedulerMixin` with `_scheduled_scan` + `_scheduled_search`. Both are methods on the scanner instance.

Extract two module-level tick functions that resolve the scanner instance:

```python
def wanted_scanner_tick() -> None:
    from services.wanted_scanner_core import get_wanted_scanner
    scanner = get_wanted_scanner()
    scanner._run_scan_with_context()  # or whatever the actual work fn is

def wanted_search_tick() -> None:
    from services.wanted_scanner_core import get_wanted_scanner
    scanner = get_wanted_scanner()
    scanner._run_search_with_context()
```

Two JobSpecs — `wanted_scanner` (IntervalTrigger hours=6) + `wanted_search` (hours=24).

`_WantedSchedulerMixin.start_scheduler()` becomes an adapter that calls `modify_trigger` for both ids.

---

## Task 4: Test regressions + final acceptance

- [ ] Run full scheduler test suite — expect no regressions.
- [ ] Read each legacy scheduler's existing test file (`test_cleanup_scheduler.py`, etc.) and ensure it still passes or update to exercise the new tick functions directly.
- [ ] Verify `bootstrap_scheduler` registers all 5 new JobSpecs at startup (check prod logs).
- [ ] Merge to master.

---

## Task 5: Deploy

- [ ] Bump to 0.58.0-beta.
- [ ] Changelog describes: "All 5 recurring jobs now visible in Settings → System → Scheduler".
- [ ] Build + push + deploy to Cardinal.
- [ ] Verify 5 jobs show up at `/api/v1/scheduler/jobs`.
- [ ] Verify their next_run_time is populated.
- [ ] No regressions in the actual recurring work (wanted scanner still scans, etc.).

---

## Risks

- **Config-driven intervals:** settings UI still edits `cleanup_schedule_interval_hours` etc. The adapter path in `start_xxx_scheduler` must be called on settings save or the value gets stuck. Verify the settings routes call it.
- **Test harness:** existing tests for each scheduler may depend on the singleton pattern — update to call tick functions directly.
- **Tick function `self`:** For the wanted-scanner mixin, the tick needs the scanner instance. Use a lazy `get_wanted_scanner()` factory.
- **Legacy Timer cleanup:** ensure the old Timer-loop code is actually deleted — otherwise we have two schedulers racing.
