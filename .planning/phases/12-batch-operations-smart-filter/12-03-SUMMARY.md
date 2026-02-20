---
phase: 12-batch-operations-smart-filter
plan: 03
subsystem: ui
tags: [react, zustand, filterbar, batch-actions, i18n, fts5, pytest]

# Dependency graph
requires:
  - phase: 12-01
    provides: Backend infrastructure (FTS5 search, filter presets API, batch action endpoint)
  - phase: 12-02
    provides: Frontend core components (FilterBar, BatchActionBar, GlobalSearchModal, selectionStore)
provides:
  - Wanted page with FilterBar + sort controls + Zustand multi-select + BatchActionBar
  - History page with FilterBar + checkboxes + export-only BatchActionBar
  - Library page search + sort (already existed, verified)
  - GlobalSearchModal sidebar trigger button
  - i18n translations for batch/filter/search UI (EN + DE)
  - Backend tests for SearchRepository and FilterPresetsRepository (11 tests)
affects: [14-dashboard-widgets, 15-api-key-mgmt]

# Tech tracking
tech-stack:
  added: []
  patterns: [zustand-selection-store-per-page, filterbar-coexistence-with-button-filters, synthetic-keydown-dispatch]

key-files:
  created:
    - backend/tests/test_search.py
    - backend/tests/test_filter_presets.py
  modified:
    - frontend/src/pages/Wanted.tsx
    - frontend/src/pages/History.tsx
    - frontend/src/components/layout/Sidebar.tsx
    - frontend/src/i18n/locales/en/common.json
    - frontend/src/i18n/locales/de/common.json
    - frontend/src/i18n/locales/en/library.json
    - frontend/src/i18n/locales/de/library.json
    - .planning/ROADMAP.md

key-decisions:
  - "Wanted page Zustand store replaces local selectedIds for cross-component compatibility with BatchActionBar"
  - "FilterBar coexists with existing button filters -- activeFilters synced bidirectionally"
  - "Sort/search on Wanted page is client-side (backend API does not accept sort_by/search params on wanted endpoint)"
  - "Sidebar search trigger dispatches synthetic Ctrl+K keydown event (no prop drilling)"
  - "Library page already had search + sort -- no changes needed (Task 3 was a no-op)"
  - "i18n locale files are at frontend/src/i18n/locales/ (not frontend/public/locales/ as plan suggested)"

patterns-established:
  - "Zustand selectionStore per-page scope: use SCOPE constant + toggleItem/selectAll/clearSelection/isSelected"
  - "FilterBar activeFilters sync pattern: button clicks update FilterBar state and vice versa"
  - "Synthetic keydown dispatch for cross-component triggers without prop drilling"

# Metrics
duration: 12min
completed: 2026-02-19
---

# Phase 12 Plan 03: Page Integration Summary

**FilterBar, multi-select checkboxes, BatchActionBar, sort controls, and Sidebar search trigger wired into Wanted + History pages with 11 backend tests and EN/DE i18n translations**

## Performance

- **Duration:** 12 min
- **Started:** 2026-02-19
- **Completed:** 2026-02-19
- **Tasks:** 7 (5 with changes + 2 verification-only)
- **Files modified:** 9

## Accomplishments
- Wanted page fully wired: FilterBar with 4 filter defs, debounced search, sort dropdown/toggle, Zustand-backed checkboxes with Shift+click, floating BatchActionBar (ignore/unignore/blacklist/export)
- History page wired: FilterBar with provider/format/language/file_path filters, per-row checkboxes, BatchActionBar with export-only
- Sidebar search trigger button with Ctrl+K/Cmd+K hint for GlobalSearchModal
- i18n: filters.*, batch.*, search.* keys in common.json + wanted.sortBy/sortFields in library.json (EN + DE)
- 11 backend tests: 5 for SearchRepository (FTS5 queries), 6 for FilterPresetsRepository (CRUD + injection guard)
- Phase 12 fully complete: all 4 success criteria met (bulk actions, AND/OR filters, saved presets, global Ctrl+K search)

## Task Commits

Each task was committed atomically:

1. **Task 1: Integrate FilterBar + sort + multi-select into Wanted page** - `7dc561a` (feat)
2. **Task 2: Integrate FilterBar + multi-select into History page** - `0012030` (feat)
3. **Task 3: Add search + sort to Library page** - no commit (already implemented, verified)
4. **Task 4: Wire GlobalSearchModal into app layout** - `b02bc33` (feat)
5. **Task 5: i18n translations for batch/filter UI** - `7951cb0` (feat)
6. **Task 6: Backend tests for SearchRepository and FilterPresetsRepository** - `64fc99a` (test)
7. **Task 7: Final integration verification** - `3a24d2f` (fix)

## Files Created/Modified
- `frontend/src/pages/Wanted.tsx` - FilterBar, sort controls, Zustand selection, BatchActionBar integration
- `frontend/src/pages/History.tsx` - FilterBar, checkboxes, BatchActionBar (export only)
- `frontend/src/components/layout/Sidebar.tsx` - Search trigger button for GlobalSearchModal
- `frontend/src/i18n/locales/en/common.json` - filters/batch/search translation keys
- `frontend/src/i18n/locales/de/common.json` - German translations for filters/batch/search
- `frontend/src/i18n/locales/en/library.json` - Sort field translations for Wanted page
- `frontend/src/i18n/locales/de/library.json` - German sort field translations
- `backend/tests/test_search.py` - 5 tests for SearchRepository FTS5 search
- `backend/tests/test_filter_presets.py` - 6 tests for FilterPresetsRepository CRUD + validation
- `.planning/ROADMAP.md` - Phases 9-13 marked complete

## Decisions Made
- Replaced Wanted page's local `selectedIds` useState with Zustand `useSelectionStore` for compatibility with the floating BatchActionBar component (which reads from the store)
- FilterBar and existing filter buttons coexist: clicking a button updates FilterBar activeFilters, and FilterBar changes sync back to button state variables
- Client-side sort/search for Wanted page (backend API lacks sort_by/search params on wanted endpoint)
- Sidebar search trigger uses `document.dispatchEvent(new KeyboardEvent('keydown', { key: 'k', ctrlKey: true }))` to invoke App.tsx Ctrl+K handler without prop drilling
- Library page Task 3 was a no-op: search input + sort controls already fully implemented
- i18n locale files located at `frontend/src/i18n/locales/` (static JSON imports), not `frontend/public/locales/` as plan specified

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed pre-existing React Compiler lint warning in Wanted.tsx**
- **Found during:** Task 7 (Final verification)
- **Issue:** `useMemo` dependency `[wanted?.data]` triggered React Compiler lint error (inferred dependency mismatch)
- **Fix:** Extracted `wanted?.data` to intermediate `wantedData` variable before memo
- **Files modified:** frontend/src/pages/Wanted.tsx
- **Verification:** `npx eslint src/pages/Wanted.tsx` -- zero errors
- **Committed in:** 3a24d2f (Task 7 commit)

**2. [Rule 3 - Blocking] i18n locale file paths corrected**
- **Found during:** Task 5 (i18n translations)
- **Issue:** Plan specified `frontend/public/locales/` but actual locale files are at `frontend/src/i18n/locales/` (static JSON imports, no HTTP backend)
- **Fix:** Used correct paths for locale files
- **Files modified:** frontend/src/i18n/locales/{en,de}/{common,library}.json
- **Verification:** `python -c "import json; json.load(open('...'))"` -- all 4 files valid
- **Committed in:** 7951cb0 (Task 5 commit)

---

**Total deviations:** 2 auto-fixed (1 bug, 1 blocking)
**Impact on plan:** Both fixes necessary for correctness. No scope creep.

## Issues Encountered
None -- all tasks executed smoothly after path correction.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Phase 12 complete: all 4 success criteria satisfied
  1. Multi-select bulk actions: Wanted (ignore/unignore/blacklist/export) + History (export)
  2. AND/OR filter system: FilterBar with FilterGroup conditions + FilterPresetsRepository.build_clause()
  3. Saved filter presets: FilterPresetMenu wired to /api/v1/filter-presets
  4. Global Ctrl+K search: GlobalSearchModal with cmdk at app root, FTS5 backend
- Ready for Phase 14 (Dashboard Widgets + Quick-Actions)
- No blockers

## Self-Check: PASSED

- [x] backend/tests/test_search.py -- FOUND
- [x] backend/tests/test_filter_presets.py -- FOUND
- [x] .planning/phases/12-batch-operations-smart-filter/12-03-SUMMARY.md -- FOUND
- [x] Commit 7dc561a -- FOUND
- [x] Commit 0012030 -- FOUND
- [x] Commit b02bc33 -- FOUND
- [x] Commit 7951cb0 -- FOUND
- [x] Commit 64fc99a -- FOUND
- [x] Commit 3a24d2f -- FOUND

---
*Phase: 12-batch-operations-smart-filter*
*Completed: 2026-02-19*
