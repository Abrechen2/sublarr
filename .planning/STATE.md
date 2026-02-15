# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-02-15)

**Core value:** ASS-first Anime Subtitle-Automation mit LLM-Uebersetzung -- automatisch die besten Untertitel finden, herunterladen und uebersetzen, ohne Styles zu zerstoeren.
**Current focus:** Phase 6 - Forced/Signs Subtitle Management (Complete)

## Current Position

Phase: 6 of 16 (Forced/Signs Subtitle Management)
Plan: 3 of 3 in current phase
Status: Phase complete
Last activity: 2026-02-15 -- Completed 06-03-PLAN.md (API & Frontend UI Forced Integration)

Progress: [████████████████████] 3/3 plans in phase

## Performance Metrics

**Velocity:**
- Total plans completed: 30
- Average duration: 6 min
- Total execution time: 195 min

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 00-architecture-refactoring | 3/3 | 27 min | 9 min |
| 01-provider-plugin-expansion | 6/6 | 64 min | 11 min |
| 02-translation-multi-backend | 6/6 | 23 min | 4 min |
| 03-media-server-abstraction | 3/3 | 18 min | 6 min |
| 04-whisper-speech-to-text | 3/3 | 13 min | 4 min |
| 05-standalone-mode | 5/5 | 28 min | 6 min |
| 06-forced-signs-subs | 3/3 | 22 min | 7 min |

**Recent Trend:**
- Last 5 plans: 05-05 (13 min), 06-01 (6 min), 06-02 (5 min), 06-03 (11 min)
- Trend: UI-heavy plans take longer (~11 min) vs backend-only (~5 min)

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
- [04-01]: WhisperManager uses single active backend (not fallback chain) -- only one Whisper instance at a time
- [04-01]: whisper_backend config entry selects active backend, defaults to "subgen"
- [04-01]: Config namespaced as whisper.<name>.<key> in config_entries (mirrors backend.<name>.<key> pattern)
- [04-01]: FasterWhisperBackend lazy-loads model and caches until model_size/device/compute_type changes
- [04-01]: SubgenBackend import wrapped in try/except ImportError for resilience
- [04-01]: LANGUAGE_TAG_MAP covers 14 languages with ISO 639-1 and 639-2 variants (no external dependency)
- [04-01]: WhisperQueue uses tempfile for extracted audio with guaranteed cleanup in finally block
- [04-02]: WhisperQueue singleton in routes/whisper.py with lazy initialization and config-based concurrency
- [04-02]: Case D returns whisper_pending status (async) -- does not block translate_file() return
- [04-02]: WhisperSubgenProvider kept with @register_provider but all methods are no-ops (deprecated)
- [04-02]: Global whisper config uses three keys: whisper_enabled, whisper_backend, max_concurrent_whisper
- [04-02]: Backend config uses whisper.<name>.<key> namespacing consistent with Plan 01
- [04-03]: WhisperBackendCard is a separate component from BackendCard -- different props (WhisperBackendInfo vs TranslationBackendInfo)
- [04-03]: WhisperTab combines global config section (enable/disable, backend selection, max concurrent) with backend cards below
- [04-03]: Toggle switch for whisper_enabled uses pure CSS transition (no third-party dependency)
- [04-03]: Model info table for faster_whisper shown only when that backend card is expanded
- [05-01]: Standalone CRUD follows exact pattern of db/wanted.py -- all functions use with _db_lock and return dicts
- [05-01]: Anime detection uses multi-signal heuristic: bracket groups, known fansub groups, CRC32 hashes, absolute numbering
- [05-01]: guessit called with episode_prefer_number=True for anime, standard episode then movie fallback for non-anime
- [05-01]: metadata_cache uses TEXT PRIMARY KEY (cache_key) with TTL-based expiration (not autoincrement)
- [05-02]: MetadataResolver uses lazy client creation -- only instantiated when API keys provided
- [05-02]: AniList always available (no API key required), TMDB and TVDB require keys
- [05-02]: DB cache calls wrapped in try/except for graceful degradation when DB not initialized
- [05-02]: AniList rate limiting at 0.7s between calls (conservative for 90 req/min limit)
- [05-02]: TVDB JWT token cached for 24h with automatic refresh on expiry
- [05-02]: Anime detection: AniList-first lookup, plus TMDB genre+origin_country heuristic (Animation+JP)
- [05-03]: MediaFileWatcher uses per-path threading.Timer for debounce (not global timer) to handle multiple simultaneous file events
- [05-03]: File stability check: size comparison after 2s sleep, reschedule if file still changing
- [05-03]: StandaloneScanner groups files by series before metadata lookup -- one API call per unique series title
- [05-03]: Standalone items use instance_name='standalone' in wanted_items, _cleanup skips path-based removal for them
- [05-03]: upsert_wanted_item extended with standalone_series_id and standalone_movie_id for standalone-to-wanted linking
- [05-04]: Standalone Blueprint uses /api/v1/standalone prefix (dedicated namespace, not shared /api/v1)
- [05-04]: Scanner endpoints run in daemon threads with lazy imports to avoid circular imports
- [05-04]: GET /status falls back to basic DB stats if StandaloneManager not yet implemented
- [05-04]: Series/movie deletion cascades to associated wanted_items before entity removal
- [05-04]: guessit fallback in _parse_filename_for_metadata gracefully degrades if standalone.parser unavailable
- [05-05]: Library Sources tab positioned after Radarr, before Media Servers for logical flow
- [05-05]: Watched folder management uses inline add/edit form (not modal) for simplicity
- [05-05]: Setup Mode step uses large cards with teal hover border for clear visual distinction
- [05-05]: Standalone path conditionally skips Sonarr/Radarr/Path Mapping steps via visibleSteps array
- [05-05]: StandaloneStatus polling every 10 seconds for watcher running indicator
- [06-01]: Multi-signal detection uses priority-ordered signals (ffprobe > filename > title > ASS) with confidence scoring
- [06-01]: classify_forced_result checks provider_data.foreign_parts_only (OpenSubtitles) before filename patterns
- [06-01]: Lazy import of classify_styles inside detect_subtitle_type to avoid circular imports
- [06-01]: VALID_FORCED_PREFERENCES validation in both create and update profile functions
- [06-01]: subtitle_type added to wanted upsert uniqueness check (application-level, not DB UNIQUE constraint)
- [06-02]: Scanner creates forced wanted items only for forced_preference=separate; auto and disabled do not create dedicated items
- [06-02]: OpenSubtitles filters results at provider level based on foreign_parts_only + query.forced_only
- [06-02]: ProviderManager classifies results post-search using classify_forced_result for providers without native forced support
- [06-02]: Forced subtitles are download-only -- no translation step (per research recommendation)
- [06-02]: Single-pass search pattern: search once, classify results, no double-searching
- [06-03]: Profile API validates forced_preference at route level (400 response) before db layer
- [06-03]: SubtitleTypeBadge only renders for 'forced' type -- 'full' returns null to avoid UI clutter
- [06-03]: Subtitle type filter buttons only shown when forcedCount > 0 to keep UI clean
- [06-03]: Profile list cards show forced preference only when not 'disabled' to reduce visual noise
- [06-03]: get_wanted_by_subtitle_type handles NULL subtitle_type values by defaulting to 'full'

### Pending Todos

None yet.

### Blockers/Concerns

- Phase 0 complete -- no blockers for Phases 1, 2, 3 (can proceed in parallel)
- Phase 1 complete -- all 6 plans executed, all summaries written
- Phase 2 complete -- all 6 plans executed, all summaries written, 36 unit tests passing
- Phase 3 complete -- all 3 plans executed, all summaries written (ABC + wiring + frontend)
- Phase 4 complete -- all 3 plans executed, all summaries written (whisper package + API + frontend)
- Phase 5 complete -- all 5 plans executed, all summaries written (DB + metadata + manager + API + UI)
- Phase 6 complete -- all 3 plans executed, all summaries written (data model + detection, scanner + search, API + UI)
- 28 pre-existing test failures in integration/performance tests (not caused by refactoring, existed before Phase 0)

## Session Continuity

Last session: 2026-02-15
Stopped at: Phase 6 complete -- all 3 plans executed (data model + detection, scanner + search pipeline, API + frontend UI)
Resume file: .planning/phases/06-forced-signs-subs/06-03-SUMMARY.md
