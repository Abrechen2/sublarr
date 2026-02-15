---
phase: 02-translation-multi-backend
plan: 03
subsystem: translation
tags: [openai, google-cloud-translate, llm, translation-backend, multi-backend]

# Dependency graph
requires:
  - phase: 02-translation-multi-backend/01
    provides: "TranslationBackend ABC, TranslationManager, shared LLM utilities, OllamaBackend"
provides:
  - "OpenAICompatBackend supporting OpenAI, Azure OpenAI, LM Studio, vLLM via base_url"
  - "GoogleTranslateBackend using Cloud Translation v3 SDK with credentials management"
  - "All 5 translation backends registered in TranslationManager"
affects: [02-04, 02-05, 02-06]

# Tech tracking
tech-stack:
  added: [openai>=1.0.0, google-cloud-translate>=3.10.0]
  patterns:
    - "OpenAI-compatible backend shares LLM utilities with Ollama (prompt building, response parsing, CJK detection)"
    - "API backends (Google) use direct SDK calls without LLM utilities"
    - "Import guards with graceful degradation for all optional packages"

key-files:
  created:
    - backend/translation/openai_compat.py
    - backend/translation/google_translate.py
  modified:
    - backend/translation/__init__.py
    - backend/requirements.txt

key-decisions:
  - "OpenAI-compatible backend handles retries internally (max_retries=0 on SDK client) for consistent retry logic with CJK hallucination detection"
  - "Google backend creates fresh client per call (no lazy caching) since credentials may change via env var"
  - "Both backends register via try/except ImportError guards -- missing packages don't break app startup"

patterns-established:
  - "LLM backends (Ollama, OpenAI-compat) share llm_utils for prompt/parse; API backends (DeepL, LibreTranslate, Google) do not"
  - "Optional backend packages listed in requirements.txt but wrapped in import guards at module level"

# Metrics
duration: 3min
completed: 2026-02-15
---

# Phase 2 Plan 3: OpenAI-Compatible + Google Cloud Translation Backends Summary

**OpenAI-compatible backend covering OpenAI/Azure/LM Studio/vLLM via configurable base_url, plus Google Cloud Translation v3 backend with native batch and glossary support -- completing all 5 translation backends**

## Performance

- **Duration:** 3 min
- **Started:** 2026-02-15T13:33:54Z
- **Completed:** 2026-02-15T13:36:56Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments
- OpenAI-compatible backend reuses shared LLM utilities (build_translation_prompt, parse_llm_response, has_cjk_hallucination) with OllamaBackend
- Google Cloud Translation backend uses v3 SDK with credentials via service account JSON or GOOGLE_APPLICATION_CREDENTIALS env var
- All 5 backends registered in TranslationManager: ollama, deepl, libretranslate, openai_compat, google
- Missing optional packages (openai, google-cloud-translate, deepl) degrade gracefully without breaking app startup

## Task Commits

Each task was committed atomically:

1. **Task 1: Implement OpenAI-compatible translation backend** - `7492812` (feat)
2. **Task 2: Implement Google Cloud Translation backend and register both backends** - `ca28401` (feat)

## Files Created/Modified
- `backend/translation/openai_compat.py` - OpenAI-compatible backend with lazy client, retry/backoff, CJK detection
- `backend/translation/google_translate.py` - Google Cloud Translation v3 backend with credentials management
- `backend/translation/__init__.py` - Registered openai_compat and google backends with import guards
- `backend/requirements.txt` - Added openai>=1.0.0 and google-cloud-translate>=3.10.0

## Decisions Made
- OpenAI-compatible backend sets `max_retries=0` on the SDK client and handles retries internally, so CJK hallucination detection and line-count mismatch checks happen between retries
- Google backend creates a fresh TranslationServiceClient per call rather than caching, since credentials_path may change via config_entries at runtime
- Both new backends use module-level try/except ImportError guards, logging a warning but still defining the class so it can be registered

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required. Backends are optional and activate when configured via Settings UI.

## Next Phase Readiness
- All 5 translation backends now implemented and registered
- Ready for 02-04 (Settings UI for backend configuration), 02-05 (backend testing), and 02-06 (translator.py integration)
- No blockers for next plans

## Self-Check: PASSED

All 4 files verified present. Both commit hashes (7492812, ca28401) confirmed in git log.

---
*Phase: 02-translation-multi-backend*
*Completed: 2026-02-15*
