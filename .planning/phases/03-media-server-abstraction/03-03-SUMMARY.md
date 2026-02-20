---
phase: 03-media-server-abstraction
plan: 03
subsystem: ui
tags: [mediaserver, frontend, settings, onboarding, react, typescript, tanstack-query]

# Dependency graph
requires:
  - phase: 03-media-server-abstraction
    plan: 02
    provides: "mediaservers API blueprint with 5 endpoints (types, instances, test, health)"
  - phase: 02-translation-multi-backend
    plan: 05
    provides: "TranslationBackendsTab collapsible card pattern, BackendConfigField interface"
provides:
  - "MediaServerType, MediaServerInstance, MediaServerHealthResult, MediaServerTestResult TypeScript interfaces"
  - "API client functions for all 5 media server endpoints"
  - "React Query hooks: useMediaServerTypes, useMediaServerInstances, useSaveMediaServerInstances, useTestMediaServer, useMediaServerHealth"
  - "Media Servers tab in Settings replacing legacy Jellyfin tab"
  - "Media server step in onboarding wizard (step 5 of 6)"
affects: [frontend-tests, media-server-tests, phase-3-completion]

# Tech tracking
tech-stack:
  added: []
  patterns: [MediaServersTab with collapsible cards, dynamic config fields from server types, onboarding media server step]

key-files:
  created: []
  modified:
    - frontend/src/lib/types.ts
    - frontend/src/api/client.ts
    - frontend/src/hooks/useApi.ts
    - frontend/src/pages/Settings.tsx
    - frontend/src/pages/Onboarding.tsx

key-decisions:
  - "MediaServersTab follows same collapsible card pattern as TranslationBackendsTab for UI consistency"
  - "Add Server uses dropdown menu (not modal) for quick type selection"
  - "Onboarding media server step is optional -- Skip button advances without saving"
  - "Onboarding loads types lazily on step 4 entry to avoid unnecessary API calls"
  - "Jellyfin tab and FIELDS entries fully removed -- no backward compatibility shim needed"

patterns-established:
  - "MediaServersTab: full-array save pattern (PUT with complete instance array, not per-instance updates)"
  - "Onboarding media server: lazy type loading + local state + save-on-next for optimal UX"

# Metrics
duration: 8min
completed: 2026-02-15
---

# Phase 3 Plan 03: Media Server Frontend UI Summary

**Media Servers settings tab with collapsible multi-server cards, dynamic config forms, test buttons, and onboarding wizard step -- replacing legacy Jellyfin-only tab**

## Performance

- **Duration:** 8 min
- **Started:** 2026-02-15T14:44:22Z
- **Completed:** 2026-02-15T14:52:31Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments
- TypeScript interfaces, API client functions, and React Query hooks for all 5 media server endpoints
- Media Servers settings tab with Add Server dropdown, collapsible instance cards, dynamic config forms, test connection buttons, enable/disable toggles, and path mapping fields
- Onboarding wizard gains optional media server configuration step with type selection buttons, quick config, and test functionality
- Jellyfin tab, FIELDS entries, and test connection entry fully removed from Settings

## Task Commits

Each task was committed atomically:

1. **Task 1: TypeScript types, API client functions, and React Query hooks** - `c2bb003` (feat)
2. **Task 2: Media Servers settings tab and onboarding update** - `457a130` (feat)

## Files Created/Modified
- `frontend/src/lib/types.ts` - MediaServerType, MediaServerInstance, MediaServerHealthResult, MediaServerTestResult interfaces
- `frontend/src/api/client.ts` - 5 API client functions for media server CRUD, test, and health
- `frontend/src/hooks/useApi.ts` - 5 React Query hooks with appropriate stale times
- `frontend/src/pages/Settings.tsx` - MediaServersTab component replacing Jellyfin tab, with Add Server dropdown, collapsible cards, dynamic config forms
- `frontend/src/pages/Onboarding.tsx` - Optional media server step (step 5 of 6) with type selection, config fields, test buttons

## Decisions Made
- MediaServersTab follows the same collapsible card pattern as TranslationBackendsTab for visual consistency across Settings
- Add Server uses a dropdown menu (not a modal dialog) for quick one-click type selection
- Onboarding media server step is optional with Skip/Save & Next button text adapting based on whether instances exist
- Media server types are loaded lazily in onboarding (only when step 4 is reached) to avoid unnecessary API calls on earlier steps
- Jellyfin tab, FIELDS entries, and hasTestConnection entry fully removed since media servers have their own dedicated tab

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Phase 3 (Media Server Abstraction) is now complete -- all 3 plans executed
- Full stack: ABC + backends (Plan 01), API routes + wiring (Plan 02), frontend UI (Plan 03)
- Users can configure Jellyfin/Emby, Plex, and Kodi media servers from Settings or Onboarding
- No blockers for Phase 4 or subsequent phases

## Self-Check: PASSED

All 5 files verified present. Both commits (c2bb003, 457a130) found in git log.

---
*Phase: 03-media-server-abstraction*
*Completed: 2026-02-15*
