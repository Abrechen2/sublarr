---
phase: 06-forced-signs-subs
plan: 01
subsystem: database, detection
tags: [sqlite, forced-subs, signs, detection, ffprobe, ass, data-model]

# Dependency graph
requires:
  - phase: 05-standalone-mode
    provides: "Database schema with wanted_items, language_profiles, subtitle_downloads tables"
provides:
  - "subtitle_type column on wanted_items and subtitle_downloads (full/forced/signs)"
  - "forced_preference column on language_profiles (disabled/separate/auto)"
  - "forced_detection.py multi-signal detection engine"
  - "VideoQuery.forced_only flag for provider search"
  - "get_forced_output_path() for standard forced naming"
  - "detect_existing_target_for_lang() subtitle_type parameter"
affects: [06-02, 06-03, wanted_scanner, wanted_search, providers]

# Tech tracking
tech-stack:
  added: []
  patterns: ["multi-signal detection with confidence scoring", "parallel wanted tracking by subtitle_type"]

key-files:
  created:
    - backend/forced_detection.py
  modified:
    - backend/db/__init__.py
    - backend/providers/base.py
    - backend/db/profiles.py
    - backend/db/wanted.py
    - backend/translator.py

key-decisions:
  - "Multi-signal detection uses priority-ordered signals (ffprobe > filename > title > ASS) with confidence scoring"
  - "classify_forced_result checks provider_data.foreign_parts_only (OpenSubtitles) before filename patterns"
  - "Lazy import of classify_styles inside detect_subtitle_type to avoid circular imports"
  - "VALID_FORCED_PREFERENCES validation in both create and update profile functions"
  - "subtitle_type added to wanted upsert uniqueness check (not DB UNIQUE constraint) per research recommendation"

patterns-established:
  - "Multi-signal agreement: 2+ signals agreeing returns highest confidence among them"
  - "Forced subtitle naming: {base}.{lang}.forced.{fmt} (Plex/Jellyfin/Emby/Kodi standard)"
  - "Parallel wanted items: same file + language can have both full and forced entries"

# Metrics
duration: 6min
completed: 2026-02-15
---

# Phase 6 Plan 01: Forced/Signs Data Model & Detection Summary

**Forced subtitle data model (subtitle_type, forced_preference) with multi-signal detection engine using ffprobe disposition, filename patterns, stream titles, and ASS style analysis**

## Performance

- **Duration:** 6 min
- **Started:** 2026-02-15T17:28:05Z
- **Completed:** 2026-02-15T17:34:22Z
- **Tasks:** 2
- **Files modified:** 6

## Accomplishments
- Database migrations add subtitle_type to wanted_items and subtitle_downloads, forced_preference to language_profiles
- Multi-signal forced detection engine (forced_detection.py) with confidence scoring
- VideoQuery extended with forced_only flag for provider search filtering
- Profile CRUD supports forced_preference with validation
- Wanted upsert enables parallel tracking (full + forced for same file/language)
- detect_existing_target_for_lang handles forced subtitle file paths
- get_forced_output_path generates standard forced naming convention

## Task Commits

Each task was committed atomically:

1. **Task 1: Database schema + forced_detection.py module** - `7ffe251` (feat)
2. **Task 2: Extend VideoQuery, profiles CRUD, wanted upsert, and detect_existing_target** - `bb3c1f9` (feat)

## Files Created/Modified
- `backend/forced_detection.py` - Multi-signal forced/signs subtitle detection engine with SUBTITLE_TYPES, detect_subtitle_type, is_forced_external_sub, classify_forced_result
- `backend/db/__init__.py` - Schema migrations for subtitle_type and forced_preference columns
- `backend/providers/base.py` - VideoQuery.forced_only field for provider filtering
- `backend/db/profiles.py` - forced_preference in profile CRUD with VALID_FORCED_PREFERENCES validation
- `backend/db/wanted.py` - subtitle_type parameter in upsert_wanted_item with extended uniqueness check
- `backend/translator.py` - detect_existing_target_for_lang subtitle_type parameter + get_forced_output_path function

## Decisions Made
- Multi-signal detection uses Counter-based vote aggregation for agreement checking
- classify_forced_result also checks fansub-style patterns like "Signs & Songs" in filenames
- detect_existing_target_for_lang explicitly ignores .forced. files when checking for "full" type (prevents cross-contamination)
- VALID_FORCED_PREFERENCES tuple defined at module level for reuse in create and update validation

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Data model foundation complete for Plans 02 (provider search integration) and 03 (UI/frontend)
- All existing tests pass (60/60 unit tests, pre-existing integration failures unchanged)
- forced_detection.py ready for import by wanted_scanner, wanted_search, and provider modules

---
*Phase: 06-forced-signs-subs*
*Completed: 2026-02-15*
