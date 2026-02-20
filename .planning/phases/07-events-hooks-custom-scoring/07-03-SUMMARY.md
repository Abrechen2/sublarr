---
phase: 07-events-hooks-custom-scoring
plan: 03
subsystem: api, ui
tags: [flask-blueprint, react, hooks, webhooks, scoring, event-catalog, settings-ui]

# Dependency graph
requires:
  - phase: 07-events-hooks-custom-scoring (plans 01-02)
    provides: event system (blinker signals, EVENT_CATALOG), db/hooks.py CRUD, db/scoring.py CRUD, HookEngine, WebhookDispatcher
provides:
  - routes/hooks.py Blueprint with 18+ API endpoints for event catalog, hooks, webhooks, logs, scoring weights, provider modifiers
  - TypeScript interfaces for all hook/webhook/scoring types
  - React Query hooks and API client functions for all CRUD operations
  - Settings "Events & Hooks" tab with hook/webhook management, test buttons, execution log
  - Settings "Scoring" tab with episode/movie weight editors and provider modifier sliders
affects: [08-i18n-frontend, 09-openapi-docs]

# Tech tracking
tech-stack:
  added: []
  patterns: [collapsible-section-pattern, inline-add-edit-form, range-slider-modifier]

key-files:
  created:
    - backend/routes/hooks.py
  modified:
    - backend/routes/__init__.py
    - backend/db/hooks.py
    - frontend/src/lib/types.ts
    - frontend/src/api/client.ts
    - frontend/src/hooks/useApi.ts
    - frontend/src/pages/Settings.tsx

key-decisions:
  - "clear_hook_logs() added to db/hooks.py for DELETE /hooks/logs endpoint (missing from Plan 02)"
  - "Webhook test with event_name='*' uses 'config_updated' as sample event (needs a real event name for catalog payload keys)"
  - "ScoringTab initializes local state from query data with weightsInit/modsInit guard to avoid re-clobbering user edits"
  - "Provider modifiers rendered as range sliders (-100 to +100) with color-coded values"

patterns-established:
  - "EventsHooksTab: collapsible section pattern for hooks/webhooks/logs matching TranslationBackendsTab and MediaServersTab"
  - "Scoring weight tables: side-by-side episode/movie with editable inputs and default reference values"
  - "Provider modifier sliders: range input with green/red/grey color coding for bonus/malus/neutral"

# Metrics
duration: 10min
completed: 2026-02-15
---

# Phase 7 Plan 3: API & Frontend UI for Events/Hooks and Scoring Summary

**hooks Blueprint with 18+ endpoints for event catalog, hook/webhook CRUD, execution logs, scoring weights, and provider modifiers; Settings UI with Events & Hooks tab and Scoring tab**

## Performance

- **Duration:** 10 min
- **Started:** 2026-02-15T19:18:32Z
- **Completed:** 2026-02-15T19:28:49Z
- **Tasks:** 2
- **Files modified:** 7

## Accomplishments
- hooks Blueprint registered with full CRUD for shell hooks, webhooks, hook logs, scoring weights, and provider modifiers (18+ endpoints)
- Settings "Events & Hooks" tab: hook cards with enable/test/edit/delete, webhook cards with status badges, event catalog dropdown, inline add/edit forms, execution log table with expandable details
- Settings "Scoring" tab: episode/movie weight editors with defaults shown, provider modifier range sliders with color coding, save and reset-to-defaults buttons

## Task Commits

Each task was committed atomically:

1. **Task 1: Create hooks Blueprint with CRUD + event catalog + scoring API** - `ba5fabe` (feat)
2. **Task 2: Frontend Settings tabs for Events/Hooks and Scoring** - `6fe9654` (feat)

## Files Created/Modified
- `backend/routes/hooks.py` - New Blueprint: event catalog, hook/webhook CRUD, logs, scoring weights, provider modifiers
- `backend/routes/__init__.py` - Register hooks_bp Blueprint
- `backend/db/hooks.py` - Added clear_hook_logs() helper
- `frontend/src/lib/types.ts` - EventCatalogItem, HookConfig, WebhookConfig, HookLog, HookTestResult, ScoringWeights, ProviderModifiers
- `frontend/src/api/client.ts` - 21 new API functions for events/hooks/scoring
- `frontend/src/hooks/useApi.ts` - 18 new React Query hooks for events/hooks/scoring
- `frontend/src/pages/Settings.tsx` - EventsHooksTab and ScoringTab components, two new tabs in TABS array

## Decisions Made
- clear_hook_logs() added to db/hooks.py (Rule 2 - missing functionality for DELETE /hooks/logs)
- Webhook test with wildcard event_name uses 'config_updated' as fallback for sample payload generation
- ScoringTab uses weightsInit/modsInit guard pattern to prevent query refetch from clobbering user edits
- Provider modifiers use range slider (-100 to +100) rather than number inputs for better UX

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] Added clear_hook_logs() to db/hooks.py**
- **Found during:** Task 1 (hooks Blueprint creation)
- **Issue:** DELETE /hooks/logs endpoint requires a clear_hook_logs() function that was not defined in db/hooks.py (Plan 02 only defined log_hook_execution and get_hook_logs)
- **Fix:** Added clear_hook_logs() function with DELETE FROM hook_log and rowcount return
- **Files modified:** backend/db/hooks.py
- **Verification:** DELETE /hooks/logs returns 204
- **Committed in:** ba5fabe (Task 1 commit)

---

**Total deviations:** 1 auto-fixed (1 missing critical)
**Impact on plan:** Necessary for API completeness. No scope creep.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Phase 7 complete: all 3 plans executed (event system + engine/dispatcher + API/UI)
- Event system fully operational with blinker signals, HookEngine, WebhookDispatcher, and full Settings UI
- Custom scoring with DB-backed weights and provider modifiers, cache invalidation, and Settings UI
- Ready for Phase 8 (i18n Frontend Localization)

## Self-Check: PASSED

All 7 files verified present. Both commit hashes (ba5fabe, 6fe9654) confirmed in git log.

---
*Phase: 07-events-hooks-custom-scoring*
*Completed: 2026-02-15*
