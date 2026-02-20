---
phase: 16-external-integrations
plan: 02
subsystem: api
tags: [plex, kodi, bazarr, compatibility, export, health-check, flask-blueprint]

# Dependency graph
requires:
  - phase: 15-api-key-mgmt-notifications-cleanup
    provides: "Bazarr migrator with generate_mapping_report, existing client health_check methods"
provides:
  - "Plex/Kodi subtitle naming and placement compatibility validation"
  - "Multi-format config export (Bazarr, Plex manifest, Kodi manifest, generic JSON)"
  - "ZIP export bundling for multi-format downloads"
  - "Integrations API blueprint with 10 endpoints"
affects: [16-external-integrations]

# Tech tracking
tech-stack:
  added: []
  patterns: ["Pure-function validation module (compat_checker)", "Strategy pattern for export formats", "Lazy-import blueprint pattern"]

key-files:
  created:
    - backend/compat_checker.py
    - backend/export_manager.py
    - backend/routes/integrations.py
  modified:
    - backend/routes/__init__.py

key-decisions:
  - "ISO 639 codes hardcoded as sets (~50 common codes) instead of external dependency"
  - "Export manager uses lazy imports for all DB modules to avoid circular imports"
  - "Media path scan limited to 1000 subtitle files to prevent excessive scanning"
  - "Compat checker validates relative positioning not absolute paths (per research pitfall 6)"

patterns-established:
  - "Pure-function validation modules with no Flask dependencies for testability"
  - "Format strategy pattern: main dispatcher routes to format-specific exporters"

# Metrics
duration: 5min
completed: 2026-02-20
---

# Phase 16 Plan 02: Compat Checker, Export Manager, and Integrations API Summary

**Plex/Kodi subtitle compatibility validation, 4-format config export with ZIP bundling, and 10-endpoint integrations API blueprint**

## Performance

- **Duration:** 5 min
- **Started:** 2026-02-20T14:58:00Z
- **Completed:** 2026-02-20T15:03:00Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments
- Plex and Kodi subtitle naming/placement validation with ISO 639-1/2 language code checking
- Multi-format export producing Bazarr-compatible, Plex manifest, Kodi manifest, and generic JSON formats
- ZIP export bundling multiple formats into a single downloadable archive
- Integrations API blueprint with 10 endpoints covering compat check, extended health, export, and Bazarr mapping

## Task Commits

Each task was committed atomically:

1. **Task 1: Create compat_checker.py and export_manager.py modules** - `83960d3` (feat)
2. **Task 2: Create integrations API blueprint and register it** - `e36ede8` (feat)

## Files Created/Modified
- `backend/compat_checker.py` - Plex/Kodi subtitle naming and placement validation (pure functions)
- `backend/export_manager.py` - Multi-format config export with strategy pattern and ZIP bundling
- `backend/routes/integrations.py` - Flask Blueprint with 10 endpoints for all Phase 16 API features
- `backend/routes/__init__.py` - Added integrations_bp registration

## Decisions Made
- ISO 639-1 (~80 codes) and ISO 639-2 (~130 codes) hardcoded as Python sets for zero external dependencies
- Compat checker validates relative path positioning (not absolute paths) to handle Docker volume mappings correctly
- Export manager limits subtitle file scanning to 1000 files to prevent excessive I/O on large libraries
- Kodi checker accepts BCP 47 with underscore separator and English language names per Kodi 22+ docs
- Media server health endpoint uses extended_health_check if available, falls back to basic health_check

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- All Phase 16 backend API endpoints are exposed and ready for frontend consumption
- Compat checker, export manager, and integrations blueprint are fully importable and functional
- Extended health checks leverage existing methods on SonarrClient, RadarrClient, JellyfinClient

---
*Phase: 16-external-integrations*
*Completed: 2026-02-20*

## Self-Check: PASSED

All files created, all commits verified.
