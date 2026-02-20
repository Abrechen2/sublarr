---
phase: 12-batch-operations-smart-filter
plan: 01
subsystem: api, database
tags: [fts5, trigram, filter-presets, batch-actions, sqlalchemy, flask-blueprints]

# Dependency graph
requires:
  - phase: 10-performance-scalability
    provides: ORM models, repositories, Flask-SQLAlchemy integration
provides:
  - FilterPreset ORM model and Alembic migration
  - SearchRepository with FTS5 trigram tables
  - FilterPresetsRepository with CRUD and condition tree builder
  - Extended WantedRepository with sort/search/preset params
  - Extended LibraryRepository with format/score/search/sort params
  - POST /wanted/batch-action endpoint
  - GET /api/v1/search global search endpoint
  - Full CRUD /api/v1/filter-presets endpoints
affects: [12-batch-operations-smart-filter]

# Tech tracking
tech-stack:
  added: [fts5-trigram]
  patterns: [condition-tree-builder, field-allowlist-validation]

key-files:
  created:
    - backend/db/models/core.py (FilterPreset model added)
    - backend/db/migrations/versions/fa890ea72dab_add_filter_presets.py
    - backend/db/repositories/search.py
    - backend/db/repositories/presets.py
    - backend/db/search.py
    - backend/db/presets.py
    - backend/routes/search.py
    - backend/routes/filter_presets.py
  modified:
    - backend/db/models/__init__.py
    - backend/db/repositories/__init__.py
    - backend/db/repositories/wanted.py
    - backend/db/repositories/library.py
    - backend/db/wanted.py
    - backend/db/library.py
    - backend/routes/__init__.py
    - backend/routes/wanted.py
    - backend/routes/blacklist.py
    - backend/app.py

key-decisions:
  - "FTS5 trigram tables use LIKE queries (not MATCH) for 2+ char search support"
  - "SearchRepository uses db.engine directly instead of session.bind for test compatibility"
  - "Condition tree builder uses field allowlist per scope to prevent injection"
  - "Alembic migration written manually due to stamp_existing_db_if_needed incompatibility"

patterns-established:
  - "Condition tree pattern: {logic: AND|OR, conditions: [...]} with leaf nodes {field, op, value}"
  - "Field allowlist per scope: ALLOWED_FIELDS dict gates which fields presets can filter on"

# Metrics
duration: 11min
completed: 2026-02-19
---

# Phase 12 Plan 01: Backend Infrastructure Summary

**FilterPreset model, FTS5 global search, extended repository filters, batch-action endpoint, and filter preset CRUD API**

## Performance

- **Duration:** 11 min
- **Started:** 2026-02-19T16:39:48Z
- **Completed:** 2026-02-19T16:50:41Z
- **Tasks:** 8
- **Files modified:** 18

## Accomplishments
- FilterPreset ORM model with scope-indexed table and Alembic migration
- FTS5 trigram search across series, episodes, and subtitles with rebuild capability
- FilterPresetsRepository with full CRUD plus nested AND/OR condition tree builder
- WantedRepository extended with sort_by (5 fields), sort_dir, text search, and preset conditions
- LibraryRepository extended with format, score_min/max, text search, sort_by (4 fields), sort_dir
- POST /wanted/batch-action supporting ignore, unignore, blacklist, export (max 500 items)
- GET /api/v1/search global search and POST /search/rebuild-index endpoints
- Full CRUD /api/v1/filter-presets with field validation per scope

## Task Commits

Each task was committed atomically:

1. **Task 1: FilterPreset ORM model + Alembic migration** - `705119b` (feat)
2. **Task 2: SearchRepository with FTS5 trigram tables** - `0931ea6` (feat)
3. **Task 3: FilterPresetsRepository + shim** - `f302067` (feat)
4. **Task 4: Extend WantedRepository with sort + search** - `9fd9f44` (feat)
5. **Task 5: Extend LibraryRepository with format, score, search** - `f254906` (feat)
6. **Task 6: POST /wanted/batch-action** - `e0a989e` (feat)
7. **Task 7: Global search route + filter presets route** - `eda751d` (feat)
8. **Task 8: Wire sort/search params into routes + update shims** - `8b52f7d` (feat)

## Files Created/Modified
- `backend/db/models/core.py` - FilterPreset model added at end of file
- `backend/db/models/__init__.py` - FilterPreset import and __all__ registration
- `backend/db/migrations/versions/fa890ea72dab_add_filter_presets.py` - Manual Alembic migration
- `backend/db/repositories/search.py` - SearchRepository with FTS5 init, rebuild, search_all
- `backend/db/repositories/presets.py` - FilterPresetsRepository with CRUD + build_clause
- `backend/db/repositories/__init__.py` - SearchRepository and FilterPresetsRepository registration
- `backend/db/search.py` - Convenience shim for search operations
- `backend/db/presets.py` - Convenience shim for preset CRUD + build_preset_clause
- `backend/db/repositories/wanted.py` - Extended get_wanted_items with sort/search/preset params
- `backend/db/repositories/library.py` - Extended get_download_history with format/score/search/sort
- `backend/db/wanted.py` - Shim updated with sort_by, sort_dir, search params
- `backend/db/library.py` - Shim updated with format, score_min/max, search, sort_by, sort_dir
- `backend/routes/search.py` - GET /search and POST /search/rebuild-index blueprints
- `backend/routes/filter_presets.py` - Full CRUD /filter-presets blueprint
- `backend/routes/__init__.py` - search_bp and filter_presets_bp registered
- `backend/routes/wanted.py` - sort/search params extracted, batch-action endpoint added
- `backend/routes/blacklist.py` - History endpoint wired with new filter/sort params
- `backend/app.py` - init_search_tables() called after db.create_all()

## Decisions Made
- FTS5 trigram tables use LIKE '%query%' instead of MATCH for 2+ character search support (trigram MATCH requires 3+ chars)
- SearchRepository uses `db.engine` from extensions directly instead of `session.bind` to avoid NoneType errors in test fixtures
- Condition tree builder validates field names against per-scope allowlists (wanted: 6 fields, library: 3, history: 4)
- Alembic migration written manually because autogenerate failed due to stamp_existing_db_if_needed using unsupported context.stamp() API

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed SearchRepository session.bind NoneType error**
- **Found during:** Task 4 (while running existing tests)
- **Issue:** `self.session.bind` was None in test fixtures because Flask-SQLAlchemy session bind is not always set
- **Fix:** Changed to use `db.engine` from extensions module directly via `_get_engine()` helper
- **Files modified:** backend/db/repositories/search.py
- **Verification:** `create_app(testing=True)` succeeds, app starts without errors
- **Committed in:** 9fd9f44 (Task 4 commit)

---

**Total deviations:** 1 auto-fixed (1 bug)
**Impact on plan:** Essential fix for test compatibility. No scope creep.

## Issues Encountered
- Alembic autogenerate failed with `AttributeError: module 'alembic.context' has no attribute 'stamp'` due to stamp_existing_db_if_needed calling context.stamp() which is not a valid Alembic context method. Wrote migration manually instead.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- All backend infrastructure for Plans 02 and 03 is in place
- 7 new API endpoints registered (167 total, up from 160)
- Filter presets, global search, batch actions, and extended sorting/filtering ready for frontend consumption

---
*Phase: 12-batch-operations-smart-filter*
*Completed: 2026-02-19*
