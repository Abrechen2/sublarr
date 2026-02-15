---
phase: 06-forced-signs-subs
plan: 03
subsystem: api, frontend, ui
tags: [forced-subs, language-profiles, wanted-filter, react, flask, typescript, status-badge]

# Dependency graph
requires:
  - phase: 06-forced-signs-subs
    plan: 01
    provides: "forced_preference on language_profiles, subtitle_type on wanted_items, forced_detection.py"
  - phase: 06-forced-signs-subs
    plan: 02
    provides: "Scanner forced item creation, provider forced classification, download-only pipeline"
provides:
  - "Profile API endpoints accept and return forced_preference with validation"
  - "Wanted API supports subtitle_type filter parameter"
  - "Wanted summary includes by_subtitle_type breakdown"
  - "Settings UI has forced subtitles dropdown in language profile editor"
  - "Wanted UI shows SubtitleTypeBadge on forced items and subtitle_type filter"
  - "SubtitleTypeBadge reusable component for forced subtitle indication"
affects: [frontend, routes, settings, wanted-page]

# Tech tracking
tech-stack:
  added: []
  patterns: ["conditional badge rendering (only show for non-default values)", "server-side subtitle_type filter with client-side filter buttons"]

key-files:
  created: []
  modified:
    - backend/routes/profiles.py
    - backend/routes/wanted.py
    - backend/db/wanted.py
    - frontend/src/lib/types.ts
    - frontend/src/api/client.ts
    - frontend/src/hooks/useApi.ts
    - frontend/src/components/shared/StatusBadge.tsx
    - frontend/src/pages/Settings.tsx
    - frontend/src/pages/Wanted.tsx

key-decisions:
  - "Profile API validates forced_preference at route level (400 response) before passing to db layer"
  - "SubtitleTypeBadge only renders for 'forced' type -- 'full' returns null to avoid UI clutter"
  - "Subtitle type filter buttons only shown when forcedCount > 0 to keep UI clean for users without forced subs"
  - "Profile list cards show forced preference only when not 'disabled' to reduce visual noise"
  - "get_wanted_by_subtitle_type handles NULL subtitle_type values by defaulting to 'full'"

patterns-established:
  - "Conditional filter UI: only render filter group when relevant data exists (forcedCount > 0)"
  - "Badge suppression for default values: SubtitleTypeBadge returns null for 'full' type"

# Metrics
duration: 11min
completed: 2026-02-15
---

# Phase 6 Plan 03: Forced Subtitle API & Frontend UI Summary

**Forced subtitle preference in language profile Settings UI with forced badge display and subtitle_type filter on Wanted page, plus profile and wanted API endpoint extensions**

## Performance

- **Duration:** 11 min
- **Started:** 2026-02-15T17:46:04Z
- **Completed:** 2026-02-15T17:56:41Z
- **Tasks:** 2
- **Files modified:** 9

## Accomplishments
- Profile API create/update endpoints accept and validate forced_preference field with 400 error on invalid values
- Wanted list API supports subtitle_type query parameter for server-side filtering
- Wanted summary includes by_subtitle_type counts for forced/full breakdown
- Settings page has forced subtitles dropdown with contextual helper text per option
- Wanted page has subtitle_type filter buttons and displays SubtitleTypeBadge on forced items
- SubtitleTypeBadge exported from StatusBadge module as reusable forced indicator

## Task Commits

Each task was committed atomically:

1. **Task 1: Profile and Wanted API endpoints** - `9595f3a` (feat)
2. **Task 2: Frontend types, Settings forced preference, Wanted forced badges** - `b0b0ded` (feat)

## Files Created/Modified
- `backend/routes/profiles.py` - forced_preference in create/update endpoints with validation
- `backend/routes/wanted.py` - subtitle_type filter parameter on GET /wanted, by_subtitle_type in summary
- `backend/db/wanted.py` - subtitle_type filter in get_wanted_items, new get_wanted_by_subtitle_type function
- `frontend/src/lib/types.ts` - forced_preference on LanguageProfile, subtitle_type on WantedItem, by_subtitle_type on WantedSummary
- `frontend/src/api/client.ts` - getWantedItems accepts subtitleType parameter
- `frontend/src/hooks/useApi.ts` - useWantedItems passes subtitleType to query
- `frontend/src/components/shared/StatusBadge.tsx` - SubtitleTypeBadge component for forced badge
- `frontend/src/pages/Settings.tsx` - Forced subtitles dropdown in profile editor with helper text
- `frontend/src/pages/Wanted.tsx` - Subtitle type filter buttons and SubtitleTypeBadge in table rows

## Decisions Made
- Route-level validation for forced_preference returns 400 before db call (defense in depth with db-level validation)
- SubtitleTypeBadge uses teal accent color (matches *arr-style theme) for forced badge
- Filter buttons conditionally rendered only when forced items exist to avoid cluttering UI for users without forced subs
- Profile display hides forced preference when set to "disabled" (the default) to reduce noise

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Phase 6 complete -- all 3 plans executed (data model + detection, scanner + search pipeline, API + frontend UI)
- End-to-end forced subtitle flow: profile preference -> scanner -> wanted item -> search -> download -> save -> UI display
- All 60 unit tests pass with no regressions
- Frontend builds, type checks, and lints cleanly (no new errors)

## Self-Check: PASSED

- All 9 modified files verified on disk
- Commit `9595f3a` (Task 1) verified in git log
- Commit `b0b0ded` (Task 2) verified in git log
- 60/60 unit tests passing
- Frontend TypeScript check passes
- Frontend build succeeds

---
*Phase: 06-forced-signs-subs*
*Completed: 2026-02-15*
