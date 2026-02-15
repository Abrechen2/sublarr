# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-02-15)

**Core value:** ASS-first Anime Subtitle-Automation mit LLM-Uebersetzung -- automatisch die besten Untertitel finden, herunterladen und uebersetzen, ohne Styles zu zerstoeren.
**Current focus:** Phase 1 - Provider Plugin Expansion

## Current Position

Phase: 1 of 16 (Provider Plugin Expansion)
Plan: 4 of 6 in current phase
Status: In progress
Last activity: 2026-02-15 -- Completed 01-03-PLAN.md (hot-reload + plugin template)

Progress: [█████████████░░░░░░░] 4/6 plans in phase

## Performance Metrics

**Velocity:**
- Total plans completed: 7
- Average duration: 8 min
- Total execution time: 59 min

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 00-architecture-refactoring | 3/3 | 27 min | 9 min |
| 01-provider-plugin-expansion | 4/6 | 32 min | 8 min |

**Recent Trend:**
- Last 5 plans: 00-03 (14 min), 01-01 (8 min), 01-03 (8 min), 01-04 (8 min), 01-05 (8 min)
- Trend: Stable

*Updated after each plan completion*

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- [Roadmap]: 17 phases (0-16) derived from 134 requirements across Phase 2+3
- [Roadmap]: Phase 0 (Architecture Refactoring) is prerequisite -- blocks Phases 1-3, 5, 7, 8, 11-12, 14-15
- [Roadmap]: Phases 1, 2, 3 can run in parallel after Phase 0
- [Research]: apispec (not Flask-smorest/APIFlask) for OpenAPI to avoid route rewrites
- [Research]: openai library covers all OpenAI-compatible endpoints, making litellm unnecessary
- [00-01]: Schema DDL and migrations stay in db/__init__.py -- single source of truth for all 17 tables
- [00-01]: Private helpers (_row_to_job, _row_to_wanted, _row_to_profile) stay with their domain modules
- [00-01]: database.py preserved intact until Plan 03 updates all external imports
- [00-02]: SocketIOLogHandler takes socketio as constructor parameter (not module-level binding)
- [00-02]: Mutable state (batch_state, wanted_batch_state, _memory_stats) stays in owning route module
- [00-02]: system.py imports batch_state/_memory_stats from routes.translate for cross-module stats
- [00-03]: database.py and server.py fully deleted -- clean break, no backward compat shims
- [00-03]: Gunicorn workers=1 (Flask-SocketIO requires single worker for WebSocket state)
- [00-03]: Test fixtures use create_app(testing=True) -- no global app instance in tests
- [00-03]: 28 pre-existing test failures noted (not caused by refactoring)
- [01-01]: Plugin config stored in config_entries table with plugin.<name>.<key> namespacing -- no new DB table
- [01-01]: Built-in providers always win name collisions -- plugins with duplicate names rejected
- [01-01]: Safe import = exception catching only (no sandboxing), same trust model as Bazarr
- [01-01]: Config field keys match Pydantic Settings field names, stripped to short params for constructor
- [01-04]: Gestdown covers both PROV-01 (Addic7ed) and PROV-03 (Gestdown) -- single provider, no duplication
- [01-04]: Gestdown language mapping uses API fetch with hardcoded fallback for resilience
- [01-04]: Podnapisi uses lxml with graceful fallback to stdlib xml.etree.ElementTree

### Pending Todos

None yet.

### Blockers/Concerns

- Phase 0 complete -- no blockers for Phases 1, 2, 3 (can proceed in parallel)
- 28 pre-existing test failures in integration/performance tests (not caused by refactoring, existed before Phase 0)

## Session Continuity

Last session: 2026-02-15
Stopped at: Plan 01-04 complete (Gestdown + Podnapisi providers)
Resume file: .planning/phases/01-provider-plugin-expansion/01-02-PLAN.md
