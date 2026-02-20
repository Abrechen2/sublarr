---
phase: 16-external-integrations
plan: 01
subsystem: api
tags: [sonarr, radarr, jellyfin, plex, kodi, bazarr, health-check, diagnostics, migration]

# Dependency graph
requires:
  - phase: 03-media-server-abstraction
    provides: PlexServer and KodiServer base classes with health_check()
  - phase: 15-api-key-mgmt-notifications-cleanup
    provides: Bazarr migration foundation (bazarr_migrator.py)
provides:
  - extended_health_check() on SonarrClient, RadarrClient, JellyfinClient, PlexServer, KodiServer
  - generate_mapping_report() for Bazarr database analysis
  - Deeper Bazarr DB reading (history, shows, movies tables)
affects: [16-external-integrations, settings-ui, system-health]

# Tech tracking
tech-stack:
  added: []
  patterns: [structured-diagnostic-report, column-discovery-via-pragma, sensitive-field-masking]

key-files:
  created: []
  modified:
    - backend/sonarr_client.py
    - backend/radarr_client.py
    - backend/jellyfin_client.py
    - backend/mediaserver/plex.py
    - backend/mediaserver/kodi.py
    - backend/bazarr_migrator.py

key-decisions:
  - "extended_health_check() added as new method -- existing health_check() completely untouched"
  - "Bazarr _get_table_info() uses PRAGMA table_info for schema-tolerant column discovery"
  - "generate_mapping_report() masks sensitive fields (apikey, password, token, secret) in sample rows"
  - "Kodi JSON-RPC version extracted via JSONRPC.Version method (major.minor.patch)"
  - "_read_history limited to 1000 rows DESC for performance on large Bazarr databases"

patterns-established:
  - "Structured diagnostic report: {connection, info, access, issues} pattern for all service clients"
  - "Column discovery before SELECT: _get_table_info() for version-tolerant Bazarr DB reading"

# Metrics
duration: 3min
completed: 2026-02-20
---

# Phase 16 Plan 01: External Integrations - Extended Health Checks & Bazarr Migration Summary

**Extended health checks on 5 service clients (Sonarr/Radarr/Jellyfin/Plex/Kodi) returning structured diagnostics, plus deeper Bazarr DB reading with generate_mapping_report()**

## Performance

- **Duration:** 3 min
- **Started:** 2026-02-20T14:58:02Z
- **Completed:** 2026-02-20T15:01:31Z
- **Tasks:** 2
- **Files modified:** 6

## Accomplishments
- All 5 service clients now have extended_health_check() returning structured dicts with connection, version/info, library access, and health issues
- Bazarr migrator extended with history, shows, movies table reading using schema-tolerant column discovery
- generate_mapping_report() provides detailed per-table inventory with row counts, columns, sample rows (secrets masked), and compatibility info
- preview_migration() enhanced with shows_count, movies_count, history_count

## Task Commits

Each task was committed atomically:

1. **Task 1: Add extended_health_check() to Sonarr, Radarr, Jellyfin, Plex, and Kodi clients** - `9ed5022` (feat)
2. **Task 2: Extend Bazarr migration with deeper DB reading and mapping report** - `abd9135` (feat)

## Files Created/Modified
- `backend/sonarr_client.py` - Added SonarrClient.extended_health_check() with connection, api_version, library_access, webhook_status, health_issues
- `backend/radarr_client.py` - Added RadarrClient.extended_health_check() with movie_count variant
- `backend/jellyfin_client.py` - Added JellyfinClient.extended_health_check() with server_info, library folders, pending restart/update detection
- `backend/mediaserver/plex.py` - Added PlexServer.extended_health_check() with friendly_name, version, library sections
- `backend/mediaserver/kodi.py` - Added KodiServer.extended_health_check() with JSON-RPC version, video sources
- `backend/bazarr_migrator.py` - Added _get_table_info, _read_history, _read_shows, _read_movies, generate_mapping_report; extended migrate_bazarr_db and preview_migration

## Decisions Made
- extended_health_check() is a pure addition -- no existing method signatures or return values changed
- Column discovery via PRAGMA table_info ensures forward compatibility with Bazarr schema changes
- Sensitive fields masked using a static set (_SENSITIVE_FIELDS) for consistent security in mapping reports
- Kodi version extracted from both Application.GetProperties and JSONRPC.Version for complete info

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Extended health checks ready for UI integration in subsequent plans
- Bazarr mapping report ready for settings UI consumption
- All 5 service clients provide structured diagnostics for troubleshooting integration issues

---
*Phase: 16-external-integrations*
*Completed: 2026-02-20*

## Self-Check: PASSED
All 6 modified files exist. Both task commits (9ed5022, abd9135) verified in git log.
