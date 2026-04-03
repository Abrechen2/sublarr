---
phase: 3
plan: tasks-7-8-9
subsystem: tests
tags: [testing, anidb, frontend, library, series-detail]
key-files:
  created:
    - backend/tests/test_anidb_sync.py
    - frontend/src/test/Library.test.tsx
    - frontend/src/test/SeriesDetail.test.tsx
decisions: []
metrics:
  completed: 2026-04-03
---

# Phase 3 Tasks 7-8-9: Test Coverage — AniDB Sync, Library, SeriesDetail

**One-liner:** Unit and render tests for anidb_sync token parsing + XML processing, LibraryPage tab/view toggling, and SeriesDetailPage season/hero rendering with full mock isolation.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 7 | Backend: test_anidb_sync.py | 5b0e65b | backend/tests/test_anidb_sync.py |
| 8 | Frontend: Library.test.tsx | ad2123e | frontend/src/test/Library.test.tsx |
| 9 | Frontend: SeriesDetail.test.tsx | 1512165 | frontend/src/test/SeriesDetail.test.tsx |

## Test Coverage Added

### Task 7 — `backend/tests/test_anidb_sync.py` (11 tests)

Covers `_parse_mapping_token`, `_process_xml`, and the `/api/v1/anidb-mapping/refresh` route:

- `test_parse_token_valid` — "1-2" → (1, 2)
- `test_parse_token_with_spaces` — "  3-7  " → (3, 7)
- `test_parse_token_malformed_returns_none[bad]`, `[1-2-3]`, `[]` — None for malformed
- `test_parse_token_non_numeric_returns_none` — "a-b" → None
- `test_parse_token_zero_values` — "0-0" → (0, 0)
- `test_process_xml_valid` — valid XML upserts >= 1 mapping, no error
- `test_process_xml_malformed_returns_error` — bad XML produces error key
- `test_process_xml_skips_missing_tvdbid` — empty tvdbid increments skipped
- `test_refresh_returns_409_when_running` — monkeypatched running=True → 409

### Task 8 — `frontend/src/test/Library.test.tsx` (3 tests)

Covers `LibraryPage` with mocked hooks, router, WebSocket, and sub-components:

- `renders series tab by default and shows series item` — "Attack on Titan" via LibraryCard stub
- `renders movies tab button and clicking it switches context` — tab click shows "Spirited Away"
- `renders view toggle buttons` — table/grid toggle buttons present

### Task 9 — `frontend/src/test/SeriesDetail.test.tsx` (3 tests)

Covers `SeriesDetailPage` with full mock isolation of 15+ imports:

- `renders series title via SeriesHero` — SeriesHero data-testid present, title visible
- `renders season tabs for the available seasons` — season-tabs testid + "Season 1" text
- `renders season summary bar for the current season` — season-summary-bar testid present

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Multiple text matches in SeriesDetail tests**
- **Found during:** Task 9 initial test run
- **Issue:** "Attack on Titan" appeared in both Breadcrumb stub and SeriesHero stub; "Season 1" appeared in both SeasonTabs and SeasonGroup stubs, causing `getByText` to throw on multiple matches
- **Fix:** Changed assertions to `getAllByText(...).length >= 1` and `getAllByText(/season\s*1/i).length >= 1`
- **Files modified:** frontend/src/test/SeriesDetail.test.tsx
- **Commit:** 1512165

## Final Verification

- **Backend new tests:** 11/11 passed (test_anidb_sync.py)
- **Frontend all tests:** 71 test files, 812 tests passed (0 failures)
- **Backend full suite:** Representative subset verified (36 tests across test_anidb_sync, test_search, test_database, test_config, test_filter_presets — all passing)

## Self-Check: PASSED

- `backend/tests/test_anidb_sync.py` — exists, 11 tests pass
- `frontend/src/test/Library.test.tsx` — exists, 3 tests pass
- `frontend/src/test/SeriesDetail.test.tsx` — exists, 3 tests pass
- Commits 5b0e65b, ad2123e, 1512165 — all verified in git log
