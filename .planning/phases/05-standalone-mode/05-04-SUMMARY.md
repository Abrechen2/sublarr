---
phase: 05-standalone-mode
plan: 04
subsystem: api, backend
tags: [flask-blueprint, rest-api, standalone, wanted-search, metadata-enrichment, guessit]

# Dependency graph
requires:
  - phase: 05-standalone-mode
    provides: "DB CRUD operations (db/standalone.py), standalone config fields, media file parser"
provides:
  - "Standalone API Blueprint at /api/v1/standalone with 13 endpoints"
  - "CRUD for watched folders, series listing/deletion, movie listing/deletion"
  - "Scanner control endpoints (scan all, scan folder, status)"
  - "Metadata refresh endpoint for re-resolving TMDB/AniList/TVDB data"
  - "Three-tier metadata enrichment in build_query_from_wanted: Sonarr/Radarr -> standalone DB -> filename"
affects: [05-05-PLAN, frontend-standalone-pages, provider-search-quality]

# Tech tracking
tech-stack:
  added: []
  patterns: [standalone-api-blueprint, three-tier-metadata-enrichment, guessit-filename-fallback]

key-files:
  created:
    - backend/routes/standalone.py
  modified:
    - backend/routes/__init__.py
    - backend/wanted_search.py

key-decisions:
  - "Standalone Blueprint uses /api/v1/standalone prefix (not /api/v1 like other blueprints) for clear namespace separation"
  - "Scanner endpoints run in daemon threads following same pattern as wanted scan in routes/wanted.py"
  - "GET /status falls back to basic DB stats if StandaloneManager not yet implemented (ImportError guard)"
  - "Series/movie deletion cascades to associated wanted_items via explicit DELETE before entity removal"
  - "guessit fallback in _parse_filename_for_metadata gracefully degrades if standalone.parser unavailable"

patterns-established:
  - "Standalone API namespace: all endpoints under /api/v1/standalone/* with Blueprint url_prefix"
  - "Three-tier metadata: arr client -> standalone DB -> filename parsing, each wrapped in try/except"
  - "Daemon thread scan: import scanner inside thread function to avoid circular imports at module level"

# Metrics
duration: 3min
completed: 2026-02-15
---

# Phase 5 Plan 4: Standalone API Blueprint and Wanted Search Extension Summary

**REST API Blueprint with 13 endpoints for standalone mode CRUD plus three-tier metadata enrichment in wanted_search**

## Performance

- **Duration:** 3 min
- **Started:** 2026-02-15T16:31:42Z
- **Completed:** 2026-02-15T16:34:52Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments
- Full standalone API Blueprint with 13 endpoints covering watched folders CRUD, series/movies listing and deletion, scanner control, status, and metadata refresh
- Three-tier metadata enrichment in build_query_from_wanted: Sonarr/Radarr first, then standalone DB (via standalone_series_id/standalone_movie_id), then filename parsing
- guessit integration in filename fallback parser for more robust metadata extraction
- Blueprint registered alongside 12 existing blueprints in routes/__init__.py

## Task Commits

Each task was committed atomically:

1. **Task 1: Standalone API Blueprint** - `27aa715` (feat)
2. **Task 2: Extend wanted_search for standalone metadata** - `c661926` (feat)

## Files Created/Modified
- `backend/routes/standalone.py` - New Blueprint with 13 endpoints for watched folders, series, movies, scanner, status, metadata
- `backend/routes/__init__.py` - Added standalone_bp registration
- `backend/wanted_search.py` - Added standalone metadata paths, guessit fallback, fixed missing re import and _EPISODE_PATTERNS

## Decisions Made
- Standalone Blueprint uses dedicated /api/v1/standalone prefix instead of shared /api/v1 prefix -- cleaner namespace for standalone-specific endpoints
- Scanner runs in daemon threads with lazy imports inside the thread function to avoid circular import issues at module load time
- Status endpoint gracefully falls back to basic DB stats (folder/series/movie counts) when StandaloneManager is not yet implemented
- Series/movie deletion explicitly removes associated wanted_items before deleting the entity itself

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed missing `import re` and `_EPISODE_PATTERNS` in wanted_search.py**
- **Found during:** Task 2 (extending wanted_search)
- **Issue:** `_parse_filename_for_metadata()` used `re.search()`, `re.split()`, `re.sub()` and `_EPISODE_PATTERNS` but neither `re` was imported nor `_EPISODE_PATTERNS` was defined -- pre-existing bugs that would crash on any filename-fallback code path
- **Fix:** Added `import re` to module imports and defined `_EPISODE_PATTERNS` list with 4 compiled regex patterns (S01E02, 1x02, Episode 02, anime absolute numbering)
- **Files modified:** backend/wanted_search.py
- **Verification:** build_query_from_wanted successfully parses filenames for both TV and anime patterns
- **Committed in:** c661926 (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (1 bug)
**Impact on plan:** Bug fix was necessary for the existing filename fallback to function at all. No scope creep.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- Standalone API ready for frontend integration (Plan 05)
- All 13 endpoints tested for import/registration
- wanted_search correctly enriches standalone items with metadata from DB
- Scanner endpoints ready to use once standalone.scanner module is implemented (Plan 03)

## Self-Check: PASSED

- FOUND: backend/routes/standalone.py
- FOUND: backend/routes/__init__.py (modified)
- FOUND: backend/wanted_search.py (modified)
- FOUND: commit 27aa715 (Task 1)
- FOUND: commit c661926 (Task 2)

---
*Phase: 05-standalone-mode*
*Completed: 2026-02-15*
