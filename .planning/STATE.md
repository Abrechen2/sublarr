# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-02-15)

**Core value:** ASS-first Anime Subtitle-Automation mit LLM-Uebersetzung -- automatisch die besten Untertitel finden, herunterladen und uebersetzen, ohne Styles zu zerstoeren.
**Current focus:** Phase 3 - Media-Server Abstraction (COMPLETE)

## Current Position

Phase: 3 of 16 (Media-Server Abstraction)
Plan: 3 of 3 in current phase
Status: Phase complete
Last activity: 2026-02-15 -- Completed 03-03-PLAN.md (frontend UI: Media Servers tab + onboarding)

Progress: [████████████████████] 3/3 plans in phase

## Performance Metrics

**Velocity:**
- Total plans completed: 19
- Average duration: 7 min
- Total execution time: 132 min

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 00-architecture-refactoring | 3/3 | 27 min | 9 min |
| 01-provider-plugin-expansion | 6/6 | 64 min | 11 min |
| 02-translation-multi-backend | 6/6 | 23 min | 4 min |
| 03-media-server-abstraction | 3/3 | 18 min | 6 min |

**Recent Trend:**
- Last 5 plans: 02-05 (6 min), 02-06 (2 min), 03-01 (4 min), 03-02 (6 min), 03-03 (8 min)
- Trend: Stable (~5 min avg)

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
- [01-03]: Hot-reload uses 2-second debounce via threading.Timer to coalesce rapid file events
- [01-03]: plugin_hot_reload defaults to false (opt-in) to avoid unnecessary filesystem watching
- [01-03]: Watchdog is optional dependency -- ImportError caught gracefully in app.py
- [01-04]: Gestdown covers both PROV-01 (Addic7ed) and PROV-03 (Gestdown) -- single provider, no duplication
- [01-04]: Gestdown language mapping uses API fetch with hardcoded fallback for resilience
- [01-04]: Podnapisi uses lxml with graceful fallback to stdlib xml.etree.ElementTree
- [01-05]: Kitsunekko uses conditional BeautifulSoup import -- degrades gracefully if bs4 not installed
- [01-05]: Napisy24 computes MD5 of first 10MB for file hash matching (Bazarr-compatible algorithm)
- [01-05]: WhisperSubgen returns low-score placeholder (score=10) in search, defers transcription to download()
- [01-05]: WhisperSubgen uses ffmpeg pipe:1 for audio extraction (no temp files)
- [01-06]: Titrari uses no auth -- browser-like UA and Accept-Language headers for polite scraping
- [01-06]: LegendasDivx uses lazy auth -- login deferred to first search via _ensure_authenticated()
- [01-06]: Daily limit safety margin 140/145 with date comparison reset (today > last_reset_date)
- [01-06]: Session expiry detected via 302 redirect to login page, auto re-authentication
- [01-02]: Auto-disable threshold = 2x circuit_breaker_failure_threshold (default 10 consecutive failures)
- [01-02]: provider_auto_disable_cooldown_minutes config setting with 30 min default
- [01-02]: Response time uses weighted running average: (old_avg * (n-1) + new) / n
- [01-02]: clear_auto_disable resets consecutive_failures to 0 for clean re-enable
- [02-01]: Shared LLM utilities extracted as standalone module -- reusable by all LLM backends
- [02-01]: OllamaBackend reads config from config_entries with Pydantic Settings fallback for migration
- [02-01]: TranslationManager uses lazy backend creation -- misconfigured backends don't break others
- [02-01]: Circuit breakers per backend reuse existing CircuitBreaker class from provider system
- [02-02]: DeepL glossary cached by (source, target) pair -- avoids re-creating glossaries on every batch
- [02-02]: LibreTranslate translates line-by-line (max_batch_size=1) to guarantee 1:1 line mapping
- [02-02]: DeepL import guarded with try/except -- backend class loads even without deepl SDK installed
- [02-02]: Both API backends return TranslationResult(success=False) on error instead of raising exceptions
- [02-03]: OpenAI-compatible backend handles retries internally (max_retries=0 on SDK client) for consistent CJK hallucination detection
- [02-03]: Google backend creates fresh client per call (no lazy caching) since credentials may change via config_entries
- [02-03]: Both backends register via try/except ImportError guards -- missing packages don't break app startup
- [02-04]: _translate_with_manager returns (lines, result) tuple to propagate backend_name for config hash and stats
- [02-04]: Config hash includes backend_name -- Ollama uses model+prompt[:50], non-Ollama uses backend_name+target_lang only
- [02-04]: Synthetic default profile includes translation_backend and fallback_chain to prevent KeyError
- [02-05]: Removed Ollama tab entirely -- all backend config now managed through Translation Backends tab
- [02-05]: Backend cards use collapsible pattern with lazy config loading (fetch only when expanded)
- [02-05]: Fallback chain editor uses select dropdown + up/down arrows (no drag-and-drop dependency)
- [02-05]: Password fields have show/hide toggle per field for API key UX
- [02-06]: Per-test DB isolation via autouse fixture with tmp_path (not shared temp_db)
- [02-06]: MockBackend hierarchy (MockBackend/MockBackendFail/MockBackendAlt) for fallback chain testing
- [02-06]: Backend config_fields tested via class-level attributes (no instantiation needed for smoke tests)
- [03-01]: JellyfinEmbyServer is single class covering Jellyfin and Emby (server_type config field)
- [03-01]: Media server config stored as JSON array in single media_servers_json config_entries key
- [03-01]: MediaServerManager uses refresh_all (all-notify), not fallback chain
- [03-01]: PlexServer uses lazy plexapi connection (no connect in __init__)
- [03-01]: KodiServer uses directory-scoped VideoLibrary.Scan (not per-item ID lookup)
- [03-01]: plexapi import guarded with try/except -- PlexServer class loads without plexapi installed
- [03-02]: PUT /mediaservers/instances saves full array then invalidate+reload (not partial updates)
- [03-02]: POST /mediaservers/test creates temporary non-persisted instance for UI Test button
- [03-02]: Legacy jellyfin_url auto-migration stores back to config_entries as one-time migration
- [03-02]: jellyfin_client.py not deleted -- preserved for tests, no production code imports it
- [03-02]: Health endpoint aggregates per-instance status into media_servers summary
- [03-03]: MediaServersTab follows collapsible card pattern from TranslationBackendsTab for UI consistency
- [03-03]: Add Server uses dropdown menu (not modal) for quick type selection
- [03-03]: Onboarding media server step is optional -- Skip button advances without saving
- [03-03]: Onboarding loads media server types lazily on step entry to avoid unnecessary API calls
- [03-03]: Jellyfin tab and FIELDS entries fully removed -- no backward compatibility shim

### Pending Todos

None yet.

### Blockers/Concerns

- Phase 0 complete -- no blockers for Phases 1, 2, 3 (can proceed in parallel)
- Phase 1 complete -- all 6 plans executed, all summaries written
- Phase 2 complete -- all 6 plans executed, all summaries written, 36 unit tests passing
- Phase 3 complete -- all 3 plans executed, all summaries written (ABC + wiring + frontend)
- 28 pre-existing test failures in integration/performance tests (not caused by refactoring, existed before Phase 0)

## Session Continuity

Last session: 2026-02-15
Stopped at: Phase 3 complete -- next: Phase 4 planning/research or next roadmap phase
Resume file: .planning/phases/03-media-server-abstraction/03-03-SUMMARY.md
