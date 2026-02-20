---
phase: 03-media-server-abstraction
plan: 01
subsystem: api
tags: [mediaserver, abc, jellyfin, plex, kodi, plexapi, json-rpc, circuit-breaker]

# Dependency graph
requires:
  - phase: 00-architecture-refactoring
    provides: "circuit_breaker.py, db/config.py config_entries pattern"
  - phase: 02-translation-multi-backend
    provides: "TranslationBackend ABC and TranslationManager singleton pattern to mirror"
provides:
  - "MediaServer ABC with health_check, refresh_item, refresh_library, apply_path_mapping"
  - "MediaServerManager singleton with register, load_instances, refresh_all, health_check_all"
  - "JellyfinEmbyServer backend (migrated from jellyfin_client.py)"
  - "PlexServer backend (plexapi library, lazy connection, file path search)"
  - "KodiServer backend (JSON-RPC 2.0, directory-scoped scan)"
affects: [03-02-PLAN, translator.py integration, routes/mediaservers.py, frontend settings]

# Tech tracking
tech-stack:
  added: [PlexAPI>=4.18.0]
  patterns: [MediaServer ABC, MediaServerManager singleton, JSON array config in config_entries, per-instance circuit breakers]

key-files:
  created:
    - backend/mediaserver/__init__.py
    - backend/mediaserver/base.py
    - backend/mediaserver/jellyfin.py
    - backend/mediaserver/plex.py
    - backend/mediaserver/kodi.py
  modified:
    - backend/requirements.txt

key-decisions:
  - "JellyfinEmbyServer is a single class covering both Jellyfin and Emby (server_type config field)"
  - "Config stored as JSON array in single media_servers_json config_entries key (not per-type keys)"
  - "refresh_all dispatches to ALL servers (not fallback chain like translation)"
  - "PlexServer uses lazy connection (no plexapi.PlexServer in __init__)"
  - "KodiServer uses directory-scoped VideoLibrary.Scan (not per-item ID lookup)"
  - "plexapi import guarded with try/except -- class loads even without plexapi installed"

patterns-established:
  - "MediaServer ABC: same config_fields declarative pattern as TranslationBackend"
  - "MediaServerManager: multi-instance config via JSON array, fire-and-forget refresh_all"
  - "Path mapping: apply_path_mapping in ABC base class, reusable by all backends"

# Metrics
duration: 4min
completed: 2026-02-15
---

# Phase 3 Plan 01: Media Server Abstraction Layer Summary

**MediaServer ABC with Manager singleton, JellyfinEmby/Plex/Kodi backends, and PlexAPI dependency -- mirrors TranslationBackend pattern for multi-server refresh dispatch**

## Performance

- **Duration:** 4 min
- **Started:** 2026-02-15T14:28:07Z
- **Completed:** 2026-02-15T14:32:15Z
- **Tasks:** 2
- **Files modified:** 6

## Accomplishments
- MediaServer ABC defines health_check, refresh_item, refresh_library, get_config_fields, and apply_path_mapping contract
- MediaServerManager singleton registers 3 types, loads instances from JSON config, dispatches refresh_all to all servers with circuit breakers
- JellyfinEmbyServer migrated from jellyfin_client.py preserving all retry/rate-limit logic
- PlexServer uses plexapi with lazy connection, file path search via Media__Part__file__startswith filter, section-aware refresh
- KodiServer uses raw JSON-RPC 2.0 with optional Basic Auth and directory-scoped VideoLibrary.Scan

## Task Commits

Each task was committed atomically:

1. **Task 1: MediaServer ABC, Manager, and JellyfinEmby backend** - `cc100ca` (feat)
2. **Task 2: Plex and Kodi backends + requirements.txt** - `34dc3b6` (feat)

## Files Created/Modified
- `backend/mediaserver/base.py` - MediaServer ABC with RefreshResult dataclass and apply_path_mapping
- `backend/mediaserver/__init__.py` - MediaServerManager singleton with register, load_instances, refresh_all, health_check_all
- `backend/mediaserver/jellyfin.py` - JellyfinEmbyServer with full retry/rate-limit logic from jellyfin_client.py
- `backend/mediaserver/plex.py` - PlexServer with lazy plexapi connection, section-based file path search
- `backend/mediaserver/kodi.py` - KodiServer with JSON-RPC 2.0, directory-scoped scan, optional Basic Auth
- `backend/requirements.txt` - Added PlexAPI>=4.18.0

## Decisions Made
- JellyfinEmbyServer keeps Jellyfin and Emby as single class with server_type field (APIs are 95% identical)
- Media server config stored as JSON array in single config_entries key (media_servers_json) supporting multiple instances per type
- Manager uses refresh_all (all-notify) pattern, not fallback chain -- every configured server gets the refresh
- PlexServer lazy-connects (no plexapi.PlexServer in constructor) to avoid blocking on misconfigured instances
- KodiServer prefers directory-scoped VideoLibrary.Scan over per-item ID lookup (simpler, more reliable)
- plexapi guarded with try/except ImportError so PlexServer class loads even without plexapi installed

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- MediaServer package complete and self-contained -- ready for Plan 02 (wiring into app, routes, frontend)
- All 3 backend types importable and registered in the singleton manager
- jellyfin_client.py still exists (not deleted) -- Plan 02 will handle migration/deprecation
- No blockers for Plan 02

## Self-Check: PASSED

All 7 files verified present. Both commits (cc100ca, 34dc3b6) found in git log.

---
*Phase: 03-media-server-abstraction*
*Completed: 2026-02-15*
