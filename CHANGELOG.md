# Changelog

All notable changes to Sublarr are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.9.0-beta] - 2026-02-16

### Added

#### Provider Plugin System (Phase 1)
- Plugin architecture with hot-reload for custom subtitle providers
- Plugin discovery from `/config/plugins/` with manifest validation
- Plugin-specific configuration stored in `config_entries` database table
- Watchdog-based hot-reload with 2-second debounce (opt-in via `plugin_hot_reload`)
- Plugin developer template and documentation

#### New Built-in Providers (Phase 1)
- **Gestdown** -- Addic7ed proxy with REST API, covers both Addic7ed and Gestdown content
- **Podnapisi** -- Large multilingual database with XML API and lxml parsing
- **Kitsunekko** -- Japanese anime subtitles via HTML scraping (BeautifulSoup optional)
- **Napisy24** -- Polish subtitles with MD5 file hash matching (first 10MB)
- **Whisper-Subgen** -- External ASR integration, returns low-score placeholder in search
- **Titrari** -- Romanian subtitles via polite scraping (no auth required)
- **LegendasDivx** -- Portuguese subtitles with session authentication and daily limit tracking

#### Provider Health Monitoring (Phase 1)
- Per-provider response time tracking with weighted running average
- Auto-disable after consecutive failure threshold (default: 10 failures)
- Configurable cooldown period (`provider_auto_disable_cooldown_minutes`, default: 30 min)
- Provider health dashboard with success rate, response time, and download counts

#### Translation Multi-Backend (Phase 2)
- **DeepL** backend with glossary caching by (source, target) language pair
- **LibreTranslate** backend for self-hosted translation (line-by-line for 1:1 mapping)
- **OpenAI-compatible** backend supporting any OpenAI API endpoint with CJK hallucination detection
- **Google Cloud Translation** backend with fresh client per call for credential rotation
- Per-profile backend selection in language profiles
- Automatic fallback chains with configurable backend priority
- Circuit breakers per translation backend (reuses provider circuit breaker pattern)
- Translation quality metrics tracked per backend

#### Media Server Abstraction (Phase 3)
- **Plex** support with lazy `plexapi` connection (optional dependency)
- **Kodi** support with JSON-RPC `VideoLibrary.Scan` (directory-scoped)
- Unified media server settings page with multi-server configuration
- `MediaServerManager.refresh_all()` notifies all configured servers after subtitle changes
- Legacy Jellyfin configuration auto-migrated to new multi-server format

#### Whisper Speech-to-Text (Phase 4)
- **faster-whisper** backend with lazy model loading and device/compute_type caching
- **Subgen** backend for external Whisper API integration
- Case D translation pipeline: automatic Whisper fallback when all providers fail
- Whisper job queue with configurable max concurrency and progress via WebSocket
- Audio extraction via ffmpeg pipe (no temp files)
- Language detection validation against expected source language

#### Standalone Mode (Phase 5)
- Folder-watch operation without Sonarr/Radarr dependency
- **TMDB** metadata lookup (requires API key)
- **AniList** metadata lookup (no API key required, 0.7s rate limiting)
- **TVDB** metadata lookup with 24h JWT token caching
- Anime detection via multi-signal heuristic (bracket groups, fansub groups, CRC32, absolute numbering)
- `guessit`-based filename parsing with anime-aware mode
- `MediaFileWatcher` with per-path debounce and file stability checks
- `StandaloneScanner` groups files by series for efficient metadata lookup
- Standalone items integrate with existing Wanted pipeline

#### Forced/Signs Subtitle Management (Phase 6)
- Multi-signal forced subtitle detection (ffprobe flags, filename patterns, title analysis, ASS style analysis)
- Per-series forced subtitle preference (disabled/separate/auto) in language profiles
- OpenSubtitles `foreign_parts_only` filter for native forced search
- Post-search forced classification for providers without native support
- Forced subtitle type badges and filter buttons in Wanted UI

#### Event Bus and Hooks (Phase 7)
- Internal event bus using `blinker` with signal isolation namespace
- 22+ business events published (subtitle_downloaded, translation_complete, provider_failed, etc.)
- Shell script hooks with environment variable payload and configurable timeouts
- Outgoing webhooks with HTTP POST, JSON payload, and retry logic on failure
- Event catalog with versioned payload schemas (CATALOG_VERSION=1)
- SocketIO bridge for real-time event forwarding to frontend

#### Custom Scoring (Phase 7)
- Configurable scoring weights (hash, series, year, season, episode, release_group, ASS bonus)
- Per-provider score modifiers (-100 to +100 range)
- Scoring cache with 60s TTL and config-change invalidation

#### UI Internationalization (Phase 8)
- English and German translations for entire UI
- `react-i18next` with static JSON imports (no HTTP backend)
- Language preference stored in localStorage (`sublarr-language`)
- `LanguageSwitcher` component in header

#### Theme System (Phase 8)
- Dark/light theme toggle with system preference detection
- Theme stored in localStorage (`sublarr-theme`) with 3 states: dark, light, system
- Inline script in `index.html` prevents flash of wrong theme before React hydration
- CSS variable-based theming

#### Backup and Restore (Phase 8)
- Full backup (config + database as ZIP) with in-memory buffer
- Scheduled automatic backups with configurable interval
- Restore from ZIP upload via Settings UI
- Backup rotation with configurable retention count

#### Statistics Page (Phase 8)
- Recharts-based charts with responsive containers
- Time-range filters (7d, 30d, 90d, all)
- Daily stats, provider usage, translation backend performance, format distribution
- Subtitle download and upgrade history visualization

#### Subtitle Tools (Phase 8)
- Timing adjustment (centisecond precision, H:MM:SS.cc format)
- Encoding fix (detect and convert to UTF-8)
- Hearing impaired tag removal
- Style stripping (ASS to plain text)
- All tools create `.bak` backup before modification
- Path traversal prevention via `os.path.abspath` validation

#### OpenAPI Documentation (Phase 9)
- OpenAPI 3.0.3 specification at `/api/v1/openapi.json` with 65+ documented paths
- Swagger UI at `/api/docs` for interactive API exploration
- `apispec` + `apispec-webframeworks` for YAML docstring-based spec generation
- X-Api-Key security scheme for authenticated endpoints

#### Performance Optimizations (Phase 9)
- Incremental wanted scan with timestamp tracking (only rescans modified items)
- Full scan forced every 6th cycle as safety fallback
- Parallel ffprobe via `ThreadPoolExecutor` (max 4 workers per series)
- Parallel wanted search processing (removed 0.5s inter-item delay)
- Route-level code splitting with `React.lazy` for all 13 page components
- `PageSkeleton` loading component for Suspense fallback

#### Health Monitoring (Phase 9)
- Extended `/health/detailed` with 11 subsystem categories
- Translation backend health checks per instance
- Media server health checks per instance
- Whisper backend health reporting
- Sonarr/Radarr connectivity checks across all configured instances
- Scheduler status reporting

### Changed

- **Architecture:** Application Factory pattern (`create_app()`) with 15 Flask Blueprints (from monolithic `server.py`)
- **Database:** Split `database.py` into `db/` package with 9 domain modules (from monolithic 2153-line file)
- **Frontend:** React 19 + TypeScript + Tailwind v4 (upgraded from React 18 + Tailwind CSS)
- **Translation:** Ollama configuration moved from dedicated tab to unified Translation Backends tab
- **Settings:** Split 4703-line `Settings.tsx` monolith into 7 focused tab modules under `Settings/` directory
- **Version numbering:** Changed from v1.0.0-beta to v0.9.0-beta (standard pre-release convention -- v1.0.0 reserved for stable release)
- **Gunicorn:** Single worker mode required for Flask-SocketIO WebSocket state consistency

### Fixed

- Case-sensitive email uniqueness in provider configurations
- Hardcoded version strings ("0.1.0") replaced with centralized `version.py`
- SPA fallback route now returns correct version string
- Toast message and ThemeToggle label i18n gaps closed
- Pre-existing integration test expectations updated for health endpoint response format

### Migration Notes

See [docs/MIGRATION.md](docs/MIGRATION.md) for upgrade instructions from v1.0.0-beta.

## [1.0.0-beta] - 2026-02-14

### Added

- **Provider System:** Direct subtitle sourcing from AnimeTosho, Jimaku, OpenSubtitles, and SubDL
- **Wanted System:** Automatic detection of missing subtitles via Sonarr/Radarr integration
- **Search & Download Workflow:** End-to-end subtitle acquisition without Bazarr
- **Upgrade System:** Automatic SRT-to-ASS upgrades with configurable score delta
- **Language Profiles:** Per-series/movie target language configuration with multi-language support
- **LLM Translation:** Integrated subtitle translation via Ollama (ASS and SRT formats)
- **Glossary System:** Per-series translation glossaries for consistent terminology
- **Prompt Presets:** Customizable translation prompt templates with default preset
- **Blacklist & History:** Track downloads and block unwanted subtitle releases
- **HI Removal:** Hearing impaired marker removal from subtitles before translation
- **Embedded Subtitle Detection:** Extract and translate subtitles embedded in MKV files
- **AniDB Integration:** TVDB-to-AniDB ID mapping for better anime episode matching
- **Webhook Automation:** Sonarr/Radarr webhooks trigger scan-search-translate pipeline
- **Multi-Instance Support:** Configure multiple Sonarr/Radarr instances
- **Notification System:** Apprise-based notifications (Pushover, Discord, Telegram, etc.)
- **Onboarding Wizard:** Guided first-time setup
- **Provider Caching:** TTL-based search result caching per provider
- **Re-Translation:** Detect and re-translate files when model/prompt/language changes
- **Config Export/Import:** Backup and restore application configuration
- **Docker Multi-Arch:** Builds for linux/amd64 and linux/arm64
- **Unraid Template:** Community Applications template for Unraid

### Architecture

- Flask + Flask-SocketIO backend with Blueprint-based API
- React 18 + TypeScript + Tailwind CSS frontend
- SQLite with WAL mode for persistence
- Pydantic Settings for type-validated configuration
- Multi-stage Docker build (Node 20 + Python 3.11-slim + ffmpeg + unrar-free)

### Provider Details

| Provider | Auth | Format | Specialty |
|---|---|---|---|
| AnimeTosho | None | ASS (Fansub) | Extracts subs from releases, XZ compressed |
| Jimaku | API Key | ASS/SRT | Anime-focused, ZIP/RAR archives |
| OpenSubtitles | API Key | SRT/ASS | Largest database, REST API v2 |
| SubDL | API Key | SRT/ASS | Subscene successor, ZIP download |
