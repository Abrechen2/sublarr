# Phase 25-02 — AniDB Absolute Episode Order: Frontend Summary

## What Was Implemented

### Task 1: API Client Functions (`frontend/src/api/client.ts`)

Added a `// --- Phase 25-02: AniDB Absolute Episode Order ---` section with three typed async functions:

- `updateSeriesSettings(seriesId, settings)` — PUT `/library/series/<id>/settings` with `{ absolute_order: bool }`
- `getAnidbMappingStatus()` — GET `/anidb-mapping/status`, returns `{ last_sync?, entry_count?, status }`
- `refreshAnidbMapping()` — POST `/anidb-mapping/refresh`, returns `{ success, message? }`

### Task 2: React Query Hooks (`frontend/src/hooks/useApi.ts`)

Added three hooks following the existing patterns:

- `useUpdateSeriesSettings()` — mutation that invalidates `['series', seriesId]` on success
- `useAnidbMappingStatus()` — query with 60s staleTime on key `['anidb-mapping-status']`
- `useRefreshAnidbMapping()` — mutation that invalidates `['anidb-mapping-status']` on success

### Task 3: Series Detail UI (`frontend/src/pages/SeriesDetail.tsx`)

**Type update:** Added `absolute_order?: boolean` to `SeriesDetail` interface in `frontend/src/lib/types.ts`.

**Icon:** Added `Database` to lucide-react imports.

**Hook calls in `SeriesDetailPage`:**
- `useUpdateSeriesSettings()` — mutation for toggling the setting
- `useAnidbMappingStatus()` — fetches last sync time and entry count
- `useRefreshAnidbMapping()` — mutation for triggering a sync
- `handleToggleAbsoluteOrder(enabled)` callback with toast feedback
- `handleRefreshAnidbMapping()` callback with toast feedback

**UI elements** added in the language info chip row (alongside the Glossary button):

1. **"Absolute order" toggle button** — always visible; highlighted in accent color when active; shows a spinner while saving; tooltip explains the anime use case. Clicking it toggles the setting via PUT.

2. **"Refresh AniDB" button** — conditionally rendered only when `absolute_order` is `true`; tooltip shows last sync timestamp and entry count from `useAnidbMappingStatus()`; shows spinner while refreshing.

## Constraints Verified

- Zero TypeScript errors (`npx tsc --noEmit` clean)
- Phase 22-02 Auto-Sync button logic is untouched
- Existing imports and hook usage unchanged; only additions made
- Immutable patterns used throughout (no state mutation)
