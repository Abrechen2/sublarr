---
phase: 04-whisper-speech-to-text
plan: 02
subsystem: whisper
tags: [whisper, api, blueprint, routes, case-d, translator, deprecation, flask]

# Dependency graph
requires:
  - phase: 04-whisper-speech-to-text
    plan: 01
    provides: "whisper/ package (WhisperManager, WhisperQueue, backends, db/whisper.py)"
  - phase: 00-architecture-refactoring
    provides: "routes/ blueprint registration pattern, config_entries DB"
  - phase: 02-translation-multi-backend
    provides: "backend management endpoint pattern (routes/translate.py)"
provides:
  - "Whisper API blueprint with 11 routes under /api/v1/whisper/"
  - "Case D in translator.py: Whisper fallback after all providers fail"
  - "Deprecated WhisperSubgenProvider (no-op search, error on download)"
affects: [04-03, whisper-settings-ui, whisper-frontend]

# Tech tracking
tech-stack:
  added: []
  patterns: [whisper API blueprint, Case D async whisper fallback, provider deprecation pattern]

key-files:
  created:
    - backend/routes/whisper.py
  modified:
    - backend/routes/__init__.py
    - backend/translator.py
    - backend/providers/whisper_subgen.py

key-decisions:
  - "WhisperQueue singleton in routes/whisper.py with lazy initialization and config-based concurrency"
  - "Case D returns whisper_pending status (async) -- does not block translate_file() return"
  - "WhisperSubgenProvider kept with @register_provider decorator to avoid import errors but all methods are no-ops"
  - "Global whisper config uses three keys: whisper_enabled, whisper_backend, max_concurrent_whisper"
  - "Backend config uses whisper.<name>.<key> namespacing consistent with Plan 01"

patterns-established:
  - "Provider deprecation: keep decorator + class, replace methods with warnings/no-ops, add module-level DeprecationWarning"
  - "Case D async integration: _is_whisper_enabled() guard + _submit_whisper_job() helper returning dict with whisper_pending status"

# Metrics
duration: 3min
completed: 2026-02-15
---

# Phase 4 Plan 2: Whisper API Wiring Summary

**Whisper API blueprint with 11 endpoints (transcribe, queue, backends, config, stats), Case D translator fallback, and deprecated WhisperSubgenProvider**

## Performance

- **Duration:** 3 min
- **Started:** 2026-02-15T15:34:22Z
- **Completed:** 2026-02-15T15:37:56Z
- **Tasks:** 2
- **Files created:** 1
- **Files modified:** 3

## Accomplishments
- Whisper API blueprint registered with 11 routes covering job submission, queue listing, backend management, config CRUD, and statistics
- Case D integrated into translate_file() as async Whisper fallback after Case C4 failure (returns whisper_pending status)
- WhisperSubgenProvider deprecated: search returns empty list, download raises error, module-level DeprecationWarning on import
- Blueprint registered in routes/__init__.py alongside existing 11 blueprints (now 12 total)

## Task Commits

Each task was committed atomically:

1. **Task 1: Whisper API blueprint and blueprint registration** - `7524f41` (feat)
2. **Task 2: Case D integration in translator.py and WhisperSubgenProvider deprecation** - `a5b3951` (feat)

## Files Created/Modified
- `backend/routes/whisper.py` - Whisper API blueprint with transcribe, queue, backends, config, and stats endpoints
- `backend/routes/__init__.py` - Added whisper_bp to blueprint registration list
- `backend/translator.py` - Added Case D (Whisper fallback), _is_whisper_enabled(), _submit_whisper_job() helpers
- `backend/providers/whisper_subgen.py` - Deprecated: no-op search, error on download, DeprecationWarning on import

## Decisions Made
- WhisperQueue singleton in routes/whisper.py uses lazy initialization -- created on first API call, not at import time
- Case D is async by design: returns whisper_pending immediately, actual transcription runs in queue worker thread
- WhisperSubgenProvider kept registered via @register_provider to avoid breaking provider_manager enumeration
- Global config endpoint restricted to three known keys (whisper_enabled, whisper_backend, max_concurrent_whisper) for safety
- Queue singleton resets when max_concurrent_whisper changes via config PUT endpoint

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- All Whisper API endpoints are wired and serving
- Plan 03 (frontend UI) can now build against /api/v1/whisper/ endpoints
- Case D is guarded by whisper_enabled config entry (defaults to false, no behavior change until explicitly enabled)
- No blockers identified

## Self-Check: PASSED

All files verified present. Both task commits (7524f41, a5b3951) verified in git log.

---
*Phase: 04-whisper-speech-to-text*
*Completed: 2026-02-15*
