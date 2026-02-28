# Changelog

All notable changes to Sublarr are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.13.2-beta] — 2026-02-28

### Security
- **Path traversal hardening** — `is_safe_path()` from `security_utils` now enforced on all 8 remaining routes that accepted user-supplied file paths: `tools.py`, `video.py`, `whisper.py`, `spell.py`, `integrations.py`, `webhooks.py`, `translate.py` (4 endpoints + batch directory), `subtitles.py`; inline ad-hoc `os.path.abspath().startswith()` checks replaced throughout (CRITICAL)
- **WebSocket authentication** — Socket.IO `connect` handler now rejects connections with an invalid or missing API key when `SUBLARR_API_KEY` is set; frontend `WebSocketContext` passes the key via socket `auth` dict (HIGH)
- **Secret masking in API responses** — `get_safe_config()` extended to deep-mask JSON blob fields (`sonarr_instances_json`, `radarr_instances_json`, `media_servers_json`) — credential sub-keys (`api_key`, `password`, `token`, `secret`, `pin`) replaced with `"***"`; `notification_urls_json` always masked; `routes/config.py` blocklist extended with 8 additional sensitive keys (HIGH)
- **Request size limit** — `MAX_CONTENT_LENGTH = 16 MB` added to Flask app factory to prevent DoS via oversized request bodies (HIGH)
- **Hook script path restriction** — `create_hook` and `update_hook` now validate `script_path` against `/config/hooks/` using `is_safe_path()`; arbitrary filesystem execution blocked (HIGH)
- **SQL injection in Bazarr migrator** — table names read from the Bazarr SQLite file validated with `^[a-zA-Z_][a-zA-Z0-9_]*$` regex before interpolation into queries; invalid names skipped with a warning (HIGH)
- **XZ decompression bomb protection** — `AnimeTosho._decompress_xz()` now enforces a 10 MB limit on decompressed output; payloads exceeding the limit raise `ValueError` (MEDIUM)
- **Container hardening** — port binding changed from `0.0.0.0` to `127.0.0.1`; `read_only: true` + `tmpfs: [/tmp]` added to `docker-compose.yml` (MEDIUM)

### Changed
- **Dev/prod requirements split** — test and lint tools (`pytest`, `ruff`, `mypy`, `bandit`, `locust`, etc.) moved from `requirements.txt` to new `requirements-dev.txt`; production image no longer installs dev dependencies
- **CI** — backend job now installs `requirements-dev.txt` alongside `requirements.txt` so lint and test tools are available

---

## [0.13.1-beta] — 2026-02-28

### Added

**Sidecar subtitle management**
- **Sidecar discovery APIs** — `GET /api/v1/library/series/<id>/subtitles` scans all episode files in parallel (ThreadPoolExecutor) and returns sidecar metadata keyed by Sonarr episode ID; `GET /api/v1/library/episodes/<id>/subtitles` for single-episode scan; response includes path, language, format, size, and mtime for each sidecar file
- **Sidecar delete API** — `DELETE /api/v1/library/subtitles` moves one or more sidecar files to a `.sublarr_trash/` folder (manifest.json per entry) instead of permanently deleting; only files inside `SUBLARR_MEDIA_PATH` are accepted — path-traversal attempts return 403
- **Trash management APIs** — `GET /api/v1/library/trash` lists recoverable files; `POST /api/v1/library/trash/<id>/restore` moves the file back; `DELETE /api/v1/library/trash/<id>` permanently removes it; auto-purge of entries older than `subtitle_trash_retention_days` (default: 7 days) runs on every delete call
- **Batch delete API** — `POST /api/v1/library/series/<id>/subtitles/batch-delete` removes sidecars across all episodes of a series filtered by language and/or format; all deletions go through the trash system
- **Inline sidecar badges** — SeriesDetail episode rows now show a badge for every sidecar file found on disk (language + format label); non-target-language sidecars are displayed in a dimmed style with a × delete button; clicking × soft-deletes the file and immediately refreshes the row
- **Subtitle Cleanup Modal** — series-level "Clean up" button opens a modal grouped by language showing file count and total size per language; "Keep target languages only" quick action pre-selects all non-target languages for deletion; preview shows file count and MB to be moved to trash before confirming

**Batch extraction improvements**
- **Live extraction progress** — `batch-extract-tracks` emits a `batch_extract_progress` WebSocket event after each episode; SeriesDetail shows a progress banner (file name + `X / N episodes`) with a progress bar and animated spinner while extraction is running; Extract button is disabled during the operation
- **Activity page visibility** — `batch-extract-tracks` now creates a DB job record (`running` → `completed`/`failed`) so every extraction run appears on the Activity page with succeeded, failed, and skipped episode counts; the job is visible within one poll cycle (~3 s) of starting

**Series action toolbar**
- **Always-visible series toolbar** — new action row pinned to the SeriesDetail hero header containing three buttons: "Extract Tracks" (triggers `batch-extract-tracks` for the whole series, shows live X/N counter), "Clean up" (opens Subtitle Cleanup Modal), and "Search N missing" (moved here from the language row); all three actions are available without selecting individual episodes

**Auto-cleanup after extraction**
- **Auto-cleanup settings** — three new config fields: `auto_cleanup_after_extract` (boolean toggle), `auto_cleanup_keep_languages` (comma-separated ISO 639-1 codes, e.g. `de,en`), `auto_cleanup_keep_formats` (`ass` / `srt` / `any`); when enabled, sidecars not matching the keep rules are moved to trash automatically at the end of each `batch-extract-tracks` run
- **Settings UI** — three new fields added to the Automation tab; `subtitle_trash_retention_days` field also added to control automatic trash purge interval

**Queue page — full background visibility**
- **Wanted Batch Search card** — `useWantedBatchStatus()` was previously wired but never rendered; now shown as an amber card with a progress bar and found/failed/skipped item counts while a batch search is running
- **Batch Probe card** — live progress card appears while `batch-probe` is running; shows total tracks scanned, found, extracted, and failed counts plus the currently processed file path; teal accent with animated `Layers` icon
- **Wanted Scanner card** — new `GET /api/v1/wanted/scanner/status` endpoint exposes the full live state of the background wanted scanner (`is_scanning`, `is_searching`, phase label, current/total progress, added/updated counters); rendered as a green card with an optional phase badge and progress bar; adaptive polling — 3 s while active, 30 s idle
- The Queue page now shows all four background operations simultaneously: Batch Translation, Wanted Batch Search, Batch Probe, and Wanted Scanner — each with a distinct colour accent and its own progress indicator

### Changed
- **Subtitle badge semantics** — three visual states: teal = ASS/embedded-ASS (optimal), violet = SRT/upgradeable, orange = missing; non-target-language sidecar files shown in a separate dimmed group with × delete button
- **Language code normalisation** — `normLang()` maps ISO 639-2 three-letter codes (`ger`, `eng`, `jpn`, `fre`, …) to ISO 639-1 two-letter codes (`de`, `en`, `ja`, `fr`, …) so MKV track tags and sidecar filenames no longer generate duplicate badges for the same language
- **SeriesDetail subtitle column** — changed from a fixed `w-40` (160 px) width to `flex-1 min-w-[200px]` so badge rows expand to fill available space and avoid excessive wrapping on wide screens
- **Sidecar query live refresh** — `['series-subtitles']` TanStack Query polls every 4 s while extraction is running; on completion both `['series-subtitles']` and `['series']` are invalidated so episode rows update without a manual reload
- **Queue page polling** — job list refetch interval reduced from 15 s to 3 s so short-lived translation jobs are reliably visible while the Queue page is open

### Fixed
- **Batch-extract series_id 400** — `batch_extract` read `page.get("items", [])` but `get_wanted_items()` returns `{"data": [...]}`, causing every series-level extraction triggered from SeriesDetail to return 400 "item_ids or series_id required"; fixed to `page.get("data", [])`
- **Batch-probe deadlock** — a database error inside `get_wanted_items()` during a probe run left `probe.running = True` permanently until process restart; the call is now wrapped in try/except so the flag is always cleared on failure
- **wanted_item_searched event dropped** — the `wanted_item_searched` signal was emitted in `routes/wanted.py` but never registered in `events/catalog.py`, causing the event to be silently discarded by the unknown-name guard in `emit_event()`; catalog entry and signal registration added
- **Duplicate language badges** — `ger` MKV track tag and target language `de` previously rendered as two separate badges; `normLang()` now normalises both sides before comparison so they collapse to a single badge

### Tests
- Full test suite brought to green (167 passed, 0 failed) across 10 previously failing test files; fixes include app-context push in async fixtures, corrected patch paths for lazily imported modules, Windows-compatible path normalisation in conftest, and adjusted timing thresholds in performance benchmarks

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
