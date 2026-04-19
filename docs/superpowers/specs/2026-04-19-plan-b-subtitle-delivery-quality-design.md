# Plan B — Subtitle Delivery Quality

> **Parallel to:** Plan A (`2026-04-19-translation-platform-lingarr-parity-design.md`), shipped as 0.63.0-beta.

## Goal

Close the Bazarr operational gap on subtitle delivery quality. Sublarr is structurally ahead of Bazarr on scheduler hardening, observability, circuit breakers, and (after Plan A) the translation platform. Bazarr still wins on three axes this plan targets:

1. **Provider coverage** — Bazarr vendors Subliminal (~20 community-hardened providers) plus ~10 Subzero fork additions.
2. **Matching quality** — Bazarr's `subliminal_patch/score.py` carries ~30 penalty rules tuned over years of production use.
3. **Delivery pipeline maturity** — Bazarr ships post-processing shell scripts, SRT repair, and multi-engine sync out of the box.

## Architecture

Single master spec, seven sequential rollout phases (B1 → B7), matching Plan A's A1 → A5 shape. Each phase ships as its own `-beta` bump, deploys to Cardinal, and is verified in production before the next phase begins. Baseline: `0.63.0-beta` → `0.70.0-beta` when Plan B completes.

Phases group by subsystem layer:

- **Provider layer** (B1 → B3): vendor Subliminal, adopt its providers, selective Subzero merge, granular blacklist
- **Matching quality** (B4 → B5): scoring penalty port, SRT repair + embedded-extraction hardening
- **Delivery pipeline** (B6 → B7): post-processing with safe-by-default ops + shell escape, multi-engine sync with fallback chain

## Decisions Locked During Brainstorming

| Decision | Choice | Rationale |
|---|---|---|
| Subliminal integration | **Vendor** (copy into `backend/providers/_vendor/subliminal/`) | Bazarr's proven approach; lets us patch provider-specific bugs immediately and pin to known-good state |
| Post-processing style | **Hybrid: curated ops + opt-in shell escape** behind `SUBLARR_ALLOW_SHELL_SCRIPTS=true` | Safe-by-default catalogue for the 90% case; shell power for operators who explicitly opt in |
| Sync engine selection | **Ordered fallback chain with early-exit** | Cost-predictable, matches existing Sublarr fallback patterns (providers, translation backends); avoids the research-grade "score sync quality without reference" problem |

## Phase Breakdown

### B1 — Subliminal Vendor Foundation

Copy `subliminal/` source tree and its transitive dependencies (`babelfish`, `enzyme`, `chardet` or `cchardet`) into `backend/providers/_vendor/`. Build thin adapter shim `SubliminalProviderAdapter(BaseProvider)` conforming to Sublarr's provider interface. Wire ONE pilot provider end-to-end (e.g., Subliminal's OpenSubtitles flavor) via the adapter. Registry picks native vs Subliminal flavor via config flag `use_subliminal_flavor`. Smoke-test in prod.

**Acceptance:** pilot provider searches + downloads through adapter; circuit-breaker integration intact; native providers untouched.

### B2 — Full Subliminal Provider Adoption

Bring all remaining ~19 vendored providers online through the adapter. Per-provider config surfaces in existing Providers settings UI. Rate-limits declared per provider. Circuit breaker per-instance. Duplicate resolution: keep native adapters for API-key-gated paths (e.g. `opensubtitles_fetch`); use Subliminal for scrape-only providers where Sublarr has no native adapter.

**Acceptance:** ≥ 20 Subliminal-flavor providers instantiable + config-validate; existing 16 native providers unchanged; provider count ≥ 35.

### B3 — Subzero Selective Merge + Granular Blacklist

Cherry-pick 3-5 providers/fixes from the Subzero fork that Subliminal lacks. Skip abandoned or scrape-broken providers explicitly (listed in `VENDOR_PATCHES.md`). Extend `backend/db/blacklist.py` + UI with per-provider + file-hash dimensions. Migration adds `file_hash VARCHAR(64)` nullable column + composite UNIQUE index `(provider, file_hash)`.

**Acceptance:** 3-5 Subzero providers merged; granular blacklist working via UI; per-provider per-hash retry-suppression functional.

### B4 — Scoring Penalty Port

Audit Bazarr's `subliminal_patch/score.py` (~30 penalty rules). Port into `backend/wanted_search/scoring.py` as a `penalties: list[PenaltyRule]` pipeline — each rule is a named class (`MissingReleaseGroupPenalty`, `HIMismatchPenalty`, etc.) with `weight: int` + `applies(candidate, request) -> bool` predicate. Ship with Bazarr-equivalent defaults. Expose in existing ScoringTab with clear labels (e.g. "HI mismatch: -25 points"). One unit test per rule for both applies/doesn't-apply branches.

**Acceptance:** ≥ 30 penalty rules registered; UI exposes them; golden-dataset integration test produces Bazarr-equivalent ranking on fixture.

### B5 — SRT Repair + Embedded-Extraction Hardening

New `backend/subtitle_repair.py` module with pure functions `repair_srt(text) → text` and `repair_ass(text) → text`. Handles five defect classes:

1. Overlapping cues (timing collisions)
2. BOM at file start
3. Wrong newline encoding (`\r\r\n`, lone `\r`)
4. Invalid decimals in timestamps (`00:01:23,45` → `00:01:23,450`)
5. Encoding auto-detect + fix (Windows-1252, Shift-JIS mis-labeled as UTF-8)

Repair runs on every save path: provider download, embedded extract, post-translate. Embedded-extraction hardening in `backend/providers/embedded.py` — smarter track-selection ranks by `(language_match, forced_flag, hearing_impaired_flag)` priority from mkvmerge metadata.

**Acceptance:** 5 defect classes handled + tested with fixture files; embedded extraction picks correct track on ≥ 10 multi-track test files; no regression in existing embedded-extract tests.

### B6 — Post-Processing Pipeline

New Settings tab "Post-Processing". Three triggers: `after_download`, `after_translate`, `after_sync`. Per-profile ordered list of ops. Curated op catalogue (≥ 8 ops):

- `strip_html` — remove HTML tags from subtitle body
- `convert_encoding` — target-encoding parameter
- `remove_bom` — strip BOM
- `webhook` — URL + method + payload template (with `validate_service_url()` SSRF check)
- `discord_notify` — Discord webhook
- `plex_refresh` — trigger Plex library scan
- `emby_refresh` — Emby equivalent
- `jellyfin_refresh` — Jellyfin equivalent

Shell escape hatch behind `SUBLARR_ALLOW_SHELL_SCRIPTS=true` env: script body field, timeout (default 30s), variable substitution (`{subtitle_path}`, `{video_path}`, `{lang}`, `{score}`), stdout/stderr captured to Scheduler history drawer. Warning banner in UI. Runs inside dedicated thread pool separate from request handlers. Each op class implements `BaseOp.execute(context) -> OpResult` interface; pipeline writes a `post_processing_runs` audit row per run.

**Acceptance:** ≥ 8 curated ops shipped + tested individually; trigger wiring verified for all three trigger points; shell escape hatch functional with security tests (injection, path traversal, timeout) passing.

### B7 — Multi-Engine Sync with Fallback Chain

New `backend/services/sync_engines/` package, one module per engine conforming to `BaseSyncEngine` abstract interface:

- `ffsubsync_engine.py` — existing logic moved into engine class
- `alass_engine.py` — existing logic moved into engine class
- `nanosync_engine.py` — ML-based, reuses existing GPU/CPU path
- `oai_sync_engine.py` — LLM-assisted, reuses Plan A `LLMBackend` infrastructure

`SyncOrchestrator` in `backend/services/video_sync.py` owns the fallback chain. Settings: ordered preference list, per-engine timeout, sanity threshold (max offset in milliseconds). Orchestrator runs engines in declared order, early-exits on success within sanity threshold, falls through on timeout/exception/insanity. Per-job audit row in new `sync_job_runs` table (engine, offset_ms, status, duration_ms, subtitle_id, created_at). Per-engine health check on startup (e.g., `ffsubsync --version` probe).

**Acceptance:** 4 engines functional; orchestrator fallback tested for first-wins/all-fail/sanity-rejection cases; audit trail per job queryable via UI; no regression in existing sync tests.

## Key Components

### Provider Layer

- `backend/providers/_vendor/subliminal/` — vendored source tree. LICENSE file preserved. Modifications recorded in `backend/providers/_vendor/VENDOR_PATCHES.md` (minimal — only security + Python compat patches).
- `backend/providers/_vendor/babelfish/`, `enzyme/`, `chardet/` — transitive deps, same vendor convention.
- `backend/providers/subliminal_adapter.py` — `SubliminalProviderAdapter(BaseProvider)` class factory. Takes a Subliminal `Provider` instance + Sublarr config, exposes Sublarr's `search(query) → list[SubtitleCandidate]` + `download(id) → bytes`. Converts Subliminal `Subtitle` objects into Sublarr's `SubtitleCandidate` dataclass. Handles per-provider auth.
- `backend/providers/registry.py` — auto-discover vendored providers by walking `_vendor/subliminal/providers/`. Duplicate name resolution via `use_subliminal_flavor` config flag.

### Matching Quality Layer

- `backend/wanted_search/scoring.py` — extended `compute_score()` takes a `penalties: list[PenaltyRule]` pipeline. Each rule is a named class. Additive to existing base-score calculation.
- `backend/subtitle_repair.py` — new module. Pure functions per defect class. Caller decides when to run.

### Delivery Pipeline Layer

- `backend/post_processing/` — new package:
  - `pipeline.py` — `PostProcessingPipeline` runs ordered ops for a trigger
  - `ops/` — one file per curated op with shared `BaseOp` interface
  - `shell_runner.py` — shell-escape-hatch executor, only imported when env flag set
  - `events.py` — writes pipeline run audit to `post_processing_runs` table
- `backend/services/video_sync.py` — `SyncOrchestrator` class owns engine fallback chain.
- `backend/services/sync_engines/` — one file per engine (4 engines, 4 files).

### Database Schema

Three explicit Alembic migrations (never autogenerate, per `feedback_alembic_pitfalls`):

- `post_processing_runs` — trigger (text), ops_executed (jsonb), duration_ms (int), outcome (text), created_at (timestamp)
- `sync_job_runs` — engine (text), offset_ms (int), status (text), duration_ms (int), subtitle_id (int FK), created_at (timestamp)
- Extend `subtitle_blacklist` — add `file_hash VARCHAR(64)` nullable + composite UNIQUE index `(provider, file_hash)`

## Data Flow

### Download Path (existing skeleton, new stages)

```
provider.search() → rank (with new penalty pipeline)
                 → provider.download()
                 → subtitle_repair.run()
                 → save
                 → post_processing.after_download()
                 → optional translator → post_processing.after_translate()
                 → optional sync_orchestrator → post_processing.after_sync()
```

### Sync Orchestrator Fallback Chain

```python
def sync(subtitle, video):
    for engine in config.engine_order:  # e.g. [ffsubsync, alass, nanosync]
        try:
            result = engine.sync(subtitle, video, timeout=engine.timeout)
            if abs(result.offset_ms) < engine.sanity_threshold:
                audit(engine, result, ok=True)
                return result
            else:
                audit(engine, result, ok=False, reason="insanity")
                continue
        except (TimeoutError, Exception) as e:
            audit(engine, None, error=e)
            continue
    raise SyncAllEnginesFailed()
```

### Post-Processing Pipeline

```python
def run(trigger, context):  # context = {subtitle_path, video_path, lang, score}
    for op in settings.post_processing[trigger]:
        try:
            op.execute(context, timeout=op.timeout)
        except Exception as e:
            audit(op, error=e)
            if op.abort_on_error:
                break
    write_post_processing_run_row(...)
```

### Scoring Pipeline

```python
def compute_score(candidate, request):
    score = base_score(candidate)
    for penalty in registered_penalties:
        if penalty.applies(candidate, request):
            score += penalty.weight  # always negative
    return score
```

## Error Handling and Observability

- **Provider failures** — existing per-backend circuit breaker stays. Vendored Subliminal providers get wrapped in the adapter's breaker layer (one breaker per provider, not per-call).
- **Post-processing op failures** — each op declares `abort_on_error: bool` (default `false`). Failed ops log to Scheduler history drawer; pipeline continues unless flag set. Shell scripts: non-zero exit = failure; stdout + stderr captured to log.
- **Sync engine failures** — fallback chain handles natively. All-fail case: subtitle saves without sync + `WARNING` log + Prometheus counter `sublarr_sync_all_failed_total`.
- **Subtitle repair failures** — never abort save. Log warning, save unrepaired subtitle, emit Prometheus counter.
- **Blacklist additions** — atomic per `(provider, file_hash)` tuple via UNIQUE constraint.
- **Shell script security** — env flag gate + warning banner + admin-only setting + audit every run with full command + exit code. No rate-limit exemption.

### Prometheus Metrics Added

- `sublarr_post_processing_runs_total{trigger, op, outcome}` counter
- `sublarr_sync_engine_runs_total{engine, outcome}` counter
- `sublarr_sync_engine_duration_seconds{engine}` histogram
- `sublarr_subtitle_repair_total{format, outcome}` counter
- `sublarr_scoring_penalty_applied_total{rule}` counter
- `sublarr_sync_all_failed_total` counter

## Testing Strategy

Follow Sublarr conventions: TDD, 80%+ coverage target, tests in `backend/tests/`, pytest.

### Unit Tests Per Phase

- **B1** — `SubliminalProviderAdapter`: mock Subliminal `Provider`, verify search/download roundtrip, config passthrough, error translation. ~15 tests.
- **B2** — per-provider smoke tests (mocked HTTP). Each adapter-wrapped provider produces valid `SubtitleCandidate`. ~20 tests.
- **B3** — Subzero merge: per-provider tests. Granular blacklist: hash-based add/remove, composite UNIQUE constraint, query filters. ~10 tests.
- **B4** — one test file per penalty rule. 30 rules × 2 tests (applies/doesn't-apply) = ~60 tests. Plus integration test: full scoring pipeline produces Bazarr-equivalent results on golden-dataset fixture.
- **B5** — SRT repair: fixture-based tests per defect class. Embedded extraction: mock mkvmerge JSON, verify track-selection logic. ~25 tests.
- **B6** — each op gets its own test file. Pipeline orchestration tests (abort_on_error, timeout, audit-write). Shell escape: security-focused tests (injection, path traversal, timeout enforcement). ~40 tests.
- **B7** — each engine gets its own test file with mocked subprocess/API. Orchestrator fallback tests (first-wins, all-fail, sanity-rejection). ~25 tests.

**Total new tests: ~195.**

### Integration Tests

- End-to-end download → repair → post-processing → sync path with one real-format fixture per phase.
- Per-phase regression against existing `test_wanted_search.py` + `test_subtitle_download.py` — no degradation.
- Full provider suite smoke test (all vendored providers instantiable + config-validate).

### Security Tests

- Shell escape: command injection attempts, PATH pollution, subprocess resource limits.
- Vendored Subliminal: scan for hardcoded credentials / telemetry / auto-update calls before merge.
- Webhook op: URL validation via existing `validate_service_url()` (SSRF protection).

### Golden Dataset

New fixture directory `backend/tests/fixtures/subtitle_quality/` with ~20 real-world subtitle files covering the five defect classes, HI tags, malformed ASS drawing modes. Used across B4/B5/B6 tests.

### CI Gate

Each phase's merge to master requires full backend suite green + ruff clean. No phase ships to prod with known regressions.

## Success Criteria and Acceptance

### Per-Phase Acceptance

- All new + existing tests green
- Ruff + mypy clean on touched code
- Alembic migrations forward + backward work
- Docker image builds + pushes successfully
- Cardinal deploy verified via `/api/v1/health` + domain-specific endpoint
- No log errors in first 60s of prod runtime

### Plan B Overall Acceptance (after B7 ships as 0.70.0-beta)

- Provider count ≥ 30 (currently 16 native; target 16 + ~20 Subliminal + 3-5 Subzero ≈ 35+)
- Scoring rules ≥ 30 penalty rules configurable via UI
- Post-processing: ≥ 8 curated ops shipped + shell escape hatch functional
- Sync engines: ≥ 4 engines in fallback chain (ffsubsync, alass, nanosync, oai-sync)
- Subtitle repair handles all 5 defect classes
- Granular blacklist working with file-hash dimension
- No regression in Plan A translation platform (294+ tests still green)
- Prod verified: real download → real repair → real post-proc → real sync path tested on Cardinal against live media library

## Out of Scope

Reserved for future plans:

- Plugin marketplace extensions (already exists as `routes/marketplace.py`; not touched in Plan B)
- Provider SDK for third-party integrations (candidate for Plan C)
- WebRTC-based real-time subtitle previews (unrelated)
- Migration from SQLAlchemy sync engine to async (independent infrastructure project)
- Bazarr `subsync_scraper` / `subsyncarr` integrations (non-core, community tooling)

## Dependencies

- **Plan A (Translation Platform)** must ship before Plan B — settled, 0.63.0-beta shipped 2026-04-19.
- **GitNexus index** refreshed after each phase to keep impact-analysis surgical when touching `providers/` tree.
- **Docker Desktop** on dev PC for multi-arch builds (existing requirement).

## Open Follow-Ups After Plan B

- Cache-aware cost accounting for Claude (Plan A follow-up)
- Ollama CJK-hallucination retry reintroduction (Plan A follow-up)
- TranslationMemory ORM `backend` column exposure (Plan A follow-up)
- Plan C: provider SDK + community plugin distribution (tentative next milestone)
