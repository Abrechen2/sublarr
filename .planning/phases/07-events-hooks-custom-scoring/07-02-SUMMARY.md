---
phase: 07-events-hooks-custom-scoring
plan: 02
subsystem: events, hooks, webhooks
tags: [blinker, hooks, webhooks, hmac, subprocess, threadpool, event-bus]

# Dependency graph
requires:
  - phase: 07-events-hooks-custom-scoring
    plan: 01
    provides: "events/ package with blinker catalog, db/hooks.py CRUD, emit_event helper"
provides:
  - "HookEngine executing shell scripts with controlled env and subprocess timeout"
  - "WebhookDispatcher sending HTTP POST with HMAC-SHA256 signing and retry"
  - "All business-level socketio.emit calls rewired to event bus"
  - "init_event_system + hook/webhook subscribers called in app.py create_app"
  - "standalone_scan_complete and standalone_file_detected added to EVENT_CATALOG"
affects: [07-03-api-ui, settings-ui, hook-configuration, webhook-management]

# Tech tracking
tech-stack:
  added: []
  patterns: [hook-engine-subprocess-dispatch, webhook-hmac-signing, emit-event-rewiring]

key-files:
  created:
    - backend/events/hooks.py
    - backend/events/webhooks.py
  modified:
    - backend/app.py
    - backend/events/catalog.py
    - backend/routes/config.py
    - backend/routes/translate.py
    - backend/routes/wanted.py
    - backend/routes/webhooks.py
    - backend/wanted_scanner.py
    - backend/whisper/queue.py
    - backend/standalone/__init__.py

key-decisions:
  - "Progress/streaming events (job_update, batch_progress, whisper_progress, etc.) kept as direct socketio.emit -- they fire at high frequency and should NOT trigger hooks/webhooks"
  - "hook_executed signal skipped in hook/webhook subscribers to prevent infinite recursion"
  - "standalone_scan_complete and standalone_file_detected added to EVENT_CATALOG for standalone mode events"
  - "Scoring cache invalidation triggered on config_updated when scoring-related keys change"
  - "webhook_completed kept as socketio.emit (operational event, not a catalog business event)"

patterns-established:
  - "emit_event rewiring pattern: business events use emit_event, progress streams use direct socketio.emit"
  - "HookEngine subprocess pattern: controlled env with SUBLARR_ prefix, no shell=True, /tmp cwd"
  - "WebhookDispatcher HMAC pattern: sha256={hex} in X-Sublarr-Signature header"
  - "Auto-disable pattern: skip webhooks with 10+ consecutive failures"

# Metrics
duration: 10min
completed: 2026-02-15
---

# Phase 7 Plan 02: Hook Engine + Webhook Dispatcher + socketio.emit Rewiring

**HookEngine executing shell scripts via subprocess with controlled env, WebhookDispatcher sending HMAC-signed HTTP POST with retry, and all 22+ business socketio.emit calls rewired to use blinker event bus**

## Performance

- **Duration:** 10 min
- **Started:** 2026-02-15T19:04:34Z
- **Completed:** 2026-02-15T19:15:07Z
- **Tasks:** 2
- **Files modified:** 11

## Accomplishments
- Built HookEngine that executes shell scripts via subprocess.run with controlled environment (SUBLARR_ prefixed vars), configurable timeout, no shell=True, and ThreadPoolExecutor async dispatch
- Built WebhookDispatcher that sends HTTP POST with HMAC-SHA256 signing, exponential backoff retry (2s/4s/8s), and auto-disable after 10 consecutive failures
- Rewired all business-level socketio.emit calls across 7 files to use emit_event, while preserving progress streams as direct socketio.emit
- Initialized event system (SocketIO bridge + HookEngine + WebhookDispatcher) in app.py create_app before blueprint registration
- Added 2 new events (standalone_scan_complete, standalone_file_detected) to EVENT_CATALOG

## Task Commits

Each task was committed atomically:

1. **Task 1: Build HookEngine and WebhookDispatcher with async execution** - `3dacbe1` (feat)
2. **Task 2: Rewire all socketio.emit calls to use event bus and initialize in app.py** - `116f518` (feat)

## Files Created/Modified
- `backend/events/hooks.py` - HookEngine with subprocess execution, ThreadPoolExecutor dispatch, init_hook_subscribers
- `backend/events/webhooks.py` - WebhookDispatcher with HMAC signing, retry session, init_webhook_subscribers
- `backend/app.py` - init_event_system + HookEngine + WebhookDispatcher initialization in create_app
- `backend/events/catalog.py` - Added standalone_scan_complete and standalone_file_detected signals
- `backend/routes/config.py` - config_updated -> emit_event + scoring cache invalidation
- `backend/routes/translate.py` - batch_completed and retranslation_completed -> emit_event
- `backend/routes/wanted.py` - wanted_scan_complete, wanted_item_processed, upgrade_complete, batch_complete -> emit_event
- `backend/routes/webhooks.py` - webhook_received -> emit_event
- `backend/wanted_scanner.py` - wanted_search_completed -> emit_event
- `backend/whisper/queue.py` - whisper_completed and whisper_error -> emit_event
- `backend/standalone/__init__.py` - standalone_scan_complete and standalone_file_detected -> emit_event

## Decisions Made
- Kept progress/streaming events (job_update, batch_progress, retranslation_progress, wanted_batch_progress, wanted_search_progress, whisper_progress) as direct socketio.emit since they fire at high frequency and hooks/webhooks should not subscribe to them
- Skipped hook_executed in hook/webhook subscribers to prevent infinite recursion (hook fires -> hook_executed signal -> hook fires again)
- Added standalone events to catalog since standalone module was already emitting them via socketio
- Added scoring cache invalidation in config_updated handler when scoring-related keys change
- Kept webhook_completed as socketio.emit since it is an operational event, not a business event worth triggering hooks/webhooks on

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] Added standalone events to EVENT_CATALOG**
- **Found during:** Task 2 (socketio.emit rewiring)
- **Issue:** standalone_scan_complete and standalone_file_detected were not in EVENT_CATALOG but were being emitted by standalone module
- **Fix:** Added both signals and catalog entries to catalog.py
- **Files modified:** backend/events/catalog.py
- **Verification:** App starts with 16 events (14 original + 2 new)
- **Committed in:** 116f518 (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (1 missing critical)
**Impact on plan:** Necessary addition for standalone mode events to work through the event bus. No scope creep.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- Event system fully operational end-to-end: events fire -> SocketIO bridge + hooks + webhooks all receive them
- 16 events in catalog, all with hook and webhook subscribers
- Ready for Plan 03 (API endpoints and Settings UI for hooks/webhooks/scoring)
- 24 unit tests passing, no regressions

## Self-Check: PASSED

- All 11 files verified present
- Both commit hashes verified in git log
- 24 unit tests passing, no regressions
- App starts cleanly with event system initialized

---
*Phase: 07-events-hooks-custom-scoring*
*Completed: 2026-02-15*
