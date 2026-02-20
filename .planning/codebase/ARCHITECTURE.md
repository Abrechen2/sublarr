# Architecture

**Analysis Date:** 2026-02-15

## Pattern Overview

**Overall:** Three-Tier API-Driven SPA with Event-Driven Backend

**Key Characteristics:**
- Flask Blueprint API backend with SQLite persistence and Socket.IO WebSocket layer
- React 19 SPA frontend with TanStack Query for state management
- Provider-based subtitle search architecture with circuit breakers and parallel execution
- Three-case translation pipeline (skip → upgrade → full translation)
- Multi-instance support for Sonarr/Radarr with path mapping
- Configuration cascade: Environment → Pydantic Settings → Database runtime overrides

## Layers

**Presentation Layer (React Frontend):**
- Purpose: User interface and real-time status updates
- Location: `frontend/src/`
- Contains: Pages, components, API client, WebSocket hooks
- Depends on: Backend REST API (`/api/v1/`), WebSocket (`/socket.io/`)
- Used by: End users via browser

**API Layer (Flask Blueprint):**
- Purpose: RESTful endpoints and WebSocket event emission
- Location: `backend/server.py` (2618 lines, monolithic Blueprint)
- Contains: All `/api/v1/` endpoints, error handlers, SPA fallback routing
- Depends on: Translation pipeline, database, provider system, *arr clients, Ollama client
- Used by: Frontend, Sonarr/Radarr webhooks (`/api/v1/webhook/sonarr`, `/api/v1/webhook/radarr`)

**Domain Logic Layer:**
- Purpose: Translation orchestration, provider management, subtitle processing
- Location: `backend/*.py` (22 modules)
- Contains:
  - `translator.py` (885 lines) — Three-case translation pipeline
  - `providers/__init__.py` — ProviderManager with scoring and parallel search
  - `wanted_search.py` — Connects wanted items to provider system
  - `ollama_client.py` — LLM translation with batch processing
  - `ass_utils.py` — ASS style classification, tag extraction
  - `upgrade_scorer.py` — SRT→ASS upgrade decision logic
- Depends on: Database, config, circuit breaker, external APIs
- Used by: API layer, scheduled jobs

**Provider Abstraction Layer:**
- Purpose: Unified interface for multiple subtitle sources
- Location: `backend/providers/`
- Contains:
  - `base.py` — SubtitleProvider ABC, VideoQuery, SubtitleResult, scoring algorithm
  - `animetosho.py`, `jimaku.py`, `opensubtitles.py`, `subdl.py` — Provider implementations
  - `http_session.py` — RetryingSession with rate limiting
- Depends on: Circuit breaker, database (cache, downloads)
- Used by: ProviderManager via ThreadPoolExecutor (parallel search)

**Integration Layer:**
- Purpose: External service clients (*arr apps, Ollama, Jellyfin/Emby)
- Location: `backend/*_client.py`
- Contains:
  - `sonarr_client.py`, `radarr_client.py` — v3 API clients with multi-instance support
  - `jellyfin_client.py` — Library refresh triggers
  - `ollama_client.py` — LLM translation via Ollama API
- Depends on: Config (URLs, API keys), path mapping
- Used by: Translation pipeline, wanted scanner, webhooks

**Persistence Layer:**
- Purpose: SQLite storage with thread-safe access
- Location: `backend/database.py` (2153 lines)
- Contains: 17 tables (jobs, wanted, config_entries, provider_cache, subtitle_downloads, language_profiles, etc.)
- Pattern: `_db_lock` threading.Lock for all database operations, WAL mode enabled
- Depends on: Config (db_path)
- Used by: All backend modules

**Resilience Layer:**
- Purpose: Error handling, circuit breaking, transaction management
- Location: `backend/error_handler.py`, `backend/circuit_breaker.py`, `backend/transaction_manager.py`
- Contains:
  - SublarrError hierarchy with HTTP status mapping and troubleshooting hints
  - CircuitBreaker (CLOSED/OPEN/HALF_OPEN states, per-provider)
  - Transaction context manager for database consistency
- Depends on: Database lock
- Used by: API layer (error handlers), provider system (circuit breakers), database operations

## Data Flow

**Webhook-Triggered Translation (Sonarr/Radarr → Sublarr):**

1. Sonarr/Radarr sends POST to `/api/v1/webhook/sonarr` or `/api/v1/webhook/radarr` (event: Download)
2. Webhook handler parses series/movie metadata, maps remote path to local path
3. Creates translation job in database (status: queued)
4. Spawns background thread → `translate_file()` in `translator.py`
5. Three-case pipeline executes:
   - Case A: Target ASS exists → skip (emit `webhook_completed` event)
   - Case B: Target SRT exists → upgrade attempt (provider search for ASS)
   - Case C: No target → extract embedded → provider search → translate
6. Provider search (if needed):
   - ProviderManager builds VideoQuery from file path + *arr metadata
   - Parallel search across enabled providers via ThreadPoolExecutor
   - Circuit breaker per provider (rate limiting, timeout, failure threshold)
   - Score results (hash match > series match > year > season > episode > release_group + ASS bonus)
   - Download best result
7. Translation (if no ASS found):
   - Extract/parse subtitle to pysubs2.SSAFile
   - Classify styles (dialog vs signs/songs via `\pos()`/`\move()` density)
   - Extract tags from dialog lines
   - Batch translate dialog content via Ollama (15 lines/batch)
   - Restore tags to translated lines
   - Write output as `.{target_lang}.ass` or `.{target_lang}.srt`
8. Update job status (success/failed) in database
9. Emit WebSocket event (`webhook_completed`, `job_update`)
10. Trigger Jellyfin library refresh (if configured)

**Manual Translation (User → Frontend → Backend):**

1. User clicks "Search" on Wanted item in frontend
2. Frontend calls `POST /api/v1/wanted/{id}/search`
3. Backend builds VideoQuery from wanted item + Sonarr/Radarr metadata
4. Provider search executes (same as webhook flow step 6)
5. Best result auto-downloaded and processed
6. WebSocket event emitted (`wanted_search_completed`)
7. Frontend updates UI via React Query invalidation

**Wanted System (Scheduled Scan):**

1. Scheduler runs `wanted_scanner.py` (interval: 30 minutes default)
2. For each Sonarr series with language profile:
   - List all episodes with files
   - Check for missing target language subtitles (external files + embedded streams)
   - Create/update wanted_items entries (status: wanted)
3. Emit WebSocket event (`wanted_scan_completed`)
4. User or scheduler triggers batch search → `wanted_search.py`
5. Sequential provider searches for all wanted items (inter-item delay for rate limiting)

**State Management:**

- Backend: SQLite (jobs, wanted, config_entries, stats, cache)
- Frontend: TanStack Query cache + WebSocket events for live updates
- WebSocket events trigger query invalidation in React Query

## Key Abstractions

**SubtitleProvider (Abstract Base Class):**
- Purpose: Unified interface for subtitle sources
- Examples: `backend/providers/animetosho.py`, `backend/providers/jimaku.py`, `backend/providers/opensubtitles.py`, `backend/providers/subdl.py`
- Pattern: ABC with `search(query: VideoQuery)` and `download(result: SubtitleResult)` methods
- Scoring: `compute_score(result, query)` in `backend/providers/base.py` (max 709 points: hash=359, series=180, year=90, season=30, episode=30, release_group=14, ASS bonus=50)

**VideoQuery:**
- Purpose: Rich search metadata extracted from file path + *arr context
- Examples: Constructed in `wanted_search.py::build_query_from_wanted()`, `translator.py` (direct translation)
- Pattern: Dataclass with series_title, season, episode, year, imdb_id, tmdb_id, anilist_id, release_group, hash (OpenSubtitles hash)
- Used by: All providers for search matching

**SubtitleResult:**
- Purpose: Normalized search result across providers
- Pattern: Dataclass with provider_name, subtitle_id, language, format (ASS/SRT), url, score, metadata
- Used by: ProviderManager to rank and download best match

**CircuitBreaker:**
- Purpose: Prevent cascade failures from unresponsive providers
- Location: `backend/circuit_breaker.py`
- Pattern: State machine (CLOSED → OPEN → HALF_OPEN → CLOSED)
- Transitions:
  - CLOSED → OPEN: failure_count >= 5
  - OPEN → HALF_OPEN: after 60s cooldown
  - HALF_OPEN → CLOSED: probe call succeeds
  - HALF_OPEN → OPEN: probe call fails
- Used by: ProviderManager (one breaker per provider)

**Language Profile:**
- Purpose: Per-series/movie target languages (override global config)
- Location: `backend/database.py` (language_profiles table), series_language_profiles mapping
- Pattern: Profile has name + list of target languages, series map to profile ID
- Used by: Translation pipeline to determine which languages to generate

## Entry Points

**Flask Application:**
- Location: `backend/server.py::app`
- Triggers: `gunicorn --bind 0.0.0.0:5765 --worker-class gthread --workers 2 --threads 4 --timeout 300 server:app` (Docker CMD)
- Responsibilities:
  - Serve React SPA from `static/` directory
  - Mount `/api/v1/` Blueprint with all REST endpoints
  - Initialize Socket.IO WebSocket server
  - Register error handlers (SublarrError → JSON)
  - Initialize authentication (optional API key)
  - Start database (SQLite connection with WAL mode)

**React SPA:**
- Location: `frontend/src/main.tsx`
- Triggers: User browser navigation to `http://host:5765/`
- Responsibilities:
  - Initialize TanStack QueryClient
  - Render `App.tsx` with React Router
  - Establish WebSocket connection to `/socket.io/`
  - Mount Sidebar + routed pages

**Sonarr/Radarr Webhooks:**
- Location: `backend/server.py` — `POST /api/v1/webhook/sonarr`, `POST /api/v1/webhook/radarr`
- Triggers: Sonarr/Radarr Download event (configured in *arr app settings)
- Responsibilities:
  - Parse webhook payload (series/movie metadata, file path, episode IDs)
  - Map remote path to local path (if path_mapping configured)
  - Create translation job
  - Spawn background translation thread
  - Return HTTP 200 immediately (async processing)

**Wanted Scanner (Scheduled):**
- Location: `backend/wanted_scanner.py::run_wanted_scan()`
- Triggers: Scheduled interval (default 30 minutes) or manual `/api/v1/wanted/refresh`
- Responsibilities:
  - Query all Sonarr series with language profiles
  - For each episode with file, check for missing target language subtitles
  - Create/update wanted_items entries
  - Emit WebSocket event

**Translation Worker:**
- Location: `backend/translator.py::translate_file()` (spawned as thread)
- Triggers: Webhook, manual translation request, wanted item processing
- Responsibilities:
  - Execute three-case pipeline (A: skip, B: upgrade, C: full)
  - Coordinate provider search, LLM translation, file I/O
  - Update job status in database
  - Emit WebSocket events (`job_update`, `webhook_completed`)

## Error Handling

**Strategy:** Structured exception hierarchy with Flask error handlers

**Patterns:**
- All application errors inherit from `SublarrError` (base class in `backend/error_handler.py`)
- Each error has `code` (machine-readable), `http_status`, `context` (debug data), `troubleshooting` (user hint)
- Flask error handlers catch SublarrError → JSON response with request_id
- Generic exceptions (500) caught by fallback handler
- Request IDs generated via `flask.g.request_id` for log correlation
- Circuit breakers prevent error cascade (providers)
- Transaction context manager ensures database consistency on errors

**Exception Hierarchy:**
```
SublarrError (base)
├── TranslationError
│   ├── OllamaConnectionError
│   ├── OllamaTimeoutError
│   └── SubtitleExtractionError
├── ConfigurationError
├── ProviderAuthError
├── ProviderRateLimitError
└── ProviderTimeoutError
```

**HTTP Status Mapping:**
- 400: Bad request (invalid parameters)
- 401: Unauthorized (missing/invalid API key)
- 404: Not found (job, wanted item, series)
- 429: Rate limit exceeded (provider)
- 500: Internal error (translation failure, database error)
- 502: Bad gateway (Ollama/provider unavailable)
- 504: Gateway timeout (Ollama/provider timeout)

## Cross-Cutting Concerns

**Logging:**
- Framework: Python `logging` module (root logger)
- Handlers: Console (stderr), rotating file (`/config/sublarr.log`, 5MB × 3 backups), WebSocket (real-time to frontend)
- Format: Text (default) or JSON (structured, set via `log_format` config)
- Level: Configurable via `log_level` (default: INFO)
- Features: Request ID correlation, exception tracing, StructuredJSONFormatter for ELK/Loki

**Validation:**
- Config: Pydantic Settings with Field validators (URLs, ports, language codes)
- API requests: Flask request.json parsing with KeyError/TypeError catching
- File paths: Existence checks before processing (`os.path.exists()`)
- Subtitle formats: pysubs2 format detection (ASS/SRT)
- Provider results: Score validation, format enforcement (ASS preferred)

**Authentication:**
- Approach: Optional API key via `X-Api-Key` header
- Implementation: `backend/auth.py::init_auth()` + `@require_api_key` decorator
- Configuration: `SUBLARR_API_KEY` environment variable (empty = no auth)
- Exemptions: `/api/v1/health`, static files, SPA routes

**Configuration Management:**
- Three-layer cascade:
  1. Environment variables (`SUBLARR_` prefix) / `.env` file
  2. Pydantic Settings defaults (`backend/config.py`)
  3. Runtime overrides in `config_entries` database table
- Dynamic reload: `reload_settings()` function invalidates singleton, re-reads env + DB
- Multi-instance support: Sonarr/Radarr instances stored as JSON arrays in config
- Path mapping: Remote→local path translation for *arr apps on different hosts

**Monitoring & Observability:**
- Prometheus metrics: `backend/metrics.py` (gracefully disabled if prometheus_client missing)
- Metrics exposed: Translation counts, provider success rates, job queue depth, database size
- Health check: `GET /api/v1/health` (Ollama, database, provider circuit breaker status)
- Database health: `backend/database_health.py` (integrity check, vacuum, stats)
- WebSocket events: Real-time progress, errors, completions emitted to frontend

**Resilience:**
- Circuit breakers: Per-provider, prevents cascade failures
- Rate limiting: Per-provider (e.g., OpenSubtitles 40 req/10s), in ProviderManager
- Retries: Configurable per provider (default 2-3 retries with exponential backoff)
- Timeouts: Per-provider (15-30s), global fallback (30s)
- Database backups: Automatic SQLite backups with rotation (`backend/database_backup.py`)
- Transaction safety: Context manager ensures rollback on errors

**Concurrency:**
- API: Gunicorn with `gthread` worker class (2 workers × 4 threads)
- Translation jobs: Background threads (spawned per job)
- Provider searches: ThreadPoolExecutor (max 4 workers, parallel across providers)
- Database: `_db_lock` threading.Lock for thread-safe SQLite access
- WebSocket: Socket.IO with `async_mode="threading"`

---

*Architecture analysis: 2026-02-15*
