# Provisional Machine-Translation — Phase 2: re-seek + replace the original (#8b)

> **For agentic workers:** implement task-by-task with TDD (superpowers:subagent-driven-development /
> executing-plans). Each task: write failing test → run (RED) → implement → run (GREEN) → lint → commit.
> Builds on Phase 1 (`docs/plans/2026-07-03-v1.6-provisional-mt.md`).

**Goal:** When a Sublarr-produced MT is kept `provisional` (per profile
`mt_keep_seeking_original=1`), Sublarr must actively **seek a genuine human/provider
original** and, on finding one good enough, **replace the MT** — instead of the item
sitting inert forever (the current shipped gap; the UI help already promises this).

**Current reality (verified 2026-07-05):**
- Config columns already exist on `LanguageProfile` (`backend/db/models/core.py:185-187`):
  `mt_keep_seeking_original:int=0`, `mt_on_original_found:str="notify"`, `mt_min_original_score:int=1`.
  **No migration needed.** `mt_on_original_found` / `mt_min_original_score` currently have ZERO consumers.
- Provisional items sit at `status="provisional"`. `upgrade_scheduler._execute_scan`
  (`backend/upgrade_scheduler.py:139-260`) scans recent `subtitle_downloads` for UPGRADES and
  deliberately **skips** MT rows (`:176-178`) and any item whose status is
  `wanted`/`searching`/`provisional` (`:201-205`). So it will NOT drive the re-seek — Phase 2 needs
  its own path.
- The search pipeline honours an `auto_translate` toggle: `wanted_search/process.py:922`
  `ctx["auto_translate"] = getattr(settings,"wanted_auto_translate",True)`; when False, steps
  3-5 (translate) are skipped and only genuine provider/embedded originals are considered
  (`:728-733`, `:934`, `:952`). This is exactly the "original-only" mode we need.
- MT rows are `source="machine_translation"`, `score=0`. `penalty_rules.py:534` already penalizes
  MT-flagged candidates — any real original outscores an MT.
- `finalize_translation` (`services/mt_provisional.py:57-93`) is what set the item provisional.

**Design:** a dedicated **`mt_reseek` scheduled job** (NOT upgrade_scan) that:
1. Selects `status="provisional"` wanted items whose profile still has `mt_keep_seeking_original=1`
   and that are NOT pinned (user-edited/confirmed MT — see pinning below), respecting a per-item
   search backoff (reuse `last_search_at` + the wanted-search cadence).
2. Runs the existing search pipeline for each in **original-only** mode (`ctx["auto_translate"]=False`).
3. If a genuine provider/embedded original is found scoring **≥ `mt_min_original_score`** (MT is 0, so
   any real sub qualifies unless the profile raises the bar): apply `mt_on_original_found`:
   - `"auto_replace"` → download/install the original, **trash the MT sidecar** (via the existing
     trash path, not hard-delete), clear the provisional item (resolve it), record the swap.
   - `"notify"` → do NOT replace; create a **pending-original notification/record** and leave the
     item provisional until the user approves (Task 3/4).
4. If nothing qualifies, update `last_search_at` and leave it provisional.

**Tech Stack:** Python 3.12 runtime (CI must match — see `feedback_ci_python312_runtime`), Flask,
SQLAlchemy, APScheduler, pytest. React 19 frontend for Task 4.

## Global Constraints
- Ruff `line-length=100`, target py311. Run `ruff check . && ruff format --check .` on whole `backend/`.
- No new env vars (config on `LanguageProfile`/DB). Scheduler job via `SCHEDULED_JOBS` registry +
  a module-level picklable tick (SQLAlchemyJobStore constraint — see `feedback_apscheduler_pickle_closure`).
- Tests `-n auto --ignore=tests/performance`. Any DB-touching thread needs `app.app_context()`.
- Postgres-vs-SQLite: no raw-SQL date/`GROUP_CONCAT`/`AVG→Decimal` gotchas (`feedback_postgres_sqlite_compat_gotchas`);
  media files 0644+ (mkstemp 0600 → chmod). RC (:5766, Postgres) catches what CI (SQLite) misses.
- Conventional Commits. Release ends at **1.6.2** (RC-first validate on :5766 before prod promote).

---

### Task 1 — `mt_reseek` scheduler job: original-only re-search of provisional items
**Files:** create `backend/services/mt_reseek.py` (module-level `mt_reseek_tick()` + core `reseek_provisional_items(app)`);
register JobSpec in `backend/services/scheduler/__init__.py` (`_build_default_jobs`, id=`mt_reseek`,
IntervalTrigger, sensible timeout); test `backend/tests/test_mt_reseek.py`.
**Interfaces / behaviour:**
- Select provisional wanted items (read the wanted repo — `db/repositories/wanted*` — for a
  `status="provisional"` query; add one if absent). Skip items whose profile no longer has
  `mt_keep_seeking_original` or that are pinned.
- For each, invoke the search entry (`wanted_search/process.py`) with a ctx that forces
  `auto_translate=False`. READ `process.py` first for the real entry-point signature + how ctx is
  built (line ~922) so you flip only the translate toggle, nothing else.
- On no-qualifying-original: set `last_search_at` and continue (respect backoff so the job is cheap).
- TDD: test that a provisional item IS picked, that the search is called with auto_translate False,
  and that a `wanted` item is NOT picked by this job. Stub the search call.

### Task 2 — replace-on-found + trash MT + honour `mt_on_original_found`
**Files:** extend `mt_reseek.py` (the on-found branch); reuse the download/install path the normal
wanted-search success uses + the existing **trash** helper for the MT sidecar; test extend
`test_mt_reseek.py`.
**Behaviour:**
- When the original-only search yields a genuine original with score ≥ `mt_min_original_score`:
  - `mt_on_original_found=="auto_replace"`: install the original (same path as a normal successful
    download), trash the superseded MT sidecar (soft, recoverable), resolve the provisional item
    (delete/clear provisional), record the swap for stats/history.
  - `mt_on_original_found=="notify"`: create a pending record (Task 3), do NOT touch files, keep provisional.
- **Pinning:** an MT the user has edited/confirmed must never be auto-replaced — define the pin
  signal (e.g. a flag/marker on the subtitle row or a `pinned` wanted attribute) and honour it here
  AND in Task 1 selection. READ how "confirmed/edited" is currently represented before choosing.
- TDD: auto_replace path replaces + trashes + resolves; notify path creates pending + leaves files;
  min-score gate respected; pinned item never replaced.

### Task 3 — pending-original notifications + approve/reject API (for `notify` mode)
**Files:** a pending-original store (reuse notifications infra if present, else a small table/model +
migration); routes under `/api/v1/` to list pending + approve (→ do the Task-2 replace) + reject
(→ keep MT, stop seeking or snooze); tests.
- Approve reuses the Task-2 auto_replace action. Reject sets a terminal state so the item isn't
  re-notified. READ the existing notifications/webhooks infra (`settings/hooks-webhooks`,
  `services` notifications) before adding anything new.

### Task 4 — frontend: provisional badge + pending-original approve UX
**Files:** `frontend/src/…` — a badge marking provisional items (Library/Wanted), and a small
review surface listing pending originals with Approve/Reject wired to Task-3 API. Follow the
Pure-Tailwind policy + `feedback_axios_for_api_calls` (shared `api` client). Vitest + tsc + lint green.
- Keep scope tight: a badge + a list with two buttons. No waveform-level surface.

### Final Verification & Release
- `cd backend && ruff check . && ruff format --check .`; full `pytest -n auto --ignore=tests/performance`.
- `cd frontend && npm run lint && npx tsc --noEmit && npm run test -- --run`.
- Build `1.6.2-rc.x` → deploy RC (:5766, Postgres) → **functionally validate**: seed a provisional MT,
  drop a real original in reach, run `mt_reseek` run-now → auto_replace swaps + trashes MT; notify
  mode raises a pending + approve swaps. Then promote 1.6.2 to prod.
- **Then** un-hold `…/scratchpad/provisional-translation.mdx.hold`, REWRITE it to describe the real
  end-to-end lifecycle (provisional → re-seek → replace/notify-approve), add its diagram + sidebar
  entry (Translation group), build + deploy docs. Also soften/align the in-app help text if still
  needed. Update `penalty_rules` note is already satisfied (MT penalized).
