---
phase: 15-api-key-mgmt-notifications-cleanup
plan: 03
subsystem: api, database, cleanup
tags: [sha256, dedup, cleanup, scheduler, threading, socketio, sqlite]

# Dependency graph
requires:
  - phase: 10-performance-scalability
    provides: "ORM models, BaseRepository, Flask-SQLAlchemy extensions"
  - phase: 00-architecture-refactoring
    provides: "Blueprint pattern, routes/__init__.py registration"
provides:
  - "SubtitleHash, CleanupRule, CleanupHistory ORM models"
  - "CleanupRepository with hash CRUD, duplicate detection, rule management, disk stats"
  - "Dedup engine with SHA-256 content hashing and ThreadPoolExecutor scanning"
  - "Cleanup API Blueprint with 13 endpoints under /api/v1/cleanup"
  - "CleanupScheduler with configurable weekly schedule"
affects: [frontend-cleanup-ui, dashboard-widgets]

# Tech tracking
tech-stack:
  added: []
  patterns: ["SHA-256 content hashing with line-ending normalization", "keep-at-least-one safety guard for batch deletion", "module-level scan state with threading.Lock for background operations"]

key-files:
  created:
    - backend/db/models/cleanup.py
    - backend/db/repositories/cleanup.py
    - backend/dedup_engine.py
    - backend/routes/cleanup.py
    - backend/cleanup_scheduler.py
  modified:
    - backend/db/models/__init__.py
    - backend/db/repositories/__init__.py
    - backend/routes/__init__.py
    - backend/app.py

key-decisions:
  - "SHA-256 hash computed on normalized content (stripped + \r\n -> \n) to detect duplicates regardless of line ending differences"
  - "ThreadPoolExecutor(max_workers=4) for parallel file hashing during scan"
  - "Keep-at-least-one safety guard validates before any deletion starts (pre-validation, not mid-deletion)"
  - "CleanupScheduler uses threading.Timer pattern (same as wanted_scanner) with configurable interval from config_entries"
  - "Module-level _scan_state dict with threading.Lock for background scan tracking (same pattern as wanted_scanner)"
  - "Orphan detection compares subtitle basenames against media file basenames in same directory"
  - "_start_schedulers receives app parameter for cleanup scheduler app_context needs"

patterns-established:
  - "Background scan pattern: module-level state dict + Lock + daemon thread + WebSocket progress"
  - "Safety guard pattern: pre-validate all groups before executing any deletions"
  - "Disk analysis pattern: aggregate from DB hashes + trend from cleanup_history"

# Metrics
duration: 8min
completed: 2026-02-20
---

# Phase 15 Plan 03: Cleanup System Summary

**SHA-256 dedup engine with ThreadPoolExecutor scanning, cleanup rules scheduler, and 13-endpoint API Blueprint for duplicate/orphan management**

## Performance

- **Duration:** 8 min
- **Started:** 2026-02-20T13:12:51Z
- **Completed:** 2026-02-20T13:20:40Z
- **Tasks:** 2
- **Files modified:** 9

## Accomplishments
- Content-hash deduplication engine with SHA-256 hashing, parallel scanning, and batch deletion with keep-at-least-one safety guard
- Cleanup API Blueprint with 13 endpoints: dedup scan/status/duplicates/delete, orphan scan/list/delete, rules CRUD + execution, stats/history, preview
- CleanupScheduler with configurable weekly interval (threading.Timer pattern matching existing schedulers)
- Disk space analysis with format breakdown, duplicate waste calculation, and 30-day cleanup trend tracking

## Task Commits

Each task was committed atomically:

1. **Task 1: Cleanup DB Models, Repository, and Dedup Engine** - `9c3c14c` (feat)
2. **Task 2: Cleanup API Blueprint and Scheduler** - `db3de38` (feat)

## Files Created/Modified
- `backend/db/models/cleanup.py` - SubtitleHash, CleanupRule, CleanupHistory ORM models
- `backend/db/repositories/cleanup.py` - CleanupRepository with hash, rule, history, and disk analysis operations
- `backend/dedup_engine.py` - SHA-256 hashing, duplicate scanning, safe deletion, orphan detection, disk analysis
- `backend/routes/cleanup.py` - 13-endpoint Blueprint for all cleanup operations
- `backend/cleanup_scheduler.py` - Weekly cleanup scheduler with threading.Timer
- `backend/db/models/__init__.py` - Registered cleanup models (already present from prior commit)
- `backend/db/repositories/__init__.py` - Registered CleanupRepository (already present from prior commit)
- `backend/routes/__init__.py` - Registered cleanup Blueprint
- `backend/app.py` - Wired cleanup scheduler into _start_schedulers

## Decisions Made
- SHA-256 hash computed on normalized content (stripped + CRLF->LF) to detect duplicates regardless of line ending differences
- ThreadPoolExecutor(max_workers=4) for parallel file hashing during scan (matches existing FFPROBE_MAX_WORKERS pattern)
- Keep-at-least-one safety guard pre-validates all groups before starting any deletions
- CleanupScheduler uses threading.Timer pattern matching wanted_scanner for consistency
- _start_schedulers updated to accept app parameter (backward compatible with default=None)
- Orphan detection uses filename base matching -- a subtitle is orphaned if no media file shares its basename in the same directory
- Old backups rule type scans for .bak files (matching tools.py backup pattern) but does not auto-delete

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
- Models __init__.py and repositories __init__.py already contained cleanup imports from a prior parallel plan execution -- no modifications needed (git showed no diff for those files)

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- All cleanup backend infrastructure complete and importable
- Ready for frontend cleanup UI integration
- All 7 verification checks pass (models, repo, engine, routes, scheduler, blueprint registration, safety guard)

---
*Phase: 15-api-key-mgmt-notifications-cleanup*
*Completed: 2026-02-20*

## Self-Check: PASSED

All created files verified present. All commit hashes verified in git log.
