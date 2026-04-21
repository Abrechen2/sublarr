# 0.71.0-beta — Subtitle Manager Automation (Codex-drafted plan)

**Status:** Draft — awaiting user approval
**Source:** Codex (`gpt-5.3-codex`, reasoning=`high`) analysis of `D:\Sublarr_Projekt\Sublarr`
**Date:** 2026-04-21
**Estimated total LOC:** 850–1,300

## User intent (from Agatha All Along screenshot session)

The user observed that a freshly-added series with 9 episodes shows red DE/EN
pills even though German subtitle tracks are embedded in the MKV, and the
"Extraktion läuft" banner suggests automation hasn't caught up. Five
concrete requirements emerged:

1. **Library display = real state.** Embedded German track must count as
   "present" immediately, not only once a sidecar `.ger.srt` has been written.
2. **Auto-extract continuous.** Batch-probe should run automatically on every
   library add and keep draining the backlog until nothing is pending — no
   manual "Extract" button.
3. **SDH tolerance.** Today English is hidden behind an "English (SDH)" track
   only, and batch-probe skips it. SDH must become a valid source by default
   (with a slight preference for non-SDH when both are available).
4. **Foreign-track cleanup.** After DE + EN have been extracted to sidecars,
   all other embedded subtitle tracks in the MKV should be stripped via
   mkvmerge (opt-in, with existing backup-to-trash safety).
5. **Unified Subtitle Manager automation page.** One master toggle plus
   granular sub-toggles in a single Settings page; when on, the product
   handles everything end-to-end.

## Per-requirement implementation notes

### 1) Library display = real state (80–130 LOC)

Mostly already correct in Sonarr path — standalone path lags. Update:

- `backend/routes/library/series.py` — `get_series_detail`,
  `_get_standalone_series_detail`: merge `wanted_items.existing_sub`
  fallback (`embedded_ass` / `embedded_srt`) identical to Sonarr.
- `backend/routes/library/list.py` — missing/with_subs counter SQL: count
  only `status='wanted'` AND `existing_sub IS NULL OR existing_sub=''`.
- Frontend rendering is mostly already correct
  (`SeriesDetail.tsx`, `SeasonGroup.tsx`); standardize badge copy /
  tooltips in `SubBadge.tsx`, type comments in `types/library.ts`.

### 2) Auto-extract on add + run-until-done (320–480 LOC)

Largest backend piece. New components:

- **New DB table `subtitle_automation_queue`** — one row per pending
  extract, with retry/backoff/state.
- **New service `backend/services/subtitle_automation_runner.py`** —
  drains the queue, calls `_extract_embedded_sub`, reports state.
- **Enqueue wiring** in `services/wanted_item_scanner.py` and
  `services/wanted_scanner_sources.py` — today only new rows trigger
  immediate extract; now `updated-to-embedded` rows also get queued.
- **Scheduler registration** in `services/scheduler.py`
  (`_build_default_jobs`) — periodic drain tick.
- **Status API** — extension of `routes/wanted/providers.py` or new
  `/wanted/automation/status` endpoint with queue counts + last-run
  state.
- **Transition hygiene** in `routes/wanted/extract.py` +
  `routes/wanted/batch_extract.py` so drain + search + manual extract
  don't race.

### 3) SDH tolerance (70–120 LOC)

- **Config keys** in `backend/config_settings.py` + view in
  `config_views.py`:
  - `embedded_allow_sdh` (bool, default `true`, user-visible)
  - `embedded_sdh_penalty` (int, default `5`, user-visible advanced)
- **Ranking** in `backend/ass_probe.py::select_best_subtitle_stream`
  and `backend/providers/embedded.py::search` — SDH tracks eligible
  by default, lose to equivalent non-SDH.
- **HI-preference compatibility** preserved in
  `backend/wanted_search/process.py`.

### 4) Foreign-track cleanup (200–320 LOC)

- **Per-series override** on `SeriesSettings` in `backend/db/models/core.py`:
  `cleanup_foreign_tracks` (nullable bool, `NULL` = inherit global).
- **Global default config** `cleanup_foreign_tracks_default` (bool,
  default `false`) + optional `cleanup_foreign_tracks_keep_und`
  (bool, default `false`) as safety knob.
- **Remux helper** in `backend/remux/__init__.py` — remove subtitle
  streams where normalized language is not in target languages, via
  existing backup-to-trash swap path.
- **Trigger only** after successful target-language extraction in
  `routes/wanted/extract.py` + `routes/wanted/batch_probe.py`; gated
  by effective policy; only when all required target sidecars are
  satisfied for that file.
- **Series-settings API** extension in
  `routes/library/series_settings.py` or
  `routes/series_settings_overrides.py`.

### 5) Unified Subtitle Automation page (180–260 LOC)

- **New page** `frontend/src/pages/Settings/SubtitleAutomationPage.tsx`
  with one master toggle + granular toggles for queue drain, SDH
  handling, foreign-track cleanup default.
- **Route + nav** registration in
  `frontend/src/pages/Settings/index.tsx` and
  `frontend/src/components/settings/SettingsNav.tsx`.
- **API wiring** in `frontend/src/api/wanted.ts` and
  `frontend/src/hooks/useWantedApi.ts` for new automation
  status/run-now endpoints.
- **Live status card** — render `queue_size`, `last_run`, `last_error`.
- **Per-series override UI** control in
  `frontend/src/components/series/SeriesSettingsPanel.tsx` +
  `SeriesDetail.tsx`.

## DB migrations

1. Add column `series_settings.cleanup_foreign_tracks` (`Boolean`,
   nullable, default `NULL` = inherit global).
2. Add table `subtitle_automation_queue`:
   - `id` PK, `wanted_item_id` UNIQUE, `file_path`, `target_language`,
   - `state` ENUM(`pending|running|failed|done`),
   - `attempt_count`, `next_retry_at`, `last_error`,
   - `last_started_at`, `last_finished_at`, `created_at`, `updated_at`.
   - Indexes: `(state, next_retry_at)`, `(wanted_item_id) unique`.

## New config keys

| Key | Default | Scope | Visible |
|---|---|---|---|
| `subtitle_automation_enabled` | `false` | global | ✓ (master) |
| `subtitle_automation_queue_enabled` | `true` | global | ✓ |
| `subtitle_automation_drain_interval_minutes` | `2` | global | ✓ (advanced) |
| `embedded_allow_sdh` | `true` | global | ✓ |
| `embedded_sdh_penalty` | `5` | global | ✓ (advanced) |
| `cleanup_foreign_tracks_default` | `false` | global | ✓ |
| `cleanup_foreign_tracks_keep_und` | `false` | global | ✓ (advanced) |
| `cleanup_foreign_tracks` (per-series) | `NULL` | series | via UI toggle |

## API changes

- **NEW** `GET /api/v1/wanted/automation/status` →
  `{ enabled, queue_size, queue: {pending,running,failed,done},
     last_run_at, last_run_status, last_error }`
- **NEW** `POST /api/v1/wanted/automation/run-now` →
  `{ status: "queued"|"running" }`
- **CHANGE** `GET /api/v1/wanted/scanner/status` — add nested
  `automation` block (or alias to new endpoint).
- **CHANGE** `PATCH /api/v1/series/<id>/settings` — accept
  `cleanup_foreign_tracks: true|false|null`.
- **CHANGE** `GET /api/v1/library/series/<id>` — include
  `cleanup_foreign_tracks_override` and
  `cleanup_foreign_tracks_effective`.

## Frontend components to add/change

- **ADD** `frontend/src/pages/Settings/SubtitleAutomationPage.tsx`
- **CHANGE** `pages/Settings/index.tsx`,
  `components/settings/SettingsNav.tsx`
- **CHANGE** `api/wanted.ts`, `hooks/useWantedApi.ts`
- **CHANGE** `components/series/SeriesSettingsPanel.tsx`,
  `pages/SeriesDetail.tsx`
- **CHANGE** (minor) `components/series/SubBadge.tsx`,
  `components/series/SeasonGroup.tsx` — copy/tooltip polish

## Risks

1. **Backward-compat:** master toggle vs existing
   `wanted_auto_extract` semantics could collide if not mapped
   carefully. Need a clear mapping / migration.
2. **Concurrency:** queue drain + manual extract + scheduled search
   may race on the same `wanted_item_id`. Requires atomic
   claim/lock (recommend: `FOR UPDATE SKIP LOCKED` pattern or
   advisory lock).
3. **Remux safety:** bad / empty language tags can cause
   over-deletion. `und` (undefined) policy must be explicit and
   default conservative (keep by default).
4. **Performance:** bulk ffprobe + remux on large libraries can
   saturate disk / CPU. Cap worker counts + interval.
5. **Recovery:** failed queue entries need retry + backoff or they
   become permanent dead letters. Ensure backoff policy.

## Implementation order (dep graph)

1. DB migration + model updates (`SeriesSettings.cleanup_foreign_tracks`,
   `subtitle_automation_queue` table).
2. Config keys + config API exposure (7 keys above).
3. Queue repository/service + scheduler job registration.
4. Enqueue wiring in scanner/upsert paths + status endpoint.
5. SDH scoring/selection adjustments.
6. Foreign-track cleanup helper + extraction call-sites.
7. Frontend Subtitle Automation page + per-series toggle UI.
8. Counter/display alignment for standalone path + polish.
9. Test pass + regression sweep.

## Tests to add (Codex-drafted list)

- `tests/test_subtitle_automation_queue.py`
  - `test_enqueue_on_new_or_updated_embedded_item`
  - `test_drain_processes_until_empty_across_restarts`
  - `test_atomic_claim_prevents_double_extract`
- `tests/test_routes_wanted.py`
  - `test_automation_status_shape_and_counts`
  - `test_automation_run_now_endpoint`
- `tests/test_embedded_track_selection.py`
  - `test_sdh_allowed_by_default_with_penalty`
  - `test_non_sdh_wins_when_both_present`
  - `test_sdh_blocked_when_embedded_allow_sdh_false`
- `tests/test_remux.py`
  - `test_remove_foreign_subtitle_streams_keeps_target_languages`
- `tests/test_routes_wanted_extract.py`
  - `test_foreign_cleanup_runs_only_after_target_langs_satisfied`
- `tests/test_routes_library.py`
  - `test_standalone_embedded_fallback_visible_in_series_detail`
  - `test_standalone_missing_counts_ignore_embedded_existing_sub`
- `frontend/src/pages/Settings/__tests__/SubtitleAutomationPage.test.tsx`
  - `renders_master_and_granular_toggles`
  - `shows_queue_last_run_and_error`
  - `master_toggle_updates_package_keys`
- `frontend/src/pages/SeriesDetail.test.tsx`
  - `per_series_cleanup_toggle_persists`

## Estimated LOC per requirement

| Req | Name | LOC |
|---|---|---|
| 1 | Library display = real state | 80–130 |
| 2 | Auto-extract on add + run-until-done | 320–480 |
| 3 | SDH tolerance | 70–120 |
| 4 | Foreign-track cleanup | 200–320 |
| 5 | Unified Subtitle Automation page | 180–260 |
| — | **Total** | **850–1,300** |

## Next session

- Claude reviews this plan with user for approval.
- If approved, implementation proceeds phase-by-phase per the dep graph.
- Codex session resumable via `codex exec resume --last` for follow-up
  architecture questions.
