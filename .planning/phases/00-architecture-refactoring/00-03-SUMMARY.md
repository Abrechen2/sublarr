---
phase: 00-architecture-refactoring
plan: 03
subsystem: api
tags: [flask, refactoring, imports, cleanup, docker, entry-points]

# Dependency graph
requires:
  - phase: 00-architecture-refactoring plan 01
    provides: "db/ package with 9 domain modules as import targets"
  - phase: 00-architecture-refactoring plan 02
    provides: "create_app() factory and routes/ package as import targets"
provides:
  - "Zero references to old database.py or server.py anywhere in codebase"
  - "All external modules import from db.* and app/extensions"
  - "Dockerfile with app:create_app() entry point and workers=1"
  - "package.json dev:backend using FLASK_APP=app.py"
  - "Test fixtures using Application Factory pattern (create_app(testing=True))"
  - "Clean break: database.py (2154 lines) and server.py (2618 lines) deleted"
affects: [all future phases - clean modular import paths established]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Import pattern: 'from db.{domain} import {function}' for all database access"
    - "Test fixture pattern: create_app(testing=True) for Flask test client"
    - "Entry point: gunicorn app:create_app() with workers=1 for Flask-SocketIO"
    - "Dev server: FLASK_APP=app.py with flask run"

key-files:
  created: []
  modified:
    - backend/translator.py
    - backend/wanted_scanner.py
    - backend/wanted_search.py
    - backend/ollama_client.py
    - backend/anidb_mapper.py
    - backend/ass_utils.py
    - backend/config.py
    - backend/metrics.py
    - backend/providers/__init__.py
    - backend/tests/conftest.py
    - backend/tests/test_server.py
    - backend/tests/test_database.py
    - backend/tests/integration/test_database_operations.py
    - backend/tests/performance/test_api_performance.py
    - Dockerfile
    - package.json

key-decisions:
  - "database.py and server.py fully deleted -- clean break, no backward compat shims"
  - "Gunicorn workers set to 1 (Flask-SocketIO requires single worker for WebSocket state)"
  - "Test fixtures use create_app(testing=True) -- no global app instance in tests"
  - "close_db() added to test fixtures to prevent PermissionError on temp file cleanup (Windows)"

patterns-established:
  - "All database imports use domain-specific paths: from db.jobs, db.wanted, db.profiles, db.translation, db.cache, db.providers, db.blacklist, db.library, db.config"
  - "All app/server imports use factory: from app import create_app"
  - "Deferred imports inside functions remain deferred but point to new db.* modules"

# Metrics
duration: 14min
completed: 2026-02-15
---

# Phase 0 Plan 3: Import Migration and Monolith Deletion Summary

**Replaced all 15+ import sites from database/server to db.*/app across 16 files, deleted 4772-line monoliths, updated Docker and npm entry points -- zero old references remain**

## Performance

- **Duration:** 14 min (including human verification checkpoint)
- **Started:** 2026-02-15T10:23:38Z
- **Completed:** 2026-02-15T10:37:22Z
- **Tasks:** 2 (1 auto + 1 human-verify checkpoint)
- **Files modified:** 16 (+ 2 files deleted)

## Accomplishments
- Updated all `from database import` statements across 10 backend modules to use domain-specific `from db.{module} import` paths
- Updated all `from server import app` statements in test files to `from app import create_app` with factory pattern
- Deleted database.py (2154 lines) and server.py (2618 lines) -- clean break from monolithic architecture
- Updated Dockerfile CMD from `server:app` to `app:create_app()` with workers reduced from 2 to 1 (Flask-SocketIO requirement)
- Updated package.json dev:backend from `FLASK_APP=server.py` to `FLASK_APP=app.py`
- Human verification confirmed: 58 tests pass, create_app() works, 79 routes registered

## Task Commits

Each task was committed atomically:

1. **Task 1: Update all external module imports and entry points** - `94af441` (feat)
2. **Task 2: Human verification checkpoint** - approved (58 tests pass, 0 new failures)

**Post-checkpoint fixes (by user during verification):**
- `c79ddb1` - fix: close DB connections before cleanup in test fixtures (Windows PermissionError)
- `5c1787d` - fix: remove accidentally re-added database.py and server.py

## Files Modified
- `backend/translator.py` - Updated import: `from db.translation import record_translation_config`
- `backend/wanted_scanner.py` - Updated 4 import sites: db.wanted, db.profiles
- `backend/wanted_search.py` - Updated import: db.wanted, db.library
- `backend/ollama_client.py` - Updated import: `from db.translation import get_glossary_for_series`
- `backend/anidb_mapper.py` - Updated import: `from db.cache import get_anidb_mapping, save_anidb_mapping`
- `backend/ass_utils.py` - Updated deferred import: `from db.cache import get_ffprobe_cache, set_ffprobe_cache`
- `backend/config.py` - Updated deferred import: `from db.translation import get_default_prompt_preset`
- `backend/metrics.py` - Updated deferred import: `from db.jobs` and `from db.wanted`
- `backend/providers/__init__.py` - Updated 4 deferred import sites: db.providers, db.blacklist
- `backend/tests/conftest.py` - Factory pattern: `from app import create_app`, updated client fixture
- `backend/tests/test_server.py` - Factory pattern: `from app import create_app`, updated client fixture
- `backend/tests/test_database.py` - Updated: `from db import get_db, close_db` + `from db.jobs import ...`
- `backend/tests/integration/test_database_operations.py` - Updated: db.jobs, db.wanted, db.blacklist, db.library
- `backend/tests/performance/test_api_performance.py` - Updated: `from db.library import get_download_history`
- `Dockerfile` - CMD: `app:create_app()`, workers=1
- `package.json` - dev:backend: `FLASK_APP=app.py`

## Files Deleted
- `backend/database.py` - 2154-line monolith (replaced by db/ package with 9 modules)
- `backend/server.py` - 2618-line monolith (replaced by app.py + routes/ package with 9 blueprints)

## Decisions Made
- Clean break: database.py and server.py fully deleted with no compatibility shims -- all consumers already updated
- Gunicorn workers=1: Flask-SocketIO requires single worker process for WebSocket state consistency (per RESEARCH.md)
- Test fixtures use create_app(testing=True) rather than importing a global app instance
- close_db() added to test fixtures (post-checkpoint fix) to prevent Windows PermissionError on temp file cleanup

## Deviations from Plan

None - plan executed exactly as written. The two post-checkpoint fixes (c79ddb1, 5c1787d) were made by the user during human verification and are not deviations from the plan's scope.

## Issues Encountered

- **28 pre-existing test failures:** These tests were already broken before the refactoring (integration tests used function signatures that didn't match the original database.py). The refactoring did not introduce any new test failures.
- **Windows PermissionError on temp DB cleanup:** Fixed in post-checkpoint commit c79ddb1 by adding close_db() to test fixture teardown.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Phase 0 (Architecture Refactoring) is COMPLETE -- all 3 plans executed
- Codebase fully migrated to modular architecture:
  - `db/` package: 9 domain modules (jobs, config, providers, library, wanted, blacklist, profiles, translation, cache)
  - `routes/` package: 9 Blueprint files (translate, providers, library, wanted, config, webhooks, system, profiles, blacklist)
  - `app.py`: Application Factory with create_app()
  - `extensions.py`: Unbound SocketIO instance
- Phase 0 requirements satisfied:
  - ARCH-01: Application Factory pattern (create_app)
  - ARCH-02: Blueprint-based routing (9 blueprints)
  - ARCH-03: Database package extraction (9 domain modules)
  - ARCH-04: Clean module boundaries (zero cross-references to old files)
- Phases 1, 2, 3 can now proceed in parallel (all depend on Phase 0)

## Self-Check: PASSED

- All 16 modified files verified present in codebase
- backend/database.py confirmed deleted
- backend/server.py confirmed deleted
- Commit 94af441 (Task 1) verified in git log
- Commit c79ddb1 (post-checkpoint fix 1) verified in git log
- Commit 5c1787d (post-checkpoint fix 2) verified in git log
- `grep -r "from database import" backend/` returns zero results
- `grep -r "from server import" backend/` returns zero results
- create_app(testing=True) produces working app with 79 URL rules

---
*Phase: 00-architecture-refactoring*
*Completed: 2026-02-15*
