---
phase: 10-performance-scalability
plan: 01
subsystem: database
tags: [sqlalchemy, orm, alembic, flask-migrate, flask-sqlalchemy, sqlite, postgresql]

# Dependency graph
requires:
  - phase: 09-openapi-release-preparation
    provides: "Stable API + schema with 28 tables in db/__init__.py SCHEMA DDL"
provides:
  - "SQLAlchemy 2.0 ORM models for all 28 database tables"
  - "Flask-SQLAlchemy db instance in extensions.py"
  - "Flask-Migrate migrate instance in extensions.py"
  - "Alembic migration infrastructure with batch mode and stamp-existing-db logic"
  - "psycopg2-binary, redis, rq as optional dependencies for future plans"
affects: [10-02, 10-03, 10-04, 10-05, 10-06, 10-07]

# Tech tracking
tech-stack:
  added: [SQLAlchemy 2.0.46, Flask-SQLAlchemy 3.1.1, Flask-Migrate 4.1.0, alembic 1.18.4, psycopg2-binary 2.9.10, redis 7.1.0, rq 2.6.1, fakeredis 2.26.2]
  patterns: [SQLAlchemy 2.0 Mapped[] + mapped_column() annotations, Flask-SQLAlchemy db.Model inheritance, Alembic render_as_batch for SQLite, stamp-existing-db migration strategy]

key-files:
  created:
    - backend/db/models/__init__.py
    - backend/db/models/core.py
    - backend/db/models/providers.py
    - backend/db/models/translation.py
    - backend/db/models/hooks.py
    - backend/db/models/standalone.py
    - backend/db/migrations/env.py
    - backend/db/migrations/alembic.ini
    - backend/db/migrations/script.py.mako
    - backend/db/migrations/versions/.gitkeep
  modified:
    - backend/requirements.txt
    - backend/extensions.py

key-decisions:
  - "All models inherit from db.Model (Flask-SQLAlchemy pattern) for clean integration"
  - "Text type (not DateTime) for all timestamp columns to preserve backward compatibility"
  - "Flask-SQLAlchemy/Migrate imports guarded with try/except ImportError for graceful degradation"
  - "extensions.py updated in Task 1 (not Task 2) because models depend on db import -- Rule 3 blocking fix"
  - "stamp_existing_db_if_needed() uses 'jobs' table as sentinel for pre-existing databases"

patterns-established:
  - "ORM model pattern: SQLAlchemy 2.0 style with Mapped[] type hints and mapped_column()"
  - "Migration infrastructure: render_as_batch=True for all contexts (SQLite compatibility)"
  - "Model organization: 5 domain modules (core, providers, translation, hooks, standalone)"
  - "Re-export pattern: db/models/__init__.py imports and re-exports all 28 model classes"

# Metrics
duration: 9min
completed: 2026-02-16
---

# Phase 10 Plan 01: SQLAlchemy ORM Models + Alembic Migration Infrastructure Summary

**28 SQLAlchemy 2.0 ORM models covering all database tables with Alembic migration infrastructure configured for SQLite batch mode**

## Performance

- **Duration:** 9 min
- **Started:** 2026-02-16T21:06:02Z
- **Completed:** 2026-02-16T21:15:01Z
- **Tasks:** 2
- **Files modified:** 12

## Accomplishments
- Created SQLAlchemy 2.0 ORM models for all 28 database tables across 5 domain modules
- Configured Alembic migration infrastructure with batch mode for SQLite ALTER TABLE compatibility
- Added stamp-existing-db logic to prevent "Table already exists" errors on existing installations
- Added Flask-SQLAlchemy and Flask-Migrate instances to extensions.py with ImportError guards
- Added 8 new dependencies (4 core + 4 optional) to requirements.txt

## Task Commits

Each task was committed atomically:

1. **Task 1: Add dependencies and create SQLAlchemy ORM models for all tables** - `0e892eb` (feat)
2. **Task 2: Flask-SQLAlchemy extension + Alembic migration infrastructure** - `663cd2c` (feat)

## Files Created/Modified
- `backend/db/models/__init__.py` - Base imports, all 28 model re-exports, __all__ list
- `backend/db/models/core.py` - Job, DailyStats, ConfigEntry, WantedItem, UpgradeHistory, LanguageProfile, SeriesLanguageProfile, MovieLanguageProfile, FfprobeCache, BlacklistEntry (10 models)
- `backend/db/models/providers.py` - ProviderCache, SubtitleDownload, ProviderStats, ProviderScoreModifier, ScoringWeights (5 models)
- `backend/db/models/translation.py` - TranslationConfigHistory, GlossaryEntry, PromptPreset, TranslationBackendStats, WhisperJob (5 models)
- `backend/db/models/hooks.py` - HookConfig, WebhookConfig, HookLog (3 models)
- `backend/db/models/standalone.py` - WatchedFolder, StandaloneSeries, StandaloneMovie, MetadataCache, AnidbMapping (5 models)
- `backend/db/migrations/env.py` - Alembic env with render_as_batch and stamp-existing-db logic
- `backend/db/migrations/alembic.ini` - Alembic configuration with UTC timestamps
- `backend/db/migrations/script.py.mako` - Migration template with batch mode import
- `backend/db/migrations/versions/.gitkeep` - Empty directory for future migration files
- `backend/requirements.txt` - Added SQLAlchemy, Flask-SQLAlchemy, Flask-Migrate, alembic, psycopg2-binary, redis, rq, fakeredis
- `backend/extensions.py` - Added Flask-SQLAlchemy db and Flask-Migrate migrate instances

## Decisions Made
- **extensions.py updated early:** Task 1 models import `from extensions import db`, so db had to be added before Task 2. Tracked as Rule 3 (blocking) deviation.
- **Text for timestamps:** All timestamp columns use Text type (not DateTime) to match existing schema exactly and avoid data migration issues.
- **ImportError guards:** Flask-SQLAlchemy/Migrate imports wrapped in try/except so existing code that only imports socketio continues to work if SQLAlchemy is not installed.
- **'jobs' as sentinel table:** stamp_existing_db_if_needed uses the 'jobs' table to detect pre-existing databases that predate Alembic.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Moved extensions.py update from Task 2 to Task 1**
- **Found during:** Task 1 (model creation)
- **Issue:** All ORM models import `from extensions import db`, but the plan assigns extensions.py changes to Task 2. Task 1 verification would fail without db in extensions.py.
- **Fix:** Added Flask-SQLAlchemy db and Flask-Migrate migrate instances to extensions.py as part of Task 1.
- **Files modified:** backend/extensions.py
- **Verification:** `from db.models import *` succeeds, all 28 models importable
- **Committed in:** 0e892eb (Task 1 commit)

---

**Total deviations:** 1 auto-fixed (1 blocking)
**Impact on plan:** Task 2 still created all Alembic infrastructure files as specified. The only change was moving the extensions.py update earlier in the sequence.

## Issues Encountered
- Pre-existing integration test failure (test_health_endpoint) unrelated to this plan. All 13 unit tests pass cleanly.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- All 28 ORM models ready for Plan 02 (repository pattern) and Plan 05 (integration wiring)
- Alembic infrastructure ready for initial migration creation in Plan 05
- No blockers for parallel plans in Phase 10

## Self-Check: PASSED

All 12 created/modified files verified present. Both task commits (0e892eb, 663cd2c) verified in git log.

---
*Phase: 10-performance-scalability*
*Completed: 2026-02-16*
