---
phase: 04-whisper-speech-to-text
plan: 01
subsystem: whisper
tags: [whisper, speech-to-text, faster-whisper, subgen, ffmpeg, audio-extraction, transcription]

# Dependency graph
requires:
  - phase: 00-architecture-refactoring
    provides: "db package with _db_lock pattern, circuit_breaker.py, config_entries"
  - phase: 02-translation-multi-backend
    provides: "TranslationBackend ABC + Manager singleton pattern to mirror"
  - phase: 03-media-server-abstraction
    provides: "MediaServer ABC + Manager pattern (JSON config variant)"
provides:
  - "WhisperBackend ABC with TranscriptionResult dataclass"
  - "WhisperManager singleton with lazy backend creation and circuit breakers"
  - "Audio extraction utilities (ffprobe track selection + ffmpeg WAV extraction)"
  - "WhisperQueue with Semaphore concurrency control and WebSocket progress"
  - "whisper_jobs DB table with full CRUD operations"
  - "FasterWhisperBackend (local GPU/CPU) with lazy model loading and VAD"
  - "SubgenBackend (external /asr API) with timeout and health check"
affects: [04-02, 04-03, whisper-api, whisper-settings-ui]

# Tech tracking
tech-stack:
  added: [faster-whisper (optional), ffprobe, ffmpeg]
  patterns: [WhisperBackend ABC, WhisperManager singleton, whisper.<name>.<key> config namespacing]

key-files:
  created:
    - backend/whisper/__init__.py
    - backend/whisper/base.py
    - backend/whisper/audio.py
    - backend/whisper/queue.py
    - backend/whisper/faster_whisper_backend.py
    - backend/whisper/subgen_backend.py
    - backend/db/whisper.py
  modified:
    - backend/db/__init__.py

key-decisions:
  - "WhisperManager uses single active backend (not fallback chain) -- only one Whisper instance runs at a time"
  - "whisper_backend config entry selects active backend (defaults to 'subgen')"
  - "Config namespaced as whisper.<name>.<key> in config_entries (mirrors backend.<name>.<key> pattern)"
  - "FasterWhisperBackend lazy-loads model (GPU memory released when idle, reloads on config change)"
  - "SubgenBackend import wrapped in try/except for graceful module-not-found handling"
  - "LANGUAGE_TAG_MAP covers 14 languages with ISO 639-1 and 639-2 variants (no external dependency)"
  - "WhisperQueue uses tempfile for extracted audio with guaranteed cleanup in finally block"

patterns-established:
  - "WhisperBackend ABC: name/display_name/config_fields/supports_gpu class attrs + transcribe/health_check/get_available_models abstract methods"
  - "Single-backend manager: get_active_backend() reads whisper_backend config entry (not fallback chain)"
  - "Audio extraction pipeline: ffprobe select track -> ffmpeg extract 16kHz mono WAV -> transcribe -> cleanup temp"

# Metrics
duration: 5min
completed: 2026-02-15
---

# Phase 4 Plan 1: Whisper Core Package Summary

**Complete whisper/ package with ABC, Manager singleton, audio extraction (ffprobe+ffmpeg), queue system, faster-whisper and Subgen backends, and whisper_jobs DB persistence**

## Performance

- **Duration:** 5 min
- **Started:** 2026-02-15T15:25:55Z
- **Completed:** 2026-02-15T15:31:24Z
- **Tasks:** 2
- **Files created:** 7
- **Files modified:** 1

## Accomplishments
- WhisperBackend ABC with TranscriptionResult following established translation/base.py pattern
- WhisperManager singleton with single active backend, lazy creation, circuit breaker, config_entries integration
- Audio extraction utilities: ffprobe stream selection with ISO 639 language mapping, ffmpeg WAV extraction
- WhisperQueue with Semaphore-based concurrency (default 1), WebSocket progress events, temp file cleanup
- whisper_jobs table with schema DDL + migration + full CRUD (create, update, get, list, delete, stats)
- FasterWhisperBackend with lazy model loading, VAD filtering, GPU/CPU auto-detection, 7 config fields
- SubgenBackend wrapping external /asr HTTP endpoint with timeout and health check

## Task Commits

Each task was committed atomically:

1. **Task 1: WhisperBackend ABC, Manager, audio extraction, queue, and DB schema** - `d1c0191` (feat)
2. **Task 2: faster-whisper and Subgen backend implementations** - `cb17379` (feat)

## Files Created/Modified
- `backend/whisper/base.py` - WhisperBackend ABC and TranscriptionResult dataclass
- `backend/whisper/__init__.py` - WhisperManager singleton with registry and circuit breakers
- `backend/whisper/audio.py` - Audio track selection (ffprobe) and extraction (ffmpeg)
- `backend/whisper/queue.py` - WhisperQueue with Semaphore concurrency and progress tracking
- `backend/whisper/faster_whisper_backend.py` - Local faster-whisper transcription backend
- `backend/whisper/subgen_backend.py` - External Subgen API transcription backend
- `backend/db/whisper.py` - whisper_jobs table CRUD operations
- `backend/db/__init__.py` - Added whisper_jobs table DDL to SCHEMA + migration

## Decisions Made
- WhisperManager uses single active backend (not fallback chain) -- only one Whisper instance runs at a time, unlike translation which chains backends
- whisper_backend config entry selects active backend, defaults to "subgen" for zero-config Docker setups
- Config namespaced as whisper.<name>.<key> in config_entries, consistent with backend.<name>.<key> for translation
- FasterWhisperBackend lazy-loads model and caches until model_size/device/compute_type changes
- SubgenBackend import wrapped in try/except ImportError (not just the faster-whisper guard) for resilience during development
- LANGUAGE_TAG_MAP dict covers 14 common anime/media languages with both ISO 639-1 and 639-2 codes

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Wrapped SubgenBackend import in try/except in __init__.py**
- **Found during:** Task 1 (WhisperManager verification)
- **Issue:** `_register_builtin_backends` imported SubgenBackend directly, but subgen_backend.py did not exist yet (created in Task 2), causing ModuleNotFoundError
- **Fix:** Wrapped SubgenBackend import in try/except ImportError, matching the pattern used for FasterWhisperBackend
- **Files modified:** backend/whisper/__init__.py
- **Verification:** `get_whisper_manager()` imports cleanly even before backend files exist
- **Committed in:** d1c0191 (Task 1 commit)

---

**Total deviations:** 1 auto-fixed (1 blocking)
**Impact on plan:** Necessary for cross-task import resilience. No scope creep.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Whisper package is self-contained and ready for Plan 02 (API endpoints + settings wiring)
- Plan 03 (frontend UI) can reference the backend types once Plan 02 exposes them via /api/v1/
- No blockers identified

## Self-Check: PASSED

All 7 created files verified present. Both task commits (d1c0191, cb17379) verified in git log.

---
*Phase: 04-whisper-speech-to-text*
*Completed: 2026-02-15*
