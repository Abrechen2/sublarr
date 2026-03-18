# v0.31.0 — Code Quality & Architecture Refactoring Roadmap

**Date:** 2026-03-18
**Version:** v0.31.0
**Type:** Non-functional — quality, architecture, tech debt
**Strategy:** Foundation-first (tests → safe cleanup → file splits → architecture → frontend)

---

## Goal

Systematically bring the entire Sublarr codebase up to the project's own best-practice standards. No new features. Every file over 800 lines gets split. Every bare `except Exception: pass` gets a specific type and log. Every in-memory singleton state gets persisted. The test coverage floor rises to 80%.

Bugs found along the way are fixed in the same PR as the surrounding refactor.

---

## Phase 1 — Test Foundation

**Goal:** Build the safety net before touching anything structural.

### 1.1 `wanted_search.py` test suite
The most complex business logic in the codebase (1,783 lines). A `test_wanted_search_reliability.py` exists but is in the standard pre-PR ignore list due to flakiness — part of this phase is fixing that flakiness and removing the ignore flag. Cover:
- Provider search orchestration (multi-provider, deduplication)
- Adaptive retry computation (`_compute_retry_after`)
- Download pipeline (score → select → download → verify)
- State transitions (wanted → searching → downloaded / failed)

### 1.2 `translator.py` test suite
- Backend selection logic (Ollama, DeepL, Google, Whisper)
- Whisper fallback path
- Format selection (ASS vs SRT)
- Translation config history persistence

### 1.3 `ProviderManager` orchestration tests
- `search()` with multiple providers
- Rate limiting behavior
- Circuit breaker activation and recovery
- Timeout enforcement

### 1.4 Test isolation fixes
- Singleton reset fixtures (`providers`, `wanted_scanner`, `translator`)
- Batch-state dict reset between tests (currently carries over)
- Conftest cleanup: remove any `pass`-on-exception patterns in fixtures
- Remove `test_wanted_search_reliability.py` from the pre-PR ignore list once flakiness is resolved

---

## Phase 2 — Safe Cleanup

**Goal:** Remove false safety signals and fix bounded, high-impact issues with zero structural risk.

### 2.1 Remove `_db_lock` No-Op
`db/__init__.py` exports `_NoOpLock`. It does nothing but creates a false sense of thread safety. Steps:
1. Audit all `from db import _db_lock` usages across the codebase (known: `wanted_scanner.py`, `routes/wanted.py`, `routes/system.py`, `routes/subtitles.py`, `routes/library.py`, `routes/standalone.py`, `standalone/scanner.py`)
2. Audit test files importing `_db_lock` (`tests/test_quality_dashboard.py`, `tests/test_translation_backends.py`) — remove or rewrite relevant fixtures before deletion
3. Remove the lock acquisitions — SQLAlchemy session scoping handles thread safety
4. Delete the `_NoOpLock` class and export
5. Verify zero remaining references with `grep -r "_db_lock" backend/`

### 2.2 Fix `WAVEFORM_CACHE` (unbounded)
`routes/tools.py:19` — `WAVEFORM_CACHE: dict = {}` grows without bound. Replace with `functools.lru_cache` or a size-capped `OrderedDict` with TTL.

### 2.3 Persist Batch State to DB
Full inventory of in-memory state dicts to migrate:
- `routes/wanted.py` — `wanted_batch_state`, `_batch_extract_state`, `_batch_probe_state` (+ co-located `_batch_extract_lock`, also imported by `routes/system.py` — that import must be removed when the lock goes away)
- `routes/translate.py` — `batch_state` (translation batch)
- `routes/cleanup.py` — `_scan_state` (dedup scan), `_orphan_state` (orphan scan)

Replace all with DB-persisted job records via the existing `jobs` repository. Benefits: survives server restart, enables proper status polling, fixes test isolation.

### 2.4 Exception Handling Audit
Scan all `except Exception` and `except Exception: pass` occurrences. For each:
- Replace with the most specific exception type(s) possible
- Add `logger.warning()` or `logger.error()` with context
- Never swallow silently unless the fallback is explicitly documented

---

## Phase 3 — Backend File Splits

**Goal:** Every file over 800 lines gets broken into focused modules. Follow the existing `db/repositories/` pattern — small files, one responsibility each.

### Execution order (largest risk first, now safe because Phase 1 tests exist)

| File | Lines | Target Structure |
|------|-------|-----------------|
| `routes/tools.py` | 2,911 | `routes/tools/waveform.py`, `subtitle_utils.py`, `file_ops.py`, `media_info.py` |
| `routes/system.py` | 2,812 | `routes/system/health.py`, `backup.py`, `logs.py`, `support.py`, `scheduler.py` |
| `routes/wanted.py` | 1,902 | `routes/wanted/list.py`, `search.py`, `extraction.py`, `batch.py` |
| `wanted_search.py` | 1,783 | `services/wanted_search/orchestrator.py`, `scorer.py`, `downloader.py`, `dedup.py` |
| `translator.py` | 1,742 | `services/translation/dispatcher.py`, `whisper.py`, `backends.py`, `history.py` |
| `routes/translate.py` | 1,632 | `routes/translate/batch.py`, `single.py`, `status.py` |
| `routes/library.py` | 1,201 | `routes/library/list.py`, `detail.py`, `subtitles.py` |
| `routes/hooks.py` | 1,051 | `routes/hooks/list.py`, `triggers.py`, `validation.py` |

**For each split:**
1. Create subdirectory with `__init__.py` that re-exports the Blueprint
2. Move functions to appropriate sub-modules
3. Update all imports
4. Run tests — fix any discovered bugs before next file

---

## Phase 4 — Architecture

**Goal:** Structural improvements that reduce coupling and make future changes safer.

### 4.1 `config.py` — Nested Settings
Split the flat 160+ parameter `Settings` class into nested sections:
```python
class Settings(BaseSettings):
    general: GeneralSettings
    translation: TranslationSettings
    providers: ProviderSettings
    media_servers: MediaServerSettings
    scanning: ScanningSettings
```
Keep backward compatibility via `@property` shims during transition.

### 4.2 Provider Registration — Metadata-Driven
Replace the 20+ manual provider registrations with a metadata dict:
```python
PROVIDER_METADATA = {
    "opensubtitles": {"timeout": 10, "rate_limit": (40, 10), "retries": 3},
    ...
}
```
Extract to `providers/registry.py`. Eliminates copy-paste errors when adding providers.

### 4.3 Singleton Lifecycle
Register `WantedScanner` and `ProviderManager` via `app.extensions` in the app factory for better testability and explicit lifecycle ownership. Do NOT use Flask `g` — these are application-lifetime objects, not request-scoped. Keep `invalidate_scanner()` and `invalidate_manager()` as the reset mechanism after config changes.

---

## Phase 5 — Frontend

**Goal:** Same principles applied to the React codebase.

### 5.1 `SyncControls.tsx` (585 lines) → Tab Components
```
components/sync/
  SyncControls.tsx       (orchestrator, <150 lines)
  OffsetTab.tsx
  SpeedTab.tsx
  FramerateTab.tsx
  ChapterTab.tsx
```

### 5.2 `useApi.ts` → Logical Hook Groups
Replace 77 flat exports with domain-grouped hooks:
- `useWantedApi.ts`
- `useTranslationApi.ts`
- `useLibraryApi.ts`
- `useSystemApi.ts`

### 5.3 Per-Section Error Boundaries
`ErrorBoundary` already exists at `components/shared/ErrorBoundary.tsx` and wraps the root app. Add per-section boundaries inside the root — wrap the Library, Wanted, and Settings page trees individually so a crash in one section does not degrade the others.

---

## Quality Gates

Each phase must pass before the next begins:

- **Phase 1 complete:** `pytest` passes without the `test_wanted_search_reliability.py` ignore flag, coverage ≥80% for `wanted_search.py`, `translator.py`, and `providers/__init__.py` as measured by `pytest --cov`
- **Phase 2 complete:** Zero `_db_lock` references, zero unbounded caches, batch state in DB, ruff clean
- **Phase 3 complete:** Zero files >800 lines in `backend/` (excluding `venv/`), all imports resolve, tests pass
- **Phase 4 complete:** Settings nested, provider registry in place, ruff clean
- **Phase 5 complete:** Zero frontend files >400 lines, `npm run lint` and `tsc --noEmit` pass

---

## Non-Goals

- No new user-facing features
- No API contract changes (endpoints stay the same)
- No database schema migrations (except batch state persistence in Phase 2)
- No dependency upgrades (separate concern)
