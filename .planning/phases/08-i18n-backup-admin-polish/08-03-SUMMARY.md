---
phase: 08-i18n-backup-admin-polish
plan: 03
subsystem: ui
tags: [react, recharts, statistics, charts, backup, subtitle-tools, logs, rotation, settings-tabs]

# Dependency graph
requires:
  - phase: 08-i18n-backup-admin-polish
    provides: "Backend APIs for statistics, backup, tools, log rotation (Plan 02)"
provides:
  - "Statistics page with 4 Recharts chart types and time-range filter"
  - "Backup tab in Settings with create/list/download/restore controls"
  - "Subtitle Tools tab in Settings with HI removal, timing adjustment, common fixes, preview"
  - "Logs page download button and rotation config section"
affects: [08-04-openapi-docs, 08-05-final-polish]

# Tech tracking
tech-stack:
  added: [recharts v3]
  patterns: [chart component pattern with CSS custom properties, collapsible rotation config, file upload restore]

key-files:
  created:
    - frontend/src/pages/Statistics.tsx
    - frontend/src/components/charts/TranslationChart.tsx
    - frontend/src/components/charts/ProviderChart.tsx
    - frontend/src/components/charts/FormatChart.tsx
    - frontend/src/components/charts/DownloadChart.tsx
  modified:
    - frontend/src/pages/Settings.tsx
    - frontend/src/pages/Logs.tsx
    - frontend/src/hooks/useApi.ts
    - frontend/src/api/client.ts
    - frontend/src/lib/types.ts
    - frontend/src/App.tsx
    - frontend/src/components/layout/Sidebar.tsx
    - frontend/src/i18n/locales/en/settings.json
    - frontend/src/i18n/locales/de/settings.json
    - backend/routes/system.py

key-decisions:
  - "Recharts v3 for chart library -- built-in TypeScript support, responsive containers, CSS variable theming"
  - "Statistics endpoint enhanced with by_format aggregation from daily_stats.by_format_json column"
  - "Backend downloads_by_provider normalized to use provider_name key (was provider)"
  - "BackupTab uses file upload for restore (FormData) -- no server-side file path needed"
  - "SubtitleToolsTab uses inline tool forms rather than modal dialogs for simplicity"
  - "Logs rotation config is collapsible section at bottom to avoid cluttering the log viewer"
  - "PieLabelRenderProps type used for Recharts v3 pie chart label compatibility"

patterns-established:
  - "Chart component pattern: data prop + ResponsiveContainer + CSS custom properties for theming"
  - "Export dropdown pattern: button + absolute positioned menu with format options"
  - "File upload restore pattern: hidden input + visible button + filename display + confirm button"

# Metrics
duration: 42min
completed: 2026-02-15
---

# Phase 8 Plan 3: Frontend UI for Statistics, Backup, Tools, and Logs Summary

**Statistics page with Recharts charts and time-range filter, Backup and Subtitle Tools Settings tabs, and Logs page with download and rotation config**

## Performance

- **Duration:** 42 min
- **Started:** 2026-02-15T20:21:53Z
- **Completed:** 2026-02-15T21:04:31Z
- **Tasks:** 2
- **Files modified:** 15

## Accomplishments
- Statistics page with 4 chart types (Translation area, Provider bar, Format pie, Download horizontal bar) using Recharts v3
- Time-range filter (7d/30d/90d/365d) controlling all charts with 60s auto-refresh
- JSON/CSV export via dropdown triggering browser download
- Sidebar navigation link with BarChart3 icon in System group
- Backup tab in Settings: create ZIP, list backups, download, restore from file upload
- Subtitle Tools tab: HI removal, timing adjustment (ms offset), common fixes (4 checkbox options), subtitle preview with ASS/SRT syntax highlighting
- Logs page: download button in toolbar, collapsible rotation config section with max size and backup count inputs

## Task Commits

Each task was committed atomically:

1. **Task 1: Statistics page with Recharts charts, time-range filter, and export** - `4329104` (feat)
2. **Task 2: Backup Settings tab, Subtitle Tools Settings tab, Logs page enhancements** - `1336fed` (feat)

## Files Created/Modified
- `frontend/src/pages/Statistics.tsx` - Statistics page with 4 charts, range filter, export dropdown
- `frontend/src/components/charts/TranslationChart.tsx` - Daily translations area chart
- `frontend/src/components/charts/ProviderChart.tsx` - Provider usage bar chart
- `frontend/src/components/charts/FormatChart.tsx` - ASS vs SRT format pie chart
- `frontend/src/components/charts/DownloadChart.tsx` - Downloads by provider horizontal bar chart
- `frontend/src/pages/Settings.tsx` - Added BackupTab and SubtitleToolsTab components, TABS array, tab rendering
- `frontend/src/pages/Logs.tsx` - Added download button, rotation config section
- `frontend/src/hooks/useApi.ts` - Added 10 new hooks for statistics, backup, tools, rotation
- `frontend/src/api/client.ts` - Added 10 new API functions
- `frontend/src/lib/types.ts` - Added StatisticsData, FullBackupInfo, SubtitleToolResult, LogRotationConfig
- `frontend/src/App.tsx` - Added /statistics route
- `frontend/src/components/layout/Sidebar.tsx` - Added Statistics nav link with BarChart3 icon
- `frontend/src/i18n/locales/en/settings.json` - Added backup and subtitle_tools tab keys
- `frontend/src/i18n/locales/de/settings.json` - Added backup and subtitle_tools tab keys (German)
- `backend/routes/system.py` - Added by_format aggregation to statistics endpoint, fixed provider_name key

## Decisions Made
- Used Recharts v3 (latest) which has stricter TypeScript types requiring PieLabelRenderProps and explicit type handling for tooltips
- Enhanced backend statistics endpoint to include by_format totals aggregated from daily_stats.by_format_json -- needed for the Format pie chart (deviation from frontend-only plan)
- Fixed backend downloads_by_provider to use consistent "provider_name" key instead of "provider"
- Backup restore uses FormData file upload rather than server-path approach for security
- Subtitle Tools shows result status inline per tool card rather than a global notification

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] Added by_format aggregation to backend statistics endpoint**
- **Found during:** Task 1 (Statistics page -- FormatChart needed format data)
- **Issue:** Statistics endpoint did not expose by_format_json data from daily_stats table
- **Fix:** Added by_format_totals aggregation from daily_stats.by_format_json, included in response
- **Files modified:** backend/routes/system.py
- **Verification:** TypeScript build passes, FormatChart renders with real data
- **Committed in:** 4329104 (Task 1 commit)

**2. [Rule 1 - Bug] Fixed downloads_by_provider key name inconsistency**
- **Found during:** Task 1 (Mapping backend response to TypeScript types)
- **Issue:** Backend used "provider" key but TypeScript type expected "provider_name"
- **Fix:** Changed backend to use "provider_name" key for consistency
- **Files modified:** backend/routes/system.py
- **Verification:** Frontend properly reads provider_name from API response
- **Committed in:** 4329104 (Task 1 commit)

**3. [Rule 3 - Blocking] Fixed corrupted node_modules from parallel npm install**
- **Found during:** Task 1 (Build step -- redux module missing package.json)
- **Issue:** Parallel npm install processes corrupted redux directory, missing package.json
- **Fix:** Removed corrupted redux directory, ran npm install again
- **Files modified:** node_modules only (not committed)
- **Verification:** npm run build succeeds
- **Committed in:** N/A (node_modules not tracked)

---

**Total deviations:** 3 auto-fixed (1 missing critical, 1 bug, 1 blocking)
**Impact on plan:** All auto-fixes necessary for correctness. Backend change was minimal (4 lines). No scope creep.

## Issues Encountered
- Recharts v3 has stricter TypeScript types than v2: PieLabelRenderProps required for pie chart labels, tooltip formatter needs `unknown` parameter types instead of concrete types. Fixed with proper type annotations.
- npm install race condition from parallel background processes corrupted node_modules/redux. Fixed by removing and reinstalling.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- All 4 success criteria met: Statistics page (ADMN-01), Backup UI (BKUP-03), Log improvements (ADMN-02), Subtitle Tools (ADMN-04)
- Frontend build passes with no TypeScript errors
- All chart components use CSS custom properties for theme compatibility (dark/light mode)
- 10 new React Query hooks provide complete API coverage for Plans 02 backend endpoints

## Self-Check: PASSED

- FOUND: frontend/src/pages/Statistics.tsx
- FOUND: frontend/src/components/charts/TranslationChart.tsx
- FOUND: frontend/src/components/charts/ProviderChart.tsx
- FOUND: frontend/src/components/charts/FormatChart.tsx
- FOUND: frontend/src/components/charts/DownloadChart.tsx
- FOUND: commit 4329104
- FOUND: commit 1336fed

---
*Phase: 08-i18n-backup-admin-polish*
*Completed: 2026-02-15*
