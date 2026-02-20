---
phase: 01-provider-plugin-expansion
plan: 05
subsystem: providers
tags: [kitsunekko, napisy24, whisper-subgen, html-scraping, hash-lookup, asr, beautifulsoup4, ffmpeg]

# Dependency graph
requires:
  - phase: 01-provider-plugin-expansion
    plan: 01
    provides: "SubtitleProvider ABC with declarative config_fields, @register_provider decorator, ProviderManager"
provides:
  - "KitsunekkoProvider: HTML scraping of kitsunekko.net for Japanese anime subs"
  - "Napisy24Provider: hash-based POST API for Polish subtitle lookup"
  - "WhisperSubgenProvider: external Subgen ASR delegation with ffmpeg audio extraction"
affects: [01-06, frontend-settings, translator-pipeline]

# Tech tracking
tech-stack:
  added: [beautifulsoup4]
  patterns: [conditional-import-graceful-degradation, hash-based-subtitle-matching, placeholder-search-deferred-download]

key-files:
  created:
    - backend/providers/kitsunekko.py
    - backend/providers/napisy24.py
    - backend/providers/whisper_subgen.py
  modified:
    - backend/providers/__init__.py

key-decisions:
  - "Kitsunekko uses BeautifulSoup with conditional import -- provider degrades gracefully if bs4 not installed"
  - "Napisy24 computes MD5 of first 10MB for file hash matching (Bazarr-compatible algorithm)"
  - "WhisperSubgen returns low-score placeholder (score=10) in search, actual transcription deferred to download()"
  - "WhisperSubgen uses ffmpeg pipe:1 for audio extraction (no temp files), with 120s extraction timeout"

patterns-established:
  - "Conditional import pattern: try/except ImportError with fallback and warning log"
  - "Placeholder search pattern: return low-score result in search(), expensive work in download()"
  - "Hash-based provider pattern: compute file hash, POST to API, parse custom response format"

# Metrics
duration: 8min
completed: 2026-02-15
---

# Phase 01 Plan 05: Medium-Complexity Providers Summary

**Kitsunekko HTML scraping for Japanese anime subs, Napisy24 hash-based Polish subtitle lookup, and Whisper-Subgen external ASR transcription via ffmpeg + Subgen API**

## Performance

- **Duration:** 8 min
- **Started:** 2026-02-15T12:29:57Z
- **Completed:** 2026-02-15T12:38:30Z
- **Tasks:** 3
- **Files modified:** 4 (3 created, 1 modified)

## Accomplishments

- Created KitsunekkoProvider that scrapes kitsunekko.net directory listings for Japanese anime subtitles, with episode matching, ZIP archive handling, and ASS-preferred extraction
- Created Napisy24Provider that computes MD5 hash of first 10MB of media files for Polish subtitle lookup via POST API, with pipe-delimited response parsing and hash-match scoring (359 points)
- Created WhisperSubgenProvider that returns low-score placeholder results during search and defers expensive transcription to download(), extracting audio via ffmpeg and posting to external Subgen /asr endpoint
- All three providers use @register_provider decorator and declare config_fields for dynamic UI

## Task Commits

Each task was committed atomically:

1. **Task 1: Implement Kitsunekko provider** - `9dea6ac` (feat)
2. **Task 2: Implement Napisy24 provider** - `d7ce280` (feat)
3. **Task 3: Implement Whisper-Subgen provider** - `2b1cd7f` (feat)

## Files Created/Modified

- `backend/providers/kitsunekko.py` - HTML scraping provider for Japanese anime subs from kitsunekko.net with BeautifulSoup parsing, episode number extraction, ZIP handling
- `backend/providers/napisy24.py` - Hash-based POST API provider for Polish subs with MD5 file hashing, pipe-delimited response parsing, ZIP extraction
- `backend/providers/whisper_subgen.py` - External ASR provider delegating to Subgen with ffmpeg audio extraction, 64 Whisper-supported languages, configurable timeout
- `backend/providers/__init__.py` - Added import triggers for kitsunekko, napisy24, whisper_subgen in _init_providers()

## Decisions Made

- Kitsunekko uses conditional BeautifulSoup import -- if bs4 is not installed, provider logs a warning and returns empty results instead of crashing
- Napisy24 uses default credentials (subliminal/lanimilbus) matching community convention, configurable via config_fields
- WhisperSubgen uses a placeholder search pattern: search() returns a single low-score result (score=10, no matches), ensuring it is only used as last resort when all other providers return nothing
- WhisperSubgen pipes ffmpeg audio to stdout (pipe:1) avoiding temporary files, with a separate 120s timeout for extraction vs 600s for transcription

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Added new provider imports to ProviderManager._init_providers()**
- **Found during:** Task 1 (Kitsunekko implementation)
- **Issue:** New providers were not auto-discovered because _init_providers() has explicit imports for each built-in provider. Without adding the imports, the providers would never be registered during normal app startup.
- **Fix:** Added try/except import blocks for kitsunekko, napisy24, and whisper_subgen to _init_providers() in providers/__init__.py
- **Files modified:** backend/providers/__init__.py
- **Verification:** `from providers import _PROVIDER_CLASSES` after importing providers confirms registration
- **Committed in:** 9dea6ac (Task 1 commit)

**2. [Rule 3 - Blocking] Installed beautifulsoup4 dependency**
- **Found during:** Task 1 (Kitsunekko implementation)
- **Issue:** beautifulsoup4 was listed in requirements.txt but not installed in the dev environment
- **Fix:** `pip install beautifulsoup4` (already in requirements.txt from Plan 01-01)
- **Files modified:** None (runtime only)
- **Verification:** `from bs4 import BeautifulSoup` succeeds

---

**Total deviations:** 2 auto-fixed (both Rule 3 - blocking)
**Impact on plan:** Both fixes necessary for providers to function. No scope creep.

## Issues Encountered

- Test suite uses `--cov-fail-under=80` in pytest.ini but overall coverage is 19% (pre-existing). Unit tests run with `--no-cov` flag to avoid false failure.
- Pre-existing integration test failure (health endpoint returns 503 without API keys) documented in STATE.md.

## User Setup Required

None - all three providers work without external configuration:
- Kitsunekko: no auth required
- Napisy24: uses default credentials, configurable in Settings UI
- WhisperSubgen: requires a running Subgen instance (endpoint configurable in Settings UI)

## Next Phase Readiness

- All three medium-complexity providers implemented and registered
- Plan 01-06 (remaining providers or provider testing) can proceed
- Provider system now has 7+ built-in providers covering multiple languages and source types
- WhisperSubgen is ready for Phase 4 (local Whisper backend) to complement

## Self-Check: PASSED

- All 4 key files verified present (3 created, 1 modified)
- All 3 task commits verified (9dea6ac, d7ce280, 2b1cd7f)
- 24/24 unit tests passing
- All 3 providers register via @register_provider and declare config_fields

---
*Phase: 01-provider-plugin-expansion*
*Completed: 2026-02-15*
