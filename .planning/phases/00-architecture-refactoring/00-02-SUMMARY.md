---
phase: 00-architecture-refactoring
plan: 02
subsystem: api
tags: [flask, application-factory, blueprints, socketio, routing, refactoring]

# Dependency graph
requires:
  - phase: 00-architecture-refactoring plan 01
    provides: "db/ package with 9 domain modules for import by route handlers"
provides:
  - "create_app() factory function in app.py"
  - "extensions.py with unbound SocketIO instance"
  - "routes/ package with 9 Blueprint files covering all 67+ API routes"
  - "register_blueprints() helper for app initialization"
affects: [00-03 import updates and cleanup, all future phases using app factory]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Application Factory: create_app(testing=False) builds Flask app with all extensions"
    - "Blueprint pattern: bp = Blueprint('name', __name__, url_prefix='/api/v1')"
    - "Deferred imports inside create_app() and route handlers to prevent circular imports"
    - "SocketIO via extensions.py: 'from extensions import socketio' everywhere"
    - "No global settings: all handlers call get_settings() at execution time"

key-files:
  created:
    - backend/extensions.py
    - backend/app.py
    - backend/routes/__init__.py
    - backend/routes/translate.py
    - backend/routes/providers.py
    - backend/routes/library.py
    - backend/routes/wanted.py
    - backend/routes/config.py
    - backend/routes/webhooks.py
    - backend/routes/system.py
    - backend/routes/profiles.py
    - backend/routes/blacklist.py
  modified: []

key-decisions:
  - "SocketIOLogHandler takes socketio as constructor parameter instead of module-level reference"
  - "Owned mutable state (batch_state, wanted_batch_state, _memory_stats) stays in its owning route module"
  - "webhooks.py imports _run_job from routes.translate for direct translation fallback"
  - "system.py /stats route imports batch_state and _memory_stats from routes.translate for cross-module stats"
  - "server.py left intact -- Plan 03 handles cleanup and deletion"

patterns-established:
  - "Route module pattern: bp = Blueprint, deferred imports inside handlers, get_settings() per request"
  - "Cross-module state access: import mutable state dicts from owning module (e.g., routes.translate.batch_state)"
  - "App factory initialization order: config -> logging -> socketio -> errors -> auth -> db -> overrides -> blueprints -> app routes -> socketio events -> schedulers"

# Metrics
duration: 8min
completed: 2026-02-15
---

# Phase 0 Plan 2: Application Factory and Blueprint Routing Summary

**Flask Application Factory with create_app(), unbound SocketIO in extensions.py, and 9 Blueprint modules covering all 67+ routes extracted from server.py's monolithic api Blueprint**

## Performance

- **Duration:** 8 min
- **Started:** 2026-02-15T10:12:42Z
- **Completed:** 2026-02-15T10:20:53Z
- **Tasks:** 2
- **Files created:** 12

## Accomplishments
- Created extensions.py with unbound SocketIO instance (no app binding at import time)
- Built create_app() factory function with full initialization pipeline: config, logging, SocketIO, error handlers, auth, database, config overrides, blueprints, app-level routes, SocketIO events, and schedulers
- Extracted all 67+ routes from server.py into 9 Blueprint files organized by domain, with 79 total URL rules registered (including Flask internals)
- Eliminated all `global settings` patterns -- every route handler calls `get_settings()` at execution time

## Task Commits

Each task was committed atomically:

1. **Task 1: Create extensions.py and app.py with factory function** - `021ac7d` (feat)
2. **Task 2: Create routes/ package with 9 Blueprint files** - `cfb33ff` (feat)

## Files Created
- `backend/extensions.py` - Unbound SocketIO instance for import by all modules
- `backend/app.py` - create_app() factory, _setup_logging(), _register_app_routes(), _start_schedulers()
- `backend/routes/__init__.py` - register_blueprints() helper importing and registering all 9 blueprints
- `backend/routes/translate.py` - Translation, batch, retranslation routes with owned batch_state and _memory_stats
- `backend/routes/providers.py` - Provider management, search, stats, cache routes
- `backend/routes/library.py` - Library browsing, Sonarr/Radarr instances, episode search/history
- `backend/routes/wanted.py` - Wanted queue, batch search, embedded extraction with owned wanted_batch_state
- `backend/routes/config.py` - Configuration CRUD, path mapping, onboarding, export/import
- `backend/routes/webhooks.py` - Sonarr/Radarr webhook handlers with auto-pipeline
- `backend/routes/system.py` - Health checks, stats, database admin, logs, notifications
- `backend/routes/profiles.py` - Language profiles, glossary entries, prompt presets
- `backend/routes/blacklist.py` - Blacklist CRUD and download history

## Decisions Made
- SocketIOLogHandler accepts socketio as constructor parameter (not module-level binding) -- enables factory pattern
- Mutable state dicts (batch_state, wanted_batch_state, _memory_stats) stay in their owning route module -- clear ownership
- system.py /stats route imports batch_state and _memory_stats from routes.translate -- avoids duplicating state
- webhooks.py imports _run_job from routes.translate for the direct translation fallback step
- Notification routes (/notifications/test, /notifications/status) do NOT use @require_api_key decorator -- auth handled by before_request hook in init_auth()
- server.py left intact for backward compatibility during Plan 03 transition

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Application Factory pattern fully implemented with create_app()
- All 67+ routes accessible via Blueprint modules at original URL paths
- Plan 03 (import updates and cleanup) can proceed:
  - Update all external imports from `database` to `db.*`
  - Update entry points (Docker, npm scripts) from server.py to app.py
  - Delete server.py and database.py
- server.py and database.py still present for backward compatibility during transition

## Self-Check: PASSED

- All 12 files verified present in backend/
- Commit 021ac7d (Task 1) verified in git log
- Commit cfb33ff (Task 2) verified in git log
- create_app(testing=True) produces working app with 79 registered URL rules
- All key routes verified: /health, /translate, /providers, /wanted, /config, /library, /webhook/sonarr, /language-profiles, /blacklist, /metrics

---
*Phase: 00-architecture-refactoring*
*Completed: 2026-02-15*
