---
phase: 13-comparison-sync-health-check
plan: 01
subsystem: api, tools
tags: [pysubs2, health-check, quality-scoring, subtitle-sync, auto-fix, orm]

# Dependency graph
requires:
  - phase: 11-subtitle-editor
    provides: "tools.py blueprint with _validate_file_path and _create_backup patterns"
  - phase: 10-performance-scalability
    provides: "ORM base classes, repository pattern, db shim pattern"
provides:
  - "health_checker.py: 10 check functions, scoring engine, 6 auto-fix functions"
  - "SubtitleHealthResult ORM model with indexed columns"
  - "QualityRepository with CRUD, series queries, trend aggregation"
  - "db/quality.py convenience shim"
  - "5 new tools.py endpoints: health-check, health-fix, advanced-sync, compare, quality-trends"
affects: [13-02, 13-03]

# Tech tracking
tech-stack:
  added: []
  patterns: [health-check-engine, quality-scoring, batch-health-check, sync-preview]

key-files:
  created:
    - backend/health_checker.py
    - backend/db/models/quality.py
    - backend/db/repositories/quality.py
    - backend/db/quality.py
  modified:
    - backend/routes/tools.py
    - backend/db/models/__init__.py
    - backend/db/repositories/__init__.py

key-decisions:
  - "Quality score: 100 minus penalties (10/error, 3/warning, 1/info), clamped to 0"
  - "Health results stored as new records each time (not upsert) for trend tracking"
  - "Advanced sync preview returns 5 representative events (first, 25%, 50%, 75%, last)"
  - "Batch health-check limited to 50 files per request"
  - "apply_fixes creates backup via shutil.copy2 directly (same .bak pattern as tools.py)"

patterns-established:
  - "Health check function signature: (subs) -> list[HealthIssue dict]"
  - "Encoding check takes extra raw_bytes parameter for BOM/charset detection"
  - "Sync preview mode: apply operation to in-memory copy, return before/after timestamps"

# Metrics
duration: 5min
completed: 2026-02-18
---

# Phase 13 Plan 01: Backend Health-Check, Quality DB, Advanced Sync & Compare Summary

**10-check health engine with quality scoring, SubtitleHealthResult ORM, 6 auto-fix functions, and 5 new tools.py API endpoints (health-check, health-fix, advanced-sync, compare, quality-trends)**

## Performance

- **Duration:** 5 min
- **Started:** 2026-02-18T21:08:48Z
- **Completed:** 2026-02-18T21:13:40Z
- **Tasks:** 2
- **Files modified:** 7

## Accomplishments
- Health-check engine with 10 detection functions covering duplicates, timing, encoding, styles, duration, and formatting
- Quality scoring system (0-100) with severity-weighted penalties and database persistence for trend tracking
- 6 auto-fix functions that safely resolve duplicate lines, timing overlaps, missing styles, empty events, negative timing, and zero-duration events
- Advanced sync via pysubs2: offset, speed multiplier, and framerate conversion with preview mode
- Multi-file comparison endpoint serving 2-4 subtitle files in a single response

## Task Commits

Each task was committed atomically:

1. **Task 1: Health-check engine + quality DB model/repository/shim** - `15a79b6` (feat)
2. **Task 2: Advanced sync, health-check, health-fix, compare, quality-trends endpoints** - `c855417` (feat)

## Files Created/Modified
- `backend/health_checker.py` - 10 check functions, score calculation, 6 auto-fix functions, orchestrator
- `backend/db/models/quality.py` - SubtitleHealthResult ORM model with file_path and score indexes
- `backend/db/repositories/quality.py` - QualityRepository with CRUD, series queries, trend aggregation
- `backend/db/quality.py` - Convenience shim with lazy-initialized repository
- `backend/routes/tools.py` - 5 new endpoints (health-check, health-fix, advanced-sync, compare, quality-trends)
- `backend/db/models/__init__.py` - Added SubtitleHealthResult import
- `backend/db/repositories/__init__.py` - Added QualityRepository + convenience functions

## Decisions Made
- Quality score: 100 minus penalties (10/error, 3/warning, 1/info), clamped to 0
- Health results stored as new records each time (not upsert) for trend tracking over time
- Advanced sync preview returns 5 representative events at 0%, 25%, 50%, 75%, 100% positions
- Batch health-check limited to max 50 files per request to avoid timeout
- apply_fixes in health_checker.py uses shutil.copy2 directly for backup (same .bak pattern as tools.py)
- Encoding check uses chardet with ImportError fallback to basic UTF-8 decode test

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- All 5 backend endpoints ready for Plan 02 (frontend health dashboard) and Plan 03 (comparison UI)
- SubtitleHealthResult model registered in db/models/__init__.py for Alembic migration detection
- QualityRepository and shim provide all DB operations needed by frontend-facing endpoints

## Self-Check: PASSED

All 4 created files verified present. Both commit hashes (15a79b6, c855417) verified in git log.

---
*Phase: 13-comparison-sync-health-check*
*Completed: 2026-02-18*
