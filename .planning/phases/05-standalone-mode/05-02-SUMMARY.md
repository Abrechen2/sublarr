---
phase: 05-standalone-mode
plan: 02
subsystem: api
tags: [tmdb, anilist, tvdb, metadata, graphql, rest, requests]

# Dependency graph
requires:
  - phase: 04-whisper-speech-to-text
    provides: "Established backend package patterns (whisper/)"
provides:
  - "TMDBClient for TV/movie search and details via API v3"
  - "AniListClient for anime metadata via GraphQL"
  - "TVDBClient for series lookup with JWT auth via API v4"
  - "MetadataResolver orchestrating lookup chain with caching"
affects: [05-standalone-mode, standalone-scanner, library-management]

# Tech tracking
tech-stack:
  added: [TMDB API v3, AniList GraphQL API, TVDB API v4]
  patterns: [lazy-client-creation, normalized-result-dicts, graceful-error-handling, db-cache-with-fallback]

key-files:
  created:
    - backend/metadata/__init__.py
    - backend/metadata/tmdb_client.py
    - backend/metadata/anilist_client.py
    - backend/metadata/tvdb_client.py

key-decisions:
  - "MetadataResolver uses lazy client creation -- only instantiated when API keys provided"
  - "AniList always available (no API key required), TMDB and TVDB require keys"
  - "DB cache calls wrapped in try/except for graceful degradation when DB not initialized"
  - "AniList rate limiting at 0.7s between calls (conservative for 90 req/min limit)"
  - "TVDB JWT token cached for 24h with automatic refresh on expiry"
  - "Anime detection: AniList-first lookup, plus TMDB genre+origin_country heuristic (Animation+JP)"

patterns-established:
  - "Metadata normalization: all sources return same dict format {title, year, *_id, poster_url, metadata_source}"
  - "Lookup chain pattern: cache -> primary source -> fallback -> filename fallback"
  - "Lazy property pattern for optional API clients (None if no key)"

# Metrics
duration: 3min
completed: 2026-02-15
---

# Phase 5 Plan 2: Metadata Lookup Clients Summary

**TMDB/AniList/TVDB API clients with MetadataResolver orchestrating anime-first lookup chain and normalized result format**

## Performance

- **Duration:** 3 min
- **Started:** 2026-02-15T16:24:07Z
- **Completed:** 2026-02-15T16:27:00Z
- **Tasks:** 2
- **Files created:** 4

## Accomplishments
- TMDBClient with 7 methods covering TV and movie search, details, external IDs, and season data
- AniListClient with GraphQL queries for anime/manga search and details, rate limited at 0.7s
- TVDBClient with JWT authentication, auto-refresh, and series/movie search
- MetadataResolver with AniList-first-for-anime, TMDB-primary, TVDB-fallback lookup chain
- All clients handle errors gracefully (return None, log warnings, never crash)
- Normalized result dicts ensure consistent format regardless of metadata source

## Task Commits

Each task was committed atomically:

1. **Task 1: TMDB and AniList API clients** - `fad151b` (feat)
2. **Task 2: TVDB client and MetadataResolver orchestrator** - `3f447b1` (feat)

## Files Created/Modified
- `backend/metadata/__init__.py` - MetadataResolver orchestrating TMDB/AniList/TVDB lookup chain with DB caching
- `backend/metadata/tmdb_client.py` - TMDB API v3 client with Bearer token auth, search and detail endpoints
- `backend/metadata/anilist_client.py` - AniList GraphQL client with rate limiting, anime/manga search
- `backend/metadata/tvdb_client.py` - TVDB API v4 client with JWT auth and automatic token refresh

## Decisions Made
- MetadataResolver uses lazy client creation -- clients only instantiated when API keys provided
- AniList always available (no API key), TMDB and TVDB require keys to be useful
- DB cache calls wrapped in try/except for graceful degradation when DB not initialized
- AniList rate limiting at 0.7s between calls (conservative approach for 90 req/min limit)
- TVDB JWT token cached for 24 hours with automatic refresh on expiry
- Anime detection: AniList-first lookup chain, plus TMDB heuristic (Animation genre + JP origin_country)
- Poster URLs: TMDB uses `https://image.tmdb.org/t/p/w500{path}`, AniList uses coverImage.large directly

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None

## User Setup Required

None - no external service configuration required. API keys are optional and configured at runtime.

## Next Phase Readiness
- Metadata package ready for integration with standalone file scanner (05-03)
- MetadataResolver can be instantiated with API keys from config_entries
- All clients tested with invalid/missing keys -- graceful degradation confirmed

## Self-Check: PASSED

- FOUND: backend/metadata/__init__.py
- FOUND: backend/metadata/tmdb_client.py
- FOUND: backend/metadata/anilist_client.py
- FOUND: backend/metadata/tvdb_client.py
- FOUND: commit fad151b (Task 1)
- FOUND: commit 3f447b1 (Task 2)

---
*Phase: 05-standalone-mode*
*Completed: 2026-02-15*
