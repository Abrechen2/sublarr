---
phase: 02-translation-multi-backend
plan: 01
subsystem: translation
tags: [abc, ollama, llm, translation-backend, circuit-breaker, sqlite]

# Dependency graph
requires:
  - phase: 00-architecture-refactoring
    provides: "db/ package structure, config.py Settings, circuit_breaker.py"
  - phase: 01-provider-plugin-expansion
    provides: "Plugin config storage pattern (config_entries namespacing), circuit breaker integration"
provides:
  - "TranslationBackend ABC with translate_batch, health_check, get_config_fields contract"
  - "TranslationManager singleton with registry, lazy config loading, fallback chain orchestration"
  - "Shared LLM utilities (prompt building, response parsing, CJK hallucination detection)"
  - "OllamaBackend implementing TranslationBackend ABC"
  - "translation_backend_stats table for per-backend metrics"
  - "language_profiles.translation_backend and fallback_chain_json columns"
affects: [02-02, 02-03, 02-04, 02-05, 02-06]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "TranslationBackend ABC (mirrors SubtitleProvider ABC from providers/base.py)"
    - "TranslationManager singleton with lazy backend creation from config_entries"
    - "backend.<name>.<key> config namespacing in config_entries table"
    - "Pydantic Settings fallback for Ollama migration compatibility"

key-files:
  created:
    - backend/translation/__init__.py
    - backend/translation/base.py
    - backend/translation/llm_utils.py
    - backend/translation/ollama.py
  modified:
    - backend/db/__init__.py
    - backend/db/translation.py
    - backend/db/profiles.py

key-decisions:
  - "Shared LLM utilities extracted as standalone module (not ABC methods) -- reusable by all LLM backends"
  - "OllamaBackend reads config from config_entries with Pydantic Settings fallback for migration"
  - "TranslationManager uses lazy backend creation -- misconfigured backends don't break others"
  - "Circuit breakers per backend reuse existing CircuitBreaker class from provider system"

patterns-established:
  - "TranslationBackend ABC: all backends implement translate_batch, health_check, get_config_fields"
  - "Backend config loaded from config_entries with backend.<name>.<key> namespacing"
  - "TranslationResult dataclass as standardized return type for all backends"
  - "Fallback chain orchestration with circuit breaker skip for OPEN backends"

# Metrics
duration: 5min
completed: 2026-02-15
---

# Phase 2 Plan 1: Translation Backend ABC + Ollama Migration Summary

**TranslationBackend ABC with registry manager, shared LLM utilities, and OllamaBackend as first implementation -- plus database schema for backend stats and per-profile backend selection**

## Performance

- **Duration:** 5 min
- **Started:** 2026-02-15T13:25:08Z
- **Completed:** 2026-02-15T13:30:27Z
- **Tasks:** 2
- **Files modified:** 7

## Accomplishments
- TranslationBackend ABC defines the contract for all 5 planned backends (translate_batch, health_check, get_config_fields, get_usage)
- OllamaBackend preserves all existing Ollama translation logic (batch, retry, CJK hallucination detection, single-line fallback) within the new ABC
- Shared LLM utilities extracted from ollama_client.py (prompt building, response parsing, CJK detection) for reuse by OpenAI-compatible backend
- TranslationManager singleton handles backend registration, lazy instance creation, config loading from config_entries, circuit breaker integration, and fallback chain orchestration
- Database schema extended with translation_backend_stats table and language_profiles backend columns without breaking existing data

## Task Commits

Each task was committed atomically:

1. **Task 1: Create translation package with ABC, LLM utilities, and OllamaBackend** - `77890fb` (feat)
2. **Task 2: Extend database schema with backend stats table and profile columns** - `1c82b7a` (feat)

## Files Created/Modified
- `backend/translation/base.py` - TranslationBackend ABC + TranslationResult dataclass
- `backend/translation/llm_utils.py` - Shared LLM prompt building, response parsing, CJK hallucination detection
- `backend/translation/ollama.py` - OllamaBackend implementing TranslationBackend ABC with full retry/fallback logic
- `backend/translation/__init__.py` - TranslationManager singleton with registry, config loading, circuit breakers, fallback chain
- `backend/db/__init__.py` - Added translation_backend_stats DDL + language_profiles migration
- `backend/db/translation.py` - Added backend stats CRUD (record_success, record_failure, get_stats, reset)
- `backend/db/profiles.py` - Updated _row_to_profile and update_language_profile for translation_backend/fallback_chain

## Decisions Made
- Shared LLM utilities extracted as standalone module (translation/llm_utils.py) rather than ABC methods, since only LLM backends (Ollama, OpenAI-compat) need them while API backends (DeepL, Google, LibreTranslate) do not
- OllamaBackend applies Pydantic Settings fallback in constructor for seamless migration -- existing installations keep working without reconfiguring config_entries
- TranslationManager creates backend instances lazily on first use, so a misconfigured DeepL key does not prevent Ollama from working
- Circuit breakers per backend reuse the existing CircuitBreaker class from the provider system with same config settings

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- ABC foundation complete, ready for DeepL (02-02), LibreTranslate (02-03), OpenAI-compatible (02-04), and Google Cloud (02-05) backend implementations
- TranslationManager.translate_with_fallback() ready for integration into translator.py (02-06)
- Profile-based backend selection columns in place for wiring in 02-06
- No blockers for next plans

## Self-Check: PASSED

All 7 files verified present. Both commit hashes (77890fb, 1c82b7a) confirmed in git log.

---
*Phase: 02-translation-multi-backend*
*Completed: 2026-02-15*
