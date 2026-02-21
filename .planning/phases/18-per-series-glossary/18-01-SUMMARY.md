---
phase: 18-per-series-glossary
plan: 01
subsystem: database, api, translation
tags: [sqlalchemy, alembic, glossary, migration, flask, rest-api]

# Dependency graph
requires:
  - phase: none
    provides: existing glossary_entries table with series_id NOT NULL
provides:
  - "GlossaryEntry.series_id nullable (NULL = global entry)"
  - "get_global_glossary() and get_merged_glossary_for_series() repository methods"
  - "GET/POST /api/v1/glossary with optional series_id"
  - "Translator loads merged glossary (global + per-series) during translation"
affects: [18-02-per-series-glossary, translation-pipeline, glossary-ui]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Global vs per-series glossary merge with case-insensitive source_term override"
    - "Optional[int] series_id pattern for global/per-series branching"

key-files:
  created:
    - backend/db/migrations/versions/make_glossary_series_id_nullable.py
  modified:
    - backend/db/models/translation.py
    - backend/db/repositories/translation.py
    - backend/db/translation.py
    - backend/routes/profiles.py
    - backend/translator.py

key-decisions:
  - "Global entries use series_id=NULL rather than a sentinel value like 0"
  - "Per-series entries override global on same source_term (case-insensitive)"
  - "Merged glossary limited to 30 entries total"
  - "Non-series translations (movies) use global glossary only"

patterns-established:
  - "Optional[int] series_id = None pattern for global/per-series branching in repository and facade"
  - "get_merged_glossary_for_series merges global-first then series-overrides via dict spread"

# Metrics
duration: 6min
completed: 2026-02-21
---

# Phase 18 Plan 01: Global Glossary Backend Summary

**Nullable series_id on glossary_entries with Alembic migration, merged glossary repository methods, optional-series_id API routes, and translator integration for global+per-series glossary merge**

## Performance

- **Duration:** 6 min
- **Started:** 2026-02-21T22:45:07Z
- **Completed:** 2026-02-21T22:51:53Z
- **Tasks:** 2
- **Files modified:** 6

## Accomplishments
- GlossaryEntry.series_id made nullable with Alembic migration (batch_alter_table for SQLite)
- Repository layer gains get_global_glossary() and get_merged_glossary_for_series() with case-insensitive override logic
- API routes (GET/POST /glossary) now accept optional series_id, returning/creating global entries when omitted
- Translation pipeline loads merged glossary (global + per-series) for series, global-only for movies

## Task Commits

Each task was committed atomically:

1. **Task 1: DB migration + model + repository methods for global glossary** - `7cc9e66` (feat)
2. **Task 2: API route updates + translator merge integration** - `3d17049` (feat)

## Files Created/Modified
- `backend/db/migrations/versions/make_glossary_series_id_nullable.py` - Alembic migration making series_id nullable
- `backend/db/models/translation.py` - GlossaryEntry.series_id changed to Optional[int], nullable=True
- `backend/db/repositories/translation.py` - Added get_global_glossary(), get_merged_glossary_for_series(), updated search_glossary_terms
- `backend/db/translation.py` - Facade functions for global and merged glossary, updated signatures
- `backend/routes/profiles.py` - GET/POST /glossary with optional series_id, updated OpenAPI docs
- `backend/translator.py` - Merged glossary loading (global+series for series, global for movies)

## Decisions Made
- Global entries use series_id=NULL (not a sentinel value like 0) -- cleaner semantics and standard SQL pattern
- Per-series entries override global entries on same source_term using case-insensitive matching (lowered key)
- Merged glossary is capped at 30 entries to keep translation prompts reasonable
- Movies/standalone translations get global glossary only (no series_id available)

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Backend data model and API ready for Plan 02 (frontend glossary UI)
- Migration will auto-apply on next backend startup via Alembic upgrade
- Global glossary entries can be created immediately via API

---
*Phase: 18-per-series-glossary*
*Completed: 2026-02-21*

## Self-Check: PASSED
All 7 files verified. Both commit hashes (7cc9e66, 3d17049) confirmed in git log.
