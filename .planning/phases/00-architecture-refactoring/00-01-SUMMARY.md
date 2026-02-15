---
phase: 00-architecture-refactoring
plan: 01
subsystem: database
tags: [sqlite, refactoring, modular-architecture, python-package]

# Dependency graph
requires: []
provides:
  - "db/ package with 9 domain modules (jobs, config, providers, library, wanted, blacklist, profiles, translation, cache)"
  - "get_db(), close_db(), init_db(), _db_lock exports from db package"
  - "Schema DDL and migrations centralized in db/__init__.py"
affects: [00-02 routes extraction, 00-03 import updates and cleanup]

# Tech tracking
tech-stack:
  added: []
  patterns: ["db/ package pattern: domain modules import get_db and _db_lock from db package", "from db import get_db, _db_lock as standard import for all db domain modules"]

key-files:
  created:
    - backend/db/__init__.py
    - backend/db/jobs.py
    - backend/db/config.py
    - backend/db/providers.py
    - backend/db/library.py
    - backend/db/wanted.py
    - backend/db/blacklist.py
    - backend/db/profiles.py
    - backend/db/translation.py
    - backend/db/cache.py
  modified: []

key-decisions:
  - "Schema DDL and migrations stay in db/__init__.py -- single source of truth for all 17 tables"
  - "Each domain module gets its own logger via logging.getLogger(__name__)"
  - "Private helpers (_row_to_job, _row_to_wanted, _row_to_profile) stay with their domain module, not in __init__.py"
  - "database.py preserved intact for backward compatibility until Plan 03 updates all imports"

patterns-established:
  - "Domain module pattern: import get_db/_db_lock from db, define logger, export public functions"
  - "Package-level exports: get_db, close_db, init_db, _db_lock accessible via 'from db import ...'"

# Metrics
duration: 5min
completed: 2026-02-15
---

# Phase 0 Plan 1: Database Package Extraction Summary

**Split database.py (2154 lines, 80+ functions, 17 tables) into db/ package with __init__.py + 9 domain modules preserving all function signatures and logic**

## Performance

- **Duration:** 5 min
- **Started:** 2026-02-15T10:04:32Z
- **Completed:** 2026-02-15T10:09:51Z
- **Tasks:** 2
- **Files created:** 10

## Accomplishments
- Created db/ package with schema DDL, connection management, and migrations in __init__.py
- Extracted all 80+ database functions into 9 domain-specific modules matching CONTEXT.md boundaries
- Added init_db() convenience function for the Application Factory pattern (Plan 02 dependency)
- Fixed missing timedelta import in cleanup_old_anidb_mappings (latent bug in database.py)

## Task Commits

Each task was committed atomically:

1. **Task 1: Create db/__init__.py with schema, connection, and migrations** - `14d5471` (feat)
2. **Task 2: Create 9 domain modules extracting functions from database.py** - `d43224f` (feat)

## Files Created
- `backend/db/__init__.py` - Schema DDL (17 tables), get_db(), close_db(), init_db(), _run_migrations()
- `backend/db/jobs.py` - Job CRUD, daily stats, outdated jobs (9 functions + _row_to_job helper)
- `backend/db/config.py` - Config entry CRUD (3 functions)
- `backend/db/providers.py` - Provider cache, download recording, provider stats (10 functions)
- `backend/db/library.py` - Download history, upgrade tracking (5 functions)
- `backend/db/wanted.py` - Wanted item CRUD, search, cleanup (16 functions + _row_to_wanted helper)
- `backend/db/blacklist.py` - Blacklist CRUD and lookup (6 functions)
- `backend/db/profiles.py` - Language profiles, series/movie assignments (14 functions + _row_to_profile helper)
- `backend/db/translation.py` - Glossary, prompt presets, config history (15 functions)
- `backend/db/cache.py` - FFprobe cache, episode history, AniDB mappings (8 functions)

## Decisions Made
- Schema DDL stays in db/__init__.py (single source of truth for 17 tables in one SQLite file)
- Private helpers (_row_to_job, _row_to_wanted, _row_to_profile) placed in their domain modules
- database.py left intact -- Plan 03 will update all external imports then remove it
- init_db() is a thin wrapper around get_db() for Application Factory semantics

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed missing timedelta import in cleanup_old_anidb_mappings**
- **Found during:** Task 2 (cache.py extraction)
- **Issue:** database.py imports `from datetime import datetime, date` but cleanup_old_anidb_mappings uses `timedelta` without importing it -- would crash at runtime
- **Fix:** Added `timedelta` to the datetime import in db/cache.py: `from datetime import datetime, timedelta`
- **Files modified:** backend/db/cache.py
- **Verification:** Module imports cleanly, timedelta available
- **Committed in:** d43224f (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (1 bug fix)
**Impact on plan:** Bug fix necessary for correctness. No scope creep.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- db/ package complete with all domain modules importable
- Plan 02 (routes/ extraction) can proceed -- init_db() available for create_app() factory
- Plan 03 (import updates) can proceed -- all db.* import targets exist
- database.py still present for backward compatibility during Plan 02/03 transition

## Self-Check: PASSED

- All 10 files verified present in backend/db/
- Commit 14d5471 (Task 1) verified in git log
- Commit d43224f (Task 2) verified in git log
- All modules import cleanly without errors
- database.py backward compatibility confirmed

---
*Phase: 00-architecture-refactoring*
*Completed: 2026-02-15*
