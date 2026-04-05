# Phase 3b — Backend Test Coverage (Remaining Items)

**Branch:** `phase/3b-test-coverage`
**Goal:** Raise backend test coverage from ~10% to ≥40% by testing the highest-LOC untested route files.
**Date:** 2026-04-03

---

## Prerequisites

- `pytest-cov` is NOT installed — never pass `--cov` flags
- `pytest.ini` currently has `--cov=.` and related flags in `addopts` that break all test runs → fix first
- Use `client` fixture from `conftest.py` for all HTTP route tests
- Mock external dependencies with `monkeypatch` or `MagicMock`
- **Read target file before writing tests** — never assume endpoint shape

## Standard test run (per task)

```bash
cd D:/Sublarr_Projekt/Sublarr/backend && python -m pytest tests/test_<file>.py -v --tb=short
```

## Full pre-PR run (after all tasks complete)

```bash
cd D:/Sublarr_Projekt/Sublarr/backend && python -m pytest --tb=short -q \
  --ignore=tests/performance \
  --ignore=tests/integration/test_provider_pipeline.py \
  --ignore=tests/test_video_sync.py \
  --ignore=tests/test_translation_backends.py \
  -k "not (test_sonarr_download_webhook or test_radarr_download_webhook or test_parse_llm_response_too_many_merge or test_record_backend_success)"
```

---

## Task 0 — Fix pytest.ini (prerequisite)

**File:** `backend/pytest.ini`

- [ ] Open `backend/pytest.ini`
- [ ] Remove these five lines from the `addopts` block:
  ```
      --cov=.
      --cov-report=term-missing
      --cov-report=html
      --cov-report=xml
      --cov-fail-under=25
  ```
- [ ] Keep `-v`, `--tb=short`, `--strict-markers`, `--disable-warnings` intact
- [ ] Keep the `[coverage:run]` and `[coverage:report]` sections intact (harmless without the plugin active)
- [ ] Verify: `python -m pytest tests/test_auth.py -v --tb=short` completes without "no module named pytest_cov" error
- [ ] Commit: `fix: remove pytest-cov flags from pytest.ini (plugin not installed)`

---

## Task 1 — `routes/subtitles.py` — Subtitle CRUD

**File to read first:** `backend/routes/subtitles.py`
**New test file:** `backend/tests/test_routes_subtitles.py`
**Target:** ~40–60 tests

### Steps

- [ ] Read `backend/routes/subtitles.py` in full — note every `@bp.route` decorator, method, URL rule, and expected request/response shape
- [ ] Identify which routes require DB rows (items, subtitles) and insert them via `get_db()` in test setup
- [ ] Mock `providers.get_provider_manager` using the existing `mock_provider_manager` fixture where search/download routes are hit
- [ ] Write tests covering:
  - [ ] `GET /api/v1/subtitles/<item_id>` — list subtitles for item (empty, populated)
  - [ ] `POST /api/v1/subtitles/<item_id>` or equivalent download/search trigger endpoint — 200 path, missing item 404
  - [ ] `DELETE /api/v1/subtitles/<subtitle_id>` — success, not-found
  - [ ] Any search-trigger endpoint — success returns 202/200, provider error returns 500
  - [ ] Auth guard: if `SUBLARR_API_KEY` is set, unauthenticated requests return 401
- [ ] Verify: `python -m pytest tests/test_routes_subtitles.py -v --tb=short` — all pass
- [ ] Commit: `test: add HTTP tests for routes/subtitles.py`

---

## Task 2 — `routes/library/` — Library Browsing

**Files to read first:** `backend/routes/library/list.py`, `backend/routes/library/series.py`, `backend/routes/library/episodes.py`
**New test file:** `backend/tests/test_routes_library.py`
**Target:** ~40–60 tests

### Steps

- [ ] Read all three library route files — note URL rules, query parameters, response shapes
- [ ] Identify DB tables touched (items, series, episodes) and seed minimal rows in test setup
- [ ] Write tests covering:
  - [ ] `GET /api/v1/library/series` — empty list, populated list, pagination params
  - [ ] `GET /api/v1/library/series/<id>` — found, not found (404)
  - [ ] `GET /api/v1/library/movies` — empty list, populated list
  - [ ] `GET /api/v1/library/series/<id>/episodes` — episode list for series, series not found
  - [ ] Filter/search query params where present — valid, invalid type (400 expected)
- [ ] Verify: `python -m pytest tests/test_routes_library.py -v --tb=short` — all pass
- [ ] Commit: `test: add HTTP tests for routes/library/`

---

## Task 3 — `routes/wanted/` — Wanted Items

**Files to read first:** `backend/routes/wanted/list.py`, `backend/routes/wanted/search.py`, `backend/routes/wanted/providers.py`, `backend/routes/wanted/extract.py`
**New test file:** `backend/tests/test_routes_wanted.py`
**Target:** ~30–40 tests

### Steps

- [ ] Read all wanted route files — note URL rules and which ones trigger background tasks vs. return immediately
- [ ] Use `mock_provider_manager` fixture to prevent real provider calls
- [ ] Write tests covering:
  - [ ] `GET /api/v1/wanted` — empty list, populated list, filter params
  - [ ] Search-trigger endpoint — returns 202/200 (not 500) when provider mock returns empty
  - [ ] Mark-complete / skip endpoint if present — success, not found
  - [ ] Extract endpoint — success stub, file-not-found error path
- [ ] Verify: `python -m pytest tests/test_routes_wanted.py -v --tb=short` — all pass
- [ ] Commit: `test: add HTTP tests for routes/wanted/`

---

## Task 4 — `routes/providers.py` — Provider Management

**File to read first:** `backend/routes/providers.py`
**New test file:** `backend/tests/test_routes_providers.py`
**Target:** ~30–40 tests

### Steps

- [ ] Read `backend/routes/providers.py` — note enable/disable, config, test-connection endpoints
- [ ] Mock `providers.get_provider_manager` with `mock_provider_manager` fixture; patch test-connection calls with `monkeypatch`
- [ ] Write tests covering:
  - [ ] `GET /api/v1/providers` — returns list with status fields
  - [ ] `POST /api/v1/providers/<name>/enable` — success, unknown provider 404
  - [ ] `POST /api/v1/providers/<name>/disable` — success
  - [ ] `POST /api/v1/providers/<name>/test` — mock passes (200), mock raises (200 with error flag or 500)
  - [ ] `PUT /api/v1/providers/<name>` or config endpoint — valid config, invalid field (422/400)
- [ ] Verify: `python -m pytest tests/test_routes_providers.py -v --tb=short` — all pass
- [ ] Commit: `test: add HTTP tests for routes/providers.py`

---

## Task 5 — `routes/translate/` — Translation Routes

**Files to read first:** `backend/routes/translate/core.py`, `backend/routes/translate/backends.py`, `backend/routes/translate/batch.py`, `backend/routes/translate/memory.py`
**New test file:** `backend/tests/test_routes_translate.py`
**Target:** ~30–40 tests

### Steps

- [ ] Read all four translate route files — note URL rules, which routes gate on the translation feature flag, which hit Ollama
- [ ] Use `mock_ollama` fixture from `conftest.py` to prevent real Ollama calls
- [ ] Set `SUBLARR_TRANSLATION_ENABLED=true` in env where feature-gated routes are tested; test 403/404 response when disabled
- [ ] Write tests covering:
  - [ ] Translation trigger endpoint — 202 when mock returns ok, error path
  - [ ] `GET /api/v1/translate/backends` — list of configured backends
  - [ ] Batch translate endpoint — accepts list, delegates to mock, returns job id or result
  - [ ] Translation memory endpoints if present — add entry, list entries
  - [ ] Feature-disabled path — gated endpoints return appropriate error (403 or 404)
- [ ] Verify: `python -m pytest tests/test_routes_translate.py -v --tb=short` — all pass
- [ ] Commit: `test: add HTTP tests for routes/translate/`

---

## Task 6 — `bazarr_migrator.py` — Migration Safety

**File to read first:** `backend/bazarr_migrator.py`
**New test file:** `backend/tests/test_bazarr_migrator.py`
**Target:** ~20–30 tests

### Steps

- [ ] Read `backend/bazarr_migrator.py` in full — identify pure transformation functions (no DB I/O) vs. functions that read/write SQLite
- [ ] Mock all SQLite connections with `MagicMock` or `sqlite3.connect` patches; do NOT require a real Bazarr DB
- [ ] Write tests covering:
  - [ ] Data transformation functions: given Bazarr row dict → expected Sublarr row dict (field mapping, type coercion, defaults)
  - [ ] Language code normalization if present
  - [ ] Path rewriting / prefix substitution logic
  - [ ] Missing/null field handling — None input → graceful default, not exception
  - [ ] Top-level migrate function with mocked DB: verify `INSERT` is called with correctly transformed data
- [ ] Verify: `python -m pytest tests/test_bazarr_migrator.py -v --tb=short` — all pass
- [ ] Commit: `test: add unit tests for bazarr_migrator.py`

---

## Final Verification

- [ ] Run full pre-PR test suite (command above) — no unexpected failures
- [ ] Confirm all six new test files committed on branch `phase/3b-test-coverage`
- [ ] Open PR targeting `master`
