---
phase: 13-comparison-sync-health-check
plan: 02
subsystem: frontend, ui
tags: [react, codemirror, comparison, sync, typescript, tailwind]

# Dependency graph
requires:
  - phase: 13-comparison-sync-health-check
    plan: 01
    provides: "5 backend API endpoints (health-check, health-fix, advanced-sync, compare, quality-trends)"
  - phase: 11-subtitle-editor
    provides: "CodeMirror editor infrastructure (editor-theme, lang-ass, lang-srt, SubtitleEditorModal)"
provides:
  - "11 new TypeScript types for health-check, comparison, and sync"
  - "6 API client functions for health-check, comparison, and sync endpoints"
  - "5 React Query hooks for health-check, comparison, and sync"
  - "ComparisonPanel: read-only CodeMirror panel with syntax highlighting"
  - "ComparisonSelector: file picker for 2-4 subtitle files"
  - "SubtitleComparison: multi-panel CSS grid comparison view"
  - "SyncControls: offset/speed/framerate timing adjustment UI"
  - "SyncPreview: before/after timing table"
  - "SeriesDetail: Compare and Sync buttons per episode row"
affects: [13-03]

# Tech tracking
tech-stack:
  added: []
  patterns: [multi-panel-comparison, sync-preview-confirm, lazy-modal-loading]

key-files:
  created:
    - frontend/src/components/comparison/ComparisonPanel.tsx
    - frontend/src/components/comparison/ComparisonSelector.tsx
    - frontend/src/components/comparison/SubtitleComparison.tsx
    - frontend/src/components/sync/SyncControls.tsx
    - frontend/src/components/sync/SyncPreview.tsx
  modified:
    - frontend/src/lib/types.ts
    - frontend/src/api/client.ts
    - frontend/src/hooks/useApi.ts
    - frontend/src/pages/SeriesDetail.tsx

key-decisions:
  - "ComparisonPanel uses same CodeMirror setup (sublarrTheme, assLanguage, srtLanguage) as existing editor for consistency"
  - "Scroll synchronization uses debounced DOM scroll events (50ms) via useRef to prevent cascading"
  - "SyncControls has two-step apply: Preview first, then confirm with warning about file modification"
  - "Actions column widened from w-20 to w-32 to accommodate Compare and Sync buttons"
  - "Compare button only shown when episode has 2+ subtitle files; Sync only when at least 1 file"
  - "SubtitleComparison and SyncControls use React.lazy for code splitting"

patterns-established:
  - "ComparisonSelector toggle-button pattern: Set-based selection with max limit"
  - "Sync two-step confirmation: Preview button + Apply with inline confirm/cancel"
  - "Full-screen modal for comparison (like editor), centered modal for sync controls"

# Metrics
duration: 7min
completed: 2026-02-18
---

# Phase 13 Plan 02: Frontend Comparison & Sync Components Summary

**Multi-panel subtitle comparison view (2-4 panels with synchronized scrolling) and timing sync UI (offset/speed/framerate with preview) integrated into SeriesDetail episode rows**

## Performance

- **Duration:** 7 min
- **Started:** 2026-02-18T21:16:24Z
- **Completed:** 2026-02-18T21:23:56Z
- **Tasks:** 2
- **Files modified:** 9

## Accomplishments
- TypeScript types, API client functions, and React Query hooks for all Phase 13 frontend features (health-check, comparison, sync)
- Multi-panel subtitle comparison with CodeMirror syntax highlighting in responsive CSS grid layout
- Timing sync UI with three operation modes (offset/speed/framerate), preview table, and confirmation workflow
- SeriesDetail integration with Compare (Columns2) and Sync (Timer) icon buttons per episode row

## Task Commits

Each task was committed atomically:

1. **Task 1: TypeScript types, API client functions, and React Query hooks** - `9062f22` (feat)
2. **Task 2: Comparison + Sync components and SeriesDetail integration** - `ca688b0` (feat)

## Files Created/Modified
- `frontend/src/lib/types.ts` - 11 new interfaces for health-check, comparison, and sync
- `frontend/src/api/client.ts` - 6 new API functions (runHealthCheck, runHealthCheckBatch, applyHealthFix, getQualityTrends, compareSubtitles, advancedSync)
- `frontend/src/hooks/useApi.ts` - 5 new hooks (useHealthCheck, useHealthFix, useQualityTrends, useCompareSubtitles, useAdvancedSync)
- `frontend/src/components/comparison/ComparisonPanel.tsx` - Read-only CodeMirror panel with ASS/SRT highlighting
- `frontend/src/components/comparison/ComparisonSelector.tsx` - Toggle-button file picker for 2-4 files
- `frontend/src/components/comparison/SubtitleComparison.tsx` - Multi-panel grid with scroll sync
- `frontend/src/components/sync/SyncControls.tsx` - Three-tab sync UI with preview/apply workflow
- `frontend/src/components/sync/SyncPreview.tsx` - Before/after timing table with teal highlights
- `frontend/src/pages/SeriesDetail.tsx` - Compare and Sync buttons, modals, lazy loading

## Decisions Made
- ComparisonPanel reuses existing CodeMirror theme and language modules for visual consistency
- Scroll synchronization uses debounced (50ms) DOM event handlers to prevent feedback loops
- SyncControls employs two-step confirmation: user clicks Apply, sees warning, then confirms
- Actions column width increased from w-20 to w-32 for the additional Compare/Sync buttons
- Compare button conditionally rendered only when episode has 2+ subtitle files
- Lazy-loaded components (SubtitleComparison, SyncControls) for optimal code splitting

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- All comparison and sync UI components ready for Plan 03 (health dashboard and quality trends)
- Health-check types and hooks already included in this plan for Plan 03 consumption
- SeriesDetail has full Phase 13 feature integration (Compare, Sync, and existing Edit/Preview)

## Self-Check: PASSED

All 5 created files verified present. Both commit hashes (9062f22, ca688b0) verified in git log.

---
*Phase: 13-comparison-sync-health-check*
*Completed: 2026-02-18*
