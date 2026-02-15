---
phase: 04-whisper-speech-to-text
plan: 03
subsystem: whisper-frontend
tags: [whisper, frontend, react, typescript, settings-ui, tanstack-query, collapsible-cards]

# Dependency graph
requires:
  - phase: 04-whisper-speech-to-text
    plan: 02
    provides: "Whisper API blueprint with 11 routes under /api/v1/whisper/"
  - phase: 03-media-server-abstraction
    plan: 03
    provides: "MediaServersTab collapsible card pattern in Settings.tsx"
  - phase: 02-translation-multi-backend
    plan: 05
    provides: "TranslationBackendsTab and BackendCard pattern in Settings.tsx"
provides:
  - "WhisperBackendInfo, WhisperJob, WhisperConfig, WhisperStats, WhisperHealthResult TypeScript interfaces"
  - "11 Whisper API client functions in client.ts"
  - "8 React Query hooks for Whisper data fetching"
  - "Whisper Settings tab with global config and backend cards"
affects: [whisper-queue-ui, whisper-dashboard, whisper-activity]

# Tech tracking
tech-stack:
  added: []
  patterns: [WhisperBackendCard collapsible pattern, WhisperTab global config + cards layout]

key-files:
  created: []
  modified:
    - frontend/src/lib/types.ts
    - frontend/src/api/client.ts
    - frontend/src/hooks/useApi.ts
    - frontend/src/pages/Settings.tsx

key-decisions:
  - "WhisperBackendCard is a separate component from BackendCard -- different props (WhisperBackendInfo vs TranslationBackendInfo) and model info table for faster_whisper"
  - "WhisperTab combines global config section (enable/disable, backend selection, max concurrent) with backend cards below"
  - "Toggle switch for whisper_enabled uses inline CSS transition (no library dependency)"
  - "Model info table for faster_whisper shown only when that backend card is expanded"

patterns-established:
  - "Whisper backend card pattern: same collapsible layout as TranslationBackendsTab but with GPU and Language Detection badges instead of Glossary badge"
  - "Global config + backend cards layout: config section in a bordered card at top, backend cards below"

# Metrics
duration: 5min
completed: 2026-02-15
---

# Phase 4 Plan 3: Whisper Frontend Settings UI Summary

**Whisper Settings tab with global config (enable/disable, backend selection, max concurrent), collapsible backend cards with config forms and test buttons, and model info table for faster-whisper**

## Performance

- **Duration:** 5 min
- **Started:** 2026-02-15T15:40:15Z
- **Completed:** 2026-02-15T15:45:24Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments
- TypeScript types for all Whisper entities (WhisperBackendInfo, WhisperJob, WhisperConfig, WhisperStats, WhisperHealthResult)
- 11 API client functions covering all Whisper endpoints (backends, config, queue, jobs, stats)
- 8 React Query hooks with proper caching, invalidation, and auto-refresh intervals
- Whisper tab in Settings with global config section (enable/disable toggle, backend dropdown, max concurrent slider)
- Collapsible WhisperBackendCard with dynamic config form, password show/hide toggle, test button, and save button
- Model info table for faster-whisper showing all available models with approximate VRAM sizes

## Task Commits

Each task was committed atomically:

1. **Task 1: TypeScript types, API client functions, and React Query hooks** - `8c50126` (feat)
2. **Task 2: Whisper Settings tab with backend cards and global config** - `a226dc7` (feat)

## Files Created/Modified
- `frontend/src/lib/types.ts` - Added WhisperBackendInfo, WhisperJob, WhisperConfig, WhisperStats, WhisperHealthResult interfaces
- `frontend/src/api/client.ts` - Added 11 Whisper API client functions (getWhisperBackends, testWhisperBackend, etc.)
- `frontend/src/hooks/useApi.ts` - Added 8 React Query hooks (useWhisperBackends, useWhisperConfig, useWhisperStats, etc.)
- `frontend/src/pages/Settings.tsx` - Added WhisperBackendCard component, WhisperTab component, Whisper tab routing, and model info table

## Decisions Made
- WhisperBackendCard is separate from BackendCard because the prop shapes differ (WhisperBackendInfo has supports_gpu/supports_language_detection vs TranslationBackendInfo has supports_glossary/max_batch_size)
- WhisperTab renders global config section above backend cards (unlike TranslationBackendsTab which has no global config)
- Toggle switch for whisper_enabled uses pure CSS transition (no third-party toggle component)
- Model info table only shown inside faster_whisper backend card when expanded (not cluttering subgen card)

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Phase 4 (Whisper Speech-to-Text) is fully complete -- all 3 plans executed
- Backend: whisper package (managers, backends, DB), API blueprint (11 routes), Case D translator fallback
- Frontend: TypeScript types, API client, React Query hooks, Settings UI with backend management
- Users can configure faster-whisper or Subgen from the browser, test connections, and enable Whisper as a fallback
- No blockers for subsequent phases

## Self-Check: PASSED

All files verified present. Both task commits (8c50126, a226dc7) verified in git log.

---
*Phase: 04-whisper-speech-to-text*
*Completed: 2026-02-15*
