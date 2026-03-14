# Changelog

All notable changes to Sublarr are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.25.2-beta] — 2026-03-13

### Added
- **Subtitle Diff Viewer — Per-cue accept/reject** — `POST /tools/diff` computes a cue-level diff using pysubs2 + difflib.SequenceMatcher; returns structured diff entries (unchanged/modified/added/removed) with timing in seconds. `POST /tools/diff/apply` recomputes the diff server-side, merges accepted/rejected changes into the modified SSAFile (preserving header and styles), creates a `.bak` backup, and writes atomically via `os.replace`. Frontend `SubtitleDiff.tsx` rewritten from CodeMirror merge view to a filterable per-cue table; users can accept or reject each change individually or via Accept All / Reject All; applying navigates back to preview and invalidates the subtitle-content cache.

---

## [0.25.1-beta] — 2026-03-13

### Added

- **CLI — `sublarr search`** — search subtitle providers for all wanted items in a series via `--series-id <id>`; calls `GET /wanted` + `POST /wanted/batch-search`
- **CLI — `sublarr translate`** — translate a subtitle file via `POST /translate/sync`; supports `--force` flag; prints output path (sync) or job ID (queued)
- **CLI — `sublarr sync`** — sync subtitle timing to a video file via `POST /tools/auto-sync`; `--engine ffsubsync|alass`
- **CLI — `sublarr status`** — show active translation jobs and background task state; `--running` to filter in-progress jobs only
- **CLI — Entry point** — `backend/sublarr_cli.py`; configure via `SUBLARR_URL` and `SUBLARR_API_KEY` env vars or `--url`/`--api-key` flags

---

## [0.25.0-beta] — 2026-03-13

### Added

- **Jellyfin Play-Start Webhook — `POST /api/v1/webhook/jellyfin`** — receives `PlaybackStart` events from the Jellyfin Webhook Plugin; resolves `ItemId` → file path via configured Jellyfin media server instances (`GET /Items/{id}?Fields=Path`); triggers subtitle search+translate pipeline in background thread (same pipeline as Sonarr/Radarr webhooks)
- **`JellyfinEmbyServer.get_item_path_by_id()`** — new method on the Jellyfin backend to fetch item path by Jellyfin item ID
- **`MediaServerManager.get_item_path_from_jellyfin()`** — queries all enabled Jellyfin/Emby instances and returns the first resolved path; lazily loads instances if none are cached
- **Config — `jellyfin_play_translate_enabled`** — new boolean setting (`SUBLARR_JELLYFIN_PLAY_TRANSLATE_ENABLED`, default `false`); feature is opt-in

---

## [0.24.4-beta] — 2026-03-13

### Added

- **ChapterCache — `chapter_cache` DB table** — per-video chapter list cache (PK: `file_path`, mtime-invalidated); stores JSON list of `{id, title, start_ms, end_ms}` dicts; avoids repeated `ffprobe` invocations
- **`backend/chapters.py`** — `get_chapters(video_path)` via `ffprobe -show_chapters`; results cached in `chapter_cache`; returns `[]` if video has no chapters or `ffprobe` is unavailable
- **`GET /api/v1/tools/chapters?video_path=…`** — returns `{video_path, chapters: [{id, title, start_ms, end_ms}]}`; path validated via `is_safe_path()`
- **Advanced Sync — `chapter_range` parameter** — `POST /tools/advanced-sync` offset operation now accepts optional `chapter_range: {start_ms, end_ms}`; only subtitle events within the chapter window are shifted; preview mode samples only in-range events
- **SyncControls — Chapter Tab** — new "Chapter" tab visible when `videoPath` prop is provided and chapters are detected; chapter dropdown (title + timestamps), ±offset presets, preview, two-step confirm-apply flow

---

## [0.24.3-beta] — 2026-03-13

### Added

- **FansubPreference — `fansub_preferences` DB table** — per-series fansub group rules (PK: `sonarr_series_id`); stores preferred groups, excluded groups, and bonus points as JSON
- **`GET/PUT/DELETE /api/v1/series/<id>/fansub-prefs`** — read/write/delete fansub preferences; GET returns defaults `{preferred_groups: [], excluded_groups: [], bonus: 20}` for unconfigured series
- **Scoring Hook — `_apply_fansub_rules()`** — injected in `wanted_search.py` before result sort; case-insensitive substring match on `result["release_info"]`; preferred group → +bonus points, excluded group → −999 (effectively excluded)
- **SeriesFansubPrefsPanel** — new component mounted in SeriesDetail; comma-separated preferred/excluded group inputs + bonus score field + Save/Reset buttons

---

## [0.24.2-beta] — 2026-03-13

### Added

- **SeriesSettings — `preferred_audio_track_index`** — new nullable integer column on `series_settings` table; stores the pinned ffprobe stream index used for Whisper transcription
- **`GET/PUT /api/v1/series/<id>/audio-track-pref`** — read/write preferred audio track index; PUT accepts `null` to clear (resume auto-select)
- **WhisperQueue — `audio_track_index` propagation** — `queue_transcription()` accepts and forwards `audio_track_index`; the transcribe route extracts the preferred index from series settings when not explicitly provided
- **SeriesAudioTrackPicker** — new component mounted in SeriesDetail; lazy-loads episode audio tracks via ffprobe; dropdown sets the per-series Whisper transcription preference

---

## [0.24.1-beta] — 2026-03-12

### Added

- **OP/ED Detector — `op_ed_detector.py`** — detects Opening and Ending cue regions in ASS/SSA/SRT files using two passes: Pass 1 matches ASS style names (`OP`, `ED`, `Opening`, `Ending`, `OP Theme`, `ED Theme`); Pass 2 uses position + duration heuristics (OP: 60–120 s in first window, ED: 90–180 s in last window) with per-type gating and overlapping-window guard
- **`POST /api/v1/tools/detect-opening-ending`** — read-only endpoint returning detected OP/ED regions as `{type, start_ms, end_ms, event_count, method}`; returns `detected: []` when nothing found (not a 4xx); no file modification
- **Config — `op_window_sec`** — new setting (`SUBLARR_OP_WINDOW_SEC`, default 300 s) controls how many seconds from the start and end of a file are considered the OP/ED detection window

### Changed

- **SubtitleEditorModal — Quality Tools** — added Detect OP/ED button after Remove Credits button

---

## [0.24.0-beta] — 2026-03-12

### Added

- **Credit Remover — `credit_remover.py`** — detects and removes credits-only subtitle lines from ASS/SSA/SRT files using 4 independent heuristics: role markers (`(Translator)`, `(QC)`, etc.), credit prefix patterns (`Credits:`, `Staff:`, etc.), duration heuristic (events near end of file), and isolated capitalized names (`John Smith`); `dry_run` mode for preview without modification
- **`POST /api/v1/tools/remove-credits`** — new endpoint to strip detected credits; `dry_run=true` returns preview of lines that would be removed (capped at 50); `dry_run=false` creates `.bak` backup then writes cleaned file; returns `original_lines`, `cleaned_lines`, `removed`, `backed_up`
- **Config — `credit_threshold_sec`** — new setting (`SUBLARR_CREDIT_THRESHOLD_SEC`, default 90s) controls how many seconds from the end of a file are considered the credits region

### Changed

- **SubtitleEditorModal — Quality Tools** — added Remove Credits button alongside existing Remove HI button

---

## [0.23.0-beta] — 2026-03-12

### Added

- **Batch Translate — `POST /wanted/batch-translate`** — re-translate multiple subtitle files in one request; accepts `item_ids` array; returns per-item success/failure map
- **Batch Search Extended** — `POST /wanted/batch-search` now accepts `series_ids` array for multi-series search in a single call
- **Library — Series Checkboxes** — multi-select series in Library view with floating batch toolbar (Search All Missing)
- **SeriesDetail — Episode Checkboxes** — multi-select episodes with floating batch toolbar (Search / Extract)
- **Filter Presets** — save, load, and delete named filter configurations on Library, Wanted, and History pages; persisted in `filter_presets` DB table via `GET|POST|DELETE /api/v1/filter-presets`
- **Global Search (Ctrl+K)** — fuzzy search across series, episodes, and subtitles; keyboard-accessible command palette
- **Auto-Extract on Scan** — `scan_auto_extract` + `scan_auto_translate` settings; scanner automatically extracts embedded subs on first detection

---

## [0.22.0-beta] — 2026-03-11

### Added

- **Marketplace — GitHub Plugin Discovery** — new Settings → Providers → Marketplace tab; discovers community plugins via `topic:sublarr-provider` GitHub topic search; caches results in `marketplace_cache` DB table with 1-hour TTL
- **Marketplace — Official/Community Badges** — plugins from `official-registry.json` receive a verified "Official" badge; community plugins show a neutral "Community" label; `is_official` flag persisted in DB
- **Marketplace — SHA256 Integrity Verification** — `install_plugin_from_zip()` verifies SHA256 hash before extraction; SHA256 is required (empty string rejected with HTTP 400); prevents install of corrupted or tampered plugins
- **Marketplace — Capability Warnings** — `CapabilityWarningModal` warns users before installing non-official plugins that declare `filesystem` or `subprocess` capabilities; confirmation required before proceeding
- **Marketplace — Installed Plugins DB** — `installed_plugins` table tracks name, version, capabilities, SHA256, plugin dir, and install timestamp; persists across restarts
- **Marketplace — Hot-Reload** — `POST /marketplace/install` hot-reloads the plugin manager after successful installation via `manager.reload()` + `invalidate_manager()`
- **Marketplace — Refresh** — `POST /marketplace/refresh` force-fetches latest plugin list from GitHub, bypassing the 1-hour cache TTL
- **Marketplace — Update Detection** — UI compares installed version against registry version; highlights available updates with a yellow badge
- **Config — `github_token`** — new optional `SUBLARR_GITHUB_TOKEN` setting; used for authenticated GitHub API requests to avoid rate limiting
- **DB Migration `a2b3c4d5e6f7`** — adds `marketplace_cache` and `installed_plugins` tables via Alembic

### Security

- **SSRF Prevention** — `zip_url` validated to be HTTPS-only before download (`urlparse` scheme check)
- **Path Traversal** — `is_safe_path()` applied to all install/uninstall plugin directory operations
- **XSS Prevention** — `github_url` validated with `startsWith('https://')` before rendering as `<a href>`

## [0.21.1-beta] — 2026-03-11

### Added

- **Accessibility — Toast `aria-live`** — `ToastContainer` now has `role="status"`, `aria-live="polite"`, and `aria-atomic="true"`; screen readers announce toast messages without interrupting focus
- **Accessibility — Skip-to-Main Link** — visually-hidden skip link added as first focusable element in the render tree; activating it moves focus to `#main-content`; visible on keyboard focus
- **Accessibility — Modal `role="dialog"`** — all 7 modals (`SubtitleEditorModal`, `WidgetSettingsModal`, `GlobalSearchModal`, `SubtitleCleanupModal`, `SyncModal`, `AddProviderModal`, `ProviderEditModal`) now have `role="dialog"`, `aria-modal="true"`, `aria-labelledby` pointing to the modal title, and `autoFocus` on the close button
- **Accessibility — Semantic Tables** — all `<th>` elements in Library, History, Blacklist, and Wanted tables have `scope="col"`; Library sort headers update `aria-sort` dynamically (`ascending` / `descending` / `none`)
- **Accessibility — Form Labels** — `AddProviderModal` and `ProviderEditModal` inputs have `aria-label` or `<label htmlFor>` associations; `SettingRow` renders a semantic `<label>` when `htmlFor` is provided
- **Accessibility — Client-Side Validation** — `AddProviderModal` and `ProviderEditModal` validate required fields on blur and on submit attempt; inline `<p role="alert">` error messages with `aria-invalid` / `aria-describedby` on inputs
- **StatusBadge — Lucide Icons** — each status now renders a lucide icon alongside the color dot for colorblind accessibility (`CheckCircle2`, `XCircle`, `Clock`, `Loader2`, `AlertCircle`, `Search`, `MinusCircle`); `Loader2` animates with `animate-spin`; color dot removed
- **Page-Specific Skeletons** — `LibrarySkeleton`, `TableSkeleton`, `ListSkeleton`, `FormSkeleton` added to `PageSkeleton.tsx`; Library, History, Queue, Blacklist, Wanted, and Settings Suspense boundaries use their matching skeleton instead of the generic one
- **`prefers-reduced-motion`** — CSS media query added to `index.css`; overrides all animation/transition durations to `0.01ms` for users who opt out of motion

### Changed

- **Library Grid — Tablet Breakpoint** — added `md:grid-cols-5` between `sm:grid-cols-4` and `lg:grid-cols-6`; smooths the column jump at 768px viewport
- **Stagger Animation — 300ms Cap** — Library grid cards and Wanted list rows apply `animationDelay: Math.min(i * 30, 300)ms`; late items on large lists no longer appear broken
- **CSS Hover — Remove JS State** — `RecentActivityWidget` and `ProviderTile` replaced `useState`/`onMouseEnter`/`onMouseLeave` background-color handlers with a `.hover-surface:hover` CSS utility class; eliminates unnecessary re-renders

## [0.20.0-beta] — 2026-03-10

### Added

- **PostgreSQL — First-Class Support** — full migration guide, PG-compatible Alembic migrations, dialect-aware health endpoints (`GET /database/health`), VACUUM guard (returns 501 on PostgreSQL); `docker-compose.postgres.yml` for batteries-included PG stack; `docs/POSTGRESQL.md` covers fresh install, SQLite→PG migration via pgloader, pool tuning, backup/restore
- **Incremental Metadata Cache** — ffprobe results cached persistently in DB with mtime-based invalidation; `GET /api/v1/cache/ffprobe/stats` and `POST /api/v1/cache/ffprobe/cleanup` endpoints; batch wanted-scanner probes now use cache (`use_cache=True`); eliminates redundant ffprobe calls on unchanged files
- **Background Wanted Scanner — Batch Commits** — scanner now batches all DB writes per series/movie into a single commit (instead of one commit per episode); thread-local `_batch_mode` flag ensures batch mode in the scanner thread never blocks concurrent API request commits; `SUBLARR_SCAN_YIELD_MS` setting (default: 0) adds optional CPU yield between series to reduce contention
- **Parallel Translation Workers — Configurable Count** — `SUBLARR_TRANSLATION_MAX_WORKERS` setting (default: 4) controls the thread pool size of the in-memory job queue; `/translate` async endpoint now routes through the shared job queue (same as `/translate/sync`) so concurrency is always bounded and observable via `GET /api/v1/jobs`
- **Redis Job Queue** — `backend/worker.py` RQ worker entry point with `AppContextWorker` subclass — each job runs inside a Flask app context; `docker-compose.redis.yml` stack with Redis 7 + Sublarr + `rq-worker`; scale workers with `--scale rq-worker=N`; graceful fallback to `MemoryJobQueue` when Redis is unreachable

## [0.19.2-beta] — 2026-03-10

### Fixed

- **Remux Engine — mkvmerge wrong track ID** — `_remux_mkvmerge` was referencing an undefined `stream_index` variable (NameError) and the call site was passing `subtitle_track_index` (0-based subtitle-only index, e.g. `0`) instead of the global ffprobe stream index (e.g. `2`); mkvmerge's `--subtitle-tracks !N` flag uses global Track IDs matching ffprobe's `stream_index` — passing `!0` targeted the video track and left the subtitle untouched; now `_remux_mkvmerge` receives and uses the correct global `stream_index`; validated with mkvmerge v92.0 inside Docker

## [0.19.1-beta] — 2026-03-10

### Fixed

- **Dockerfile — mkvtoolnix missing** — added `mkvtoolnix` to the Docker image apt-get install step; without it `mkvmerge` was unavailable inside the container and all MKV stream removal jobs failed with "mkvmerge not found"

## [0.19.0-beta] — 2026-03-10

### Added

- **Stream Removal — Safe Remux Engine** — remove embedded subtitle streams from video containers without re-encoding; mkvmerge used for MKV/MK3D, ffmpeg for all other containers (MP4, AVI, etc.); backend auto-detected by file extension; ffprobe verification after remux validates duration (±2s), video/audio stream counts, subtitle count (exactly -1), and file size (≥50% of original)
- **Trash-Folder Backups — Configurable Retention** — original video moved to centralized `<media_root>/<remux_trash_dir>/trash/<YYYY-MM-DD>/<file>.<ts>.bak` before each remux (TinyMediaManager-style); absolute trash path supported; falls back to sibling `.bak` on permission error; CoW reflink attempted first on Btrfs/XFS for near-instant copies; `remux_trash_dir` (default `.sublarr`) and `remux_backup_retention_days` (default 7) configurable in Settings → Automation
- **Async Remux Jobs** — `POST /api/v1/library/episodes/<ep_id>/tracks/<index>/remove-from-container` starts a background job; `GET /api/v1/remux/jobs` and `GET /api/v1/remux/jobs/<job_id>` expose status; real-time updates via Socket.IO `remux_job_update` events; optional Sonarr/Radarr folder-monitoring pause during remux
- **Backup Management API** — `GET /api/v1/remux/backups` lists all `.bak` files in trash directories; `POST /api/v1/remux/backups/cleanup` deletes backups older than retention period (supports `dry_run` mode)
- **Undo / Restore** — `POST /api/v1/remux/backups/restore` atomically restores backup to original video path via `os.replace()`; both paths validated with `is_safe_path()` to prevent path traversal; "Rückgängig" button appears in TrackPanel after successful stream removal and restores in one click

## [0.18.0-beta] — 2026-03-10

### Added

- **HI Support — Hearing Impaired Preference** — new `hi_preference` setting (`include` / `prefer` / `exclude` / `only`); provider results scored accordingly: `prefer` adds +30, `exclude` / `only` apply ±999 penalty; `hi_removal_enabled` toggle for future HI-tag stripping
- **Forced Subtitle Support — Forced Preference** — new `forced_preference` setting (`include` / `prefer` / `exclude` / `only`) with same ±30/±999 scoring logic; bonuses stack when both HI and forced preferences match
- **TRaSH Scoring Presets — Importable Community Profiles** — `backend/scoring_presets/` package with three bundled presets (`anime`, `tv`, `movies`); `GET /api/v1/scoring/presets`, `GET /api/v1/scoring/presets/<name>`, `POST /api/v1/scoring/presets/import` endpoints; Settings → Events & Hooks → Scoring tab shows preset selector and custom JSON import; import validates schema and calls `invalidate_scoring_cache()`
- **Anti-Captcha Integration — Provider 403 Bypass** — new `CaptchaSolver` class supporting Anti-Captcha.com and CapMonster via identical `createTask` / `getTaskResult` REST API; `anti_captcha_provider` + `anti_captcha_api_key` settings; Kitsunekko calls `_try_solve_captcha_and_retry()` on HTTP 403 — submits reCAPTCHA v2 token and retries; falls back gracefully if no solver configured; Anti-Captcha section added to Providers tab in Settings

## [0.17.0-beta] — 2026-03-10

### Added
- **Duplicate Detection — SHA-256 download dedup** — skips provider downloads when SHA-256 hash matches an existing subtitle in the same directory; stale hash entries are auto-cleaned on startup; toggleable via `SUBLARR_DEDUP_ON_DOWNLOAD`; hash registered on every successful file write
- **Smart Episode Matching — multi-episode + OVA/Special** — multi-episode filenames (`S01E01E02`) parsed to full episode list; OVA/Special/SP detection via guessit + filename regex; `release_group`, `source`, `resolution`, `absolute_episode` propagated to `VideoQuery` for all providers
- **Video Hash Pre-Compute** — `file_hash` computed once in `build_query_from_wanted()` and reused across all providers; eliminates redundant file reads when multiple providers are queried in parallel
- **Release Group Filtering** — include/exclude subtitle results by release group, codec, or source tag; score bonus for preferred groups; release metadata auto-extracted from filename via guessit; configurable at Settings → Wanted
- **Provider Result Re-ranking** — auto-adjusts per-provider score modifiers from download history; formula: success rate + avg score vs. global average + consecutive failure penalty; throttled hourly; preview endpoint and manual trigger available
- **Subtitle Upgrade Scheduler** — periodic re-check for higher-quality subtitles; eligibility: score < 500 OR non-ASS format; configurable `upgrade_scan_interval_hours` at Settings → Automatisierung; manual trigger via `/tasks/upgrade-scan/trigger`
- **Translation Quality Dashboard** — daily quality trend chart (avg score + issue count) and per-series quality table (sortable, color-coded bars) added to Statistics page
- **Custom Post-Processing Scripts — `subtitle_downloaded` event** — `subtitle_downloaded` event now emitted from `save_subtitle()`; shell hooks at Settings → Events & Hooks receive `SUBLARR_SUBTITLE_PATH`, `SUBLARR_PROVIDER_NAME`, `SUBLARR_SCORE`, `SUBLARR_LANGUAGE`, and `SUBLARR_SERIES_TITLE` environment variables

---

## [0.15.2-beta] — 2026-03-03

### Added
- **Activity — Parsed media titles** — file column now shows parsed series/episode name and episode number instead of raw filename; full path still accessible in the expanded row; `parseMediaTitle()` utility added to `lib/utils.ts`
- **History — Blacklist confirmation dialog** — ban icon on history entries now opens a confirmation modal showing provider and title instead of blacklisting immediately; optional "Also delete subtitle file" checkbox deletes the sidecar file and invalidates the history cache in one atomic flow
- **SeriesDetail — Delete confirmation dialog** — deleting a subtitle sidecar now opens a confirmation modal with an "Also add to blacklist?" checkbox; when checked, the provider record is looked up from `subtitle_downloads` and added to the blacklist before the file is moved to trash
- **Activity — Expanded row layout** — expanded detail row redesigned with cleaner label/value grid, stats section, and better visual hierarchy

### Fixed
- **Wanted — `wanted_auto_translate=False` not respected** — `process_wanted_item()` always started a translation job regardless of the `wanted_auto_translate` setting; now the flag is checked and translation is skipped when disabled
- **Backend — `DELETE /library/subtitles`** — accepts optional `blacklist: bool` body parameter; when `true`, looks up the provider record in `subtitle_downloads` (LIKE-match on video base path + language) and calls `add_blacklist_entry()` before trashing the sidecar

---

## [0.15.1-beta] — 2026-03-01

### Fixed
- **App — SPA 404 on page reload** — `static_url_path=""` caused Flask's built-in static file route to intercept `/wanted`, `/library` etc. and return 404 before the `serve_spa()` catch-all; fixed by setting `static_folder=None` so only the custom handler runs
- **App — PostgreSQL startup warnings** — `rowid` in `wanted_items` dedup query replaced with `id` (primary key); `MIN(title)` aggregate added to search index rebuild query to satisfy PostgreSQL GROUP BY rules; `_patch_pre_alembic_columns()` detects and adds the `source` column to `subtitle_downloads` for databases created before Alembic was introduced
- **Scoring — `_DEFAULT_EPISODE_WEIGHTS` import** — re-exported from `db.scoring` so `routes/hooks.py` can import them without reaching into the repository layer

---

## [0.15.0-beta] — 2026-03-01

### Added
- **Sidebar — Update available badge** — a pulsing badge appears in the sidebar when a newer GitHub release is available; the version is fetched from the GitHub Releases API once on load and cached; clicking opens the release page directly

### Fixed
- **Wanted — Search and download** — provider search and download were broken due to missing Flask app context in background threads and stale cache; fixed by passing the app instance explicitly and resetting the provider cache on each call

---

## [0.14.2-beta] — 2026-03-01

### Added
- **Wanted — Extracted status** — extracting an embedded subtitle no longer removes the item from Wanted; instead it stays visible with a new teal `Extracted` badge so the user can see what was extracted and trigger translation or cleanup as a follow-up step
- **Wanted — Sidecar Cleanup** — new `POST /api/v1/wanted/cleanup` endpoint and matching UI button (with confirmation dialog) that deletes non-target-language `.ass`/`.srt` sidecar files next to media files of extracted items; supports `dry_run` mode and optional `item_ids` filter; path-traversal protected via `is_safe_path()`
- **Wanted — Extracted filter tab** — new filter tab in the status row allows filtering the Wanted list to show only items with status `extracted`

### Changed
- **Wanted — Extract behavior** — `PUT /wanted/<id>/status` now accepts `extracted` as a valid status value in addition to `wanted`, `ignored`, `failed`

---

## [0.14.1-beta] — 2026-03-01

### Added
- **Library — Grid/Thumbnail view** — toggle button (table ↔ grid) next to series/movies tabs; grid renders poster images from Sonarr/Radarr with missing-count badge; preference persisted to `localStorage`; fallback film-slate SVG when no poster available
- **Library — Status and profile filters** — dropdown to filter items by status (all / has missing / complete) and by profile name; filtering applied client-side via `useMemo` with no additional API calls
- **Wanted — Error and retry display** — failed wanted items now show the failure reason as a truncated `⚠ message` tooltip in the status column; upcoming retry time shown as `Retry: Xm/Xh` below the badge when `retry_after` is set
- **Settings — Search field** — text input at the top of the settings sidebar filters tabs by name in real-time; Migration tab is excluded from search results regardless of the Advanced toggle
- **SeriesDetail — EpisodeActionMenu** — replaces 8 unlabelled icon-only action buttons with two primary labelled buttons (Search, Edit) and a `⋯ More` dropdown grouped by category (Preview/Compare, Timing, Analyse, History); extracted into standalone `EpisodeActionMenu` component

### Fixed
- **Sidebar — Version display** — version fallback changed from the hardcoded `v0.1.0` to `v…` while the health endpoint is loading; version now always reflects `backend/VERSION` correctly
- **i18n — SeriesDetail action buttons** — all 12 episode action button tooltips (Preview, Edit, Compare, Sync Timing, Auto-Sync, Video Sync, Health Check, Embedded Tracks, Search, Interactive Search, History, Back) were hardcoded English; replaced with `t('library:episode_actions.*')` keys available in both DE and EN
- **i18n — Wanted page** — "Scan Embedded" button label, "Scanning…" state text, and "Upgrades Only (N)" filter badge were hardcoded; replaced with `t('library:wanted.*')` keys
- **i18n — FilterBar / FilterPresetMenu** — "Add filter", "Clear all", "Presets", "No saved presets", "Preset name…", "Save current filters" were hardcoded English; now use `t('common:filters.*')` keys
- **Settings — Migration tab visibility** — Migration tab was always visible in the System group; now only rendered when the Advanced toggle is active and the settings search field is empty

### Changed
- **Statistics — empty state message** — placeholder text updated to mention subtitle searches in addition to translations so users understand both workflows populate the chart
- **Statistics — download tracking** — `record_subtitle_download()` in `db/providers.py` now also writes to the `daily_stats` table via `record_stat()`; provider downloads were previously invisible on the Statistics page (only translation jobs were tracked)

---

## [0.14.0-beta] — 2026-03-01

### Added
- **Provider UI — Deaktivieren vs. Entfernen** — Power button grays out a provider tile in-grid (50% opacity, "Deaktiviert" badge) while Trash button removes it to the `+` pool entirely; new `providers_hidden` config key separates "off but visible" from "removed from grid"
- **Provider — Subscene** — 55-language community subtitle database, no account required; HTML scraping with BeautifulSoup4, rate limit 10/60 s
- **Provider — Addic7ed** — 36 languages, TV-series specialist with episode-exact matching; optional login credentials increase daily download limit; BeautifulSoup4, rate limit 10/60 s
- **Provider — TVSubtitles** — 35 languages, TV-series only, no auth; BeautifulSoup4, rate limit 15/60 s
- **Provider — Turkcealtyazi** — Turkish subtitle community site, login required; BeautifulSoup4, rate limit 10/60 s
- **Language expansion** — `_LANGUAGE_TAGS` expanded from 25 to ~70 ISO 639-1 codes; `SUPPORTED_LANGUAGES` constant with 63 ordered entries served via `GET /api/v1/languages` (cached 1 h)
- **LanguageSelect component** — searchable dropdown for source/target language settings that updates both the language code and `_name` fields simultaneously

### Changed
- **Settings — source/target language** — fields now use the new `LanguageSelect` dropdown instead of plain text inputs
- **Provider reactive health checks** — status is fetched on-demand only (no background polling); `ProviderManager.update_providers()` does selective enable/disable without full reinit; `providers_hidden` key excluded from provider reinit trigger
- **Provider UI grid** — complete tile-grid redesign: ProviderTile shows status badge, success rate, language count, and credential type; AddProviderModal replaces flat list with searchable cards; ProviderEditModal uses structured config_fields; header shows `N aktiv / M konfiguriert` counts; `+` tile only visible when hidden providers exist
- **CI** — `actions/checkout`, `actions/setup-node`, `actions/setup-python` bumped to v6

---

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
