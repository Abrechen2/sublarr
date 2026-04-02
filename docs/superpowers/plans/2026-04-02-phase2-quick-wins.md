# Phase 2 — Quick Wins Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminate deprecated datetime usage (10 occurrences across 3 files), remove the dead whisper_subgen provider, and bring ROADMAP.md up to date with actual project state (currently 9 versions behind).

**Architecture:** Pure cleanup — no new abstractions. Replace deprecated calls in-place, delete dead code, update documentation.

**Tech Stack:** Python 3.12, pytest, ruff

**Branch:** `phase/2-quick-wins`

---

## File Map

| File | Action |
|------|--------|
| `backend/whisper/queue.py` | Modify — fix 6 `datetime.utcnow()` calls |
| `backend/nfo_export.py` | Modify — fix 1 `datetime.utcnow()` call |
| `backend/routes/system/logs.py` | Modify — fix 3 `datetime.utcnow()` calls |
| `backend/providers/whisper_subgen.py` | Delete |
| `backend/providers/__init__.py` | Modify — remove whisper_subgen import block |
| `ROADMAP.md` | Modify — mark v0.29–v0.37 done, update current version, add v0.38+ |

---

## Task 1: Fix datetime.utcnow() in backend/whisper/queue.py (6 occurrences)

**Files:**
- Modify: `backend/whisper/queue.py`

`datetime.utcnow()` is deprecated in Python 3.12 and will be removed in a future version. The fix is to use `datetime.now(UTC)` with an explicit timezone. The import already exists as `from datetime import datetime` — add `UTC` to it.

- [ ] **Step 1: Update the import on line 14**

Current line 14:
```python
from datetime import datetime
```

Replace with:
```python
from datetime import UTC, datetime
```

- [ ] **Step 2: Fix line 85 (submit method — job created_at)**

Current:
```python
        now = datetime.utcnow().isoformat()
```

Replace with:
```python
        now = datetime.now(UTC).isoformat()
```

- [ ] **Step 3: Fix line 189 (_run_job — started_at timestamp)**

Current:
```python
                now = datetime.utcnow().isoformat()
```

Replace with:
```python
                now = datetime.now(UTC).isoformat()
```

- [ ] **Step 4: Fix line 262 (_run_job — completed_at in update_whisper_job call)**

Current:
```python
                        completed_at=datetime.utcnow().isoformat(),
```

Replace with:
```python
                        completed_at=datetime.now(UTC).isoformat(),
```

- [ ] **Step 5: Fix line 296 (_run_job — completed_at in _update_job call)**

Current:
```python
                    completed_at=datetime.utcnow().isoformat(),
```

Replace with:
```python
                    completed_at=datetime.now(UTC).isoformat(),
```

- [ ] **Step 6: Fix line 332 (_run_job — completed_at in exception handler, _update_job)**

Current:
```python
                completed_at=datetime.utcnow().isoformat(),
```

Replace with:
```python
                completed_at=datetime.now(UTC).isoformat(),
```

- [ ] **Step 7: Fix line 341 (_run_job — completed_at in exception handler, update_whisper_job)**

Current:
```python
                    completed_at=datetime.utcnow().isoformat(),
```

Replace with:
```python
                    completed_at=datetime.now(UTC).isoformat(),
```

- [ ] **Step 8: Run ruff check on this file**

```bash
cd D:/Sublarr_Projekt/Sublarr/backend && python -m ruff check whisper/queue.py
```

Expected: no output (zero violations)

- [ ] **Step 9: Confirm no utcnow() remains in this file**

```bash
cd D:/Sublarr_Projekt/Sublarr/backend && python -m ruff check whisper/queue.py && grep -n "utcnow" whisper/queue.py
```

Expected: no output from grep

---

## Task 2: Fix datetime.utcnow() in backend/nfo_export.py (1 occurrence)

**Files:**
- Modify: `backend/nfo_export.py`

- [ ] **Step 1: Update the import on line 8**

Current line 8:
```python
from datetime import datetime
```

Replace with:
```python
from datetime import UTC, datetime
```

- [ ] **Step 2: Fix line 53 (write_nfo — downloaded_at default)**

Current:
```python
        meta.setdefault("downloaded_at", datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S"))
```

Replace with:
```python
        meta.setdefault("downloaded_at", datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S"))
```

- [ ] **Step 3: Run ruff check on this file**

```bash
cd D:/Sublarr_Projekt/Sublarr/backend && python -m ruff check nfo_export.py
```

Expected: no output (zero violations)

---

## Task 3: Fix datetime.utcnow() in backend/routes/system/logs.py (3 occurrences)

**Files:**
- Modify: `backend/routes/system/logs.py`

`logs.py` uses `datetime` via lazy local imports (`import datetime as _dt2`, `import datetime as _dt4`) inside functions and also has a top-level `from datetime import datetime` inside `support_export()`. Each occurrence needs to be fixed at its own import scope.

- [ ] **Step 1: Fix line 92 (_get_last_scan_minutes — uses _dt2 alias)**

The function body at line 82–94 does `import datetime as _dt2`. The call on line 92 is:
```python
        delta = _dt2.datetime.utcnow() - ts
```

Replace with:
```python
        delta = _dt2.datetime.now(_dt2.timezone.utc) - ts
```

Note: `_dt2.timezone.utc` is equivalent to `UTC` — we use the module alias form here because the import is `import datetime as _dt2`, not `from datetime import datetime, UTC`.

- [ ] **Step 2: Fix line 159 (_build_diagnostic — uses _dt4 alias)**

The function body at line 145–226 does `import datetime as _dt4`. The call on line 159 is:
```python
        "timestamp_utc": _dt4.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
```

Replace with:
```python
        "timestamp_utc": _dt4.datetime.now(_dt4.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
```

- [ ] **Step 3: Fix line 307 (support_export — uses top-level from datetime import datetime)**

The `support_export()` function at line 266 has a local import block including `from datetime import datetime`. The call on line 307 is:
```python
    ts = datetime.utcnow().strftime("%Y-%m-%dT%H-%M-%SZ")
```

Find the local import block inside `support_export()` (around line 287–290):
```python
    from datetime import datetime
```

Replace that line with:
```python
    from datetime import UTC, datetime
```

Then replace line 307:
```python
    ts = datetime.utcnow().strftime("%Y-%m-%dT%H-%M-%SZ")
```

With:
```python
    ts = datetime.now(UTC).strftime("%Y-%m-%dT%H-%M-%SZ")
```

- [ ] **Step 4: Run ruff check on this file**

```bash
cd D:/Sublarr_Projekt/Sublarr/backend && python -m ruff check routes/system/logs.py
```

Expected: no output (zero violations)

- [ ] **Step 5: Confirm no utcnow() remains anywhere in the backend**

```bash
cd D:/Sublarr_Projekt/Sublarr/backend && grep -rn "utcnow" .
```

Expected: no output

- [ ] **Step 6: Run the full test suite to confirm nothing is broken**

```bash
cd D:/Sublarr_Projekt/Sublarr/backend && python -m pytest --tb=short -q \
  --ignore=tests/performance \
  --ignore=tests/integration/test_provider_pipeline.py \
  --ignore=tests/test_video_sync.py \
  --ignore=tests/test_translation_backends.py \
  -k "not (test_sonarr_download_webhook or test_radarr_download_webhook or test_parse_llm_response_too_many_merge or test_record_backend_success)"
```

Expected: all tests pass (no failures introduced by datetime changes)

- [ ] **Step 7: Commit the datetime fixes**

```bash
cd D:/Sublarr_Projekt/Sublarr && git add backend/whisper/queue.py backend/nfo_export.py backend/routes/system/logs.py
git commit -m "fix: replace deprecated datetime.utcnow() with datetime.now(UTC) (10 occurrences)"
```

---

## Task 4: Remove the whisper_subgen provider

**Files:**
- Delete: `backend/providers/whisper_subgen.py`
- Modify: `backend/providers/__init__.py` (remove import block, lines 252–255)

`whisper_subgen.py` is a fully deprecated stub — every public method either returns empty results or raises `ProviderError`. It was replaced by the Whisper backend system (`whisper/subgen_backend.py`). The `@register_provider` decorator auto-registers it into `_PROVIDER_CLASSES` when the file is imported; removing the import block in `__init__.py` and the file itself is the complete removal.

There are no test files that reference `whisper_subgen`. There is no entry in `providers/registry.py` (the `PROVIDER_METADATA` dict there does not include whisper_subgen — it uses the `@register_provider` decorator only). No other backend files import it.

- [ ] **Step 1: Delete the provider file**

```bash
rm D:/Sublarr_Projekt/Sublarr/backend/providers/whisper_subgen.py
```

- [ ] **Step 2: Remove the import block from providers/__init__.py**

Open `backend/providers/__init__.py`. Find and remove these 4 lines (around line 252–255):

```python
        try:
            from providers import whisper_subgen  # noqa: F401
        except ImportError as e:
            logger.debug("WhisperSubgen provider not available: %s", e)
```

The surrounding blocks (napisy24 above, titrari below) remain unchanged. After removal, `napisy24` block flows directly into `titrari` block.

- [ ] **Step 3: Run ruff check on the providers package**

```bash
cd D:/Sublarr_Projekt/Sublarr/backend && python -m ruff check providers/
```

Expected: no output (zero violations)

- [ ] **Step 4: Run the full test suite**

```bash
cd D:/Sublarr_Projekt/Sublarr/backend && python -m pytest --tb=short -q \
  --ignore=tests/performance \
  --ignore=tests/integration/test_provider_pipeline.py \
  --ignore=tests/test_video_sync.py \
  --ignore=tests/test_translation_backends.py \
  -k "not (test_sonarr_download_webhook or test_radarr_download_webhook or test_parse_llm_response_too_many_merge or test_record_backend_success)"
```

Expected: all tests pass; no `ImportError` or `ModuleNotFoundError` related to whisper_subgen

- [ ] **Step 5: Confirm whisper_subgen is gone from the codebase**

```bash
cd D:/Sublarr_Projekt/Sublarr && grep -rn "whisper_subgen" .
```

Expected: no output

- [ ] **Step 6: Commit the removal**

```bash
cd D:/Sublarr_Projekt/Sublarr && git add backend/providers/__init__.py
git add -u backend/providers/whisper_subgen.py
git commit -m "chore: remove deprecated whisper_subgen provider (replaced by Whisper backend system)"
```

---

## Task 5: Update ROADMAP.md

**Files:**
- Modify: `ROADMAP.md`

The current `ROADMAP.md` header claims `v0.28.0-beta` as the current release. Actual current version is `v0.37.3-beta`. Versions v0.29–v0.37 are all shipped and need to be documented as completed. The content for each released version comes from `CHANGELOG.md`.

- [ ] **Step 1: Update the header line**

Current line 1:
```markdown
> Completed versions are marked ✅. The current release is **v0.28.0-beta**. Planned versions reflect intended direction and may shift.
```

Replace with:
```markdown
> Completed versions are marked ✅. The current release is **v0.37.3-beta**. Planned versions reflect intended direction and may shift.
```

- [ ] **Step 2: Add completed versions v0.29–v0.37 after the v0.28.0 section**

Find the end of the `## v0.28.0 ✅ — AI Glossary Builder` section (the blank line before `## v0.29.0 — Web Player`). Replace the existing `## v0.29.0 — Web Player` section and everything after it up to and including `## v1.0.0 — Stable Release` with the following complete block:

```markdown
## v0.29.0 ✅ — Web Player

- Streaming endpoint — `GET /api/v1/media/stream?path=` with HTTP 206 range-request support; `is_safe_path()` enforced
- PlayerModal — portal-based HTML5 `<video>` player with play/pause/seek/volume/fullscreen
- ASS/SRT subtitle overlay via SubtitleOctopus (libass WASM) rendered natively in-browser
- Subtitle track selector — switch between all available sidecar subtitle files per episode
- Seek-to-cue — clicking a cue row in SubtitleEditorModal jumps player to that timestamp

---

## v0.30.0 ✅ — Standalone NFO & Skip Extras

- Standalone — NFO metadata integration — reads `.nfo` sidecar files to resolve series/movie title, year, TVDB/TMDB ID without API lookup
- Standalone — Skip extra files — trailers, featurettes, samples excluded via Jellyfin/Kodi naming conventions; `standalone_skip_extras` setting

---

## v0.31.0 ✅ — Code Quality & Architecture Split

- 29 new tests added for `WantedSearchService`, `ProviderManager`, quality-validation logic; suite at 736 tests, 47.76% coverage
- 8 oversized backend files (800–2921 lines) decomposed: `routes/hooks/`, `routes/library/`, `routes/wanted/`, `routes/translate/`, `routes/system/`, `routes/tools/`
- `providers/registry.py` with `PROVIDER_METADATA` replaces three class-level dicts
- Frontend — `SyncControls.tsx` and `useApi.ts` each split into 6 focused sub-files
- Frontend — `ErrorBoundary` wraps Library, Wanted, and Settings routes

---

## v0.32.0 ✅ — Settings Restructure & UX Improvements

- Settings navigation restructured from 7 groups / 23 tabs to 5 logical groups
- Provider priority via drag & drop (replaces move-up/down buttons)
- Score breakdown hover tooltip on search result badges
- Wanted — per-row failure details, attempt count, next retry countdown
- Dashboard — Automation Widget with live run times and Run Now button
- Onboarding — Language and Automation setup wizard steps added

---

## v0.33.0 ✅ — Provider Expansion & Processing Pipeline

- 7 new providers: Subf2m, Subsource, YIFY Subtitles, Zimuku, BetaSeries, Titlovi, EmbeddedSubtitles
- Post-download processing pipeline with 18 fix functions (HI removal, OCR artifact cleanup, etc.); configurable per series
- Settings — Processing Pipeline section; Series Detail — Batch Process button

---

## v0.35.0 ✅ — Movie Detail & Security Hardening

- Movie Detail — subtitle management panel (wanted items per language with inline Search / Skip / Re-enable)
- Security — CSP and Permissions-Policy headers on all responses
- Security — SSRF prevention on webhook create/update endpoints
- Security — startup warning when both API key and UI auth are disabled

---

## v0.36.0 ✅ — Bazarr Parity Features

- Scoring — `video_codec` weight: x264/x265/AV1 match adds +2 points
- Language Profiles — `mustContain` / `mustNotContain` AND-logic filters (Bazarr parity)
- Language Profiles — `cutoff` (stop searching when subtitle already present)
- Language Profiles — `audioExclude` (skip download when audio track matches target language)
- CircuitBreaker — OPEN state persisted to DB; survives application restarts
- Download quality — `upgraded_from_id` foreign key tracks subtitle upgrade chain
- Standalone Mode — auto-activation when no *arr is configured

---

## v0.37.0 ✅ — Timestamp Migration & Refactoring

**BREAKING CHANGE:** All timestamp columns migrated from TEXT to `DateTime(timezone=True)`. Migration runs automatically on startup.

- `scripts/check_datetime_migration.py` — pre/post migration DB consistency checker (70 columns, 29 tables)
- Security — `subprocess(shell=True)` replaced with `shlex.split()` throughout; IP allowlist enforced; SSRF on plugin URLs
- `services/retranslation.py` extracted; `StatisticsRepository` extracted; `useDebounce` hook extracted
- TranslationTab split from 1989 lines into 8 focused sub-components
- Frontend — `ConfirmModal` replaces all `window.confirm()` calls

---

## v0.37.2 ✅ — AniDB Resolver & AnimeTosho Fix

- AniDB title dump resolver (Tier 4) — offline 91k+ entry xml.gz lookup (36h cache)
- AnimeTosho provider — rewritten with correct two-step API flow (`?show=torrent&id=`)
- Provider cache key now includes `anidb_id` to prevent stale cache hits
- Alembic — `engine.begin()` wraps all PostgreSQL DDL in explicit transaction

---

## v0.37.3 ✅ — Activity Navigation Restructure

- "Wanted" promoted to top-level sidebar nav item
- Activity reduced to 4 tabs: Queue, Translations, History, Blacklist
- New Translations tab shows active and queued translation jobs with live polling
- Badge moved from Activity to Wanted nav item

---

## v0.38.0 — Phase 2 Cleanup (Planned)

- No `datetime.utcnow()` calls anywhere in backend (10 occurrences fixed)
- `whisper_subgen` provider removed (dead code since v0.31)
- ROADMAP.md up to date

---

## v0.39.0 — Security Hardening P1–P5 (Planned)

- P1 — Domain allowlist for provider download URLs (SSRF prevention)
- P2 — `werkzeug.secure_filename()` on all provider filenames
- P3 — Prompt injection guard for Ollama (subtitle content sanitization)
- P4 — Magic byte validation after subtitle download
- P5 — Streaming size cap (50 MB limit via `iter_content()`)
- F-05 — Webhook missing-signature warning in `auth.py`

---

## v0.40.0 — Test Coverage Phase (Planned)

- Backend coverage from ~10% toward 35–40%
- Priority: `routes/cleanup.py`, `routes/api_keys.py`, `routes/profiles.py` (all currently 0% coverage)
- `bazarr_migrator.py` — data migration tests
- Stabilize 3+ excluded CI test suites

---

## v1.0.0 — Stable Release

Requirements for stable release:

- All known data-loss bugs fixed
- Full test coverage (>80%) across backend and E2E
- Migration guide from any beta version
- Stable API (no breaking changes from v0.13+)
- Docker image on GHCR with multi-arch (amd64 + arm64)
- Unraid Community Applications template finalized
- User Guide complete and reviewed
- Load tested with library of 500+ series

---

## How to Contribute

See [wiki.sublarr.de/development/contributing](https://wiki.sublarr.de/development/contributing) for how to submit features, bug reports, and pull requests.
```

- [ ] **Step 3: Verify the file looks correct**

```bash
cd D:/Sublarr_Projekt/Sublarr && grep -n "^## v0\." ROADMAP.md
```

Expected output (all versions present in order):
```
8:## v0.11.0 ✅ — Subtitle Toolchain
...
## v0.28.0 ✅ — AI Glossary Builder
## v0.29.0 ✅ — Web Player
## v0.30.0 ✅ — Standalone NFO & Skip Extras
## v0.31.0 ✅ — Code Quality & Architecture Split
## v0.32.0 ✅ — Settings Restructure & UX Improvements
## v0.33.0 ✅ — Provider Expansion & Processing Pipeline
## v0.35.0 ✅ — Movie Detail & Security Hardening
## v0.36.0 ✅ — Bazarr Parity Features
## v0.37.0 ✅ — Timestamp Migration & Refactoring
## v0.37.2 ✅ — AniDB Resolver & AnimeTosho Fix
## v0.37.3 ✅ — Activity Navigation Restructure
## v0.38.0 — Phase 2 Cleanup (Planned)
## v0.39.0 — Security Hardening P1–P5 (Planned)
## v0.40.0 — Test Coverage Phase (Planned)
## v1.0.0 — Stable Release
```

- [ ] **Step 4: Commit the ROADMAP update**

```bash
cd D:/Sublarr_Projekt/Sublarr && git add ROADMAP.md
git commit -m "docs: update ROADMAP.md to reflect v0.37.3-beta current state and add v0.38–v0.40 plans"
```

---

## Self-Review Checklist

**Spec coverage:**

| Spec requirement | Covered by |
|-----------------|------------|
| Replace all 10 `datetime.utcnow()` occurrences | Tasks 1–3 (6 in queue.py, 1 in nfo_export.py, 3 in logs.py) |
| Delete `whisper_subgen.py` | Task 4, Step 1 |
| Remove registry import of whisper_subgen | Task 4, Step 2 |
| Run tests after each change | Tasks 1–3 Step 6, Task 4 Step 4 |
| ROADMAP.md current version header updated | Task 5, Step 1 |
| v0.29–v0.37 marked complete with descriptions | Task 5, Step 2 |
| v0.38+ planned versions added | Task 5, Step 2 |

**Placeholder scan:** No TBD, TODO, or "similar to task N" patterns present.

**Type consistency:** No types defined across tasks — pure file edits with exact before/after code.

**Count check:** 
- queue.py: lines 85, 189, 262, 296, 332, 341 = 6 occurrences ✓
- nfo_export.py: line 53 = 1 occurrence ✓  
- logs.py: lines 92, 159, 307 = 3 occurrences ✓
- Total: 10 occurrences (spec said 9 — actual grep count is 10; plan covers all 10) ✓
