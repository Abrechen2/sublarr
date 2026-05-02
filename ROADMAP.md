# Sublarr — Roadmap

> Completed versions are marked ✅. The current release is **v0.37.3-beta**. Planned versions reflect intended direction and may shift.

---

## v0.11.0 ✅ — Subtitle Toolchain

- Track Manifest — list, extract, and translate embedded subtitle/audio streams
- Video Sync — ffsubsync / alass integration with live progress bar
- Waveform Editor — wavesurfer.js audio visualization with per-cue region markers
- Format Conversion — ASS, SRT, SSA, VTT via pysubs2
- Batch OCR — Tesseract-based text extraction from PGS/VobSub image tracks
- Quality Fixes Toolbar — overlap fix, timing normalize, merge/split lines, spell check

---

## v0.12.0 ✅ — Settings & Visual Redesign

- Settings UX Redesign — SettingsCard, AdvancedSettingsContext, InfoTooltip, per-field descriptions
- arr-style UI Redesign — Sonarr/Radarr aesthetic, teal accent, neutral dark palette

---

## v0.13.0 ✅ — Sidecar Management

- Sidecar Subtitle Management — inline sidecar badges (language + format) per episode with × delete button
- Series/Episode Subtitles API — parallel filesystem scan keyed by Sonarr episode ID
- Delete & Batch-Delete API — path-traversal-safe sidecar deletion by path or language/format filter
- Sidecar Cleanup Modal — language-grouped overview, file count + size preview, target-language filter
- Auto-Cleanup after Batch Extract — three new settings run cleanup automatically after track extraction
- Dynamic subtitle column — grows with content instead of fixed width

---

## v0.14.0 ✅ — Provider Expansion

- Provider UI Redesign — Bazarr-style tile grid; disable grays tile in place, remove sends to pool
- Provider — Subscene — 55-language community subtitle database, no account required
- Provider — Addic7ed — 36 languages, TV-series specialist with episode-exact matching
- Provider — TVSubtitles — 35 languages, TV-series only, no auth
- Provider — Turkcealtyazi — Turkish subtitles, login required
- Language Expansion — `_LANGUAGE_TAGS` 25 → ~70 languages; searchable `LanguageSelect` dropdown

---

## v0.15.0 ✅ — Library & Wanted UX

- Sidebar — Update available badge — pulsing badge when a newer GitHub release exists
- Library — Grid/Thumbnail view — table ↔ grid toggle; poster images from Sonarr/Radarr
- Library — Status and profile filters — client-side filtering by status and profile name
- Wanted — Extracted status — embedded sub extraction sets `extracted` instead of removing item
- Wanted — Sidecar Cleanup — endpoint deletes non-target-language sidecars; teal badge + filter tab
- Wanted — Error and retry display — failure reason tooltip; upcoming retry time shown
- Settings — Search field — real-time filter for settings tabs
- SeriesDetail — EpisodeActionMenu — labelled primary + `⋯ More` dropdown grouped by category

---

## v0.16.0 ✅ — Security Hardening

- ZIP Slip Prevention — `safe_zip_extract()` wired into all providers; shared `extract_archive()` utility
- Download Size Limits — 5 MB per subtitle file, 20 MB per archive
- ZIP Bomb Protection — 50 MB total extracted limit; abort when compression ratio exceeds 100:1
- ASS Sanitizer — strip Lua scripts, external includes, dangerous override tags via pysubs2
- SRT/VTT Sanitizer — strip all HTML except `<i>`, `<b>`, `<u>`; remove scripts, event handlers
- Central `sanitize_subtitle()` Gate — called after every provider download, before disk write
- Content-Type Validation — verify downloaded bytes match expected subtitle format

---

## v0.17.0 ✅ — Subtitle Intelligence

- Duplicate Detection — skip downloads when SHA-256 matches existing sub in same directory
- Smart Episode Matching — multi-episode files, OVA/Special/SP detection via guessit
- Video Hash Pre-Compute — `file_hash` shared across all providers per search run
- Release Group Filtering — include/exclude results by release group, codec, or source tag
- Provider Result Re-ranking — auto-adjust per-provider score modifiers from download history
- Subtitle Upgrade Scheduler — periodic re-check for higher-quality subs; score < 500 or non-ASS
- Translation Quality Dashboard — daily quality trend chart + per-series quality table
- Custom Post-Processing Scripts — hooks receive subtitle path, provider, score on download

---

## v0.18.0 ✅ — Provider Maturity

- Hearing Impaired Support — `hi_preference` setting; ±30/±999 score modifiers
- Forced Subtitle Support — `forced_preference` setting; same scoring logic
- TRaSH-Compatible Scoring Presets — bundled `anime`, `tv`, `movies` presets; Settings UI
- Anti-Captcha Integration — CaptchaSolver (Anti-Captcha.com + CapMonster); Kitsunekko bypass

---

## v0.19.0 ✅ — Stream Removal / Safe Remux

- Remux Engine — mkvmerge (MKV) / ffmpeg (MP4) remux excluding selected streams; no re-encoding
- Verification Pipeline — ffprobe comparison of duration, stream counts, file size after remux
- Atomic File Swap — temp file → original → `.bak` chain via `os.replace()`
- Backup Retention — `remux_backup_retention_days` setting; `GET/POST /api/v1/remux/backups`
- *arr Pause Integration — `remux_arr_pause_enabled` calls Sonarr `set_monitoring()` around remux
- Track Panel UI — two-click "Entfernen" confirmation; Socket.IO job progress

---

## v0.20.0 ✅ — Performance & Scalability

- PostgreSQL First-Class Support — full migration guide, PG-compatible Alembic migrations, `docker-compose.postgres.yml`
- Incremental Metadata Cache — ffprobe results cached in DB with mtime invalidation; `GET/POST /api/v1/cache/ffprobe/*`
- Background Wanted Scanner — batch DB commits per series; `SUBLARR_SCAN_YIELD_MS` yield setting
- Parallel Translation Workers — `SUBLARR_TRANSLATION_MAX_WORKERS` configures thread pool size
- Redis Job Queue — RQ worker with `AppContextWorker`; `docker-compose.redis.yml`; fallback to MemoryJobQueue

---

## v0.21.0 ✅ — Export & UI Polish

- Subtitle Export API — `GET /api/v1/subtitles/download?path=` — single sidecar file download (path-safe, ext whitelist)
- Series ZIP Export — `GET /api/v1/series/{id}/subtitles/export[?lang=]` — all series subtitles as ZIP, 50 MB cap
- SeriesDetail — download icon per sidecar badge; Export ZIP button in series header
- Accessibility — Toast `aria-live`, skip-to-main link, `role="dialog"` on all 7 modals, `scope="col"` on all tables
- StatusBadge — Lucide icons per status; `prefers-reduced-motion` CSS override
- Page-Specific Skeletons — `LibrarySkeleton`, `TableSkeleton`, `ListSkeleton`, `FormSkeleton`
- CSS Hover — replaced JS `useState` hover handlers with `.hover-surface:hover` utility class
- Library Grid — `md:grid-cols-5` tablet breakpoint; 300 ms stagger animation cap

---

## v0.22.0 ✅ — Provider Ecosystem / Plugin Marketplace

- Marketplace — GitHub plugin discovery via `topic:sublarr-provider`; 1-hour cache TTL
- Marketplace — Official/Community badges via `official-registry.json`
- Marketplace — SHA256 integrity verification before install; empty hash rejected (HTTP 400)
- Marketplace — Capability warnings for `filesystem`/`subprocess` on non-official plugins
- Marketplace — `installed_plugins` DB table; hot-reload on install; update detection in UI
- Config — `SUBLARR_GITHUB_TOKEN` for authenticated GitHub API requests
- Security — SSRF prevention (HTTPS-only URLs), path traversal guard on all install/uninstall ops

---

## v0.23.0 ✅ — Batch Operations & Smart Filter

Goals: Multi-select workflows across Library and Wanted; auto-extract-on-scan; saved filter presets.

- Auto-Extract on Scan — `scan_auto_extract` + `scan_auto_translate` settings; scanner extracts embedded subs on first detection
- `POST /wanted/batch-extract` — extract embedded subs for multiple wanted items in one request
- `POST /wanted/batch-search` extended — accepts `series_ids` array for multi-series search
- SeriesDetail — episode checkboxes + floating batch toolbar (Search / Extract)
- Library — series checkboxes + batch toolbar ("Search All Missing")
- Filter Presets — save/load named filter configurations on Library, Wanted, History pages
- Global Search (Ctrl+K) — fuzzy search across series, episodes, and subtitles

---

## v0.24.0 ✅ — Staff Credit Filtering

Goals: Detect and strip credits-only subtitle lines from downloaded subtitles.

- `credit_remover.py` — detect credit lines by regex patterns, duration heuristic, role markers
- `POST /api/v1/tools/remove-credits` — strip detected credits; returns removed count
- Quality Tools panel — Credit Filter button alongside existing Remove HI button

---

## v0.24.1 ✅ — Opening/Ending Skip Detection

Goals: Mark OP/ED cue regions in subtitle files for optional skip during translation.

- OP/ED detection by style name, duration heuristic (OP ≈ 90s, ED ≈ 130s), and content patterns
- `POST /api/v1/tools/mark-opening-ending` — annotate OP/ED boundaries in ASS/SRT files
- Quality Tools panel — Detect OP/ED button with preview of detected ranges

---

## v0.24.2 ✅ — Multi-Audio Track Support for Whisper

Goals: Select the correct audio track per series for Whisper transcription.

- Per-series audio track preference stored in DB (`series_settings.preferred_audio_track_index`)
- `POST /whisper/transcribe` extended with optional `audio_track_index` parameter
- SeriesDetail — audio track picker showing available tracks with language/codec info

---

## v0.24.3 ✅ — Fansub Preference Rules

Goals: Per-series preferred fansub group ordering with score bonuses.

- `SeriesFansubPreference` DB table — preferred groups list + bonus int per series
- Scoring hook in `wanted_search.py` — apply fansub bonus/penalty at result ranking
- SeriesDetail — Fansub Preferences panel (preferred groups, excluded groups, bonus value)
- `GET/PUT /api/v1/series/<id>/fansub-prefs` endpoints

---

## v0.24.4 ✅ — Chapter-Aware Sync

Goals: Align subtitle timing to chapter markers in MKV files.

- Chapter extraction via mkvtoolnix/ffprobe; cache in DB per video file
- Per-chapter sync using pysubs2 to apply offset corrections per chapter segment
- `POST /tools/video-sync` extended with optional `chapter_id` parameter
- Sync modal — chapter selector dropdown when chapters are detected

---

## v0.25.0 ✅ — Jellyfin Play-Start Auto-Translate

Goals: Trigger subtitle search+translate automatically when Jellyfin starts playback.

- `POST /api/v1/webhook/jellyfin` — receive `PlaybackStart` events from Jellyfin Webhook Plugin
- `get_item_path_by_id()` on `JellyfinEmbyServer` — resolve ItemId → file path via REST API
- `get_item_path_from_jellyfin()` on `MediaServerManager` — queries all Jellyfin instances
- `jellyfin_play_translate_enabled` config setting — opt-in, default false

---

## v0.25.1 ✅ — CLI Mode

Goals: Make Sublarr scriptable from the command line.

- `sublarr search --series-id <id>` — search for missing subtitles
- `sublarr translate <file.ass>` — translate a subtitle file
- `sublarr sync --subtitle <file.ass> --video <file.mkv>` — sync subtitles to video
- `sublarr status` — show running jobs

---

## v0.25.2 ✅ — Subtitle Diff Viewer

Goals: Inline accept/reject for individual changed cues (upgrade from full-replace).

- Diff computation between original and translated cues
- Accept/reject per cue in the SubtitleEditorModal
- `POST /api/v1/tools/diff` — compute diff between two subtitle files

---

## v0.25.3 ✅ — List Virtualization

Goals: Smooth scrolling for large libraries.

- `@tanstack/react-virtual` for Library and Wanted
- Requires div-based layout refactor (currently `<table>/<tr>`)
- Deferred from v0.21.1

---

## v0.26.0 ✅ — Single-Account Login

Goals: Optional password protection for the web UI — no multi-user, no RBAC, just a simple access gate.

- `SUBLARR_UI_PASSWORD` env var (hashed, bcrypt) — if set, login is required; if unset, UI is open
- Session-based auth via signed HTTP-only cookie; configurable TTL (`SUBLARR_SESSION_TTL_HOURS`, default 72)
- `/login` page — password form with redirect to original URL after success
- Flask middleware: all non-API routes redirect to `/login` when session absent
- API routes unaffected — existing `X-Api-Key` auth continues to work independently
- Settings UI — change password, invalidate all sessions, show active session count
- Sidebar — "Lock" button + session owner display

---

## v0.27.0 ✅ — Subtitle Quality Score Export

Goals: Persist per-file quality metadata as Kodi/Jellyfin-compatible NFO sidecars for media managers.

- NFO format: XML sidecar (`<filename>.nfo`) alongside subtitle file
- Exported fields: provider, source language, target language, score, translation backend, BLEU score (if available), download timestamp, Sublarr version
- `auto_nfo_export` config setting — write NFO automatically after every subtitle download/translation
- `POST /api/v1/subtitles/export-nfo?path=` — manual trigger for single file (path-safe)
- `POST /api/v1/series/<id>/subtitles/export-nfo` — bulk export for all sidecars of a series
- SeriesDetail — "Export NFO" button in subtitle sidecar context menu

---

## v0.28.0 ✅ — AI Glossary Builder

Goals: Per-series term glossary auto-populated from translation history, injected as LLM context to improve consistency.

- `series_glossary_terms` DB table — term, translation, type (character/place/other), confidence, approved flag, per series
- Auto-detection pipeline: frequency analysis + optional NER pass over past translated cues to surface recurring proper nouns
- Glossary injected as system prompt prefix during LLM translation (`<glossary>` block, max 50 terms)
- `GET/POST/PUT/DELETE /api/v1/series/<id>/glossary` — full CRUD
- `POST /api/v1/series/<id>/glossary/suggest` — trigger auto-detection run; returns candidates for review
- SeriesDetail — Glossary panel: suggestion list (approve/reject), manual add, search, export as TSV
- `SUBLARR_GLOSSARY_ENABLED` setting (default true); `glossary_max_terms` per series (default 100)

---

## v0.29.0 ✅ — Web Player

- Streaming endpoint — `GET /api/v1/media/stream?path=` with HTTP 206 range-request support; `is_safe_path()` enforced
- PlayerModal — portal-based HTML5 `<video>` player with play/pause/seek/volume/fullscreen
- ASS/SRT subtitle overlay via SubtitleOctopus (libass WASM) rendered natively in-browser
- Subtitle track selector — switch between all available sidecar subtitle files per episode
- Seek-to-cue — clicking a cue row in SubtitleEditorModal jumps player to that timestamp

---

## v0.30.0 ✅ — Standalone NFO & Skip Extras

- Standalone — NFO metadata integration — reads `.nfo` sidecar files to resolve series/movie title, year, TVDB/TMDB ID without API lookup
- Standalone — Skip extra files — trailers, featurettes, samples excluded via Jellyfin/Kodi naming conventions; `standalone_skip_extras` setting

---

## v0.31.0 ✅ — Code Quality & Architecture Split

- 29 new tests added for `WantedSearchService`, `ProviderManager`, quality-validation logic; suite at 736 tests, 47.76% coverage
- 8 oversized backend files (800–2921 lines) decomposed: `routes/hooks/`, `routes/library/`, `routes/wanted/`, `routes/translate/`, `routes/system/`, `routes/tools/`
- `providers/registry.py` with `PROVIDER_METADATA` replaces three class-level dicts
- Frontend — `SyncControls.tsx` and `useApi.ts` each split into 6 focused sub-files
- Frontend — `ErrorBoundary` wraps Library, Wanted, and Settings routes

---

## v0.32.0 ✅ — Settings Restructure & UX Improvements

- Settings navigation restructured from 7 groups / 23 tabs to 5 logical groups
- Provider priority via drag & drop (replaces move-up/down buttons)
- Score breakdown hover tooltip on search result badges
- Wanted — per-row failure details, attempt count, next retry countdown
- Dashboard — Automation Widget with live run times and Run Now button
- Onboarding — Language and Automation setup wizard steps added

---

## v0.33.0 ✅ — Provider Expansion & Processing Pipeline

- 7 new providers: Subf2m, Subsource, YIFY Subtitles, Zimuku, BetaSeries, Titlovi, EmbeddedSubtitles
- Post-download processing pipeline with 18 fix functions (HI removal, OCR artifact cleanup, etc.); configurable per series
- Settings — Processing Pipeline section; Series Detail — Batch Process button

---

## v0.35.0 ✅ — Movie Detail & Security Hardening

- Movie Detail — subtitle management panel (wanted items per language with inline Search / Skip / Re-enable)
- Security — CSP and Permissions-Policy headers on all responses
- Security — SSRF prevention on webhook create/update endpoints
- Security — startup warning when both API key and UI auth are disabled

---

## v0.36.0 ✅ — Bazarr Parity Features

- Scoring — `video_codec` weight: x264/x265/AV1 match adds +2 points
- Language Profiles — `mustContain` / `mustNotContain` AND-logic filters (Bazarr parity)
- Language Profiles — `cutoff` (stop searching when subtitle already present)
- Language Profiles — `audioExclude` (skip download when audio track matches target language)
- CircuitBreaker — OPEN state persisted to DB; survives application restarts
- Download quality — `upgraded_from_id` foreign key tracks subtitle upgrade chain
- Standalone Mode — auto-activation when no *arr is configured

---

## v0.37.0 ✅ — Timestamp Migration & Refactoring

**BREAKING CHANGE:** All timestamp columns migrated from TEXT to `DateTime(timezone=True)`. Migration runs automatically on startup.

- `scripts/check_datetime_migration.py` — pre/post migration DB consistency checker (70 columns, 29 tables)
- Security — `subprocess(shell=True)` replaced with `shlex.split()` throughout; IP allowlist enforced; SSRF on plugin URLs
- `services/retranslation.py` extracted; `StatisticsRepository` extracted; `useDebounce` hook extracted
- TranslationTab split from 1989 lines into 8 focused sub-components
- Frontend — `ConfirmModal` replaces all `window.confirm()` calls

---

## v0.37.2 ✅ — AniDB Resolver & AnimeTosho Fix

- AniDB title dump resolver (Tier 4) — offline 91k+ entry xml.gz lookup (36h cache)
- AnimeTosho provider — rewritten with correct two-step API flow (`?show=torrent&id=`)
- Provider cache key now includes `anidb_id` to prevent stale cache hits
- Alembic — `engine.begin()` wraps all PostgreSQL DDL in explicit transaction

---

## v0.37.3 ✅ — Activity Navigation Restructure

- "Wanted" promoted to top-level sidebar nav item
- Activity reduced to 4 tabs: Queue, Translations, History, Blacklist
- New Translations tab shows active and queued translation jobs with live polling
- Badge moved from Activity to Wanted nav item

---

## v0.38.0 — Phase 2 Cleanup (Planned)

- No `datetime.utcnow()` calls anywhere in backend (10 occurrences fixed)
- `whisper_subgen` provider removed (dead code since v0.31)
- ROADMAP.md up to date

---

## v0.39.0 ✅ — Security Hardening P1–P5

Shipped incrementally across v0.38–v0.70.4-beta; final round rolled up
in the 2026-04-20 hardening batch.

- P1 ✅ — Per-provider domain allowlist for subtitle download URLs
  (SSRF prevention). `security_utils.validate_download_url()` called
  from all 29 providers; 15 were wired in the 2026-04-20 batch.
- P2 ✅ — `werkzeug.secure_filename()` centralised in
  `archive_utils._safe_basename()` (strips backslashes + non-ASCII +
  null bytes + traversal), applied to every ZIP/RAR extraction path.
  `animetosho` + `gestdown` additionally sanitise API-sourced names.
- P3 ✅ — Prompt-injection guard for Ollama / Claude / OpenAI:
  newline/CR escape, null-byte strip, zero-width Unicode strip
  (U+200B/C/D/2060/FEFF), 2000-char truncation per line.
- P4 ✅ — Magic-byte validation (`_validate_subtitle_content()`)
  called from `save_subtitle()` before every disk write.
- P5 ✅ — 50 MB streaming cap via `_stream_download()` on all 29
  provider download paths; `_MAX_SUBTITLE_SIZE` post-fetch guard for
  `legendasdivx` (keeps session-expiry redirect detection intact).
- F-05 — Webhook missing-signature warning in `auth.py` (still open;
  accepted risk for internal tool).

---

## v0.40.0 — Test Coverage Phase (Planned)

- Backend coverage from ~10% toward 35–40%
- Priority: `routes/cleanup.py`, `routes/api_keys.py`, `routes/profiles.py` (all currently 0% coverage)
- `bazarr_migrator.py` — data migration tests
- Stabilize 3+ excluded CI test suites

---

## v1.0.0 — Stable Release

Requirements for stable release:

- All known data-loss bugs fixed
- Full test coverage (>80%) across backend and E2E
- Migration guide from any beta version
- Stable API (no breaking changes from v0.13+)
- Docker image on GHCR with multi-arch (amd64 + arm64)
- Unraid Community Applications template finalized
- User Guide complete and reviewed
- Load tested with library of 500+ series

---

## How to Contribute

See [sublarr.de/docs/development/contributing](https://sublarr.de/docs/development/contributing/) for how to submit features, bug reports, and pull requests.
