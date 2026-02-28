# Changelog

All notable changes to Sublarr are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.13.1-beta] — 2026-02-28

### Added
- **Queue — Batch Probe Karte** — zeigt Fortschritt der `batch-probe`-Operation (Gesamt, Gefunden, Extrahiert, Fehlgeschlagen, aktueller Pfad) mit Teal-Akzent und Progressbar; erscheint sobald `probe.running = true`
- **Queue — Wanted Scanner Karte** — neuer `GET /api/v1/wanted/scanner/status` Endpoint; zeigt Scan-Fortschritt (Phase-Badge, Fortschritt, Neu, Aktualisiert) mit Grün-Akzent; adaptives Polling (3 s aktiv / 30 s idle)
- Die Queue-Seite zeigt jetzt alle 4 Hintergrundoperationen: Batch-Übersetzung, Wanted-Suche, Batch-Probe, Wanted-Scanner

---

## [0.13.0-beta] — 2026-02-28

### Added
- **Sidecar Subtitle Management** — inline sidecar badges (language + format) for all extracted subtitle files per episode in SeriesDetail; non-target-language sidecars displayed with × delete button
- **Series Subtitles API** — `GET /api/v1/library/series/<id>/subtitles` scans all episode files in parallel and returns sidecar metadata keyed by Sonarr episode ID
- **Episode Subtitles API** — `GET /api/v1/library/episodes/<id>/subtitles` for single-episode sidecar scan
- **Delete Subtitles API** — `DELETE /api/v1/library/subtitles` removes one or more sidecar files by path with path-traversal guard (only files inside `SUBLARR_MEDIA_PATH` deletable)
- **Batch Delete API** — `POST /api/v1/library/series/<id>/subtitles/batch-delete` deletes sidecars by language/format filter across all episodes of a series
- **Sidecar Cleanup Modal** — "Bereinigen" button in episode toolbar opens modal listing all sidecar languages with file count, total size, and checkboxes; "Nur Target-Sprachen behalten" quick action
- **Auto-Cleanup after Batch Extract** — three new settings: `auto_cleanup_after_extract` (toggle), `auto_cleanup_keep_languages` (comma-separated ISO codes), `auto_cleanup_keep_formats` (ass/srt/any); cleanup runs automatically after `batch-extract-tracks`
- **Settings UI** — three new auto-cleanup fields in the Automation tab

### Added (cont.)
- **Batch Extraction Progress** — live per-episode progress bar in SeriesDetail while `batch-extract-tracks` runs; progress banner shows filename + `X / N Episoden`; Extract button shows spinner and is disabled during extraction
- **Series-Level Action Toolbar** — always-visible row in SeriesDetail hero header: "Tracks extrahieren" (with live X/N counter), "Bereinigen" (opens cleanup modal), "N fehlende suchen" (moved from language row)
- **Activity Page visibility** — `batch-extract-tracks` now creates a DB job (`running` → `completed`/`failed`) so extraction is visible on the Activity page with succeeded/failed/skipped stats
- **Queue Page — Wanted Batch Search** — `useWantedBatchStatus()` was wired but never rendered; now shown as orange card with progressbar and item counts
- **Queue Page — faster polling** — job list now refetches every 3 s on the Queue page (was 15 s) so short-lived translation jobs are reliably visible

### Changed
- **SeriesDetail UNTERTITEL column** — changed from fixed `w-40` (160 px) to `flex-1 min-w-[200px]` so badges spread across available space without excessive line-wrapping
- **Subtitle badge semantics** — three-state badges: teal = ASS/optimal, violet = SRT/upgradeable, orange = missing. ISO 639-2 three-letter codes (ger, eng, jpn) normalized to ISO 639-1 (de, en, ja) to prevent duplicate badges from MKV filenames
- **Sidecar query live refresh** — `['series-subtitles']` query polls every 4 s while extraction is running; on completion both `['series-subtitles']` and `['series']` are invalidated so episode rows reflect new state without reload

### Fixed
- **Duplicate badges** — MKV-embedded `ger` track and target language `de` no longer rendered as two separate badges; `normLang()` normalizes both sides before comparison
- **Activity page** — extraction job now appears within 15 s (first poll cycle) instead of never

---

## [0.12.3-beta] — 2026-02-28

### Security
- **ZIP Slip** — `marketplace.py` plugin installation now uses `safe_zip_extract()` that validates every entry before extraction (CRITICAL)
- **Git clone SSRF/RCE** — `validate_git_url()` enforces HTTPS + domain allowlist (github.com, gitlab.com, codeberg.org) for plugin installs (CRITICAL)
- **Path traversal** — `is_safe_path()` guard added to video segment, audio waveform/extract and OCR endpoints (HIGH)
- **Symlink deletion bypass** — `dedup_engine.py` now skips symlinks and validates paths against `media_path` before deletion (HIGH)
- **Hook env injection** — `sanitize_env_value()` strips newlines and null-bytes from event data before passing to shell scripts (HIGH)
- **CORS wildcard Socket.IO** — replaced `"*"` with configurable `SUBLARR_CORS_ORIGINS` (default: localhost dev origins) (MEDIUM)
- New `backend/security_utils.py` — canonical security utilities used by all of the above

### Changed
- **CI** — paths-filter skips backend/frontend jobs when only the other side changed; concurrency cancels duplicate runs
- **Claude Code Review** — project context in review prompt; concurrency cancels stale reviews on new commits

---

## [0.12.0-beta] — 2026-02-23

### Added
- **Settings UX Redesign** — card-based sub-grouping in all tabs; each logical block has a header with icon, title, description and optional connection badge
- **SettingsCard component** — reusable card wrapper with divided body rows and ConnectionBadge slot
- **ConnectionBadge component** — 4-state indicator (connected/error/unconfigured/checking) for Sonarr, Radarr and media server tabs
- **Advanced Settings toggle** — global "Erweitert" checkbox in the Settings header persisted to localStorage; hides annotated advanced fields by default with orange left-border marker
- **SettingRow descriptions** — all 38 config fields now show always-visible description text beneath each label; 10 fields marked as advanced
- **InfoTooltip improvements** — ESC-key dismiss, keyboard focus/blur handlers, full ARIA accessibility (`aria-describedby`, `role="tooltip"`, `useId`), `motion-safe:` animation prefix
- **Dirty-state Save button** — Save button disabled and grayed when no changes exist; enabled with amber indicator when fields differ from loaded config
- **Navigation warning** — `useBlocker` (React Router v6) + `window.beforeunload` prevent accidental navigation away with unsaved changes
- **ProvidersTab descriptions** — credential and endpoint fields annotated with contextual help text
- **MediaServersTab & WhisperTab descriptions** — all SettingRow fields annotated
- **TranslationTab descriptions** — backend credential fields annotated; PromptPresetsTab shows available template variables
- **MigrationTab improvements** — hardcoded Tailwind color classes replaced with CSS custom properties; context header added

---

## [0.11.1-beta] — 2026-02-22

### Added
- **Scan Auto-Extract** — `wanted_auto_extract` + `wanted_auto_translate` settings; scanner
  extracts embedded subs immediately on first detection when enabled
- **Batch Extract Endpoint** — `POST /api/v1/wanted/batch-extract` extracts embedded subs
  for multiple wanted items in one request
- **Multi-Series Batch Search** — `POST /api/v1/wanted/batch-search` now accepts `series_ids`
  array to trigger search across multiple series at once
- **SeriesDetail Batch Toolbar** — episode checkboxes with Search / Extract bulk actions
- **Library Batch Toolbar** — series checkboxes with Search All Missing bulk action

---

## [0.11.0-beta] — 2026-02-22

### Added
- **Track Manifest** (Phase 29) — list all embedded subtitle/audio streams in MKV files, extract them as standalone files, or use one as the translation source; TrackPanel component in Library/Series Detail
- **Video Sync Backend** (Phase 30) — `POST /api/v1/tools/video-sync` starts async ffsubsync/alass job; `GET` polls progress; fallback timeout 300s
- **Video Sync Frontend** (Phase 31) — SyncModal with engine selector (ffsubsync / alass), live progress bar; auto-sync after download configurable per-download
- **Waveform Editor** (Phase 32) — Waveform tab in the subtitle editor: wavesurfer.js visualization with per-cue region markers; backend extracts audio via ffmpeg with in-memory waveform cache
- **Format Conversion** (Phase 33) — convert ASS ↔ SRT ↔ SSA ↔ VTT via pysubs2; convert dropdown in TrackPanel for any non-image subtitle track
- **Batch OCR Pipeline** (Phase 34) — async `POST /api/v1/ocr/batch-extract` + `GET /api/v1/ocr/batch-extract/<job_id>` for extracting text from PGS/VobSub image-based subtitle tracks via Tesseract; parallel 4-worker frame processing
- **Quality Fixes Toolbar** (Phase 35) — one-click editor buttons: Overlap Fix, Timing Normalize, Merge Lines, Split Lines, Spell Check; all endpoints create `.bak` backup before modifying

### Fixed
- ESLint `react-hooks/set-state-in-effect` in `SubtitleEditorModal` — replaced synchronous `setState` calls in `useEffect` with React's "adjust during render" pattern

---

## [0.10.0-beta] — 2026-02-22

### Added
- **Context Window Batching** (Phase 19) — subtitle cues grouped into context-window-aware chunks for coherent LLM translation
- **Translation Memory Cache** (Phase 20) — SHA-256 exact-match + difflib similarity cache avoids retranslating identical/near-identical lines; `.quality.json` sidecar file tracks per-line scores
- **Per-Line Quality Scoring** (Phase 21) — LLM scores each translated line 0–10; low-scoring lines retried automatically; quality badge in Library/Series Detail
- **Bulk Auto-Sync** (Phase 22) — auto-sync buttons in Library, Series Detail, and subtitle editor; `POST /api/v1/tools/bulk-auto-sync` batch endpoint
- **Machine Translation Detection** (Phase 23) — detects OpenSubtitles `mt`/`ai` flags; orange MT badge on search results and in Library
- **Uploader Trust Scoring** (Phase 24) — 0–20 score bonus based on provider uploader rank; emerald Trust badge for top-ranked uploaders
- **AniDB Absolute Episode Order** (Phase 25) — `anidb_sync.py` fetches anime-lists XML weekly; providers query `absolute_episode` for correct numbering; routes/anidb_mapping.py + db/repositories/anidb.py
- **Whisper Fallback Threshold** (Phase 26) — configurable minimum Whisper confidence score; subs below threshold fall back to LLM retry
- **Tag-Based Profile Assignment** (Phase 27) — Sonarr/Radarr series/movie tags automatically assign language profiles via `TagProfileMapping` table; processed in webhook handler
- **LLM Backend Presets** (Phase 28) — 5 built-in prompt templates (Anime, Documentary, Casual, Literal, Dubbed); Settings UI "Add from Template" button; user-editable custom presets

### Fixed
- `_translate_with_manager`: `batch_size` chunking now applied correctly (regression in v0.9.6)
- Prompt presets: `{source_language}` / `{target_language}` placeholders substituted at runtime, not stored pre-substituted

---

## [0.9.6-beta] — 2026-02-xx

### Fixed
- Zombie jobs: jobs stuck in "running" state after backend restart are cleaned up on startup
- Wanted page: pagination counter now reflects active filter, not full DB total
- Duplicate `wanted_items`: `UniqueConstraint(file_path, target_language, subtitle_type)` prevents race-condition duplicates
- `get_series_missing_counts()`: excludes `existing_sub = 'srt'` and `'embedded_srt'` (upgrade candidates) from "missing" count

---

## [0.9.5-beta]

### Added
- Global Glossary — per-language term overrides applied during all translations; configurable in Settings → Translation
- Per-Series Glossary — series-specific term overrides; accessible from Series Detail
- Provider test: works without explicit `Content-Type: application/json` header (`force=True` JSON parsing)

---

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
