---
phase: 10-performance-scalability
plan: 02
subsystem: database
tags: [sqlalchemy, orm, repository-pattern, flask-sqlalchemy, crud]

# Dependency graph
requires:
  - phase: 10-01
    provides: "SQLAlchemy 2.0 ORM models for all 28 tables + Flask-SQLAlchemy db instance"
provides:
  - "8 repository classes converting db/ domain modules to SQLAlchemy ORM"
  - "BaseRepository with session, commit, to_dict, now helpers"
  - "Module-level convenience functions mirroring existing db/ module APIs"
  - "Repository pattern validated for config, blacklist, cache, plugins, scoring, library, whisper, translation"
affects: [10-03, 10-05]

# Tech tracking
tech-stack:
  added: []
  patterns: [Repository pattern with BaseRepository inheritance, Convenience function bridge pattern for API compatibility, SQLAlchemy 2.0 select/where/execute query style, session.merge for upsert operations, session.get for primary key lookups]

key-files:
  created:
    - backend/db/repositories/__init__.py
    - backend/db/repositories/base.py
    - backend/db/repositories/config.py
    - backend/db/repositories/blacklist.py
    - backend/db/repositories/cache.py
    - backend/db/repositories/plugins.py
    - backend/db/repositories/scoring.py
    - backend/db/repositories/library.py
    - backend/db/repositories/whisper.py
    - backend/db/repositories/translation.py

key-decisions:
  - "Convenience functions in __init__.py create fresh repository instances per call -- stateless bridge to ORM layer"
  - "CacheRepository covers ffprobe_cache, episode_history (cross-table), and anidb_mappings -- mirrors db/cache.py scope"
  - "ScoringRepository duplicates default weight dicts from db/scoring.py for self-contained merge logic"
  - "TranslationRepository preserves weighted running average formula for backend stats exactly as in db/translation.py"
  - "BlacklistRepository uses check-then-insert pattern instead of INSERT OR IGNORE (SQLAlchemy has no direct equivalent)"
  - "LibraryRepository uses SQLite datetime() function via sqlalchemy.text() for last_24h/last_7d time filtering"

patterns-established:
  - "Repository class per db/ domain module: 1:1 mapping for straightforward migration"
  - "Return type parity: all repository methods return identical shapes (dict, list[dict], Optional[str], bool, int) to existing functions"
  - "Convenience function bridge: module-level functions in __init__.py delegate to repository.method() for drop-in replacement"
  - "_to_dict helper converts ORM instances to dicts using model.__table__.columns introspection"

# Metrics
duration: 3min
completed: 2026-02-18
---

# Phase 10 Plan 02: Repository Pattern for 8 DB Domain Modules Summary

**8 SQLAlchemy repository classes with convenience bridge functions replacing raw sqlite3 queries in config, blacklist, cache, plugins, scoring, library, whisper, and translation modules**

## Performance

- **Duration:** 3 min
- **Started:** 2026-02-18T18:53:30Z
- **Completed:** 2026-02-18T18:56:08Z
- **Tasks:** 2
- **Files modified:** 10

## Accomplishments
- Created BaseRepository with session property, _commit, _to_dict, and _now helpers
- Converted all 8 simpler db/ domain modules to SQLAlchemy ORM repository classes
- Added module-level convenience functions mirroring all existing db/ module APIs for easy swapover
- Verified all repository classes importable with correct method signatures

## Task Commits

Each task was committed atomically:

1. **Task 1: Base repository + config, blacklist, cache, plugins repositories** - `a3d5c5d` (feat)
2. **Task 2: Scoring, library, whisper, translation repositories** - `83d8e6f` (feat)

## Files Created/Modified
- `backend/db/repositories/__init__.py` - Re-exports all 8 repositories + 35 convenience bridge functions
- `backend/db/repositories/base.py` - BaseRepository with session, _commit, _to_dict, _now helpers
- `backend/db/repositories/config.py` - ConfigRepository: save, get, get_all config entries
- `backend/db/repositories/blacklist.py` - BlacklistRepository: add, remove, clear, is_blacklisted, paginated list, count
- `backend/db/repositories/cache.py` - CacheRepository: ffprobe cache, episode history, AniDB mappings
- `backend/db/repositories/plugins.py` - PluginRepository: namespaced plugin config CRUD
- `backend/db/repositories/scoring.py` - ScoringRepository: scoring weights with defaults merge, provider modifiers
- `backend/db/repositories/library.py` - LibraryRepository: download history/stats, upgrade history/stats
- `backend/db/repositories/whisper.py` - WhisperRepository: job CRUD with dynamic update, stats
- `backend/db/repositories/translation.py` - TranslationRepository: config history, glossary, prompt presets, backend stats

## Decisions Made
- Convenience functions instantiate fresh repository per call (stateless, no singleton caching) for simplicity
- CacheRepository handles three separate concerns (ffprobe, episode history, AniDB) matching the existing db/cache.py scope
- ScoringRepository self-contains default weight dicts rather than importing from providers/base.py
- Weighted running average formula preserved exactly for TranslationBackendStats to avoid statistical drift
- BlacklistRepository checks existence before insert (no INSERT OR IGNORE equivalent in SQLAlchemy Core)
- LibraryRepository uses sqlalchemy.text() for SQLite-specific datetime functions in time-based aggregation

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Task 1 was previously committed by prior execution**
- **Found during:** Plan start
- **Issue:** Task 1 files (base.py, config.py, blacklist.py, cache.py, plugins.py, __init__.py) were already committed as `a3d5c5d` by a prior execution agent. Task 2 files existed on disk but were untracked.
- **Fix:** Verified Task 1 commit integrity, proceeded directly to Task 2 completion (updating __init__.py with Task 2 exports and committing Task 2 files).
- **Files modified:** backend/db/repositories/__init__.py (updated with scoring/library/whisper/translation exports)
- **Verification:** All 8 repositories importable, all method signatures verified
- **Committed in:** 83d8e6f (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (1 blocking -- prior partial execution)
**Impact on plan:** Task 1 was already done. Only Task 2 completion (commit + __init__.py update) was needed.

## Issues Encountered
None beyond the partial prior execution state.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- All 8 simpler repository classes ready for Plan 03 (complex repositories: jobs, wanted, profiles)
- Repository pattern validated and consistent across all modules
- Convenience function bridge pattern established for Plan 05 integration wiring
- No blockers for remaining Phase 10 plans

## Self-Check: PASSED

All 10 created files verified present. Both task commits (a3d5c5d, 83d8e6f) verified in git log.

---
*Phase: 10-performance-scalability*
*Completed: 2026-02-18*
