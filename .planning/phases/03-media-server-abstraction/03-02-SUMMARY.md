---
phase: 03-media-server-abstraction
plan: 02
subsystem: api
tags: [mediaserver, blueprint, routes, translator, health, config-migration, wiring]

# Dependency graph
requires:
  - phase: 03-media-server-abstraction
    plan: 01
    provides: "MediaServer ABC, MediaServerManager singleton, JellyfinEmby/Plex/Kodi backends"
  - phase: 00-architecture-refactoring
    provides: "Blueprint route pattern, config_entries DB, circuit_breaker.py"
provides:
  - "mediaservers API blueprint with 5 endpoints (types, instances GET/PUT, test, health)"
  - "translator.py _notify_integrations rewired to MediaServerManager.refresh_all"
  - "Health endpoint reporting all media server instance statuses"
  - "Config change invalidation triggering media server manager reload"
  - "Legacy jellyfin_url/jellyfin_api_key auto-migration to media_servers_json"
  - "App startup initialization of media server manager (3 types registered)"
affects: [frontend-settings, 03-03-PLAN, media-server-tests]

# Tech tracking
tech-stack:
  added: []
  patterns: [mediaservers blueprint, legacy config migration, manager invalidation on config change]

key-files:
  created:
    - backend/routes/mediaservers.py
  modified:
    - backend/routes/__init__.py
    - backend/config.py
    - backend/translator.py
    - backend/routes/system.py
    - backend/routes/config.py
    - backend/app.py

key-decisions:
  - "Mask api_key/token/password fields in GET /mediaservers/instances (show last 4 chars only)"
  - "PUT /mediaservers/instances saves full array then invalidate+reload manager (not partial updates)"
  - "POST /mediaservers/test creates temporary instance without persisting (for UI Test button)"
  - "Legacy jellyfin_url auto-migration stores back to config_entries as one-time migration"
  - "jellyfin_client.py not deleted yet -- preserved for existing tests, no production code imports it"

patterns-established:
  - "Manager invalidation pattern: invalidate_media_server_manager() + get_media_server_manager().load_instances() for config reload"
  - "Health endpoint aggregation: per-instance status rolled up into media_servers summary"

# Metrics
duration: 6min
completed: 2026-02-15
---

# Phase 3 Plan 02: Media Server App Wiring Summary

**MediaServer blueprint with 5 API endpoints, translator.py rewired to multi-server refresh_all, health endpoint aggregating all media server statuses, and legacy Jellyfin config auto-migration**

## Performance

- **Duration:** 6 min
- **Started:** 2026-02-15T14:35:18Z
- **Completed:** 2026-02-15T14:41:27Z
- **Tasks:** 2
- **Files modified:** 7

## Accomplishments
- Created mediaservers API blueprint with types, instances GET/PUT, test, and health endpoints
- Rewired translator.py _notify_integrations to use MediaServerManager.refresh_all instead of direct jellyfin_client
- Replaced Jellyfin-specific health check with multi-server aggregated health reporting in system.py
- Added media server manager initialization at app startup (3 types: jellyfin, plex, kodi)
- Config changes now invalidate and reload media server instances automatically
- Legacy jellyfin_url + jellyfin_api_key auto-migrates to media_servers_json on first read

## Task Commits

Each task was committed atomically:

1. **Task 1: Media servers API blueprint + config migration** - `f9c50c3` (feat)
2. **Task 2: Rewire translator, health, config to use MediaServerManager** - `7af0b81` (feat)

## Files Created/Modified
- `backend/routes/mediaservers.py` - Blueprint with 5 endpoints for media server management API
- `backend/routes/__init__.py` - Registered mediaservers blueprint (11th blueprint)
- `backend/config.py` - Added media_servers_json setting + get_media_server_instances() with legacy migration
- `backend/translator.py` - _notify_integrations now uses MediaServerManager.refresh_all
- `backend/routes/system.py` - Health endpoint reports media_servers status (replaces jellyfin-only)
- `backend/routes/config.py` - Config save/import invalidates media server manager instead of jellyfin_client
- `backend/app.py` - Media server manager initialized at startup before blueprint registration

## Decisions Made
- Mask sensitive fields (api_key, token, password) in GET /instances response -- show only last 4 chars
- PUT /instances replaces entire array (not partial update) for simplicity and consistency
- POST /test creates a temporary, non-persisted instance for the UI "Test Connection" button
- Legacy Jellyfin config migration is best-effort (try/except around save_config_entry)
- jellyfin_client.py intentionally not deleted yet -- tests may still reference it

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Media server abstraction fully wired into the app -- ready for frontend settings UI
- All 3 backend types accessible via API: GET /api/v1/mediaservers/types returns jellyfin, plex, kodi
- Config changes propagate correctly through invalidation + reload cycle
- jellyfin_client.py still exists but no production code imports it -- cleanup in future gap closure
- No blockers for Phase 3 completion or Phase 4

## Self-Check: PASSED

All 7 files verified present. Both commits (f9c50c3, 7af0b81) found in git log.

---
*Phase: 03-media-server-abstraction*
*Completed: 2026-02-15*
