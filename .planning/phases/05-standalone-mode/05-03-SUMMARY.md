---
phase: 05-standalone-mode
plan: 03
subsystem: backend
tags: [watchdog, filesystem-watcher, standalone, scanner, wanted-pipeline, singleton]

requires:
  - phase: 05-standalone-mode
    provides: "DB tables (watched_folders, standalone_series, standalone_movies), config fields, parser, MetadataResolver"
provides:
  - "StandaloneManager singleton orchestrating watcher and scanner lifecycle"
  - "MediaFileWatcher with watchdog Observer, debounce, and file stability check"
  - "StandaloneScanner for full directory scans and wanted population"
  - "_scan_standalone() in WantedScanner for standalone items in wanted pipeline"
  - "app.py standalone initialization in create_app and _start_schedulers"
affects: [05-04-PLAN, 05-05-PLAN]

tech-stack:
  added: []
  patterns: [watchdog PatternMatchingEventHandler with per-path debounce timers, singleton manager with double-checked locking]

key-files:
  created:
    - backend/standalone/watcher.py
    - backend/standalone/scanner.py
  modified:
    - backend/standalone/__init__.py
    - backend/wanted_scanner.py
    - backend/app.py
    - backend/db/wanted.py

key-decisions:
  - "MediaFileWatcher uses per-path threading.Timer for debounce (not global timer) to handle multiple simultaneous file events"
  - "File stability check: size comparison after 2s sleep, reschedule if file still changing"
  - "StandaloneScanner groups files by series before metadata lookup -- one API call per unique series title, not per episode"
  - "Standalone wanted items use instance_name='standalone' to distinguish from Sonarr/Radarr items"
  - "_cleanup() skips 'path not in scan' removal for standalone items -- they manage own cleanup via scanner._cleanup_stale_wanted"

patterns-established:
  - "Standalone items flow through same wanted_items table as Sonarr/Radarr items, distinguished by instance_name='standalone'"
  - "StandaloneManager follows mediaserver/__init__.py singleton pattern with double-checked locking"
  - "Watcher module provides start/stop/restart functions with module-level Observer singleton"

duration: 5min
completed: 2026-02-15
---

# Phase 5 Plan 3: StandaloneManager, Watcher, Scanner, and Wanted Pipeline Integration Summary

**Watchdog-based filesystem watcher with debounce and stability checks, directory scanner grouping files by series for metadata lookup, and full wanted pipeline integration**

## Performance

- **Duration:** 5 min
- **Started:** 2026-02-15T16:31:29Z
- **Completed:** 2026-02-15T16:36:20Z
- **Tasks:** 2
- **Files modified:** 6

## Accomplishments
- MediaFileWatcher monitors directories with watchdog Observer, debounced per-path timers, and file stability checks (size comparison after 2s)
- StandaloneScanner walks directories, groups episode files by series (one metadata lookup per title), creates standalone entries, and populates wanted_items
- StandaloneManager singleton orchestrates watcher and scanner lifecycle with WebSocket event emission
- WantedScanner.scan_all() includes _scan_standalone() for standalone items alongside Sonarr/Radarr
- app.py initializes and starts standalone manager when standalone_enabled=True
- upsert_wanted_item extended with standalone_series_id and standalone_movie_id for standalone-to-wanted linking

## Task Commits

Each task was committed atomically:

1. **Task 1: MediaFileWatcher and StandaloneScanner** - `bd8d429` (feat)
2. **Task 2: StandaloneManager singleton and wanted_scanner/app.py integration** - `a7c35d0` (feat)

## Files Created/Modified
- `backend/standalone/watcher.py` - MediaFileWatcher with watchdog PatternMatchingEventHandler, per-path debounce timers, file stability check, module-level start/stop/restart functions
- `backend/standalone/scanner.py` - StandaloneScanner walks directories, groups files by series, resolves metadata, upserts standalone entries, populates wanted_items, cleans up stale items
- `backend/standalone/__init__.py` - StandaloneManager singleton with double-checked locking, start/stop/reload/get_status, background initial scan, watcher callback
- `backend/wanted_scanner.py` - Added _scan_standalone() method, standalone block in scan_all(), updated _cleanup() to skip path-based removal for standalone items
- `backend/app.py` - Standalone manager initialization in create_app, watcher start in _start_schedulers
- `backend/db/wanted.py` - Added standalone_series_id and standalone_movie_id params to upsert_wanted_item, updated get_wanted_items_for_cleanup to return instance_name

## Decisions Made
- Per-path debounce timers instead of global timer -- allows independent debounce for multiple simultaneous file events
- File stability check uses 2s sleep between size comparisons, reschedules if file still changing (handles slow copies)
- Series grouping before metadata lookup avoids redundant API calls (e.g., 12 episodes of same series = 1 lookup)
- Standalone items distinguished by instance_name='standalone' in wanted_items -- no separate table needed
- _cleanup() skips "path not in scanned_paths" removal for standalone items since they manage their own cleanup

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Extended upsert_wanted_item with standalone ID parameters**
- **Found during:** Task 2 (StandaloneManager integration)
- **Issue:** upsert_wanted_item in db/wanted.py lacked standalone_series_id and standalone_movie_id parameters, but scanner.py passes them
- **Fix:** Added both parameters to function signature and all INSERT/UPDATE SQL statements
- **Files modified:** backend/db/wanted.py
- **Verification:** Scanner can now correctly link wanted items to standalone series/movies
- **Committed in:** a7c35d0 (Task 2 commit)

**2. [Rule 3 - Blocking] Extended get_wanted_items_for_cleanup to return instance_name**
- **Found during:** Task 2 (_cleanup update)
- **Issue:** _cleanup() needs instance_name to skip standalone items in path-based removal, but get_wanted_items_for_cleanup didn't return it
- **Fix:** Added instance_name to SELECT query and return dicts
- **Files modified:** backend/db/wanted.py
- **Verification:** _cleanup() correctly distinguishes standalone from Sonarr/Radarr items
- **Committed in:** a7c35d0 (Task 2 commit)

---

**Total deviations:** 2 auto-fixed (2 blocking)
**Impact on plan:** Both auto-fixes necessary for scanner<->wanted integration. No scope creep.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- Standalone runtime engine complete: watcher + scanner + manager + wanted integration
- Ready for API endpoints (Plan 04) and frontend UI (Plan 05)
- All standalone items flow through existing wanted pipeline (search/download/translate)

## Self-Check: PASSED

- All 6 files verified present on disk
- Commit bd8d429 (Task 1) verified in git log
- Commit a7c35d0 (Task 2) verified in git log

---
*Phase: 05-standalone-mode*
*Completed: 2026-02-15*
