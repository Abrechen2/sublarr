---
phase: 05-standalone-mode
plan: 05
subsystem: ui
tags: [react, typescript, tanstack-query, settings, onboarding]

# Dependency graph
requires:
  - phase: 05-03
    provides: "StandaloneManager, MediaFileWatcher, StandaloneScanner backend classes"
  - phase: 05-04
    provides: "Standalone API Blueprint with /api/v1/standalone endpoints"
provides:
  - "TypeScript interfaces for all standalone entities (WatchedFolder, StandaloneSeries, StandaloneMovie, StandaloneStatus, StandaloneScanResult)"
  - "API client functions for standalone endpoints with proper typing"
  - "React Query hooks with cache invalidation for standalone data"
  - "Settings Library Sources tab with watched folder management UI"
  - "Onboarding Setup Mode with arr/standalone path selection"
affects: [06-forced-subs, 08-library-page, standalone-ui]

# Tech tracking
tech-stack:
  added: []
  patterns: [collapsible-cards, setup-mode-routing, conditional-navigation]

key-files:
  created: []
  modified:
    - frontend/src/lib/types.ts
    - frontend/src/api/client.ts
    - frontend/src/hooks/useApi.ts
    - frontend/src/pages/Settings.tsx
    - frontend/src/pages/Onboarding.tsx

key-decisions:
  - "Library Sources tab positioned after Radarr, before Media Servers for logical flow"
  - "Watched folder management uses inline add/edit form (not modal) for simplicity"
  - "Setup Mode step uses large cards with teal hover border for clear visual distinction"
  - "Standalone path conditionally skips Sonarr/Radarr/Path Mapping steps via visibleSteps array"
  - "StandaloneStatus polling every 10 seconds for watcher running indicator"

patterns-established:
  - "Pattern 1: Standalone types use optional wanted_count/wanted fields for joined queries"
  - "Pattern 2: API client functions follow consistent async/await + axios pattern"
  - "Pattern 3: React Query hooks use queryKey arrays for cache namespacing"
  - "Pattern 4: Setup Mode routing uses conditional step visibility based on user choice"

# Metrics
duration: 13min
completed: 2026-02-15
---

# Phase 5 Plan 5: Standalone Frontend UI Summary

**Complete standalone mode UI with Library Sources tab, watched folder management, and onboarding wizard path for non-arr users**

## Performance

- **Duration:** 13 min
- **Started:** 2026-02-15T17:34:00+01:00
- **Completed:** 2026-02-15T17:47:00+01:00
- **Tasks:** 3 (2 auto, 1 human-verify)
- **Files modified:** 5

## Accomplishments
- TypeScript types for all standalone entities (WatchedFolder, StandaloneSeries, StandaloneMovie, StandaloneStatus, StandaloneScanResult)
- 8 API client functions covering standalone endpoints (folders CRUD, series/movies list, scan trigger, status, metadata refresh)
- 8 React Query hooks with proper cache invalidation (useWatchedFolders, useSaveWatchedFolder, useDeleteWatchedFolder, useStandaloneSeries, useStandaloneMovies, useTriggerStandaloneScan, useStandaloneStatus, useRefreshSeriesMetadata)
- Settings "Library Sources" tab with standalone config fields (standalone_enabled, tmdb_api_key, tvdb_api_key, tvdb_pin, scan_interval, debounce) and watched folder management UI (add/edit/delete/enable/scan)
- Onboarding Setup Mode step with arr/standalone choice, standalone path skips Sonarr/Radarr steps and shows folder configuration

## Task Commits

Each task was committed atomically:

1. **Task 1: TypeScript types, API client, and React Query hooks** - `74a4cef` (feat)
2. **Task 2: Settings Library Sources tab and Onboarding standalone path** - `571a9aa` (feat)
3. **Task 3: Human verification** - APPROVED (no commit)

**Plan metadata:** (pending - will be committed with STATE.md)

## Files Created/Modified
- `frontend/src/lib/types.ts` - Added 5 standalone interfaces (WatchedFolder, StandaloneSeries, StandaloneMovie, StandaloneStatus, StandaloneScanResult) with full typing for API responses and DB columns
- `frontend/src/api/client.ts` - Added 8 API client functions for standalone endpoints following existing axios pattern
- `frontend/src/hooks/useApi.ts` - Added 8 React Query hooks with queryKey namespacing and cache invalidation on mutations
- `frontend/src/pages/Settings.tsx` - Added "Library Sources" tab with standalone config section and watched folder management UI (add/edit/delete/enable-disable/scan)
- `frontend/src/pages/Onboarding.tsx` - Added Setup Mode step with arr/standalone choice cards and conditional step navigation (standalone path skips Sonarr/Radarr/Path Mapping)

## Decisions Made
- **Library Sources tab placement:** Positioned after Radarr, before Media Servers for logical flow (arr services → standalone alternative → media servers)
- **Folder management UI:** Uses inline add/edit form (not modal) for simplicity and consistency with other Settings tabs
- **Setup Mode cards:** Large cards with teal hover border and CheckCircle icon for clear visual distinction and selection feedback
- **Conditional navigation:** Standalone path uses visibleSteps array to skip irrelevant steps (Sonarr/Radarr for standalone, folders for arr mode)
- **Status polling:** useStandaloneStatus polls every 10 seconds (refetchInterval: 10000) for real-time watcher running indicator

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None - TypeScript compilation and lint checks passed without errors. All hooks integrate cleanly with existing React Query setup.

## User Setup Required

None - no external service configuration required. Users configure standalone mode through Settings UI or Onboarding wizard.

## Next Phase Readiness

**Phase 5 Complete:**
- All 5 plans executed (05-01 through 05-05)
- Standalone mode fully functional: DB schema, manager, watcher, scanner, API, frontend UI
- Ready for Phase 6 (Forced Subs Detection) or Phase 7 (Events & Hooks)

**What's ready:**
- Users can configure watched folders in Settings or via Onboarding
- Media file watcher detects new files and triggers automatic scans
- Scanner performs metadata lookup (AniList, TMDB, TVDB) and creates wanted items
- Full UI coverage for standalone configuration and status monitoring

**No blockers** for next phase.

## Self-Check: PASSED

**Files verified:**
- frontend/src/lib/types.ts contains WatchedFolder interface: FOUND
- frontend/src/api/client.ts contains getWatchedFolders function: FOUND
- frontend/src/hooks/useApi.ts contains useWatchedFolders hook: FOUND
- frontend/src/pages/Settings.tsx contains "Library Sources" tab: FOUND
- frontend/src/pages/Onboarding.tsx contains Setup Mode step: FOUND

**Commits verified:**
- 74a4cef (Task 1): FOUND
- 571a9aa (Task 2): FOUND

All claimed files and commits exist. Summary is accurate.

---
*Phase: 05-standalone-mode*
*Completed: 2026-02-15*
