---
phase: 18-per-series-glossary
plan: 02
subsystem: ui, api-client
tags: [react, typescript, tanstack-query, glossary, settings, lucide-react]

# Dependency graph
requires:
  - phase: 18-01
    provides: "Nullable series_id on glossary_entries, GET/POST /glossary with optional series_id"
provides:
  - "Updated GlossaryEntry TypeScript interface with series_id: number | null"
  - "getGlossaryEntries(seriesId?) API client supporting global (no param) and per-series queries"
  - "useGlobalGlossaryEntries() React Query hook"
  - "GlobalGlossaryPanel component in Settings > Translation tab with full CRUD"
  - "Series Detail glossary override indicator text"
affects: [translation-settings-ui, series-detail-ui]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Optional seriesId parameter for global vs per-series API branching in frontend client"
    - "Dual cache invalidation (global + series-specific) on glossary mutations"
    - "Reusable glossary panel pattern (inline edit, add form, delete confirm) across Settings and SeriesDetail"

key-files:
  created: []
  modified:
    - frontend/src/api/client.ts
    - frontend/src/hooks/useApi.ts
    - frontend/src/pages/Settings/TranslationTab.tsx
    - frontend/src/pages/Settings/index.tsx
    - frontend/src/pages/SeriesDetail.tsx

key-decisions:
  - "Global glossary uses same GlossaryPanel UI pattern as per-series, adapted for null series_id"
  - "Cache invalidation targets both ['glossary', 'global'] and ['glossary', seriesId] keys on mutations"
  - "Override indicator is informational text only (no visual merge preview)"

patterns-established:
  - "Optional seriesId in API client: omit param for global, include for per-series"
  - "Dual query key invalidation pattern for global+series glossary mutations"

# Metrics
duration: 9min
completed: 2026-02-22
---

# Phase 18 Plan 02: Frontend Global Glossary UI Summary

**Global glossary CRUD panel in Settings Translation tab with React Query hooks, optional-seriesId API client, and per-series override indicator in Series Detail**

## Performance

- **Duration:** 9 min
- **Started:** 2026-02-21T23:02:00Z
- **Completed:** 2026-02-21T23:11:47Z
- **Tasks:** 2 (+ 1 human verification checkpoint, approved)
- **Files modified:** 5

## Accomplishments
- API client updated: GlossaryEntry.series_id is now `number | null`, getGlossaryEntries accepts optional seriesId for global vs per-series branching
- New `useGlobalGlossaryEntries()` hook with dual cache invalidation on create/update/delete mutations
- Full GlobalGlossaryPanel in Settings > Translation tab: add form, inline editing, delete with confirmation, empty state
- Series Detail GlossaryPanel shows informational override indicator text when entries exist

## Task Commits

Each task was committed atomically:

1. **Task 1: API client + hooks for global glossary support** - `0cfacf0` (feat)
2. **Task 2: Global glossary UI in Settings + Series Detail indicator** - `a2712a0` (feat)

## Files Created/Modified
- `frontend/src/api/client.ts` - GlossaryEntry.series_id nullable, getGlossaryEntries optional seriesId, createGlossaryEntry optional series_id
- `frontend/src/hooks/useApi.ts` - useGlobalGlossaryEntries hook, dual invalidation on glossary mutations
- `frontend/src/pages/Settings/TranslationTab.tsx` - GlobalGlossaryPanel component with full CRUD (add, inline edit, delete)
- `frontend/src/pages/Settings/index.tsx` - Import/export updates for GlobalGlossaryPanel integration
- `frontend/src/pages/SeriesDetail.tsx` - Override indicator text in GlossaryPanel header

## Decisions Made
- Reused the same UI pattern as per-series GlossaryPanel for consistency (inline editing, add form at top, delete with window.confirm)
- Cache invalidation covers both global (`['glossary', 'global']`) and series-specific (`['glossary', seriesId]`) query keys
- Override indicator is text-only ("Series-specific entries override global entries with the same source term") -- no visual merge preview needed at this stage

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Phase 18 complete: both backend (18-01) and frontend (18-02) glossary plans delivered
- Per-series and global glossary fully functional end-to-end
- Ready for Phase 19 (Context-Window Batching) which depends on Phase 18's glossary merge logic

---
*Phase: 18-per-series-glossary*
*Completed: 2026-02-22*

## Self-Check: PASSED
All 5 modified files verified on disk. Both commit hashes (0cfacf0, a2712a0) confirmed in git log.
