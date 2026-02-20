# External Integrations

**Analysis Date:** 2026-02-15

## APIs & External Services

**LLM Translation:**
- Ollama - Local LLM inference server (required for translation)
  - SDK/Client: `requests` library, direct HTTP API (`backend/ollama_client.py`)
  - Auth: None (local service)
  - Endpoints: `/api/generate` (translation), `/api/tags` (health check)
  - Config: `SUBLARR_OLLAMA_URL`, `SUBLARR_OLLAMA_MODEL` (e.g., `qwen2.5:14b-instruct`)
  - Features: Batch translation (15 lines default), retry with exponential backoff, CJK hallucination detection, glossary support

**Subtitle Providers:**
- AnimeTosho - Anime fansub releases (ASS format preferred)
  - Client: `backend/providers/animetosho.py`
  - Auth: None required
  - Features: Feed API, XZ-compressed files, 50 req/30s rate limit, 20s timeout

- Jimaku - Anime-focused subtitle database
  - Client: `backend/providers/jimaku.py`
  - Auth: API key (`SUBLARR_JIMAKU_API_KEY`)
  - Features: ZIP/RAR archives, AniList ID support, 100 req/60s rate limit, 30s timeout

- OpenSubtitles.com - General subtitle database (v2 REST API)
  - Client: `backend/providers/opensubtitles.py`
  - Auth: API key + optional username/password (`SUBLARR_OPENSUBTITLES_API_KEY`, `SUBLARR_OPENSUBTITLES_USERNAME`, `SUBLARR_OPENSUBTITLES_PASSWORD`)
  - Features: Hash-based matching, 40 req/10s rate limit (5 req/s), 15s timeout, 3 retries

- SubDL - Subscene successor
  - Client: `backend/providers/subdl.py`
  - Auth: API key (`SUBLARR_SUBDL_API_KEY`)
  - Features: ZIP archives, 2000 downloads/day limit, 30 req/10s rate limit, 15s timeout

**Provider Infrastructure:**
- Manager: `backend/providers/__init__.py` - ProviderManager singleton with circuit breakers
- Parallel search: ThreadPoolExecutor with per-provider timeouts
- Retry logic: 2-3 attempts per provider with exponential backoff
- Circuit breakers: Per-provider failure tracking (CLOSED/OPEN/HALF_OPEN states, see `backend/circuit_breaker.py`)
- Rate limiting: Token bucket per provider, window-based request tracking
- Scoring: Hash(359) > Series(180) > Year(90) > Season(30) > Episode(30) > Release Group(14) + ASS Bonus(50)
- Cache: 5-minute TTL in SQLite (`provider_cache` table)

**Media Management (*arr apps):**
- Sonarr v3 - TV series management
  - Client: `backend/sonarr_client.py`
  - Auth: X-Api-Key header (`SUBLARR_SONARR_API_KEY`)
  - Endpoints: `/api/v3/series`, `/api/v3/episode`, `/api/v3/episodefile`, `/api/v3/command`
  - Features: Series/episode listing, file path resolution, anime tag filtering, RescanSeries command, AniDB/AniList ID extraction
  - Multi-instance support: DB-stored instances, cache per instance name

- Radarr v3 - Movie management
  - Client: `backend/radarr_client.py`
  - Auth: X-Api-Key header (`SUBLARR_RADARR_API_KEY`)
  - Endpoints: `/api/v3/movie`, `/api/v3/moviefile`, `/api/v3/command`
  - Features: Movie listing, file path resolution, anime tag filtering, RescanMovie command
  - Multi-instance support: DB-stored instances, cache per instance name

**AniDB Mapping:**
- AniDB ID Resolution - External service for TVDB→AniDB mapping
  - Implementation: `backend/anidb_mapper.py`
  - API: HTTP endpoint (URL from config or DB)
  - Cache: SQLite `anidb_mappings` table with 7-day TTL
  - Fallback: Title-based heuristic matching if API unavailable

## Data Storage

**Databases:**
- SQLite 3 (embedded)
  - Connection: File path from `SUBLARR_DB_PATH` (default: `/config/sublarr.db`)
  - Client: stdlib `sqlite3` module (WAL mode, thread-safe with `_db_lock`)
  - Schema: 17+ tables (jobs, daily_stats, config_entries, provider_cache, subtitle_downloads, wanted_items, language_profiles, blacklist, provider_stats, glossary_entries, anidb_mappings, database_backups, sonarr_instances, radarr_instances, provider_search_cache, upgrade_candidates, webhook_history)
  - Backups: Automated backup scheduler (`backend/database_backup.py`), rotation, integrity checks (`backend/database_health.py`)

**File Storage:**
- Local filesystem only
  - Media files: Mounted at `/media` (Docker volume, read-write)
  - Config/DB: `/config` volume (persistent state)
  - Subtitle output: Alongside media files with `.{lang}.ass` or `.{lang}.srt` naming

**Caching:**
- SQLite in-memory cache via `provider_cache` table (5-minute TTL)
- No external cache service (Redis, Memcached, etc.)

## Authentication & Identity

**Auth Provider:**
- Custom (optional API key auth)
  - Implementation: `backend/auth.py`
  - Method: X-Api-Key header verification with constant-time comparison
  - Config: `SUBLARR_API_KEY` env var (empty = auth disabled)
  - Applied: Flask decorator `@require_api_key` on protected endpoints

**User Management:**
- None (single-user application, no user accounts)

## Monitoring & Observability

**Error Tracking:**
- Custom error hierarchy (`backend/error_handler.py`)
  - SublarrError base class with request ID tracking
  - Flask error handlers registered for 400/404/500 errors
  - Structured error responses with `request_id`, `timestamp`, `error`, `message`

**Logs:**
- Python logging module (stdlib)
  - Config: `SUBLARR_LOG_LEVEL` (default: INFO), `SUBLARR_LOG_FILE` (default: `/config/sublarr.log`)
  - Rotation: Not implemented (relies on Docker log rotation: 10MB max-size, 3 max-file)
  - Live logs: Flask endpoint `GET /api/v1/logs` streams last 1000 lines
  - WebSocket: Real-time log streaming via Socket.IO (`/socket.io/`)

**Metrics (optional):**
- Prometheus exporter (`backend/metrics.py`)
  - Library: `prometheus_client` (graceful degradation if not installed)
  - Metrics: HTTP request counters, translation job duration histograms, provider success rates
  - Endpoint: `/api/v1/metrics` (Prometheus scrape target)

## CI/CD & Deployment

**Hosting:**
- Self-hosted (Docker container)
  - Port: 5765 (configurable via `SUBLARR_PORT`)
  - Volumes: `/config` (persistent state), `/media` (read-write media access)
  - Health check: `curl -f http://localhost:5765/api/v1/health` every 30s

**CI Pipeline:**
- None (no GitHub Actions, GitLab CI, etc. detected)

**Development Scripts:**
- `scripts/setup-dev.ps1` (Windows PowerShell)
- `scripts/setup-dev.sh` (Linux/Mac Bash)

## Environment Configuration

**Required env vars:**
- `SUBLARR_OLLAMA_URL` - Ollama server URL (e.g., `http://localhost:11434`)
- `SUBLARR_OLLAMA_MODEL` - LLM model name (e.g., `qwen2.5:14b-instruct`)
- `SUBLARR_MEDIA_PATH` - Media directory path (default: `/media`)
- `SUBLARR_DB_PATH` - Database file path (default: `/config/sublarr.db`)

**Optional env vars (85+ total in `.env.example`):**
- Provider API keys: `SUBLARR_OPENSUBTITLES_API_KEY`, `SUBLARR_JIMAKU_API_KEY`, `SUBLARR_SUBDL_API_KEY`
- *arr integration: `SUBLARR_SONARR_URL`, `SUBLARR_SONARR_API_KEY`, `SUBLARR_RADARR_URL`, `SUBLARR_RADARR_API_KEY`
- Jellyfin: `SUBLARR_JELLYFIN_URL`, `SUBLARR_JELLYFIN_API_KEY`
- Translation: `SUBLARR_SOURCE_LANGUAGE`, `SUBLARR_TARGET_LANGUAGE`, `SUBLARR_BATCH_SIZE`, `SUBLARR_TEMPERATURE`
- Wanted system: `SUBLARR_WANTED_SCAN_INTERVAL_HOURS`, `SUBLARR_WANTED_ANIME_ONLY`, `SUBLARR_WANTED_MAX_SEARCH_ATTEMPTS`
- Upgrade system: `SUBLARR_UPGRADE_ENABLED`, `SUBLARR_UPGRADE_MIN_SCORE_DELTA`, `SUBLARR_UPGRADE_PREFER_ASS`
- Webhooks: `SUBLARR_WEBHOOK_DELAY_MINUTES`, `SUBLARR_WEBHOOK_AUTO_TRANSLATE`
- Notifications: Apprise URL JSON array (see Webhooks section)
- Path mapping: `SUBLARR_PATH_MAPPING` (semicolon-separated `remote=local` pairs)

**Secrets location:**
- `.env` file (git-ignored, not committed)
- Docker secrets: Not used (relies on env vars or volume-mounted `.env`)
- Database: `config_entries` table can override env vars at runtime (see `backend/config.py`)

## Webhooks & Callbacks

**Incoming:**
- `POST /api/v1/webhook/sonarr` - Sonarr webhook (OnGrab, OnDownload, OnRename events)
  - Payload: Sonarr v3 webhook format with `eventType`, `series`, `episodeFile`
  - Action: Delayed scan → subtitle search → translation (configurable delay, default: 5 minutes)
  - Storage: `webhook_history` table tracks all received webhooks

- `POST /api/v1/webhook/radarr` - Radarr webhook (OnGrab, OnDownload, OnRename events)
  - Payload: Radarr v3 webhook format with `eventType`, `movie`, `movieFile`
  - Action: Delayed scan → subtitle search → translation (configurable delay, default: 5 minutes)
  - Storage: `webhook_history` table tracks all received webhooks

**Outgoing:**
- Apprise notifications (`backend/notifier.py`)
  - Triggers: Subtitle download, upgrade, batch complete, errors
  - Config: `SUBLARR_NOTIFICATION_URLS_JSON` (JSON array of Apprise URLs)
  - Event toggles: `SUBLARR_NOTIFY_ON_DOWNLOAD`, `SUBLARR_NOTIFY_ON_UPGRADE`, `SUBLARR_NOTIFY_ON_BATCH_COMPLETE`, `SUBLARR_NOTIFY_ON_ERROR`, `SUBLARR_NOTIFY_MANUAL_ACTIONS`
  - Supported services: Pushover, Discord, Telegram, Gotify, Slack, SMTP, and 70+ others via Apprise

- Jellyfin/Emby library refresh (`backend/jellyfin_client.py`)
  - Trigger: After subtitle file creation
  - API: `POST /Items/{item_id}/Refresh` (item-specific) or `POST /Library/Refresh` (full scan fallback)
  - Auth: X-MediaBrowser-Token header
  - Retry: 2 attempts with exponential backoff

## Special Integrations

**ffmpeg:**
- Purpose: ASS subtitle stream detection and style analysis
- Usage: `backend/ass_utils.py` via `subprocess.run(['ffprobe', ...])`
- Required: Installed in Docker image (`apt-get install ffmpeg`)

**unrar:**
- Purpose: RAR archive extraction for subtitle provider downloads (Jimaku, SubDL)
- Package: `rarfile` Python library + `unrar-free` binary
- Required: Installed in Docker image (`apt-get install unrar-free`)

**HI Removal:**
- Implementation: Regex-based hearing-impaired tag removal (`backend/hi_remover.py`)
- Patterns: Based on Bazarr/SubZero HI-removal patterns
- Trigger: Optional processing step during subtitle download

**Wanted Scanner:**
- Implementation: `backend/wanted_scanner.py` - APScheduler background job
- Trigger: Configurable interval (default: 6 hours) + on-startup scan
- Purpose: Identify episodes/movies missing target language subtitles
- Storage: `wanted_items` table with status tracking (wanted, searching, found, failed, ignored)
- Search: `backend/wanted_search.py` - periodic batch search for wanted items (default: 24 hours)

---

*Integration audit: 2026-02-15*
