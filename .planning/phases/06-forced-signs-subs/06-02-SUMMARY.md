---
phase: 06-forced-signs-subs
plan: 02
subsystem: scanner, search, providers
tags: [forced-subs, wanted-scanner, wanted-search, opensubtitles, provider-manager, classification]

# Dependency graph
requires:
  - phase: 06-forced-signs-subs
    plan: 01
    provides: "forced_detection.py, VideoQuery.forced_only, subtitle_type on wanted_items, get_forced_output_path"
provides:
  - "Scanner creates forced wanted items for profiles with forced_preference=separate"
  - "OpenSubtitles foreign_parts_only parsing for native forced detection"
  - "ProviderManager post-search forced classification via classify_forced_result"
  - "Forced-aware search pipeline: forced_only flag, forced output paths, skip translation"
affects: [06-03, routes, frontend]

# Tech tracking
tech-stack:
  added: []
  patterns: ["single-pass search with post-classification", "forced download-only pipeline (no translation)"]

key-files:
  created: []
  modified:
    - backend/wanted_scanner.py
    - backend/wanted_search.py
    - backend/providers/opensubtitles.py
    - backend/providers/__init__.py

key-decisions:
  - "Scanner creates forced wanted items only for forced_preference=separate; auto and disabled do not create dedicated items"
  - "OpenSubtitles filters results at provider level based on foreign_parts_only + query.forced_only"
  - "ProviderManager classifies results post-search using classify_forced_result for providers without native forced support"
  - "Forced subtitles are download-only -- no translation step (per research recommendation)"
  - "Single-pass search pattern: search once, classify results, no double-searching (avoids research pitfall #5)"
  - "Forced wanted item titles include [Forced] suffix for UI clarity"

patterns-established:
  - "Forced download-only pipeline: search with forced_only, save to .lang.forced.ext, skip translation"
  - "Post-search forced classification: providers that support forced natively filter at search time, others get classified after"

# Metrics
duration: 5min
completed: 2026-02-15
---

# Phase 6 Plan 02: Scanner & Search Pipeline Forced Integration Summary

**Forced subtitle wiring into scanner (wanted item creation by profile preference) and search pipeline (single-pass classification, forced-only download path, OpenSubtitles foreign_parts_only) with no-translation forced download pattern**

## Performance

- **Duration:** 5 min
- **Started:** 2026-02-15T17:37:10Z
- **Completed:** 2026-02-15T17:42:54Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments
- Scanner creates forced wanted items when profile has forced_preference="separate", skips for "auto" and "disabled"
- OpenSubtitles provider parses foreign_parts_only from API response and filters results based on query.forced_only
- ProviderManager post-search classification catches forced results from providers without native support (AnimeTosho, Jimaku, SubDL)
- Forced wanted items follow download-only path: no translation step, saved to .lang.forced.ext
- build_query_from_wanted automatically sets forced_only based on wanted item subtitle_type
- All 60 existing unit tests pass with no regressions

## Task Commits

Each task was committed atomically:

1. **Task 1: Scanner forced item creation + OpenSubtitles foreign_parts_only** - `4c5aa00` (feat)
2. **Task 2: Search pipeline forced-aware searching + ProviderManager** - `61433b6` (feat)

## Files Created/Modified
- `backend/wanted_scanner.py` - Forced wanted item creation for "separate" preference, explicit subtitle_type="full" on existing calls, import forced_detection
- `backend/providers/opensubtitles.py` - Parse foreign_parts_only, filter by forced_only, populate SubtitleResult.forced and provider_data
- `backend/providers/__init__.py` - Post-search classify_forced_result for all providers, forced_only post-filter
- `backend/wanted_search.py` - build_query_from_wanted sets forced_only, _process_forced_wanted_item download-only path, import get_forced_output_path

## Decisions Made
- Forced subtitle search for source language also included (download source-lang forced sub as fallback), since forced subs often only exist in one language
- OpenSubtitles filters at item level (before file loop) for efficiency -- if foreign_parts_only doesn't match forced_only, skip entire subtitle entry
- ProviderManager classification uses hasattr guard for provider_data to handle results from all provider types

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Scanner + search pipeline fully forced-aware, ready for Plan 03 (UI/frontend integration)
- All existing tests pass (60/60 unit tests, pre-existing integration failures unchanged)
- The forced pipeline is end-to-end: profile preference -> scanner -> wanted item -> search -> download -> save

## Self-Check: PASSED

- All 4 modified files verified on disk
- Commit `4c5aa00` (Task 1) verified in git log
- Commit `61433b6` (Task 2) verified in git log
- 60/60 unit tests passing

---
*Phase: 06-forced-signs-subs*
*Completed: 2026-02-15*
