# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-02-20)

**Core value:** ASS-first Anime Subtitle-Automation mit LLM-Uebersetzung -- automatisch die besten Untertitel finden, herunterladen und uebersetzen, ohne Styles zu zerstoeren.
**Current focus:** Bug fixes + planning next milestone (v1.0.0)

## Current Position

Phase: 17-performance-optimizations (COMPLETE — all 3 plans done)
Plan: 17-03 complete (frontend bundle optimization, staleTime fix)
Status: All 17 phases complete — bug fix session 2026-02-21
Last activity: 2026-02-21 — Bug fixes: zombie jobs, wanted pagination, duplicate wanted_items (UNIQUE constraint + migration)

Progress: [███] 3/3 plans in phase 17 — ALL 17 PHASES COMPLETE

## Performance Metrics

**Velocity:**
- Total plans completed: 71
- Average duration: 9 min
- Total execution time: 604 min

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
| 07-events-hooks-custom-scoring | 3/3 | 46 min | 15 min |
| 08-i18n-backup-admin-polish | 5/5 | 116 min | 23 min |
| 09-openapi-release-preparation | 5/5 | 60 min | 12 min |
| 10-performance-scalability | 8/8 | 43 min | 5 min |
| 11-subtitle-editor | 4/4 | 21 min | 5 min |
| 13-comparison-sync-health-check | 3/3 | 19 min | 6 min |
| 12-batch-operations-smart-filter | 3/3 | 33 min | 11 min |
| 14-dashboard-widgets-quick-actions | 2/2 | 15 min | 8 min |
| 15-api-key-mgmt-notifications-cleanup | 5/5 | 39 min | 8 min |
| 16-external-integrations | 3/3 | 17 min | 6 min |

**Recent Trend:**
- Last 5 plans: 15-04 (10 min), 15-05 (11 min), 16-01 (5 min), 16-02 (5 min), 16-03 (7 min)
- Trend: ALL PHASES COMPLETE -- 71 plans across 17 phases executed

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
- [07-01]: blinker Namespace for signal isolation -- all Sublarr signals in sublarr_signals
- [07-01]: CATALOG_VERSION=1 for future payload schema evolution
- [07-01]: SocketIO bridge uses closure pattern (make_bridge) to correctly capture event_name in loop
- [07-01]: emit_event guards current_app with try/except RuntimeError for use outside request context
- [07-01]: Scoring cache TTL=60s -- balances DB freshness vs query overhead
- [07-01]: Provider modifier cache loads all modifiers at once (single query) instead of per-provider
- [07-01]: DB overrides merge on top of hardcoded defaults ({**defaults, **db_overrides})
- [07-02]: Progress/streaming events kept as direct socketio.emit -- high frequency, not for hooks/webhooks
- [07-02]: hook_executed signal skipped in hook/webhook subscribers to prevent infinite recursion
- [07-02]: standalone_scan_complete and standalone_file_detected added to EVENT_CATALOG
- [07-02]: Scoring cache invalidation triggered on config_updated when scoring-related keys change
- [07-02]: webhook_completed kept as socketio.emit (operational event, not catalog business event)
- [07-03]: clear_hook_logs() added to db/hooks.py for DELETE /hooks/logs endpoint (missing from Plan 02)
- [07-03]: Webhook test with event_name='*' uses 'config_updated' as sample event for payload generation
- [07-03]: ScoringTab uses weightsInit/modsInit guard to prevent query refetch from clobbering user edits
- [07-03]: Provider modifiers rendered as range sliders (-100 to +100) with color-coded values
- [08-01]: Default theme is dark (no stored preference = dark class applied, preserving current appearance)
- [08-01]: Theme stored as 'sublarr-theme' in localStorage with 3 states: dark, light, system
- [08-01]: Inline script in index.html prevents flash of wrong theme before React hydration
- [08-01]: i18n uses static JSON imports (no HTTP backend) -- only en/de, negligible bundle impact
- [08-01]: Language stored as 'sublarr-language' in localStorage via i18next-browser-languagedetector
- [08-01]: LanguageSwitcher shows target language label (DE when en active, EN when de active)
- [08-02]: ZIP backup uses in-memory BytesIO buffer then writes to backup_dir -- avoids temp file management
- [08-02]: ZIP restore imports config keys but skips secrets (same pattern as config/import endpoint)
- [08-02]: Statistics endpoint queries 5 DB tables independently (daily_stats, provider_stats, subtitle_downloads, translation_backend_stats, upgrade_history)
- [08-02]: Log rotation config stored in config_entries (log_max_size_mb, log_backup_count) -- applied on next restart
- [08-02]: Tools blueprint validates all file_path args against media_path using os.path.abspath for path traversal prevention
- [08-02]: All tool operations create .bak backup before modifying files -- non-destructive by default
- [08-02]: ASS timing adjustment uses centisecond precision (H:MM:SS.cc format) with ms-to-cs conversion
- [08-03]: Recharts v3 for chart library -- built-in TypeScript support, responsive containers, CSS variable theming
- [08-03]: Statistics endpoint enhanced with by_format aggregation from daily_stats.by_format_json column
- [08-03]: Backend downloads_by_provider normalized to use provider_name key (was provider)
- [08-03]: BackupTab uses file upload for restore (FormData) -- no server-side file path needed
- [08-03]: SubtitleToolsTab uses inline tool forms rather than modal dialogs for simplicity
- [08-03]: Logs rotation config is collapsible section at bottom to avoid cluttering the log viewer
- [08-04]: Library namespace shared across Library, Wanted, SeriesDetail (related content pages with subsections)
- [08-04]: Settings TAB_KEYS mapping keeps internal tab IDs as English strings for state comparison
- [08-04]: Sub-components receive t as prop or use useTranslation directly depending on component isolation
- [08-04]: Sidebar navGroups uses labelKey/titleKey pattern with static keys resolved at render via t()
- [08-04]: Statistics.tsx skipped (created by parallel plan 08-03) -- translation JSON files ready for consumption
- [08-05]: Activity namespace shared across Activity, Queue, History, Blacklist (related activity pages with subsections)
- [08-05]: StatusBadge uses translation map from API status strings to common:status.* keys (12 statuses mapped)
- [08-05]: Onboarding ALL_STEPS uses titleKey/descKey pattern (static const, resolved at render via t())
- [08-05]: Toast.tsx skipped -- no built-in text labels, only renders dynamic messages from callers
- [08-05]: Statistics.tsx auto-wrapped (gap from parallel 08-03 execution, translation JSON existed from 08-04)
- [09-01]: apispec-webframeworks pinned to >=1.0.0 (not >=1.3.0 as planned -- latest available is 1.2.0)
- [09-01]: OpenAPI spec is module-level singleton -- register_all_paths called once after register_blueprints
- [09-01]: Version centralized in version.py -- used by health, backup manifest, SPA fallback, and OpenAPI spec
- [09-01]: YAML docstring pattern: human summary + --- + OpenAPI YAML block in each view function
- [09-01]: Tag names match blueprint domains: System, Translate, Providers, Wanted, Library, Config
- [09-02]: Incremental scan uses ISO timestamp comparison on Sonarr lastInfoSync and Radarr movieFile.dateAdded
- [09-02]: Full cleanup only runs on full scans; incremental scans skip path-based removal to avoid false removals
- [09-02]: Parallel search uses max_workers=min(4, total) -- bounded to avoid over-parallelization
- [09-02]: Whisper backend health reported as healthy=True when whisper is disabled (not a degradation state)
- [09-02]: Arr connectivity checks iterate all configured instances per get_sonarr_instances/get_radarr_instances
- [09-02]: _cancel_search flag for graceful mid-batch cancellation without abrupt thread termination
- [09-03]: Named export adapter pattern (.then(m => ({ default: m.ExportName }))) for React.lazy with named exports
- [09-03]: Settings split into 7 files -- simple field-based tabs stay in index.tsx to avoid prop drilling
- [09-03]: Self-contained tab components fetch own data via React Query hooks (not parent-passed props)
- [09-03]: AdvancedTab.tsx groups 4 smaller tabs (LanguageProfiles, LibrarySources, Backup, SubtitleTools)
- [09-05]: CHANGELOG organized by feature area (#### headers) rather than flat list for readability
- [09-05]: Migration guide emphasizes version renumber is NOT a downgrade to avoid user confusion
- [09-05]: Unraid template Ollama URL marked as non-required (standalone mode does not need it)
- [09-05]: docker-compose.yml left unchanged -- already correct with env_file pattern and proper security settings
- [09-04]: Created dedicated /api/v1/tasks endpoint (vs reusing /health/detailed) for cleaner frontend consumption
- [09-04]: useTriggerTask maps task names to trigger endpoints (wanted_scan -> /wanted/refresh, wanted_search -> /wanted/search-all, backup -> /database/backup)
- [09-04]: ListChecks icon for Tasks nav entry, positioned between Statistics and Logs in System group
- [10-01]: All ORM models inherit from db.Model (Flask-SQLAlchemy pattern) -- not standalone DeclarativeBase
- [10-01]: Text type (not DateTime) for all timestamp columns to preserve backward compatibility with existing data
- [10-01]: Flask-SQLAlchemy/Migrate imports guarded with try/except ImportError for graceful degradation
- [10-01]: stamp_existing_db_if_needed() uses 'jobs' table as sentinel for pre-existing databases
- [10-01]: Alembic render_as_batch=True for all migration contexts (required for SQLite ALTER TABLE)
- [10-02]: Convenience functions in __init__.py instantiate fresh repository per call -- stateless bridge pattern
- [10-02]: CacheRepository covers ffprobe_cache + episode_history + anidb_mappings (mirrors db/cache.py scope)
- [10-02]: ScoringRepository self-contains default weight dicts for merge logic (not imported from providers/base.py)
- [10-02]: TranslationRepository preserves weighted running average formula exactly for backend stats
- [10-02]: BlacklistRepository uses check-then-insert (no INSERT OR IGNORE equivalent in SQLAlchemy)
- [10-02]: LibraryRepository uses sqlalchemy.text() for SQLite datetime() in time-based aggregation
- [10-03]: StandaloneRepository upsert methods return full dict (not just row_id) for ORM pattern consistency
- [10-03]: HookRepository cascade-deletes hook_log entries via explicit DELETE before hook/webhook deletion
- [10-03]: ProviderRepository separates record_search from record_download to match existing API granularity
- [10-03]: All 15 repository classes (1 base + 14 domain) re-exported from db.repositories.__init__
- [10-04]: Package named job_queue (not queue) to avoid shadowing Python stdlib queue module
- [10-04]: Redis key prefix 'sublarr:' for namespace isolation in shared Redis instances
- [10-04]: MemoryCacheBackend evicts expired entries every 100 accesses to prevent memory growth
- [10-04]: MemoryJobQueue retains job metadata for 24h with periodic cleanup every 50 enqueues
- [10-04]: RQJobQueue only enqueues -- separate rq worker process required for execution
- [10-05]: All app init code wrapped inside with app.app_context() for SQLAlchemy session access
- [10-05]: db/config.py rewritten in Task 1 (not Task 2a) because app startup depends on get_all_config_entries()
- [10-05]: Thin wrapper pattern: global _repo with lazy _get_repo() for each db/ module
- [10-05]: SQLAlchemy import aliased as sa_db to avoid name collision with db package
- [10-06]: pg_dump -Fc (custom format) for compressed PostgreSQL backups with pg_restore compatibility
- [10-06]: Backup file extension .pgdump for PostgreSQL, .db for SQLite -- restore dispatches by extension
- [10-06]: pg_restore exit code non-zero includes warnings; check stderr for ERROR keyword instead
- [10-06]: ZIP backup manifest includes db_backend field so restore knows which format to expect
- [10-06]: PostgreSQL pool stats exposed via get_pool_stats() -- returns None for SQLite (StaticPool)
- [10-07]: DB pool metrics import extensions.db as sa_db to match app.py alias convention from 10-05
- [10-07]: Redis/queue row collapsed by default on database dashboard (shown only when Redis active)
- [10-07]: Dashboard JSON uses ${DS_PROMETHEUS} variable for datasource portability
- [10-08]: Fast cache operations wrapped in try/except so Redis failure never blocks provider search
- [10-08]: DB cache hits backfill fast cache for subsequent acceleration (write-through on read)
- [10-08]: Job queue submit functions are additive wrappers -- existing route threading unchanged
- [10-08]: Business logic (translate_file, process_wanted_item) untouched -- only submission abstracted
- [11-01]: Optimistic concurrency via mtime comparison with 0.01s tolerance (no file locking)
- [11-01]: pysubs2 lazy-imported at function level to match existing tools.py pattern
- [11-01]: classify_styles from ass_utils used for /parse endpoint style classification (dialog vs signs)
- [11-01]: Editor theme uses hardcoded hex colors (not CSS vars) for reliable CodeMirror rendering
- [11-02]: SubtitlePreview uses ReactCodeMirrorRef for view access instead of EditorView.updateListener
- [11-02]: Timeline cue-to-line mapping uses format-aware estimation (ASS: header offset + index, SRT: index * 4)
- [11-02]: Timeline label count auto-scales: one label per ~5min, clamped 2-10 labels
- [11-02]: Cue color-coding: teal for dialog, amber for signs/songs -- matches SubtitleTimeline styles prop
- [11-03]: CodeMirror value prop set once (uncontrolled) to avoid cursor position reset on re-render
- [11-03]: Save tracks currentMtime in state, updated after each successful save, for correct multi-save concurrency
- [11-03]: DiffHeader extracted as shared sub-component for loading/error/404/success states
- [11-03]: Both diff panes use EditorState.readOnly to prevent accidental edits in comparison view
- [11-04]: SubtitleEditorModal uses default export for direct lazy import compatibility
- [11-04]: Named export adapter pattern for SubtitleEditor and SubtitleDiff lazy imports
- [11-04]: Wanted page shows preview only (not edit) since items are missing/incomplete subs
- [11-04]: History page shows preview and diff (GitCompare) buttons per entry
- [11-04]: deriveSubtitlePath helper replaces video extension with .{lang}.{format}
- [11-04]: Unsaved changes guard on Escape key, overlay click, and close button
- [13-01]: Quality score: 100 minus penalties (10/error, 3/warning, 1/info), clamped to 0
- [13-01]: Health results stored as new records each time (not upsert) for trend tracking
- [13-01]: Advanced sync preview returns 5 representative events (first, 25%, 50%, 75%, last)
- [13-01]: Batch health-check limited to 50 files per request
- [13-01]: apply_fixes creates backup via shutil.copy2 directly (same .bak pattern as tools.py)
- [13-02]: ComparisonPanel reuses existing CodeMirror setup (sublarrTheme, assLanguage, srtLanguage) for visual consistency
- [13-02]: Scroll synchronization uses debounced DOM scroll events (50ms) to prevent cascading
- [13-02]: SyncControls has two-step apply: Preview first, then confirm with warning about file modification
- [13-02]: Actions column widened from w-20 to w-32 to accommodate Compare and Sync buttons
- [13-02]: Compare button only shown when episode has 2+ subtitle files; Sync only when at least 1 file
- [13-02]: SubtitleComparison and SyncControls use React.lazy for code splitting
- [13-03]: HealthBadge color thresholds: green >= 80, amber >= 50, red < 50, gray with "?" for null
- [13-03]: HealthCheckPanel sorts issues by severity (errors first, then warnings, then info)
- [13-03]: Batch fix requires explicit confirmation step showing all fixes to be applied
- [13-03]: HealthDashboardWidget uses Recharts LineChart sparkline (no axes) for compact display
- [13-03]: Actions column widened from w-32 to w-40 to accommodate Health button
- [13-03]: healthScores tracked in local state per SeriesDetail, updated on fix via API re-fetch
- [13-03]: Recharts Tooltip formatter uses unknown params to match existing chart type patterns
- [12-01]: FTS5 trigram tables use LIKE queries (not MATCH) for 2+ char search support
- [12-01]: SearchRepository uses db.engine directly instead of session.bind for test compatibility
- [12-01]: Condition tree builder uses field allowlist per scope to prevent injection
- [12-01]: Alembic migration written manually due to stamp_existing_db_if_needed incompatibility
- [12-02]: cmdk Command.Dialog with shouldFilter=false -- all filtering done server-side via FTS5
- [12-02]: Zustand per-scope selection store (wanted/library/history) with independent selection sets
- [12-02]: Ctrl+K handler in App.tsx (not Sidebar) for global scope accessibility
- [12-02]: onOpenChange callback wrapper for query reset (avoids React 19 strict lint useEffect-setState)
- [12-02]: navigate() calls wrapped with void operator for floating promise lint compliance
- [12-03]: Wanted page Zustand store replaces local selectedIds for cross-component compatibility with BatchActionBar
- [12-03]: FilterBar coexists with existing button filters -- activeFilters synced bidirectionally
- [12-03]: Sort/search on Wanted page is client-side (backend API does not accept sort_by/search params on wanted endpoint)
- [12-03]: Sidebar search trigger dispatches synthetic Ctrl+K keydown event (no prop drilling)
- [12-03]: Library page already had search + sort -- no changes needed (Task 3 was a no-op)
- [12-03]: i18n locale files are at frontend/src/i18n/locales/ (not frontend/public/locales/ as plan suggested)
- [14-01]: react-grid-layout v2 with built-in TypeScript types (no @types needed)
- [14-01]: hiddenWidgets stored as string[] (not Set) for JSON serialization compatibility
- [14-01]: Widgets are self-contained: each fetches own data via React Query hooks (no prop drilling)
- [14-01]: StatCardsWidget has noPadding=true for grid-within-grid card layout pattern
- [14-01]: Layout persisted via onLayoutChange for all breakpoints (not per-pixel onDragStop)
- [14-01]: useContainerWidth hook for responsive container measurement with mounted guard
- [14-01]: QualityWidget wraps existing HealthDashboardWidget via lazy import adapter pattern
- [14-02]: react-hotkeys-hook v5 for declarative keyboard shortcut registration with useHotkeys
- [14-02]: FAB uses useQuickActionHandlers hook mapping action template IDs to handler functions
- [14-02]: GlobalShortcuts is a render-null component inside BrowserRouter for router context access
- [14-02]: Ctrl+K handler preserved in App.tsx as-is -- not re-registered in useKeyboardShortcuts to avoid double-fire
- [14-02]: FAB hides entirely when no actions available for current route
- [14-02]: Page-specific hotkeys registered dynamically based on current route actions
- [15-01]: API_KEY_REGISTRY maps 10 services to config_entries keys and optional test functions
- [15-01]: _mask_value shows first4+***+last4 (all *** if <=8 chars) for consistent secret masking
- [15-01]: Test dispatch via _TEST_DISPATCH dict with lazy-imported functions to avoid circular imports
- [15-01]: Bazarr config auto-detection: YAML first, then INI fallback when extension unknown
- [15-01]: Bazarr DB opened read-only (file:...?mode=ro) with per-table try/except for version tolerance
- [15-02]: Template fallback chain: specific (service+event) > event-only > default (both null)
- [15-02]: SandboxedEnvironment for Jinja2 template rendering prevents template injection attacks
- [15-02]: Quiet hours is_quiet_hours checks all enabled configs with overnight range support (start > end)
- [15-02]: Notification history logged on every send attempt including failures for audit trail
- [15-02]: Event filters stored as config_entries with notification_filter_* prefix for consistency
- [15-02]: Template rendering failure falls back to original title/body (backward compatible)

- [15-03]: SHA-256 hash computed on normalized content (stripped + CRLF->LF) to detect duplicates regardless of line ending differences
- [15-03]: ThreadPoolExecutor(max_workers=4) for parallel file hashing during scan
- [15-03]: Keep-at-least-one safety guard pre-validates all groups before starting any deletions
- [15-03]: CleanupScheduler uses threading.Timer pattern (same as wanted_scanner) with configurable interval from config_entries
- [15-03]: Module-level _scan_state dict with threading.Lock for background scan tracking
- [15-03]: Orphan detection compares subtitle basenames against media file basenames in same directory
- [15-03]: _start_schedulers receives app parameter for cleanup scheduler app_context needs

- [15-04]: NotificationTemplatesTab merges legacy notification toggles + Apprise URLs at top for backward compat
- [15-04]: Old Notifications tab replaced (not kept alongside) -- all notification config in one unified tab
- [15-04]: Notification fields removed from FIELDS array -- NotificationTemplatesTab manages its own config via React Query
- [15-04]: TemplateEditor uses simple regex-based Jinja2 highlighting (not full parser) for lightweight bundle
- [15-04]: TemplatePreview debounces at 500ms to avoid excessive API calls on rapid editing
- [15-04]: QuietHoursConfig includes 24h timeline bar visualization for overnight range support

- [15-05]: Polling-based scan progress (2s interval via useCleanupScanStatus) instead of WebSocket -- useWebSocket hook has no generic event listener pattern
- [15-05]: CleanupTab uses collapsible Section component for all five sections -- History collapsed by default to reduce clutter
- [15-05]: DedupGroupList initializes first file as KEEP by default, rest as DELETE -- matches user expectation for keep-best
- [15-05]: Dashboard DiskSpaceWidget uses compact donut chart without tooltips -- minimal footprint matching existing widget patterns

- [16-01]: extended_health_check() added as new method -- existing health_check() completely untouched
- [16-01]: Bazarr _get_table_info() uses PRAGMA table_info for schema-tolerant column discovery
- [16-01]: generate_mapping_report() masks sensitive fields (apikey, password, token, secret) in sample rows
- [16-01]: Kodi JSON-RPC version extracted via JSONRPC.Version method (major.minor.patch)
- [16-01]: _read_history limited to 1000 rows DESC for performance on large Bazarr databases

- [16-02]: ISO 639-1/2 codes hardcoded as Python sets (~80+130 codes) for zero external dependencies in compat_checker
- [16-02]: Compat checker validates relative path positioning (not absolute paths) to handle Docker volume mappings
- [16-02]: Export manager limits subtitle file scanning to 1000 files to prevent excessive I/O on large libraries
- [16-02]: Kodi checker accepts BCP 47 with underscore separator and English language names per Kodi 22+ docs
- [16-02]: Media server health endpoint uses extended_health_check if available, falls back to basic health_check

- [16-03]: exportIntegrationConfig named differently from existing exportConfig to avoid name collision in client.ts
- [16-03]: useExtendedHealthAll uses enabled:false with manual refetch trigger (Run Diagnostics button)
- [16-03]: Bazarr section links to existing ApiKeysTab for actual import (no duplication of import logic)
- [16-03]: Compat and Health sections default to collapsed (defaultOpen=false) to reduce initial visual load

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
- Phase 7 complete -- all 3 plans executed, all summaries written (event system + engine/dispatcher + API/UI)
- Phase 8 complete -- all 5 plans executed, all summaries written (theme, backend APIs, frontend pages, core i18n, remaining i18n)
- Phase 9 complete -- all 5 plans executed (OpenAPI infra + backend performance + frontend performance + release docs + remaining blueprints/tasks page)
- Phase 10 complete -- all 8 plans executed (ORM models + Alembic + repositories + cache/queue + app integration + operational tooling + extended metrics + Grafana dashboards + cache/queue wiring)
- Phase 11 complete -- all 4 plans executed (editor API + preview/timeline + editor/diff + modal/page integration)
- Phase 13 complete -- all 3 plans executed (backend health/sync/compare + frontend types/hooks/comparison/sync + frontend health UI/charts/dashboard)
- Phase 12 complete -- all 3 plans executed (backend FTS5/presets/batch API + frontend FilterBar/BatchActionBar/GlobalSearchModal/selectionStore + page integration/i18n/tests)
- Phase 14 complete -- all 2 plans executed (dashboard widget system + quick-actions FAB + keyboard shortcuts)
- Phase 15 complete -- all 5 plans executed (API key management + Bazarr migration, notification management backend, cleanup system backend, frontend Settings tabs, cleanup frontend)
- Phase 16 COMPLETE -- all 3 plans executed (extended health checks, compat/export/API, frontend IntegrationsTab)
- ALL 17 PHASES COMPLETE -- 71 plans executed across phases 0-16
- 28 pre-existing test failures in integration/performance tests (not caused by refactoring, existed before Phase 0)

## Session Continuity

Last session: 2026-02-20
Stopped at: Phase 16 plan 3 of 3 complete -- Frontend IntegrationsTab -- ALL PHASES COMPLETE
Resume file: .planning/phases/16-external-integrations/16-03-SUMMARY.md
