---
phase: 07-events-hooks-custom-scoring
plan: 01
subsystem: events, database, scoring
tags: [blinker, signals, event-bus, hooks, webhooks, scoring-weights, sqlite]

# Dependency graph
requires:
  - phase: 00-architecture-refactoring
    provides: "db package with _db_lock pattern, extensions.py socketio singleton"
  - phase: 01-provider-plugin-expansion
    provides: "providers/base.py compute_score, EPISODE_SCORES, MOVIE_SCORES"
provides:
  - "events/ package with blinker signal bus and 14-event catalog"
  - "SocketIO bridge forwarding all events to WebSocket clients"
  - "emit_event() helper for modules to fire events"
  - "db/hooks.py CRUD for hook_configs, webhook_configs, hook_log"
  - "db/scoring.py CRUD for scoring_weights, provider_score_modifiers"
  - "Configurable scoring weights in compute_score with 60s TTL cache"
  - "Per-provider score modifiers applied during subtitle scoring"
affects: [07-02-hook-engine, 07-03-api-ui, webhook-dispatcher, settings-ui]

# Tech tracking
tech-stack:
  added: [blinker]
  patterns: [event-bus-with-catalog, socketio-bridge-closure, scoring-cache-with-ttl]

key-files:
  created:
    - backend/events/__init__.py
    - backend/events/catalog.py
    - backend/db/hooks.py
    - backend/db/scoring.py
  modified:
    - backend/db/__init__.py
    - backend/providers/base.py

key-decisions:
  - "blinker Namespace for signal isolation -- all Sublarr signals in sublarr_signals"
  - "CATALOG_VERSION=1 for future payload schema evolution"
  - "SocketIO bridge uses closure pattern (make_bridge) to correctly capture event_name in loop"
  - "emit_event guards current_app with try/except RuntimeError for use outside request context"
  - "Scoring cache TTL=60s -- balances DB freshness vs query overhead"
  - "Provider modifier cache loads all modifiers at once (single query) instead of per-provider"
  - "DB overrides merge on top of hardcoded defaults ({**defaults, **db_overrides})"

patterns-established:
  - "Event catalog pattern: signal + label + description + payload_keys dict per event"
  - "SocketIO bridge pattern: blinker subscriber auto-forwards to WebSocket clients"
  - "Scoring cache pattern: module-level dict with TTL expiry, lazy DB import, graceful fallback"

# Metrics
duration: 26min
completed: 2026-02-15
---

# Phase 7 Plan 01: Event Bus Foundation + DB Schema + Configurable Scoring

**Blinker event bus with 14-signal catalog, SocketIO bridge, 5 new DB tables for hooks/webhooks/scoring, and configurable compute_score with per-provider modifiers**

## Performance

- **Duration:** 26 min
- **Started:** 2026-02-15T18:34:31Z
- **Completed:** 2026-02-15T19:00:41Z
- **Tasks:** 3
- **Files modified:** 6

## Accomplishments
- Created events/ package with blinker Namespace defining 14 named signals and a machine-readable EVENT_CATALOG
- Built SocketIO bridge that auto-forwards all catalog events to WebSocket clients for frontend backward compatibility
- Added 5 new database tables (hook_configs, webhook_configs, hook_log, scoring_weights, provider_score_modifiers) to the schema
- Implemented full CRUD modules (db/hooks.py, db/scoring.py) following the established _db_lock pattern
- Wired configurable scoring weights into compute_score with 60-second TTL cache and graceful fallback to defaults
- Added per-provider score modifiers that are applied after base score computation

## Task Commits

Each task was committed atomically:

1. **Task 1: Create events/ package with blinker catalog and SocketIO bridge** - `bafcc37` (feat)
2. **Task 2: Add 5 new DB tables and CRUD modules for hooks and scoring** - `4045a85` (feat)
3. **Task 3: Wire configurable scoring into compute_score** - `e2f0fbb` (feat)

## Files Created/Modified
- `backend/events/__init__.py` - Event system init: SocketIO bridge registration, emit_event helper
- `backend/events/catalog.py` - Blinker Namespace with 14 signals, EVENT_CATALOG metadata dict
- `backend/db/__init__.py` - Added 5 new CREATE TABLE statements to SCHEMA
- `backend/db/hooks.py` - CRUD for hook_configs, webhook_configs, hook_log with trigger stats
- `backend/db/scoring.py` - CRUD for scoring_weights, provider_score_modifiers with defaults
- `backend/providers/base.py` - Configurable compute_score with caching and provider modifiers

## Decisions Made
- Used blinker Namespace (not custom event system) for signal isolation and discoverability
- CATALOG_VERSION=1 included for future payload schema evolution without breaking consumers
- SocketIO bridge uses closure pattern to correctly capture event_name in loop (avoids late binding)
- Scoring cache loads all provider modifiers at once (single query) rather than per-provider lookups
- Scoring cache TTL=60s chosen as balance between DB freshness and query overhead
- emit_event guards current_app access with try/except RuntimeError for use outside Flask request context
- weak=False on bridge signal connections to prevent garbage collection of bridge subscribers

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- Event catalog ready for hook engine (Plan 02) to subscribe to signals
- DB schema ready for webhook dispatcher to store/query configurations
- Configurable scoring immediately available via DB -- API endpoints (Plan 03) will expose to UI
- All existing 60 unit tests continue to pass (no regressions)

## Self-Check: PASSED

- All 6 files verified present
- All 3 commit hashes verified in git log
- 60 unit tests passing, no regressions

---
*Phase: 07-events-hooks-custom-scoring*
*Completed: 2026-02-15*
