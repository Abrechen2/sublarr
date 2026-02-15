# Roadmap: Sublarr Phase 2+3

## Overview

Sublarr Phase 2 transforms the subtitle manager from a monolithic Ollama-only tool into an open platform with plugin extensibility, multi-backend translation, Whisper speech-to-text, and media server abstraction. Phase 3 adds advanced UX features: a subtitle editor, batch operations, comparison tools, and dashboard customization. The journey starts with architecture refactoring (Application Factory, Blueprints) that unblocks everything else, progresses through core platform capabilities, and culminates in polish and external integrations.

## Milestones

- 📋 **Phase 2: Open Platform** - Phases 0-10 (architecture through performance)
- 📋 **Phase 3: Advanced Features & UX** - Phases 11-16 (editor through integrations)

## Phases

**Phase Numbering:**
- Integer phases (0-16): Planned milestone work
- Decimal phases (e.g., 2.1): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [x] **Phase 0: Architecture Refactoring** - Convert monolith to Application Factory + Blueprints
- [x] **Phase 1: Provider Plugin + Expansion** - Plugin system and 8 new built-in providers
- [x] **Phase 2: Translation Multi-Backend** - ABC-based multi-backend translation with fallback chains
- [x] **Phase 3: Media-Server Abstraction** - Plex, Kodi support alongside existing Jellyfin/Emby
- [ ] **Phase 4: Whisper Speech-to-Text** - faster-whisper and Subgen integration as translation fallback
- [ ] **Phase 5: Standalone Mode** - Folder-watch operation without Sonarr/Radarr dependency
- [ ] **Phase 6: Forced/Signs Subtitle Management** - Forced subtitle detection, search, and per-series config
- [ ] **Phase 7: Events/Hooks + Custom Scoring** - Internal event bus, script hooks, outgoing webhooks, scoring config
- [ ] **Phase 8: i18n + Backup + Admin Polish** - UI internationalization, backup/restore, statistics, theming
- [ ] **Phase 9: OpenAPI + Release Preparation** - API documentation, performance tuning, community launch
- [ ] **Phase 10: Performance & Scalability** - SQLAlchemy/PostgreSQL option, Redis caching, RQ job queue
- [ ] **Phase 11: Subtitle Editor** - ASS/SRT preview component and inline editor with CodeMirror
- [ ] **Phase 12: Batch Operations + Smart-Filter** - Multi-select bulk actions, saved filters, global search
- [ ] **Phase 13: Comparison + Sync + Health-Check** - Side-by-side diff, timing sync, subtitle health analysis
- [ ] **Phase 14: Dashboard Widgets + Quick-Actions** - Drag-and-drop widgets, keyboard shortcuts, FAB toolbar
- [ ] **Phase 15: API-Key Mgmt + Notifications + Cleanup** - Key management, notification templates, deduplication
- [ ] **Phase 16: External Integrations** - Bazarr migration, Plex/Kodi compatibility, export formats

## Phase Details

### Phase 0: Architecture Refactoring
**Goal**: Codebase supports Application Factory pattern and Blueprint-based routing so plugins, backends, and media servers can register cleanly
**Depends on**: Nothing (prerequisite for everything)
**Requirements**: ARCH-01, ARCH-02, ARCH-03, ARCH-04
**Success Criteria** (what must be TRUE):
  1. Application starts via `create_app()` factory function, not module-level globals
  2. API routes are organized in separate Blueprint files (translate, providers, library, wanted, config, webhooks, system) instead of one monolithic server.py
  3. Database access uses Flask app context instead of module-level singletons, and database.py is split into focused modules
  4. All existing tests pass without modification (backward compatibility preserved)
**Plans:** 3 plans

Plans:
- [x] 00-01-PLAN.md -- Split database.py into db/ package (9 domain modules)
- [x] 00-02-PLAN.md -- Create extensions.py, app.py factory, routes/ package (9 blueprints)
- [x] 00-03-PLAN.md -- Update all imports, entry points, delete old files, verify tests

### Phase 1: Provider Plugin + Expansion
**Goal**: Users can install third-party provider plugins and access 8 additional built-in providers, expanding subtitle coverage across languages and sources
**Depends on**: Phase 0 (needs Application Factory for plugin registration)
**Requirements**: PLUG-01, PLUG-02, PLUG-03, PLUG-04, PLUG-05, PROV-01, PROV-02, PROV-03, PROV-04, PROV-05, PROV-06, PROV-07, PROV-08, PROV-09, PROV-10
**Success Criteria** (what must be TRUE):
  1. User can drop a Python file into the plugins directory and it appears as a usable provider after restart (or hot-reload)
  2. User can configure plugin-specific settings (credentials, options) through the Settings UI without code changes
  3. User can search and download subtitles from at least 8 new providers (Addic7ed, Podnapisi, Gestdown, Kitsunekko, Whisper-Subgen, Napisy24, Titrari, LegendasDivx)
  4. Provider health dashboard shows per-provider success rate, response time, and download count; unhealthy providers auto-disable with cooldown
  5. Plugin developer documentation and template enable creating a new provider in under 30 minutes
**Plans:** 6 plans

Plans:
- [x] 01-01-PLAN.md -- Plugin infrastructure: declarative config_fields, plugin discovery, manifest validation, DB config storage, API endpoints
- [x] 01-02-PLAN.md -- Provider health monitoring: response time tracking, auto-disable with cooldown, frontend stats display
- [x] 01-03-PLAN.md -- Plugin hot-reload (watchdog file watcher + API endpoint) and developer template with documentation
- [x] 01-04-PLAN.md -- REST/XML providers: Gestdown (Addic7ed proxy) and Podnapisi
- [x] 01-05-PLAN.md -- Specialized providers: Kitsunekko (Japanese scraping), Napisy24 (Polish hash), Whisper-Subgen (external ASR)
- [x] 01-06-PLAN.md -- Scraping providers: Titrari (Romanian) and LegendasDivx (Portuguese with session auth)

### Phase 2: Translation Multi-Backend
**Goal**: Users can translate subtitles using any of 5 backends (Ollama, DeepL, LibreTranslate, OpenAI-compatible, Google) with per-profile backend selection and automatic fallback
**Depends on**: Phase 0 (needs Application Factory for backend registration)
**Requirements**: TRAN-01, TRAN-02, TRAN-03, TRAN-04, TRAN-05, TRAN-06, TRAN-07, TRAN-08, TRAN-09, TRAN-10
**Success Criteria** (what must be TRUE):
  1. User can configure and test multiple translation backends (Ollama, DeepL, LibreTranslate, OpenAI-compatible, Google) from the Settings page
  2. User can assign a specific translation backend to each language profile, so different series use different translation services
  3. When the primary backend fails, translation automatically falls through a user-configured fallback chain to the next available backend
  4. Translation quality metrics are tracked per backend and visible in a dashboard widget, showing success rate and error history
**Plans:** 6 plans

Plans:
- [x] 02-01-PLAN.md -- TranslationBackend ABC, TranslationManager, shared LLM utilities, OllamaBackend migration, DB schema extension
- [x] 02-02-PLAN.md -- API backends: DeepL (with glossary) and LibreTranslate (self-hosted)
- [x] 02-03-PLAN.md -- LLM + API backends: OpenAI-compatible (multi-endpoint) and Google Cloud Translation
- [x] 02-04-PLAN.md -- Rewire translator.py to use TranslationManager, backend management API endpoints, profile integration
- [x] 02-05-PLAN.md -- Frontend: Translation Backends settings tab, profile backend selector, fallback chain editor, stats display
- [x] 02-06-PLAN.md -- Test suite for translation multi-backend system

### Phase 3: Media-Server Abstraction
**Goal**: Users can connect Plex and Kodi (in addition to Jellyfin/Emby) for library refresh notifications, with multi-server support
**Depends on**: Phase 0 (needs Application Factory for media server registration)
**Requirements**: MSRV-01, MSRV-02, MSRV-03, MSRV-04, MSRV-05, MSRV-06, MSRV-07
**Success Criteria** (what must be TRUE):
  1. User can configure Plex, Kodi, Jellyfin, and/or Emby instances from a unified media server settings page with test buttons
  2. After subtitle download or translation, all configured media servers receive a library refresh notification for the affected item
  3. User can configure multiple media servers of different types simultaneously (e.g., Plex + Jellyfin)
  4. Onboarding wizard offers media server selection with multi-server configuration
**Plans:** 3 plans

Plans:
- [x] 03-01-PLAN.md -- MediaServer ABC, MediaServerManager, JellyfinEmby migration, Plex and Kodi backends
- [x] 03-02-PLAN.md -- API blueprint, translator.py rewire, config invalidation, health endpoint, legacy migration
- [x] 03-03-PLAN.md -- Frontend Media Servers settings tab, onboarding wizard media server step

### Phase 4: Whisper Speech-to-Text
**Goal**: When no subtitles are found from any provider, Sublarr can generate them from audio using Whisper, creating a complete fallback chain
**Depends on**: Phase 2 (Whisper uses TranslationBackend ABC for post-transcription translation)
**Requirements**: WHSP-01, WHSP-02, WHSP-03, WHSP-04, WHSP-05, WHSP-06, WHSP-07, WHSP-08
**Success Criteria** (what must be TRUE):
  1. User can configure faster-whisper (local GPU/CPU) or Subgen API (external) as Whisper backends from Settings
  2. When all subtitle providers fail, the translation pipeline automatically falls back to Whisper transcription (Case D) for the source language
  3. Whisper jobs appear in a dedicated queue with progress updates via WebSocket, respecting max-concurrent limits
  4. Whisper correctly extracts the Japanese audio track (or user-configured source language track) from media files via ffmpeg
  5. Transcription results include language detection that is validated against the expected source language
**Plans**: TBD

Plans:
- [ ] 04-01: TBD
- [ ] 04-02: TBD
- [ ] 04-03: TBD

### Phase 5: Standalone Mode
**Goal**: Users without Sonarr/Radarr can use Sublarr by pointing it at media folders, with automatic file detection and metadata lookup
**Depends on**: Phase 0 (needs Application Factory)
**Requirements**: STND-01, STND-02, STND-03, STND-04, STND-05, STND-06, STND-07, STND-08, STND-09
**Success Criteria** (what must be TRUE):
  1. User can configure watched folders in Settings and new media files are automatically detected and added to the library
  2. Media files are parsed and grouped into series/movies with correct metadata from TMDB, AniList, or TVDB
  3. Standalone-detected items appear in the Wanted list and go through the same search/download/translate pipeline as Sonarr/Radarr items
  4. Onboarding wizard offers a standalone setup path that skips Sonarr/Radarr configuration entirely
**Plans**: TBD

Plans:
- [ ] 05-01: TBD
- [ ] 05-02: TBD
- [ ] 05-03: TBD

### Phase 6: Forced/Signs Subtitle Management
**Goal**: Users can separately manage forced/signs subtitles per series, with automatic detection and dedicated search
**Depends on**: Phase 1 (needs provider search parameter support)
**Requirements**: FRCD-01, FRCD-02, FRCD-03, FRCD-04, FRCD-05
**Success Criteria** (what must be TRUE):
  1. Forced subtitles are tracked as a separate category in the database and displayed with distinct badges in the UI
  2. Provider search can specifically target forced/signs subtitles when enabled for a series
  3. Existing subtitles are analyzed (ffprobe flags, ASS style analysis, naming patterns) to detect whether they are forced/signs
  4. User can set forced subtitle preference (disabled/separate/auto) per series in the language profile
**Plans**: TBD

Plans:
- [ ] 06-01: TBD
- [ ] 06-02: TBD

### Phase 7: Events/Hooks + Custom Scoring
**Goal**: Users can extend Sublarr behavior through shell scripts, outgoing webhooks, and custom scoring weights without modifying code
**Depends on**: Phase 0 (needs Application Factory for event bus)
**Requirements**: EVNT-01, EVNT-02, EVNT-03, EVNT-04, SCOR-01, SCOR-02
**Success Criteria** (what must be TRUE):
  1. Internal events (subtitle downloaded, translation complete, provider failed, etc.) are published on an event bus that hooks can subscribe to
  2. User can configure shell scripts that execute on specific events, with environment variables carrying event data and configurable timeouts
  3. User can configure outgoing webhooks (HTTP POST with JSON payload) for any event, with retry logic on failure
  4. User can adjust scoring weights (hash, series, year, season, episode, release_group, ASS bonus) and set per-provider score modifiers from Settings
**Plans**: TBD

Plans:
- [ ] 07-01: TBD
- [ ] 07-02: TBD

### Phase 8: i18n + Backup + Admin Polish
**Goal**: UI is available in English and German, config can be backed up and restored, and the admin experience is polished with statistics, log improvements, and theming
**Depends on**: Phase 0 (needs Blueprints for consistent i18n integration)
**Requirements**: I18N-01, I18N-02, I18N-03, BKUP-01, BKUP-02, BKUP-03, ADMN-01, ADMN-02, ADMN-03, ADMN-04
**Success Criteria** (what must be TRUE):
  1. User can switch the entire UI between English and German, with the preference persisted across sessions
  2. User can create a full backup (config + database as ZIP) manually or on a schedule, and download it from the UI
  3. User can restore from a backup ZIP (uploaded via UI), with schema validation and merge strategy
  4. Statistics page shows charts with time-range filters for translations, downloads, provider usage, and can be exported
  5. User can toggle between dark and light theme, and logs page supports level filtering, download, and rotation config
**Plans**: TBD

Plans:
- [ ] 08-01: TBD
- [ ] 08-02: TBD
- [ ] 08-03: TBD

### Phase 9: OpenAPI + Release Preparation
**Goal**: API is fully documented with Swagger UI, performance is optimized, and the project is ready for community launch as v0.9.0-beta
**Depends on**: Phase 8 (i18n should be complete before community launch)
**Requirements**: OAPI-01, OAPI-02, OAPI-03, OAPI-04, OAPI-05, OAPI-06, RELS-01, RELS-02, RELS-03, RELS-04, RELS-05
**Success Criteria** (what must be TRUE):
  1. All API endpoints are documented in an OpenAPI spec accessible via Swagger UI at /api/docs
  2. Wanted scan runs incrementally (only changed items) and provider search runs with parallelism and connection pooling
  3. A detailed health endpoint (/health/detailed) reports status of all subsystems (DB, providers, translation backends, media servers)
  4. Migration guide, user guide, and plugin developer guide are published; community provider repository is set up
  5. v0.9.0-beta is tagged, Docker images published, CHANGELOG written, Unraid template updated
**Plans**: TBD

Plans:
- [ ] 09-01: TBD
- [ ] 09-02: TBD
- [ ] 09-03: TBD

### Phase 10: Performance & Scalability
**Goal**: Users with large libraries can optionally use PostgreSQL instead of SQLite and Redis for caching/job queue, with zero-config SQLite remaining the default
**Depends on**: Phase 9 (release stabilization before database layer changes)
**Requirements**: PERF-01, PERF-02, PERF-03, PERF-04, PERF-05, PERF-06, PERF-07, PERF-08, PERF-09
**Success Criteria** (what must be TRUE):
  1. User can switch database backend to PostgreSQL via environment variable while SQLite remains the zero-config default
  2. Database access uses SQLAlchemy ORM with connection pooling, and migrations run automatically via Alembic on startup
  3. Redis can optionally be used for provider cache, session storage, and rate limiting, with graceful fallback to SQLite when Redis is unavailable
  4. Job queue uses Redis + RQ for persistent jobs that survive container restarts (falling back to in-process queue without Redis)
  5. Predefined Grafana dashboards and extended Prometheus metrics are available for monitoring at scale
**Plans**: TBD

Plans:
- [ ] 10-01: TBD
- [ ] 10-02: TBD
- [ ] 10-03: TBD

### Phase 11: Subtitle Editor
**Goal**: Users can preview and edit subtitle files directly in the browser with syntax highlighting, live preview, and version diffing
**Depends on**: Phase 0 (needs stable API structure)
**Requirements**: EDIT-01, EDIT-02, EDIT-03, EDIT-04, EDIT-05
**Success Criteria** (what must be TRUE):
  1. User can preview any ASS or SRT subtitle file with syntax highlighting and a visual timeline in the Wanted, History, and Series Detail pages
  2. User can open an inline editor (CodeMirror) for any subtitle file with undo/redo and real-time validation
  3. Editing a subtitle automatically creates a backup of the original before saving changes
  4. Editor supports live preview, diff view against previous version, and find-and-replace
**Plans**: TBD

Plans:
- [ ] 11-01: TBD
- [ ] 11-02: TBD

### Phase 12: Batch Operations + Smart-Filter
**Goal**: Users can perform bulk actions across library, wanted, and history pages, with saved filter presets and global search
**Depends on**: Phase 0 (needs stable API structure)
**Requirements**: BATC-01, BATC-02, BATC-03, BATC-04, BATC-05, BATC-06, BATC-07
**Success Criteria** (what must be TRUE):
  1. User can multi-select items in Library, Wanted, and History pages and apply bulk actions (search, process, blacklist, export)
  2. Filter system supports multiple criteria combined with AND/OR logic across all list pages
  3. User can save filter configurations as named presets and apply them with one click
  4. Global search bar (Ctrl+K) finds series, episodes, and subtitles across the entire application with fuzzy matching
**Plans**: TBD

Plans:
- [ ] 12-01: TBD
- [ ] 12-02: TBD

### Phase 13: Comparison + Sync + Health-Check
**Goal**: Users can compare subtitle versions side-by-side, adjust subtitle timing, and run health checks that detect and auto-fix common problems
**Depends on**: Phase 11 (comparison uses the subtitle parser from the editor)
**Requirements**: COMP-01, COMP-02, COMP-03, COMP-04, COMP-05, SYNC-01, SYNC-02, SYNC-03, SYNC-04, SYNC-05
**Success Criteria** (what must be TRUE):
  1. User can compare two subtitle files side-by-side with diff highlighting, and up to four versions simultaneously
  2. User can adjust subtitle timing (offset, speed multiplier, frame rate) with a sync UI on the Series Detail page
  3. Health check engine detects duplicate lines, encoding issues, timing overlaps, and missing styles, displayed as badges and dashboard widgets
  4. Per-series and global quality metrics (score trends, provider success rates) are visible in the dashboard
  5. Auto-fix options allow one-click resolution of detected problems with preview before applying
**Plans**: TBD

Plans:
- [ ] 13-01: TBD
- [ ] 13-02: TBD
- [ ] 13-03: TBD

### Phase 14: Dashboard Widgets + Quick-Actions
**Goal**: Users can customize their dashboard layout with drag-and-drop widgets and access common actions via keyboard shortcuts and a floating action button
**Depends on**: Phase 0 (needs stable frontend architecture)
**Requirements**: DASH-01, DASH-02, DASH-03, DASH-04
**Success Criteria** (what must be TRUE):
  1. User can rearrange, resize, and toggle visibility of dashboard widgets via drag-and-drop
  2. At least 8 predefined widget types are available (activity feed, provider status, translation stats, wanted count, etc.)
  3. Quick-actions toolbar (floating action button) provides context-specific actions with keyboard shortcuts on every page
**Plans**: TBD

Plans:
- [ ] 14-01: TBD
- [ ] 14-02: TBD

### Phase 15: API-Key Mgmt + Notifications + Cleanup
**Goal**: Users have centralized key management, customizable notification templates with quiet hours, and tools to deduplicate and clean up subtitle files
**Depends on**: Phase 0 (needs stable API structure)
**Requirements**: KEYS-01, KEYS-02, KEYS-03, KEYS-04, KEYS-05, NOTF-01, NOTF-02, NOTF-03, NOTF-04, NOTF-05, DEDU-01, DEDU-02, DEDU-03, DEDU-04, DEDU-05
**Success Criteria** (what must be TRUE):
  1. User can view, test, rotate, and export/import all API keys from a centralized management page with masked display
  2. Bazarr migration tool imports configuration, language profiles, and blacklist from a Bazarr installation
  3. User can create notification templates with variables, assign them per service and event type, and preview before saving
  4. Quiet hours prevent notifications during configured time windows (with exceptions for critical events)
  5. Deduplication engine scans for duplicate subtitles by content hash, groups them in a UI, and supports batch deletion with disk space analysis
**Plans**: TBD

Plans:
- [ ] 15-01: TBD
- [ ] 15-02: TBD
- [ ] 15-03: TBD

### Phase 16: External Integrations
**Goal**: Users migrating from other tools have a smooth path, and Sublarr config can be exported in formats compatible with other subtitle managers
**Depends on**: Phase 3 (needs media server abstraction for Plex/Kodi compatibility checks)
**Requirements**: INTG-01, INTG-02, INTG-03, INTG-04, INTG-05
**Success Criteria** (what must be TRUE):
  1. Extended Bazarr migration reads the Bazarr database directly and produces a detailed mapping report before import
  2. Plex compatibility check validates that subtitle file naming and placement match Plex conventions
  3. Sonarr/Radarr and Jellyfin/Emby health checks report extended diagnostics (connection, API version, library access, webhook status)
  4. Config and subtitle data can be exported in formats compatible with Bazarr, Plex, Kodi, and a generic JSON format
**Plans**: TBD

Plans:
- [ ] 16-01: TBD
- [ ] 16-02: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 0 -> 1 -> 2 -> 3 -> 4 -> 5 -> 6 -> 7 -> 8 -> 9 -> 10 -> 11 -> 12 -> 13 -> 14 -> 15 -> 16

**Parallelization note:** Phases 1, 2, and 3 can execute in parallel after Phase 0 completes (independent feature tracks). All other phases are sequential.

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 0. Architecture Refactoring | 3/3 | Complete | 2026-02-15 |
| 1. Provider Plugin + Expansion | 6/6 | Complete | 2026-02-15 |
| 2. Translation Multi-Backend | 6/6 | Complete | 2026-02-15 |
| 3. Media-Server Abstraction | 3/3 | Complete | 2026-02-15 |
| 4. Whisper Speech-to-Text | 0/TBD | Not started | - |
| 5. Standalone Mode | 0/TBD | Not started | - |
| 6. Forced/Signs Subs | 0/TBD | Not started | - |
| 7. Events/Hooks + Custom Scoring | 0/TBD | Not started | - |
| 8. i18n + Backup + Admin Polish | 0/TBD | Not started | - |
| 9. OpenAPI + Release Preparation | 0/TBD | Not started | - |
| 10. Performance & Scalability | 0/TBD | Not started | - |
| 11. Subtitle Editor | 0/TBD | Not started | - |
| 12. Batch Operations + Smart-Filter | 0/TBD | Not started | - |
| 13. Comparison + Sync + Health-Check | 0/TBD | Not started | - |
| 14. Dashboard Widgets + Quick-Actions | 0/TBD | Not started | - |
| 15. API-Key Mgmt + Notifications + Cleanup | 0/TBD | Not started | - |
| 16. External Integrations | 0/TBD | Not started | - |

## Dependency Graph

```
Phase 0 (Architecture)
  ├── Phase 1 (Plugins)
  │     └── Phase 6 (Forced Subs)
  ├── Phase 2 (Translation)
  │     └── Phase 4 (Whisper)
  ├── Phase 3 (Media-Server)
  │     └── Phase 16 (External Integrations)
  ├── Phase 5 (Standalone)
  ├── Phase 7 (Events/Hooks)
  ├── Phase 8 (i18n + Backup + Admin)
  │     └── Phase 9 (OpenAPI + Release)
  │           └── Phase 10 (Performance)
  ├── Phase 11 (Editor)
  │     └── Phase 13 (Comparison + Sync)
  ├── Phase 12 (Batch + Filter)
  ├── Phase 14 (Dashboard Widgets)
  └── Phase 15 (Keys + Notifications + Cleanup)
```

---
*Roadmap created: 2026-02-15*
*Last updated: 2026-02-15 (Phase 3 complete)*
