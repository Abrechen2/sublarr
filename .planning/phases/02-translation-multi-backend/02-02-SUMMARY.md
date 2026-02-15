---
phase: 02-translation-multi-backend
plan: 02
subsystem: translation
tags: [deepl, libretranslate, translation-backend, glossary, rest-api]

# Dependency graph
requires:
  - phase: 02-translation-multi-backend
    provides: "TranslationBackend ABC, TranslationManager registry, TranslationResult dataclass"
provides:
  - "DeepL translation backend with official SDK, glossary caching, Free/Pro auto-detection"
  - "LibreTranslate backend with per-line REST API translation"
  - "Both backends registered in TranslationManager alongside Ollama"
affects: [02-06]

# Tech tracking
tech-stack:
  added: ["deepl>=1.20.0"]
  patterns:
    - "Import guard pattern for optional SDK dependencies (try/except ImportError)"
    - "Lazy client creation via _get_client() with cached instance"
    - "Glossary cache keyed by (source_lang, target_lang) tuple"

key-files:
  created:
    - backend/translation/deepl_backend.py
    - backend/translation/libretranslate.py
  modified:
    - backend/translation/__init__.py
    - backend/requirements.txt

key-decisions:
  - "DeepL glossary cached by (source, target) pair -- avoids re-creating glossaries on every batch"
  - "LibreTranslate translates line-by-line (not batched) to guarantee 1:1 line mapping"
  - "DeepL import guarded with try/except -- backend class loads even without deepl SDK installed"
  - "Both backends return TranslationResult with success=False on error instead of raising exceptions"

patterns-established:
  - "API backend pattern: translate_batch wraps external API, returns TranslationResult, catches all exceptions"
  - "Optional SDK pattern: import guard + _AVAILABLE flag + RuntimeError in translate_batch if SDK missing"
  - "Language code mapping via module-level dict + static helper function"

# Metrics
duration: 2min
completed: 2026-02-15
---

# Phase 2 Plan 2: DeepL + LibreTranslate API Backends Summary

**DeepL backend with official SDK, glossary caching, and Free/Pro auto-detection plus LibreTranslate self-hosted backend with per-line REST translation -- both registered in TranslationManager**

## Performance

- **Duration:** 2 min
- **Started:** 2026-02-15T13:32:55Z
- **Completed:** 2026-02-15T13:35:05Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments
- DeepL backend using official SDK with lazy client creation, native glossary caching by language pair, and auto-detection of Free/Pro plan from API key suffix
- LibreTranslate backend translating line-by-line via REST API with configurable URL, optional API key, and request timeout
- Both backends registered in TranslationManager with proper import guarding for optional deepl dependency
- TranslationManager.get_all_backends() now returns all three backends (ollama, deepl, libretranslate)

## Task Commits

Each task was committed atomically:

1. **Task 1: Implement DeepL translation backend** - `ca3b1e8` (feat)
2. **Task 2: Implement LibreTranslate backend and register both backends** - `b2afee9` (feat)

## Files Created/Modified
- `backend/translation/deepl_backend.py` - DeepL backend with SDK integration, glossary caching, health check, usage reporting
- `backend/translation/libretranslate.py` - LibreTranslate backend with per-line REST API translation
- `backend/translation/__init__.py` - Register DeepLBackend (with ImportError guard) and LibreTranslateBackend
- `backend/requirements.txt` - Added deepl>=1.20.0

## Decisions Made
- DeepL glossary cached by (source, target) language pair to avoid re-creating glossaries on every translation batch call
- LibreTranslate translates one line at a time (max_batch_size=1) to guarantee exact 1:1 line mapping -- batching may be added later as config option
- DeepL SDK import wrapped in try/except with _DEEPL_AVAILABLE flag -- allows the class to load for registration even without the SDK installed
- Both backends catch all exceptions in translate_batch and return TranslationResult(success=False) rather than propagating exceptions up

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required. Users will configure API keys through the Settings UI when they choose to enable DeepL or LibreTranslate.

## Next Phase Readiness
- Two API backends complete, ready for OpenAI-compatible backend (02-03) and Google Cloud Translation (02-04)
- TranslationManager now has 3 backends available for fallback chain configuration
- Glossary support active for DeepL; LibreTranslate correctly reports supports_glossary=False
- No blockers for next plans

## Self-Check: PASSED

All 4 files verified present. Both commit hashes (ca3b1e8, b2afee9) confirmed in git log.

---
*Phase: 02-translation-multi-backend*
*Completed: 2026-02-15*
