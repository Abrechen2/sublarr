---
phase: 09-openapi-release-preparation
plan: 04
subsystem: api, ui
tags: [openapi, yaml, docstrings, apispec, flask, react, scheduler, tasks, i18n]

# Dependency graph
requires:
  - phase: 09-01
    provides: OpenAPI infrastructure (apispec, register_all_paths, 65 documented paths)
provides:
  - Full OpenAPI coverage: 120 paths across 15 tags
  - /api/v1/tasks endpoint for scheduler task status
  - Tasks page (frontend) with scheduler status and Run Now controls
affects: [openapi-consumers, swagger-ui, api-documentation]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "YAML docstring pattern: human summary + --- + OpenAPI YAML block per endpoint"
    - "Tasks page: useTasks + useTriggerTask with task-to-endpoint mapping"

key-files:
  created:
    - frontend/src/pages/Tasks.tsx
  modified:
    - backend/routes/profiles.py
    - backend/routes/blacklist.py
    - backend/routes/hooks.py
    - backend/routes/standalone.py
    - backend/routes/mediaservers.py
    - backend/routes/whisper.py
    - backend/routes/plugins.py
    - backend/routes/webhooks.py
    - backend/routes/tools.py
    - backend/routes/system.py
    - frontend/src/lib/types.ts
    - frontend/src/api/client.ts
    - frontend/src/hooks/useApi.ts
    - frontend/src/App.tsx
    - frontend/src/components/layout/Sidebar.tsx
    - frontend/src/i18n/locales/en/common.json
    - frontend/src/i18n/locales/de/common.json

key-decisions:
  - "Created dedicated /api/v1/tasks endpoint (vs reusing /health/detailed) for cleaner frontend consumption"
  - "useTriggerTask maps task names to trigger endpoints (wanted_scan -> /wanted/refresh, wanted_search -> /wanted/search-all, backup -> /database/backup)"
  - "ListChecks icon for Tasks nav entry, positioned between Statistics and Logs in System group"

patterns-established:
  - "Task trigger pattern: mutation hook with task-name-to-API-endpoint mapping"

# Metrics
duration: 16min
completed: 2026-02-16
---

# Phase 9 Plan 4: OpenAPI Remaining Blueprints + Tasks Page Summary

**Full OpenAPI coverage (120 paths, 15 tags) across all 15 blueprints plus Tasks page with scheduler status cards and Run Now controls**

## Performance

- **Duration:** 16 min
- **Started:** 2026-02-16T19:59:30Z
- **Completed:** 2026-02-16T20:15:20Z
- **Tasks:** 2
- **Files modified:** 18

## Accomplishments
- Documented all remaining 9 blueprints with YAML docstrings: profiles (13 endpoints), blacklist (7), hooks (20), standalone (14), mediaservers (5), whisper (12), plugins (4), webhooks (2), tools (4)
- OpenAPI spec now has 120 paths and all 15 tags (System, Translate, Providers, Wanted, Library, Config, Profiles, Blacklist, Events, Standalone, MediaServers, Whisper, Plugins, Webhooks, Tools)
- Created Tasks page showing background scheduler tasks (Wanted Scan, Wanted Search, Database Backup) with status indicators, last/next run times, interval info, and Run Now buttons
- Added /api/v1/tasks backend endpoint with display_name, running, last_run, next_run, interval_hours, enabled fields

## Task Commits

Each task was committed atomically:

1. **Task 1: Add OpenAPI YAML docstrings to 9 remaining blueprints** - `997c62b` (feat)
2. **Task 2: Create Tasks page with scheduler status and controls** - `f473f1b` (feat)

## Files Created/Modified
- `backend/routes/profiles.py` - 13 endpoint YAML docstrings (Profiles tag)
- `backend/routes/blacklist.py` - 7 endpoint YAML docstrings (Blacklist tag)
- `backend/routes/hooks.py` - 20 endpoint YAML docstrings (Events tag)
- `backend/routes/standalone.py` - 14 endpoint YAML docstrings (Standalone tag)
- `backend/routes/mediaservers.py` - 5 endpoint YAML docstrings (MediaServers tag)
- `backend/routes/whisper.py` - 12 endpoint YAML docstrings (Whisper tag)
- `backend/routes/plugins.py` - 4 endpoint YAML docstrings (Plugins tag)
- `backend/routes/webhooks.py` - 2 endpoint YAML docstrings (Webhooks tag)
- `backend/routes/tools.py` - 4 endpoint YAML docstrings (Tools tag)
- `backend/routes/system.py` - New /tasks endpoint
- `frontend/src/pages/Tasks.tsx` - Tasks page with card layout, status indicators, Run Now buttons
- `frontend/src/lib/types.ts` - SchedulerTask and TasksResponse interfaces
- `frontend/src/api/client.ts` - getTasks() API function
- `frontend/src/hooks/useApi.ts` - useTasks and useTriggerTask hooks
- `frontend/src/App.tsx` - Lazy TasksPage import and /tasks route
- `frontend/src/components/layout/Sidebar.tsx` - Tasks nav link with ListChecks icon
- `frontend/src/i18n/locales/en/common.json` - English tasks i18n strings
- `frontend/src/i18n/locales/de/common.json` - German tasks i18n strings

## Decisions Made
- Created dedicated `/api/v1/tasks` endpoint rather than having frontend parse `/health/detailed` -- cleaner separation of concerns
- Task trigger mapping in frontend: wanted_scan -> POST /wanted/refresh, wanted_search -> POST /wanted/search-all, backup -> POST /database/backup
- Used ListChecks icon (lucide-react) for Tasks navigation, positioned between Statistics and Logs in System group

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Phase 9 complete: all 5 plans executed
- Full OpenAPI spec with 120 paths serves at /api/v1/openapi.json
- Tasks page provides operational visibility into background schedulers
- Ready for Phase 10 (Performance Optimization)

---
*Phase: 09-openapi-release-preparation*
*Completed: 2026-02-16*
