---
phase: 12-batch-operations-smart-filter
plan: 02
subsystem: ui
tags: [react, zustand, cmdk, tanstack-query, typescript, tailwind, filters, batch-operations, search]

# Dependency graph
requires:
  - phase: 12-01
    provides: Backend FTS5 search, filter preset CRUD, batch action endpoints
provides:
  - Zustand selection store for cross-page multi-select with Shift+click
  - GlobalSearchModal cmdk command palette with Ctrl+K binding
  - FilterBar with active chips, add/remove, preset save/load
  - BatchActionBar floating pill for bulk operations
  - TypeScript types for filters, search, batch actions
  - API client functions and React Query hooks for search, presets, batch
affects: [12-03]

# Tech tracking
tech-stack:
  added: [cmdk ^1.1.1, zustand ^5.0.11]
  patterns: [Zustand per-scope selection store, cmdk shouldFilter=false for server-side search, FilterBar chip pattern with preset menu]

key-files:
  created:
    - frontend/src/stores/selectionStore.ts
    - frontend/src/components/search/GlobalSearchModal.tsx
    - frontend/src/components/filters/FilterBar.tsx
    - frontend/src/components/filters/FilterPresetMenu.tsx
    - frontend/src/components/batch/BatchActionBar.tsx
  modified:
    - frontend/package.json
    - frontend/src/lib/types.ts
    - frontend/src/api/client.ts
    - frontend/src/hooks/useApi.ts
    - frontend/src/App.tsx

key-decisions:
  - "cmdk Command.Dialog with shouldFilter=false -- all filtering done server-side via FTS5"
  - "Zustand per-scope selection store (wanted/library/history) with independent selection sets"
  - "Ctrl+K handler in App.tsx (not Sidebar) for global scope accessibility"
  - "FilterBar uses onOpenChange callback wrapper instead of useEffect for query reset (React 19 strict lint)"
  - "BatchActionBar uses new Date().getTime() instead of Date.now() to satisfy purity lint rule"
  - "navigate() calls wrapped with void operator for floating promise lint compliance"

patterns-established:
  - "Zustand store pattern: create<State & Actions>((set, get) => ...) for cross-page state"
  - "FilterBar chip pattern: active filters as pill chips with x-remove, add-filter popover dropdown"
  - "cmdk dialog pattern: overlayClassName + contentClassName for Radix Dialog styling"

# Metrics
duration: 10min
completed: 2026-02-19
---

# Phase 12 Plan 02: Frontend Core Infrastructure Summary

**Zustand selection store, cmdk Ctrl+K search modal, FilterBar with preset save/load, and BatchActionBar floating action pill -- all reusable components for Plan 03 page integration**

## Performance

- **Duration:** 10 min
- **Started:** 2026-02-19
- **Completed:** 2026-02-19
- **Tasks:** 8
- **Files modified:** 10

## Accomplishments
- Installed cmdk ^1.1.1 and zustand ^5.0.11 as new frontend dependencies
- Created Zustand selection store with per-scope isolation, Shift+click range selection, selectAll/clearSelection
- Built GlobalSearchModal using cmdk Command.Dialog with server-side FTS5 search, grouped results (series/episodes/subtitles)
- Created FilterBar with active filter chips, add-filter popover, clear-all, and FilterPresetMenu for save/load presets
- Built BatchActionBar as floating bottom pill with contextual actions (ignore/unignore/blacklist/export)
- Added 10 new TypeScript interfaces/types for Phase 12 (FilterPreset, FilterGroup, GlobalSearchResults, BatchAction, etc.)
- Added 6 API client functions and 5 React Query hooks for search, filter presets, and batch actions
- Zero TypeScript errors, zero lint errors in all new files

## Task Commits

Each task was committed atomically:

1. **Task 1: Install cmdk and zustand** - `0321b42` (chore)
2. **Task 2: TypeScript types** - `1cca312` (feat)
3. **Task 3: Zustand selection store** - `2d9e441` (feat)
4. **Task 4: API client + React Query hooks** - `cf22ea5` (feat)
5. **Task 5: GlobalSearchModal** - `1e26d99` (feat)
6. **Task 6: FilterBar + FilterPresetMenu** - `ca9ff63` (feat)
7. **Task 7: BatchActionBar** - `453d6de` (feat)
8. **Task 8: Lint verification + fixes** - `2e31016` (fix)

## Files Created/Modified
- `frontend/package.json` - Added cmdk ^1.1.1, zustand ^5.0.11
- `frontend/src/lib/types.ts` - 10 new Phase 12 types (FilterPreset, FilterGroup, GlobalSearchResults, BatchAction, etc.)
- `frontend/src/api/client.ts` - 6 new API functions (searchGlobal, getFilterPresets, createFilterPreset, updateFilterPreset, deleteFilterPreset, batchAction)
- `frontend/src/hooks/useApi.ts` - 5 new hooks (useGlobalSearch, useFilterPresets, useCreateFilterPreset, useDeleteFilterPreset, useBatchAction)
- `frontend/src/stores/selectionStore.ts` - Zustand store for cross-page multi-select with Shift+click range
- `frontend/src/components/search/GlobalSearchModal.tsx` - cmdk command palette with Ctrl+K, server-side search
- `frontend/src/components/filters/FilterBar.tsx` - Filter chip bar with add/remove, clear-all, preset support
- `frontend/src/components/filters/FilterPresetMenu.tsx` - Preset dropdown with save/load/delete
- `frontend/src/components/batch/BatchActionBar.tsx` - Floating batch action pill with contextual bulk operations
- `frontend/src/App.tsx` - Added Ctrl+K handler and GlobalSearchModal render

## Decisions Made
- cmdk shouldFilter=false: FTS5 search happens server-side, not in the client-side filter
- Zustand per-scope store: wanted/library/history maintain independent selection sets that survive navigation
- Query reset via onOpenChange wrapper: avoids React 19 strict lint rules against useEffect-setState and ref-during-render
- navigate() wrapped with void: complies with no-floating-promises rule for react-router-dom v7

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed GlobalSearchModal query reset pattern**
- **Found during:** Task 8 (lint verification)
- **Issue:** useEffect-setState pattern flagged by react-hooks/set-state-in-effect, ref-during-render by react-hooks/refs
- **Fix:** Wrapped onOpenChange callback to reset query on close, used void navigate() for promises
- **Files modified:** frontend/src/components/search/GlobalSearchModal.tsx
- **Verification:** npx eslint passes with 0 errors
- **Committed in:** 2e31016

**2. [Rule 1 - Bug] Fixed BatchActionBar Date.now() purity warning**
- **Found during:** Task 8 (lint verification)
- **Issue:** Date.now() in component body flagged as impure function by react-hooks/purity
- **Fix:** Replaced with new Date().getTime() captured in local variable
- **Files modified:** frontend/src/components/batch/BatchActionBar.tsx
- **Verification:** npx eslint passes with 0 errors
- **Committed in:** 2e31016

---

**Total deviations:** 2 auto-fixed (2 bug fixes for lint compliance)
**Impact on plan:** Both fixes necessary for React 19 strict mode lint compliance. No scope creep.

## Issues Encountered
None - all tasks executed smoothly. Pre-existing lint errors in App.tsx and client.ts (unrelated to this plan) were noted and not modified.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- All reusable components ready for Plan 03 page integration
- Plan 03 will wire FilterBar, BatchActionBar, and selection into Library, Wanted, and History pages
- GlobalSearchModal already wired into App.tsx with Ctrl+K binding

## Self-Check: PASSED

- All 5 created files verified (selectionStore.ts, GlobalSearchModal.tsx, FilterBar.tsx, FilterPresetMenu.tsx, BatchActionBar.tsx)
- All 8 commits verified (0321b42, 1cca312, 2d9e441, cf22ea5, 1e26d99, ca9ff63, 453d6de, 2e31016)
- TypeScript: 0 errors
- Lint (new files): 0 errors

---
*Phase: 12-batch-operations-smart-filter*
*Completed: 2026-02-19*
