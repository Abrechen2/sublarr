---
phase: 07-events-hooks-custom-scoring
verified: 2026-02-15T21:00:00Z
status: passed
score: 6/6 must-haves verified
re_verification: false
---

# Phase 7: Events/Hooks + Custom Scoring Verification Report

**Phase Goal:** Users can extend Sublarr behavior through shell scripts, outgoing webhooks, and custom scoring weights without modifying code

**Verified:** 2026-02-15T21:00:00Z

**Status:** passed

**Re-verification:** No - initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Internal events are published on a blinker event bus with a discoverable catalog of 14+ event types | VERIFIED | 16 events defined in EVENT_CATALOG (catalog.py), blinker Namespace created, all signals registered |
| 2 | Hook and webhook configurations can be stored and retrieved from the database | VERIFIED | hook_configs and webhook_configs tables exist, CRUD operations tested successfully (db/hooks.py) |
| 3 | Hook execution log records can be stored and queried | VERIFIED | hook_log table exists, log_hook_execution and get_hook_logs functions work (db/hooks.py) |
| 4 | Scoring weights are loaded from DB with fallback to hardcoded defaults | VERIFIED | compute_score uses _get_cached_weights with 60s TTL, lazy import from db.scoring, falls back to EPISODE_SCORES/MOVIE_SCORES |
| 5 | Per-provider score modifiers are applied during subtitle scoring | VERIFIED | compute_score calls _get_cached_modifier and adds to score (providers/base.py lines 260-261) |
| 6 | SocketIO bridge forwards all catalog events to WebSocket clients for backward compatibility | VERIFIED | init_event_system registers _make_bridge for all EVENT_CATALOG entries, socketio.emit called for each event |

**Score:** 6/6 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| backend/events/__init__.py | init_event_system function, SocketIO bridge registration, emit_event helper | VERIFIED | 78 lines, exports init_event_system and emit_event, _make_bridge closure pattern implemented |
| backend/events/catalog.py | blinker Namespace, named signals, EVENT_CATALOG dict | VERIFIED | 177 lines, sublarr_signals Namespace, 16 signals defined, EVENT_CATALOG with metadata for all events |
| backend/db/hooks.py | CRUD for hook_configs, webhook_configs, hook_log tables | VERIFIED | 446 lines, full CRUD for all 3 tables, _db_lock pattern followed, clear_hook_logs added |
| backend/db/scoring.py | CRUD for scoring_weights, provider_score_modifiers tables | VERIFIED | 192 lines, get/set/reset scoring weights, get/set/delete provider modifiers, default weights defined |
| backend/providers/base.py | Modified compute_score using configurable weights from DB | VERIFIED | 347 lines, _get_cached_weights and _get_cached_modifier with 60s TTL, invalidate_scoring_cache function |
| backend/events/hooks.py | HookEngine with shell script execution, ThreadPoolExecutor | VERIFIED | 241 lines, HookEngine class, execute_hook with subprocess, SUBLARR_ env vars, init_hook_subscribers |
| backend/events/webhooks.py | WebhookDispatcher with HTTP POST, HMAC signing, retry | VERIFIED | 261 lines, WebhookDispatcher class, HMAC-SHA256 signature, exponential backoff, init_webhook_subscribers |
| backend/routes/hooks.py | 18+ API endpoints for hooks/webhooks/logs/scoring | VERIFIED | 355 lines, full CRUD for hooks/webhooks, event catalog endpoint, scoring weights/modifiers, test endpoints |
| frontend/src/pages/Settings.tsx | EventsHooksTab and ScoringTab components | VERIFIED | Contains EventsHooksTab (hooks/webhooks/logs UI) and ScoringTab (weight editors, provider sliders) |
| frontend/src/api/client.ts | API functions for hooks/webhooks/scoring | VERIFIED | getEventCatalog, createHookConfig, createWebhookConfig, getScoringWeights, etc. |
| frontend/src/hooks/useApi.ts | React Query hooks for hooks/webhooks/scoring | VERIFIED | useEventCatalog, useHookConfigs, useWebhookConfigs, useScoringWeights, useProviderModifiers |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|----|--------|---------|
| backend/events/catalog.py | blinker.Namespace | signal definition | WIRED | sublarr_signals.signal() calls verified, 16 signals defined |
| backend/events/__init__.py | backend/events/catalog.py | import EVENT_CATALOG | WIRED | Line 12: from events.catalog import EVENT_CATALOG, CATALOG_VERSION |
| backend/providers/base.py | backend/db/scoring.py | lazy import for weights | WIRED | Lines 195, 223: from db.scoring import get_scoring_weights, get_all_provider_modifiers |
| backend/events/hooks.py | backend/events/catalog.py | subscribe to signals | WIRED | init_hook_subscribers connects to signals from EVENT_CATALOG |
| backend/events/webhooks.py | backend/events/catalog.py | subscribe to signals | WIRED | init_webhook_subscribers connects to signals from EVENT_CATALOG |
| backend/events/hooks.py | backend/db/hooks.py | reads hook_configs, writes hook_log | WIRED | Imports and uses get_hook_configs, log_hook_execution, update_hook_trigger_stats |
| backend/routes/* | backend/events | emit_event replaces socketio.emit | WIRED | emit_event imported in config.py, translate.py, wanted.py, webhooks.py, wanted_scanner.py, whisper/queue.py, standalone/__init__.py |
| backend/app.py | backend/events | init_event_system called in create_app | WIRED | Lines 143, 147: import and call init_event_system(app) |

### Requirements Coverage

Phase 7 requirements from ROADMAP.md:

| Requirement | Status | Evidence |
|-------------|--------|----------|
| EVNT-01: Internal event bus | SATISFIED | blinker signals + EVENT_CATALOG + emit_event API |
| EVNT-02: Shell script hooks | SATISFIED | HookEngine executes scripts with SUBLARR_ env vars and configurable timeout |
| EVNT-03: Outgoing webhooks | SATISFIED | WebhookDispatcher sends HTTP POST with HMAC signature and retry logic |
| EVNT-04: Event subscription | SATISFIED | init_hook_subscribers and init_webhook_subscribers connect to all catalog events |
| SCOR-01: Custom scoring weights | SATISFIED | scoring_weights table + Settings UI with episode/movie weight editors |
| SCOR-02: Per-provider modifiers | SATISFIED | provider_score_modifiers table + Settings UI with range sliders |

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| None | - | - | - | No anti-patterns detected |

**Anti-pattern scan results:**
- No TODO/FIXME/placeholder comments found in events/, db/hooks.py, db/scoring.py
- No stub patterns (return null, return {}, return []) found
- All files are substantive (78-446 lines)
- All exports present and used

### Human Verification Required

#### 1. Shell Hook Execution Test

**Test:** Create a shell hook via Settings UI that triggers on subtitle_downloaded event, point it to a test script that logs to a file, trigger a subtitle download, verify the script executed and received SUBLARR_ environment variables

**Expected:** Hook execution log shows success=true, stdout/stderr captured, SUBLARR_EVENT and SUBLARR_EVENT_DATA environment variables contain correct event data

**Why human:** Requires real file system script execution and subtitle download workflow to verify end-to-end hook triggering

#### 2. Outgoing Webhook Test

**Test:** Configure a webhook via Settings UI pointing to a test endpoint (e.g., webhook.site), trigger an event, verify the webhook endpoint receives a POST request with correct JSON payload and X-Sublarr-Signature HMAC header

**Expected:** Webhook test endpoint shows incoming POST with event_name, version, timestamp, data fields, and valid HMAC signature if secret configured

**Why human:** Requires external HTTP endpoint and visual inspection of webhook payload structure

#### 3. Custom Scoring Weights Test

**Test:** In Settings Scoring tab, change episode hash weight from 359 to 500, save, trigger a provider search, verify the scored results reflect the new weight (higher hash matches score higher)

**Expected:** Provider search results show increased scores for hash matches, Settings UI shows weight persisted after page reload

**Why human:** Requires triggering real provider search and comparing subtitle scores before/after weight change

#### 4. Provider Modifier Test

**Test:** In Settings Scoring tab, set a provider modifier (e.g., opensubtitles: -50), save, trigger a provider search, verify opensubtitles results have 50 points deducted from their scores

**Expected:** Provider search shows adjusted scores, opensubtitles results rank lower than before, Settings UI persists modifier

**Why human:** Requires multi-provider search and score comparison to verify modifier application

#### 5. Events & Hooks UI Test

**Test:** Navigate to Settings Events & Hooks tab, verify event catalog dropdown shows 16+ events with labels and descriptions, create a hook, test-fire it, verify execution log appears with stdout/stderr

**Expected:** UI shows event catalog, hook creation form works, test button executes hook synchronously and displays result, execution log table shows entries

**Why human:** UI interaction flow and visual verification of all components

#### 6. SocketIO Bridge Test

**Test:** Open browser console with WebSocket inspector, trigger any event (e.g., translation_complete), verify the WebSocket emits the same event_name with the data payload

**Expected:** WebSocket traffic shows event_name messages matching blinker signal emissions, frontend listeners receive events

**Why human:** Requires browser dev tools WebSocket inspection and event triggering

### Gaps Summary

**No gaps found.** All must-haves are verified:

- Event system foundation is complete with 16 events in the catalog, blinker signals, and SocketIO bridge
- Database schema includes all 5 new tables (hook_configs, webhook_configs, hook_log, scoring_weights, provider_score_modifiers)
- CRUD modules provide full functionality for hooks, webhooks, and scoring configuration
- HookEngine and WebhookDispatcher execute hooks/webhooks asynchronously with proper error handling and logging
- Configurable scoring is wired into compute_score with 60s TTL cache and fallback to defaults
- API Blueprint provides 18+ endpoints for all CRUD operations
- Frontend Settings tabs provide full UI for event/hook/webhook management and scoring configuration
- All 22+ socketio.emit call sites were rewired to use emit_event
- Event system is initialized in app.py during application creation

Phase goal achieved: Users can extend Sublarr behavior through shell scripts, outgoing webhooks, and custom scoring weights without modifying code.

---

_Verified: 2026-02-15T21:00:00Z_
_Verifier: Claude (gsd-verifier)_
