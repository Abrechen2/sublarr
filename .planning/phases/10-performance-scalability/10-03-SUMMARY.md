---
phase: 10-performance-scalability
plan: 03
subsystem: database
tags: [sqlalchemy, orm, repository-pattern, upsert, weighted-average, cascade-delete, json-merge]

# Dependency graph
requires:
  - phase: 10-performance-scalability
    provides: "SQLAlchemy 2.0 ORM models for all 28 tables (Plan 01) + base repository + simple repos (Plan 02)"
provides:
  - "JobRepository with daily stats JSON merge upsert"
  - "WantedRepository with complex multi-column upsert (file_path + target_language + subtitle_type)"
  - "ProfileRepository with cascade delete to series/movie assignments"
  - "ProviderRepository with weighted running average for response times and scores"
  - "HookRepository for hook/webhook CRUD with cascade log deletion"
  - "StandaloneRepository for watched folders, series/movie upserts, metadata cache, AniDB mappings"
  - "Complete repository layer: 15 classes covering all 15+ db/ domain modules"
affects: [10-05-migration-dual-write, 10-06-postgresql-migration]

# Tech tracking
tech-stack:
  added: []
  patterns: [repository-pattern, session-scoped-orm, weighted-running-average, json-merge-upsert]

key-files:
  created:
    - backend/db/repositories/jobs.py
    - backend/db/repositories/wanted.py
    - backend/db/repositories/profiles.py
    - backend/db/repositories/providers.py
    - backend/db/repositories/hooks.py
    - backend/db/repositories/standalone.py
  modified:
    - backend/db/repositories/__init__.py

key-decisions:
  - "upsert_standalone_series/movie return full dict (not just row_id) for consistency with ORM pattern"
  - "HookRepository cascade-deletes hook_log entries via explicit DELETE before hook/webhook deletion"
  - "ProviderRepository.record_search handles response_time update separately from download success"
  - "All 15 repository classes re-exported from __init__.py with grouped comments"

patterns-established:
  - "Weighted running average: (old_avg * (n-1) + new) / n for response times and scores"
  - "Multi-column upsert: file_path + target_language + subtitle_type with conditional OR for null target_language"
  - "Cascade delete pattern: explicit DELETE of related rows before parent deletion"
  - "JSON merge upsert: load existing JSON, update dict, save back for daily_stats"

# Metrics
duration: 5min
completed: 2026-02-18
---

# Phase 10 Plan 03: Complex Repository Layer Summary

**SQLAlchemy ORM repository layer for 6 complex db modules: jobs (daily stats JSON merge), wanted (multi-column upsert), profiles (cascade delete), providers (weighted averages), hooks (3-table CRUD), standalone (upserts + metadata cache)**

## Performance

- **Duration:** 5 min
- **Started:** 2026-02-18T18:54:10Z
- **Completed:** 2026-02-18T18:58:51Z
- **Tasks:** 2
- **Files modified:** 7

## Accomplishments
- Complete repository layer for all complex database operations using SQLAlchemy 2.0 ORM
- Preserved critical algorithms: weighted running average (providers), multi-column upsert (wanted), cascade deletes (profiles/hooks), JSON merge upsert (daily_stats)
- All 15 repository classes importable from db.repositories (1 base + 14 domain)
- Ready for Plan 05 to swap imports from db.* to db.repositories.*

## Task Commits

Each task was committed atomically:

1. **Task 1: Jobs, wanted, and profiles repositories** - `b7aeb90` (feat) -- from prior execution
2. **Task 2: Providers, hooks, and standalone repositories** - `2b49104` (feat)

## Files Created/Modified
- `backend/db/repositories/jobs.py` - JobRepository: CRUD + daily stats with JSON merge upsert (309 lines)
- `backend/db/repositories/wanted.py` - WantedRepository: complex multi-column upsert + status tracking (387 lines)
- `backend/db/repositories/profiles.py` - ProfileRepository: profile CRUD with cascade to series/movie assignments (325 lines)
- `backend/db/repositories/providers.py` - ProviderRepository: cache, downloads, stats with weighted running average (412 lines)
- `backend/db/repositories/hooks.py` - HookRepository: hook/webhook CRUD + cascade log deletion + trigger stats (355 lines)
- `backend/db/repositories/standalone.py` - StandaloneRepository: watched folders, series/movie upserts, metadata cache, AniDB mappings (368 lines)
- `backend/db/repositories/__init__.py` - Updated with all 15 repository class re-exports

## Decisions Made
- StandaloneRepository.upsert_standalone_series/movie returns full dict (not just row_id) for ORM pattern consistency
- HookRepository uses explicit DELETE of hook_log entries before hook/webhook deletion (manual cascade)
- ProviderRepository.record_search separates search recording from download recording to match existing API granularity
- All repository classes grouped by plan origin in __init__.py for clarity

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
- Task 1 (jobs, wanted, profiles) was already committed from a prior execution (commit b7aeb90). Verified existing commit and skipped re-execution.
- Library, scoring, translation, and whisper repositories were also pre-existing from a prior Plan 10-02 execution (commit 83d8e6f). Included them in the __init__.py re-export.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- Complete repository layer ready for Plan 05 dual-write migration
- All database operations have SQLAlchemy ORM equivalents
- No existing code changed -- repositories are additive alongside existing db/ modules

## Self-Check: PASSED

- All 7 created/modified files verified present on disk
- Commit b7aeb90 (Task 1) verified in git history
- Commit 2b49104 (Task 2) verified in git history
- All 15 repository classes importable from db.repositories

---
*Phase: 10-performance-scalability*
*Completed: 2026-02-18*
