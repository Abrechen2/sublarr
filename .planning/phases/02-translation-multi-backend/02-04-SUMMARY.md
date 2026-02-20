---
phase: 02-translation-multi-backend
plan: 04
subsystem: translation
tags: [translation-manager, multi-backend, fallback-chain, language-profiles, api]

# Dependency graph
requires:
  - phase: 02-translation-multi-backend
    provides: "TranslationManager singleton, TranslationBackend ABC, all 5 backend implementations, backend stats DB"
provides:
  - "Profile-based backend selection in translator.py (replaces hardcoded ollama_client)"
  - "Fallback chain orchestration through TranslationManager.translate_with_fallback"
  - "Backend management API: list, test, configure, stats endpoints"
  - "Config hash includes backend_name for re-translation detection"
  - "Profile CRUD endpoints accept translation_backend and fallback_chain"
affects: [02-05, 02-06]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Profile-based backend resolution via _resolve_backend_for_context()"
    - "_translate_with_manager() returns (lines, TranslationResult) tuple for stats tracking"
    - "Backend config API with backend.<name>.<key> namespacing and password masking"

key-files:
  created: []
  modified:
    - backend/translator.py
    - backend/config.py
    - backend/routes/translate.py
    - backend/routes/profiles.py
    - backend/db/profiles.py

key-decisions:
  - "_translate_with_manager returns (lines, result) tuple to propagate backend_name for config hash and stats"
  - "Config hash formula changed: backend_name included, Ollama uses model+prompt[:50], non-Ollama uses backend_name+target_lang only"
  - "Synthetic default profile (no DB rows) includes translation_backend and fallback_chain to prevent KeyError"

patterns-established:
  - "_resolve_backend_for_context: profile lookup -> backend + chain extraction -> ensure primary in chain"
  - "Backend management API: list/test/config/stats under /api/v1/backends"
  - "Password field masking in config GET via config_fields type='password' metadata"

# Metrics
duration: 5min
completed: 2026-02-15
---

# Phase 2 Plan 4: Pipeline Integration + Backend API Summary

**Rewired translator.py to use TranslationManager with profile-based backend selection, fallback chains, and backend management REST API**

## Performance

- **Duration:** 5 min
- **Started:** 2026-02-15T13:39:53Z
- **Completed:** 2026-02-15T13:45:07Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments
- translator.py uses TranslationManager.translate_with_fallback() for ALL translation paths (embedded ASS, embedded SRT, external ASS, external SRT)
- Backend selection resolved from language profile assigned to series/movie, with default profile fallback
- Backend management API provides list, test, configure, and stats endpoints for all 5 backends
- Config hash includes backend_name so switching from Ollama to DeepL triggers re-translation detection
- Profile CRUD endpoints accept translation_backend and fallback_chain for per-profile backend configuration

## Task Commits

Each task was committed atomically:

1. **Task 1: Rewire translator.py to use TranslationManager** - `3bdad29` (feat)
2. **Task 2: Add backend management API and profile backend selection** - `2f3ad0e` (feat)

## Files Created/Modified
- `backend/translator.py` - Replaced ollama_client.translate_all with _translate_with_manager using TranslationManager
- `backend/config.py` - Updated get_translation_config_hash to accept backend_name parameter
- `backend/routes/translate.py` - Added 5 backend management endpoints (list, test, save config, get config, stats)
- `backend/routes/profiles.py` - Extended POST/PUT to accept translation_backend and fallback_chain
- `backend/db/profiles.py` - Updated create_language_profile with backend params, added fields to synthetic default

## Decisions Made
- _translate_with_manager returns a tuple (translated_lines, TranslationResult) so callers can access backend_name for config hash recording and stats tracking
- Config hash for non-Ollama backends excludes model and prompt (irrelevant for API backends like DeepL/Google), using format: `{backend_name}||{target_language}`
- Synthetic default profile (when no DB rows exist) includes translation_backend="ollama" and fallback_chain=["ollama"] to prevent KeyError during resolution

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Added translation_backend and fallback_chain to synthetic default profile**
- **Found during:** Task 2 (profile endpoint verification)
- **Issue:** get_default_profile() returns synthetic dict when no profiles exist in DB, but it was missing translation_backend and fallback_chain fields, which would cause KeyError in _resolve_backend_for_context()
- **Fix:** Added translation_backend="ollama" and fallback_chain=["ollama"] to the synthetic default
- **Files modified:** backend/db/profiles.py
- **Verification:** _resolve_backend_for_context(None, "de") returns ("ollama", ["ollama"]) correctly
- **Committed in:** 2f3ad0e (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (1 bug fix)
**Impact on plan:** Essential fix for correctness -- prevents crash when no profile rows exist. No scope creep.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Full multi-backend pipeline operational: profile -> backend resolution -> TranslationManager -> fallback chain
- Backend management API ready for frontend integration
- All 5 backends (Ollama, DeepL, LibreTranslate, OpenAI-compat, Google) wired through TranslationManager
- Ready for Plan 05 (Settings UI for backend configuration) and Plan 06 (end-to-end testing)

## Self-Check: PASSED

All 5 modified files verified present. Both commit hashes (3bdad29, 2f3ad0e) confirmed in git log.

---
*Phase: 02-translation-multi-backend*
*Completed: 2026-02-15*
