---
phase: 05-standalone-mode
plan: 01
subsystem: database, backend
tags: [sqlite, guessit, standalone, media-parser, config, pydantic]

requires:
  - phase: 00-architecture-refactoring
    provides: "db package with _db_lock and get_db pattern, config.py with Pydantic Settings"
provides:
  - "4 new DB tables: watched_folders, standalone_series, standalone_movies, metadata_cache"
  - "CRUD operations in db/standalone.py for all 4 tables"
  - "standalone_series_id and standalone_movie_id columns on wanted_items"
  - "Config fields: standalone_enabled, tmdb_api_key, tvdb_api_key, tvdb_pin, metadata_cache_ttl_days"
  - "MediaFileParser in standalone/parser.py with anime detection and guessit integration"
affects: [05-02-PLAN, 05-03-PLAN, 05-04-PLAN, 05-05-PLAN]

tech-stack:
  added: [guessit]
  patterns: [standalone DB CRUD with _db_lock, anime filename detection heuristics]

key-files:
  created:
    - backend/db/standalone.py
    - backend/standalone/__init__.py
    - backend/standalone/parser.py
  modified:
    - backend/db/__init__.py
    - backend/config.py

key-decisions:
  - "Standalone CRUD follows exact pattern of db/wanted.py -- all functions use with _db_lock and return dicts"
  - "Anime detection uses multi-signal heuristic: bracket groups, known fansub groups, CRC32 hashes, absolute numbering"
  - "guessit called with episode_prefer_number=True for anime, standard episode then movie fallback for non-anime"
  - "metadata_cache uses TEXT PRIMARY KEY (cache_key) with TTL-based expiration (not autoincrement)"

patterns-established:
  - "Standalone DB CRUD: upsert by unique path/key, get single or all, delete by ID"
  - "Media file parsing: detect anime first, then choose guessit options accordingly"
  - "Config cascade for standalone: Pydantic Settings with SUBLARR_ prefix for all standalone fields"

duration: 4min
completed: 2026-02-15
---

# Phase 5 Plan 1: Standalone DB Schema, Config, and Parser Summary

**SQLite schema with 4 new tables, standalone config fields, and guessit-based media file parser with anime detection**

## Performance

- **Duration:** 4 min
- **Started:** 2026-02-15T16:24:07Z
- **Completed:** 2026-02-15T16:28:02Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments
- 4 new database tables (watched_folders, standalone_series, standalone_movies, metadata_cache) with indexes and migrations
- Full CRUD module (db/standalone.py) with 15 functions covering all 4 tables, thread-safe with _db_lock
- 7 new config fields for standalone mode (standalone_enabled, scan interval, debounce, TMDB/TVDB keys, cache TTL)
- Media file parser that correctly handles standard TV (S01E02), anime ([Group] Title - 42), and movie filenames
- Anime detection heuristic combining bracket groups, known fansub groups, CRC32 hashes, and absolute numbering

## Task Commits

Each task was committed atomically:

1. **Task 1: Database schema and operations for standalone mode** - `ab1378c` (feat)
2. **Task 2: Config settings and media file parser** - `483f2af` (feat)

## Files Created/Modified
- `backend/db/__init__.py` - Added 4 CREATE TABLE statements to SCHEMA, migration for wanted_items columns and table creation on existing DBs
- `backend/db/standalone.py` - Full CRUD operations for watched_folders, standalone_series, standalone_movies, metadata_cache (15 functions)
- `backend/config.py` - Added standalone_enabled, standalone_scan_interval_hours, standalone_debounce_seconds, tmdb_api_key, tvdb_api_key, tvdb_pin, metadata_cache_ttl_days
- `backend/standalone/__init__.py` - Package init with docstring
- `backend/standalone/parser.py` - MediaFileParser with VIDEO_EXTENSIONS, ANIME_RELEASE_GROUPS, is_video_file, detect_anime_indicators, parse_media_file, group_files_by_series

## Decisions Made
- Standalone CRUD follows exact pattern of db/wanted.py -- all functions use `with _db_lock:` and return dicts via `dict(row)`
- Anime detection uses multi-signal heuristic: bracket groups, known fansub groups, CRC32 hashes, absolute episode numbering
- guessit called with `episode_prefer_number=True` for anime filenames, standard episode type then movie fallback for non-anime
- metadata_cache uses TEXT PRIMARY KEY (cache_key) with TTL-based expiration instead of autoincrement ID
- Parent directory name used as title fallback when guessit cannot extract title from filename alone

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- DB schema and CRUD operations ready for scanner (Plan 02) and watcher (Plan 03)
- Config fields ready for Settings UI (Plan 04/05)
- Parser ready for scanner to classify discovered media files
- All 4 tables queryable and tested with inserts/reads

## Self-Check: PASSED

- All 5 files verified present on disk
- Commit ab1378c (Task 1) verified in git log
- Commit 483f2af (Task 2) verified in git log

---
*Phase: 05-standalone-mode*
*Completed: 2026-02-15*
