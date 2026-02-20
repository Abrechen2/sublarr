---
phase: 15-api-key-mgmt-notifications-cleanup
plan: 01
subsystem: api
tags: [flask-blueprint, api-keys, bazarr-migration, config-export, config-import]

# Dependency graph
requires:
  - phase: 10-performance-scalability
    provides: "SQLAlchemy repositories, config convenience functions"
  - phase: 00-architecture-refactoring
    provides: "Blueprint-based route registration pattern"
provides:
  - "API key registry with 10 services (list, detail, test, rotate)"
  - "ZIP export of config + profiles + glossary"
  - "ZIP/CSV import with masked-secret skipping"
  - "Bazarr migration tool (YAML + INI config parsing, SQLite DB reader)"
affects: [15-02, 15-03, frontend-settings]

# Tech tracking
tech-stack:
  added: []
  patterns: ["Service registry pattern for API key management", "Lazy test function dispatch to avoid circular imports"]

key-files:
  created:
    - backend/routes/api_keys.py
    - backend/bazarr_migrator.py
  modified:
    - backend/routes/__init__.py

key-decisions:
  - "API_KEY_REGISTRY as dict mapping service->keys+test_fn for centralized key management"
  - "_mask_value shows first4+***+last4 (all *** if <=8 chars) for consistent secret masking"
  - "Test dispatch via _TEST_DISPATCH dict with lazy-imported functions to avoid circular imports"
  - "Bazarr config auto-detection: YAML first, then INI fallback when extension unknown"
  - "Bazarr DB opened read-only (file:...?mode=ro) with per-table try/except for version tolerance"

patterns-established:
  - "Service registry: central dict mapping service names to config keys and test functions"
  - "Dual-format parser: try primary format, fallback to secondary, normalize to common structure"

# Metrics
duration: 4min
completed: 2026-02-20
---

# Phase 15 Plan 01: API Key Management Summary

**Centralized API key registry with 10-service CRUD, ZIP export/import, CSV import, and Bazarr dual-format migration tool**

## Performance

- **Duration:** 4 min
- **Started:** 2026-02-20T13:12:26Z
- **Completed:** 2026-02-20T13:16:25Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments
- API key registry blueprint with 7 endpoints covering list, detail, update, test, export, import, and Bazarr migration
- Service-specific cache invalidation on key rotation (Sonarr, Radarr, providers, notifier, translation)
- Bazarr migrator parses both YAML and INI config formats with auto-detection
- Bazarr DB reader extracts language profiles, blacklist, and arr connection settings with graceful table-missing handling

## Task Commits

Each task was committed atomically:

1. **Task 1: API Key Registry Blueprint** - `339c390` (feat)
2. **Task 2: Bazarr Migration Module** - `298abaf` (feat)

## Files Created/Modified
- `backend/routes/api_keys.py` - Flask Blueprint with 10-service API key registry, CRUD, test, export/import, Bazarr migration endpoints
- `backend/bazarr_migrator.py` - Dual-format Bazarr config parser (YAML/INI) and SQLite DB reader with preview/apply workflow
- `backend/routes/__init__.py` - Added api_keys_bp to blueprint registration list

## Decisions Made
- API_KEY_REGISTRY maps 10 services (sublarr, sonarr, radarr, opensubtitles, jimaku, subdl, tmdb, tvdb, deepl, apprise) to their config_entries keys and optional test functions
- _mask_value shows first 4 + "***" + last 4 chars (all "***" if value is 8 chars or fewer)
- Test dispatch uses named function references in _TEST_DISPATCH dict with lazy imports to avoid circular dependencies
- Bazarr config format auto-detected by extension first, then content (YAML tried before INI)
- Bazarr DB opened in read-only mode with each table read wrapped in try/except for version tolerance

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- API key management endpoints ready for frontend integration (Plan 15-02 or 15-03)
- Bazarr migration tool ready for UI workflow
- Export/import functionality complete for backup and migration use cases

---
*Phase: 15-api-key-mgmt-notifications-cleanup*
*Completed: 2026-02-20*

## Self-Check: PASSED
All files and commits verified.
