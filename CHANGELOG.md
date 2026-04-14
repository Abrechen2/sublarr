# Changelog

All notable changes to Sublarr are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.51.6-beta] - 2026-04-14

### Fixed
- **WantedScanner timer leak on settings save** — Every config-UI save was leaking a pair of `threading.Timer` instances because `start_scheduler()` overwrote the timer references without cancelling the previous ones. The old chains kept ticking and produced `Wanted scan already running, skipping` log lines when they eventually fired. `start_scheduler` now cancels the previous timer pair first, and the `_schedule_next_*` helpers also cancel before swapping, so recursive rescheduling stays single-chain.

### Changed
- **Removed 6 unused database indexes** — After two weeks of prod runtime `pg_stat_user_indexes` reported zero scans on six indexes. New migration `h1i2j3k4l5m6` drops them with `DROP INDEX CONCURRENTLY` on PostgreSQL (no write blocking). Removed: `subtitle_hashes.idx_subtitle_hashes_file_path` (100% duplicate of the UNIQUE constraint on the same column), `activity_log.idx_activity_log_event_type`, `activity_log.idx_activity_log_created_at`, `wanted_items.idx_wanted_sonarr_series`, `wanted_items.idx_wanted_radarr_movie`, `subtitle_downloads.idx_subtitle_downloads_path`. Frees ~2 MB of storage and saves index-maintenance cost on every insert/update. `idx_wanted_sonarr_episode` and the trigram GIN indexes on `search_*` tables are kept for existing query paths even though they are currently idle.

## [0.51.5-beta] - 2026-04-14

### Fixed
- **Stream removal after extraction now works end-to-end** — The mkvmerge `--subtitle-tracks` exclusion argument was built as `!3,!4`, which mkvmerge v91+ rejects as an invalid BCP 47 language tag. The correct form is `!3,4` (single `!` at the start of the list). Every subtitle extraction on Cardinal was logging `mkvmerge failed (exit 2)` with an empty reason — subtitles were extracted correctly to `.ass` files but the tracks stayed in the container. Error capture now also falls back to stdout when stderr is empty, because mkvmerge writes hard errors to stdout.
- **Circuit breaker hardening** — Auth and rate-limit errors in provider search methods were caught by generic exception handlers and returned as empty results, preventing the circuit breaker from ever opening. All three layers (download, provider search, coordinator retry loop) now correctly propagate these errors.
- **Orphan scanner false positives** — Episode titles containing dots (e.g. `Mr. Saturday`) were truncated by the language-tag regex, producing false orphan reports. The regex is now anchored to known subtitle extensions (srt/ass/ssa) and accepts modifier suffixes.
- **Wanted-search NULL guard** — `process_wanted_item` no longer crashes with a TypeError when `search_count` is NULL. Items inserted before a later default=0 migration triggered this crash, which in turn caused retry storms that logged identical tracebacks thousands of times at the same millisecond.
- **Unknown API paths return JSON 404** — `/api/v1/*` paths that do not match a registered blueprint now return a proper 404 instead of falling through to the SPA with HTTP 200. Client bugs fail loudly instead of silently.
- **Logging setup is idempotent** — Repeat `create_app()` invocations (tests, reloaders) no longer leak RotatingFileHandler and SocketIOLogHandler instances. Previously each leak multiplied every log record N-fold, producing the same entry at the same millisecond in the log file.
- **Sonarr/Radarr error loop on unconfigured setups** — Instance lists with empty `url` or `api_key` are now dropped at the factory. Previously a client was constructed with empty strings and every scan tick ERROR-logged `Sonarr GET /series failed after 3 attempts`.

### Docs
- **Security reporting** — SECURITY.md now points exclusively to GitHub security advisories; removed the redundant email path.

## [0.51.4-beta] - 2026-04-13

### Fixed
- **Provider errors now fully propagate to circuit breaker** — Auth and rate-limit errors in provider search methods were caught by generic exception handlers and returned as empty results, preventing the circuit breaker from ever opening. All three layers (download, provider search, coordinator retry loop) now correctly propagate these errors.
- **Server rate-limit tracking across threads** — When one search thread receives a 429 from a provider, a shared timestamp is set so all other concurrent threads skip that provider immediately instead of each hitting the same rate limit independently.
- **Timeouts propagated as errors** — Provider timeouts were silently returned as empty results. They now raise ProviderTimeoutError so the circuit breaker counts them as failures.

### Changed
- **Database indexes for subtitle_downloads** — Added indexes on `downloaded_at` and `file_path` columns, eliminating sequential scans on the 7.7M-row table. Batch worker count reduced from 4 to 2 to prevent CPU overload on small containers. Circuit breaker cooldown increased from 60s to 300s.

## [0.51.3-beta] - 2026-04-13

### Fixed
- **Subtitle hash UniqueViolation on concurrent writes** — Replaced check-then-insert with atomic UPSERT (INSERT ... ON CONFLICT DO UPDATE) for the subtitle_hashes table, preventing PendingRollbackError cascades during parallel wanted searches. Includes explicit session rollback in all callers.
- **Circuit breaker not wired into download path** — download_subtitle() now checks allow_request() before each download and records success/failure on the circuit breaker. Applies to all 22+ providers. OpenSubtitles HTTP 406 (quota exhausted) is now raised as ProviderRateLimitError with reset time instead of a generic error.
- **Log viewer entries overlapping** — Replaced fixed 30px row height with dynamic measurement via measureElement, preventing multi-line tracebacks from rendering on top of each other.
- **Status bar missing batch and provider status** — Footer now shows batch extraction/search activity and a throttled provider count with names on hover.

### Tests
- Added 20 integration tests for atomic UPSERT behavior, batch extraction flows, and download manager rollback handling.
- Added 2 StatusBar tests for throttled provider indicator.

## [0.51.2-beta] - 2026-04-12

### Fixed
- **Firefox subtitle rendering** — libass-wasm createTrack crashes in Firefox (ass_read_file returns NULL). Added WebVTT fallback: Firefox now uses native `<track>` elements with ASS→VTT conversion. Chrome/Edge/Safari keep full ASS rendering via SubtitleOctopus.
- **OpenAPI security declarations** — All 286 API routes now have explicit security declarations in the OpenAPI spec. Previously 165 routes appeared public in the spec despite being protected by runtime auth hooks.

### Docs
- **SECURITY.md** — New security policy documenting threat model, 3 pentest rounds (25 findings, all CRITICAL/HIGH resolved), accepted risks, and production security checklist.
- **MIGRATION.md** — New upgrade guide covering beta-to-V1 migration path with version-specific breaking changes and troubleshooting.

### Tests
- **737 new backend tests** — 27 new test files covering routes (standalone, notifications, whisper, webhooks, subtitle processor), services (wanted scanner, video player, cleanup, marketplace, standalone manager, NFO parser, file watcher), translator package (core, manager, jobs, helpers, cache), translation backends (DeepL, Google, LibreTranslate, Ollama, OpenAI), and DB repositories (standalone, hooks, jobs, library, whisper). Added Locust load testing configuration.

## [0.51.1-beta] - 2026-04-12

### Fixed
- **Graceful shutdown** — Background threads (wanted scanner, upgrade scheduler) now stop cleanly on SIGTERM instead of blocking container shutdown for up to 60 seconds.

### Tests
- **Full module coverage achieved** — Added 1,290 new tests across 10 files covering all previously untested modules: forced detection, mediainfo utils, download manager, HTTP session, spell checker, OCR service, retranslation, audio visualizer, OpenAPI spec, translation repository, track routes, and standalone scanner. Backend test suite now at 2,793 passing tests with 100% module coverage.

## [0.51.0-beta] - 2026-04-12

### Added
- **Provider transparency** — The dashboard provider widget now shows real-time status badges: throttled providers display a countdown timer, circuit-breaker-open and auto-disabled providers show their state clearly, and problems sort to the top. The activity queue displays a provider status line during searches (e.g. "5 active · 3 throttled") so users understand why searches are slow instead of seeing a frozen progress bar.

### Fixed
- **Cleanup stats crash** — The cleanup statistics endpoint threw a KeyError because `get_duplicate_groups()` returns `file_size` but `get_disk_stats()` accessed `size`. The key name mismatch caused every `/api/v1/cleanup/stats` request to fail with HTTP 500.

## [0.50.1-beta] - 2026-04-12

### Changed
- **V1 code health: split 10 oversized backend files** — All files exceeding the 800-line project limit have been refactored into focused modules: wanted_scanner_core (1233→627), cleanup routes (1113→928), standalone routes (967→786), profiles routes (964→748), bazarr_migrator (948→576), translator core (926→789), providers init (847→797), subtitles routes (824→785), and api_keys routes (803→796). config.py (812) accepted as declarative exception.
- **Removed 86 completed beta planning documents** — All plan/spec/research/summary files from v0.23–v0.50 deleted; replaced by a single Road to V1 release roadmap spec.

### Fixed
- **6 broken tests repaired** — Remux duration mismatch test updated for widened tolerance (v0.47.7), wanted search dedup collision fixed, CleanupSettings tests aligned with v0.47.3 redesign, SubtitlePresencePills test updated for v0.49.0 pill removal.

## [0.50.0-beta] - 2026-04-11

### Added
- **Settings search (Ctrl+K)** — Spotlight-style modal lets users search all settings pages and individual fields by name or description. Selecting a result navigates to the correct page and highlights the matched field with a 5-second pulsing glow.

### Fixed
- **Duplicate groups crash** — Backend returned `hash`/`path`/`size` keys instead of `content_hash`/`file_path`/`file_size`; the Cleanup page now loads without a TypeError.
- **Settings highlight not firing** — Fixed field matching via `htmlFor` normalisation and a custom-event mechanism for same-page navigation. Added missing `htmlFor` attributes to all Toggle-based FormGroups so every searchable field can be highlighted.
- **Highlight animation invisible** — Replaced broken CSS `@keyframes` (silently ignored by the browser) with JS-driven inline-style transitions, giving a reliable 5-second pulse sequence.

## [0.49.0-beta] - 2026-04-11

### Added
- **Wanted list visual redesign** — Multi-language groups now have a purple left accent border and a darker header row to clearly separate groups. Language tag suffixes (e.g. `[EN]`, `[DE]`) are stripped from titles since the language badge on each sub-row already conveys that information. A status legend showing all six possible states is displayed above the table.

### Fixed
- **"No embedded subtitles" pill hidden when empty** — The "nicht eingebettet" pill and its separator are no longer shown when a video file has no embedded subtitle tracks, reducing visual noise in the Existing column.

## [0.48.0-beta] - 2026-04-11

### Added
- **Wanted: grouped episode rows** — Episodes with multiple target languages now appear as a single row with one language sub-row per language, instead of a separate row for each. The title, S/E number, and "Added" date render once per episode group; the language badge, status, subtitle presence, search count, last-search time, and action buttons appear per language sub-row. Supports any number of target languages (DE + EN + JP etc.).

### Fixed
- **Wanted: search results panel restored** — Clicking a row in the Wanted list now correctly opens the inline search-results expansion panel for that item. The panel was previously disconnected and could never be shown.

## [0.47.7-beta] - 2026-04-11

### Fixed
- **Auto-extract reliability** — Four recurring failures in the embedded subtitle extraction pipeline have been resolved: (1) Duration mismatch false-positives on MKVs with phantom trailing segments are fixed by widening the remux tolerance from ±2 s to max(5 s, 1 % of file duration). (2) Non-UTF-8 bytes in file paths or ffmpeg stderr no longer crash extraction — all subprocess calls now use `errors="replace"`. (3) Race condition where two workers processed the same file concurrently now produces a clear log message instead of a cryptic "expected -1, got 0" error. (4) Default ffmpeg timeout for subtitle extraction raised from 120 s to 300 s, preventing spurious timeouts on large files over NFS.

## [0.47.6-beta] - 2026-04-11

### Fixed
- **Dashboard stats PostgreSQL error** — Fixed a type mismatch where the `upgrade_candidate` column (integer) was compared to a boolean `True`, causing PostgreSQL to throw "operator does not exist: integer = boolean" on every dashboard load. Query now uses `== 1` to match the integer column type.

## [0.47.5-beta] - 2026-04-10

### Fixed
- **Auto-extract item_id is None in batch scan** — When the wanted scanner runs in batch mode, `_commit()` is a no-op and SQLAlchemy never assigns the autoincrement PK until an explicit flush. Added `session.flush()` after `session.add()` so `item.id` is populated before being returned, eliminating the "Wanted item None not found" errors and cascading logging crashes during startup scans.

## [0.47.4-beta] - 2026-04-10

### Fixed
- **Wanted search crashes on startup** — ThreadPoolExecutor worker threads now each receive their own Flask application context. Previously every parallel item search raised "Working outside of application context", causing the startup search to fail for all items silently.
- **Language profiles blocked by duplicate Alembic revision** — A duplicate revision ID (b2c3d4e5f6a7) caused all pending migrations to be skipped on production, which prevented creation of language profiles. The hi_preference migration was renumbered, a merge migration added, and the chain restored.

## [0.47.3-beta] - 2026-04-10

### Changed
- **Cleanup page completely overhauled** — Instead of a rule manager with sidebar, modal, and arbitrarily named rules, there are now 5 fixed operations (Language Filter, Format Upgrade, Orphaned Files, Orphaned DB Entries, Old Backups) as collapsible cards with toggle, inline configuration, and schedule. No more "Create new rule" required.

### Fixed
- **Preview now shows concrete file examples** — The dry run returns up to 20 example files with path, size, and deletion reason (e.g. `lang:ja`), instead of just counts.
- **Cleanup UI fixes** — Fixed dropdown clipping in the language filter, disk widget more compact, layout and save feedback reworked.

## [0.47.2-beta] - 2026-04-10

### Fixed
- **FormGroup dividers in light mode** — The dividers between settings fields used a hardcoded dark color (`rgba(42,46,56,0.5)`) instead of `var(--border)` and were incorrectly colored in light mode.
- **Wanted page: double scrollbar** — `height: calc(100vh - 40px)` ignored the main padding (24 + 60 px), which pushed the table 44 px past the visible area. Corrected to `calc(100vh - 108px)`.
- **Settings nav: insufficient top spacing** — The sticky sidebar started with only 4 px spacing from the top edge. Increased to 16 px.
- **PillTabs: invisible in light mode** — The tab container had no border and visually blended with the page background; border `var(--border)` added.
- **CleanupTab: section content without indentation** — The content of collapsible sections had no `pt-3`, causing it to start directly below the toggle button. Top padding added.
- **Logs page: inconsistent page header** — Raw `<h1>` heading replaced by the canonical `PageHeader` component; height calculation adjusted from `7rem` to `8rem`.

## [0.47.1-beta] - 2026-04-10

### Fixed
- **Wanted scheduler logging** — `scan_all()` now correctly logs `EVENT_SCAN` (was silent before); `search_all()` logs `EVENT_SEARCH` instead of `EVENT_SCAN`, preventing search results from appearing as scan entries in the activity log. Search now also runs on startup by default.
- **Dashboard provider health** — Provider success rate was treated as a 0–100 integer but the API returns a 0–1 decimal; dots and percentages now display correctly.
- **Trash page** — Complete redesign: stats bar with total sizes and retention info, expiry badges color-coded by urgency, delete button for MKV backups, all strings via i18n.
- **Settings navigation** — Removed the tile overview page; settings now open directly on General.
- **Cleanup rules** — Fixed 5 API contract mismatches: `getCleanupRules` now handles `{rules:[…]}` wrapper; `deleteDuplicates` sends correct key `groups`; history normalizes `items→entries`; preview sends `{action:"dedup"}` with correct response mapping; scan status normalizes `running:bool→status:string`. The `old_backups` manual run now actually deletes files instead of just listing them.
- **Cleanup modal** — Redesigned rule-creation dialog with icon button cards, backdrop-close, Enter-to-submit, and X close button.

## [0.47.0-beta] - 2026-04-09

### Added
- **Movie Subtitle Management** — Existing subtitle sidecar files are now displayed on the Movie detail page with a full actions menu (HI removal, common fixes, timing offset).
- **Timing Offset Tool** — The subtitle actions menu now includes a "Shift Timing" option that applies a millisecond offset to any sidecar subtitle file directly from the UI.
- **Forced Scoring per Language Profile** — Language profiles can now specify include / prefer / exclude / only for forced subtitles, wiring directly into the scoring pipeline.
- **Cutoff Language in Profile Editor** — Language profiles now expose the cutoff_language field, allowing per-profile cutoff configuration.
- **74 Language Options** — The language selector was expanded from 20 to 74 supported languages.
- **HI Preference in Profiles** — Language profiles now carry a hearing-impaired preference (prefer / avoid / only) that feeds directly into subtitle scoring.

### Fixed
- **Toggle Revert Bug** — Settings toggles (AniDB, Standalone, Remux) were reverting to OFF immediately after click because of a `=== 'true'` string comparison against boolean values returned by the backend. All affected tabs now use `boolVal()`.
- **Optimistic Toggle Updates** — Config toggles now update the cache immediately on click, so the UI feels instant instead of waiting for the GET refetch.
- **HI/Forced Preference Migration** — Source/target language and HI/forced preference settings were moved from the General page to the Subtitles page where they belong.
- **Advanced Settings Label** — The collapsible advanced section now shows "Advanced Settings" instead of "0 advanced settings" when no count is provided.
- **German locale encoding** — 90 broken UTF-8 sequences (Ã¤, Ãœ, ÃŸ, etc.) in de/common.json were corrected to proper umlauts (ä, Ü, ß, …).

### Changed
- **Settings Information Architecture** — Settings fields were consolidated into their correct sub-pages (ffmpeg_timeout moved to Automation → Search & Scan; format tools section removed).
- **Language Profile Editor** — Translation fields removed from the profile editor; language options deduplicated and expanded.

## [0.46.0-beta] - 2026-04-06

### Added
- **Persistent settings navigation** — All settings pages now have a permanent sidebar navigation (SettingsNav + SettingsShell) that remains visible on every sub-page.

### Fixed
- **Language profiles prominently placed** — Language Profiles are now the first section on the Subtitles page and are immediately visible instead of deeply hidden in a collapsed area.
- **Language profile form fully localized** — All UI strings in the Language Profiles form are now properly translated for both supported languages (Save, Cancel, Target Languages, Profile Name, etc.).
- **Batch-Extract no longer removes subtitles without sidecar** — If extraction produces an empty sidecar file, the embedded subtitle stream is not removed from the MKV. Prevents data loss on failed extraction.

## [0.45.0-beta] - 2026-04-06

### Added
- **Settings redesign — advanced fields system** — FormGroup now supports
  an `advanced` prop that renders an amber "Advanced" badge and tooltip
  instead of an inline hint, reducing visual clutter for power-user options.
  SettingsSection displays a collapsible "N advanced settings" toggle
  when advanced fields are present.
- **LanguagePillSelector component** — Multi-language selection in Language
  Profiles now uses interactive pills with a dropdown, replacing free-text
  comma-separated input. Includes full LANGUAGE_OPTIONS list (20 languages).
- **Dedicated settings sub-pages** — Five settings areas extracted into their
  own routes for cleaner navigation: Post-Processing (`/automation/post-processing`),
  Hooks & Webhooks (`/system/hooks`), Metadata/AniDB (`/connections/metadata`),
  Stream Management/Remux (`/subtitles/stream-management`), and Transcription/Whisper
  (`/providers/transcription`). Old `/settings/hooks` and `/settings/webhooks`
  routes redirect automatically.
- **Settings i18n — hint text and advanced keys** — All settings fields now
  have translated hint/description text. Advanced toggle labels and section
  titles are fully localised in EN and DE.

### Fixed
- **Unused import removed** — Stale `Workflow` import cleaned up from
  AutomationSettings after the Post-Processing extraction.

## [0.44.0-beta] - 2026-04-06

### Added
- **Unified History Tab** — History and activity log merged into a single tab. Sub-filters (Downloads / Extractions / Deletions / Scans) switch between views.
- **Readable subtitle pills in the Wanted section** — Pills now show clear text (e.g. "DE missing", "DE ASS ⬇") instead of cryptic symbols, with explanatory tooltips on hover.

### Fixed
- **Duplicate presets button** — The preset button was rendered twice in the Wanted filter area; one was removed.
- **Filter dropdown transparent** — Popover for "Add filter" and "Presets" had no visible background and did not close when clicking outside; both fixed.
- **Filter field names** — Field labels in the filter dropdown (Status, Type, Subtitle Type, Title) are now correctly translated.
- **Activity tab i18n** — Duplicate JSON key `history` in activity.json was overwriting the filter labels; merged. Second filter bar in ActivityLogTab suppressed when used from UnifiedHistoryTab.
- **Wanted page subtitle** — Page description is now correctly localized via i18n.

## [0.43.0-beta] - 2026-04-06

### Added
- **Full UI localization (i18n)** — All visible strings in the interface have been migrated to the react-i18next system. The language can now be switched between German and English via settings. Covers all pages (Library, Wanted, History, Logs, Plugins, Setup, Settings) and components (BatchActionBar, SpellCheckPanel, SubtitleEditor, Charts, Standalone mode status, Cleanup rules, and many more).

## [0.42.0-beta] - 2026-04-06

### Added
- **Update indicator** — Pulsing amber dot on the Settings icon and a chip (↑ vX.Y.Z) next to the version number in the sidebar when a newer release is available on GitHub. The version number in the StatusBar becomes clickable and opens a popover with a link to GitHub Releases.
- **Logs page** — New route `/logs` with its own sidebar icon (ScrollText) for direct access to backend logs.
- **Full i18n localization** — All Settings pages (General, Automation, Scoring, Backup, AniDB, Cache), the Trash page, and other UI pages (Library, Plugins, Setup, Statistics, etc.) are now fully translatable. Fallback language is German.

## [0.41.8-beta] - 2026-04-05

### Fixed
- **Wanted items removed after download** — Wanted items are now deleted from the database immediately after a subtitle is successfully downloaded (previously they accumulated with `status = "found"` and were never removed). 71 stale entries cleaned up on deploy. The scanner will not re-add items that already have a subtitle file on disk.
- **Dashboard metrics populated** — The total subtitles, average score, and low score stats showed `—` because the `/stats` endpoint never returned these values. Now returns `total_subtitles` (count from `subtitle_downloads`), `average_score` (avg score), and `low_score_count` (upgrade candidates).
- **Activity page: Download history restored** — The `Downloads` tab was showing the empty `ActivityLogTab` (new `activity_log` table) instead of `HistoryPage` (subtitle_downloads). Restored correctly; the `ActivityLogTab` is now its own separate `Activity Log` tab.

## [0.41.6-beta] - 2026-04-05

### Fixed
- **Alembic duplicate revision** — `make_glossary_series_id_nullable` and `add_activity_log` both carried revision ID `e4f5a6b7c8d9`. Renamed `make_glossary_series_id_nullable` to `f2a3b4c5d6e7` and updated the four dependent migrations (`add_fansub_preferences`, `add_chapter_cache`, `add_glossary_metadata`, `add_datetime_to_health_results`). Container startup no longer fails with "Revision is present more than once".

## [0.41.0-beta] - 2026-04-04

### Added
- **Cleanup Rules page** — Dedicated first-class Settings page (`/settings/cleanup`) replacing the old CleanupTab. Rule list sidebar + detail view with 4 rule types: Language Filter (delete sidecars in non-allowed languages), Format Upgrade (delete SRT when ASS exists), Orphan Files (delete subtitle sidecars with no matching video), and DB Cleanup (remove DB entries whose subtitle file no longer exists on disk). Each rule has a name, enabled toggle, and schedule (manual / daily / weekly / after scan). Dry-run preview before executing. `.nfo` files are never touched.
- **`schedule` column on `cleanup_rules`** — New `schedule` column (manual/daily/weekly/after_scan) added via Alembic migration `f0e1d2c3b4a5`; existing rules default to `manual`.
- **Rule executors** — `backend/services/cleanup_executors.py` with pure executor functions for all 4 rule types, supporting `dry_run` mode for preview.
- **`POST /api/v1/cleanup/rules/{id}/preview`** — New dry-run endpoint returning files that would be deleted with estimated MB freed.

## [0.40.0-beta] - 2026-04-04

### Added
- **Subtitle Presence Pills** — The `Vorhanden` column on the Wanted page is replaced by a pill-based `Untertitel` column. A left pill shows the target-language subtitle status (`DE ✗` / `DE SRT ↑` / `DE ↓ ASS`); a right group shows all other embedded subtitle streams in the video file (`EN ↓ ASS`, `+N ▾` overflow dropdown sorted by configured source language). The `↑` upgrade arrow only appears when the upgrade candidate flag is set.
- **`embedded_languages` field** — New `embedded_languages` TEXT column on `wanted_items` (Alembic migration `c6d7e8f9a0b1`). The wanted scanner now probes and stores all non-target embedded subtitle streams at both movie and episode scan sites.
- **`get_all_subtitle_streams()`** — New utility in `ass_utils.py` returning all embedded subtitle streams as `[{lang, format}]`, with optional target-language exclusion and deduplication.

### Changed
- **Wanted column renamed** — i18n key `existing_col` changed from `"Vorhanden"` to `"Untertitel"` (DE) and `"Existing"` to `"Subtitles"` (EN).
- **`upsert_wanted_item` partial-update safety** — `embedded_languages` is no longer overwritten to `[]` by call sites that do not supply the field (episodes route, standalone scanner); existing data is preserved on partial updates.

## [0.39.0-beta] - 2026-04-03

### Added
- **Post-Processing UI** — Toggle and command textarea for `post_processing_enabled` / `post_download_command` added to Settings → Automation → Processing Pipeline; 7 substitution variables supported (`{subtitle_path}`, `{language}`, `{provider}`, `{score}`, `{media_type}`, etc.)
- **Rate limiting on critical routes** — `POST /api/v1/config/import` (5/min), `GET /api/v1/config/export` (30/min), `POST /api/v1/auth/setup` (5/min), `POST /api/v1/auth/change-password` (5/min + 20/hr), `POST /api/v1/providers/search` (20/min)
- **Provider cache metrics** — `sublarr_provider_cache_hits_total` and `sublarr_provider_cache_misses_total` Prometheus counters with `layer=fast/db` label; now increment correctly from two-tier cache path
- **DB performance indexes** — Composite index `(status, retry_after)` on `wanted_items` for scan-loop filter; `language` index on `subtitle_downloads` for provider history queries (Alembic migration `b5c6d7e8f9a0`)
- **Configurable Gestdown retry delay** — `gestdown_retry_delay_s` config field (default `1.0`, env `SUBLARR_GESTDOWN_RETRY_DELAY_S`); replaces hardcoded `time.sleep(1)` on HTTP 423; set to `0` to disable for batch scans
- **OpenAPI docstrings** — All 6 endpoints in `routes/auth_ui.py` and `stream_media()` in `routes/media.py` now have full OpenAPI YAML docstrings with status codes and schemas

### Changed
- **`providers/__init__.py` refactored** — 1404 → 843 LOC; search coordination extracted to `providers/search_coordinator.py` (`SearchCoordinatorMixin`)
- **`wanted_search/process.py` refactored** — 1067 → 695 LOC; post-download logic extracted to `wanted_search/post_processor.py`; score selection to `wanted_search/score_selector.py`
- **Frontend splits** — `ConnectionsSettings.tsx` (938 → 43 LOC), `EventsTab.tsx` (903 → 12 LOC), `api/system.ts` (888 → 20 LOC); all split into domain sub-components with barrel re-exports

### Tests
- **+58 new backend tests** — Route tests for `config`, `mediaservers`, `media`, `blacklist`, `series_audio`; unit tests for `archive_utils` (ZIP bomb/slip) and `anidb_sync` (token parser, XML processor, 409 guard)
- **+6 frontend tests** — `Library.test.tsx` (series/movies tab, view toggle) and `SeriesDetail.test.tsx` (title, season, episode render)
- **`test_security.py` split** — 1159-LOC file split into 4 domain files: `test_security_paths.py`, `test_security_download.py`, `test_security_prompt.py`, `test_security_auth.py`

### Docs
- **Wiki: Post-Processing** — New page `user-guide/post-processing.md` covering variables, examples, behavior limits, troubleshooting
- **Wiki: Circuit Breaker** — New page `user-guide/advanced/circuit-breaker.md` covering state machine, persistence, Prometheus metrics, manual reset
- **Wiki: Ollama Chat API (V9+)** — `user-guide/settings/translation.md` extended with Chat vs. Generate comparison, system prompt / `{series_context}` guide, per-model recommendations

## [0.38.1-beta] - 2026-04-03

### Tests
- **HTTP route tests** — 6 new test files covering `routes/subtitles.py`, `routes/library/`, `routes/wanted/`, `routes/providers.py`, `routes/translate/`, and `bazarr_migrator.py` (Phase 3b test coverage)
- **2 bug fixes via TDD** — `WantedRepository` init call fixed in `routes/wanted/search.py`; `sqlite3.Row.get()` replaced with `dict()` in `bazarr_migrator.py`
- **Flaky time test fixed** — `WantedFailureReason.test.tsx` uses `vi.useFakeTimers()` + frozen timestamp to prevent minute-boundary failures

### Changed
- **Phase 5 refactoring complete** — `wanted_scanner.py` → facade + `wanted_scanner_core.py`; `config.py` → `config_language_data.py` + `config_instances.py` + `config_utils.py`; `AdvancedTab.tsx` → 4 sub-tab components; `Wanted.tsx` → toolbar/filter/row components; `LegacySettings.tsx` reduced to 682 LOC

## [0.38.0-beta] - 2026-04-03

### Security
- **P1 — Provider domain allowlist** — `validate_download_url()` added to `security_utils.py`; all 6 provider download methods now validate URLs against a per-provider domain allowlist before fetching; blocks SSRF via compromised provider responses
- **P2 — Filename sanitization** — `werkzeug.secure_filename()` applied to all provider-supplied filenames before they reach `os.path.splitext` or disk writes; neutralizes path traversal attacks
- **P3 — Prompt injection guard** — subtitle lines and glossary entries are sanitized before LLM prompt construction in `translation/llm_utils.py`; embedded newlines escaped, oversized terms rejected
- **P4 — Magic-byte validation** — downloaded subtitle content validated against expected format signatures (SRT/ASS/VTT); binary payloads rejected before storage
- **P5 — Streaming size cap** — all provider downloads capped at 50 MB via streaming download helper; replaces unbounded `.content` reads
- **F-05 — Webhook signature warning** — `auth.py` now logs a warning when a Sonarr/Radarr webhook arrives without `X-Signature` or `X-Bazarr-Signature` header

### Added
- **Language profile filters API** — `must_contain`, `cutoff`, and `audio_exclude` fields now fully exposed via `GET/PUT /api/v1/language-profiles/:id`; repository serializer and update allowlist updated
- **Video codec scoring** — `video_codec` weight (default 2) added to scoring defaults; `apply_video_codec_bonus()` helper matches codec strings from media metadata
- **Ollama Chat API (V9)** — `use_chat_api` flag in translation config enables Ollama `/api/chat` endpoint alongside legacy `/api/generate`; `series_context` injected as system message for improved translation coherence
- **Circuit breaker state persistence** — breaker open/closed state and failure counters survive restarts via new `circuit_breaker_state` DB table + Alembic migration
- **`@handle_api_error` decorator** — `error_utils.py` provides a reusable decorator for route error handling; applied to cleanup route handlers

### Changed
- **`providers/__init__.py` split** — 1642-line file extracted into `providers/format_validator.py` (magic-byte validation) and `providers/download_manager.py` (streaming download + size cap); all imports backwards-compatible
- **`services/cleanup_scanner.py`** — cleanup business logic extracted from `routes/cleanup.py` (1016 → <400 LOC)
- **`services/standalone_manager.py`** — standalone auto-mode logic extracted from `routes/standalone.py`
- **`frontend/src/api/client.ts` split** — 2151-line file split into 9 domain modules (`core`, `library`, `providers`, `settings`, `system`, `translation`, `wanted`, `health`); backwards-compat re-exports maintained
- **`frontend/src/lib/types.ts` split** — 1301-line file split into 7 domain type files under `frontend/src/types/`; backwards-compat re-exports maintained
- **ROADMAP.md** — updated to reflect v0.37.3 current state; v0.29–v0.37 marked done; v0.38–v0.40 roadmap added
- **`datetime.utcnow()` removed** — all 10 deprecated calls replaced with `datetime.now(UTC)` across `whisper/queue.py`, `nfo_export.py`, and `routes/system/logs.py`

### Removed
- **`providers/whisper_subgen.py`** — dead provider file deleted (replaced by Whisper backend system in v0.35)

### Tests
- **+147 backend tests** — new test files for `routes/cleanup`, `routes/api_keys`, `routes/profiles`, `routes/notifications`, and `whisper/queue`
- **+72 security tests** — `TestValidateDownloadUrl`, `TestFilenameSanitization`, `TestPromptInjectionGuard`, `TestMagicByteValidation`, `TestStreamingCap` appended to `test_security.py`
- **Subtitle health timestamps** — `subtitle_health_results.checked_at` migrated from TEXT to `DateTime(timezone=True)`; in-memory scheduler state uses datetime objects throughout

---

## [0.37.3-beta] - 2026-04-01

### Changed
- **Activity navigation restructure** — "Wanted" promoted to top-level sidebar nav item (alongside Dashboard, Library, Settings); Activity reduced from 5 tabs to 4 clean tabs: Queue, Translations, History, Blacklist
- **Queue tab** — now shows only background batch operations (Wanted Batch Search, Batch Probe, Scanner) with an empty state when idle; translation jobs moved to dedicated Translations tab
- **Translations tab** (new) — shows active and queued translation jobs with live polling; replaces the old "In Progress" tab
- **Badge indicator** — moved from Activity nav item to Wanted nav item (shows count of items still needing subtitles); Translations tab shows badge for active + queued job count

### Removed
- **"Needs Attention" tab** — redundant with the Wanted page (was a filtered view of the same data)
- **"In Progress" tab** — consolidated into the new Translations tab

---

## [0.37.2-beta] - 2026-03-31

### Added
- **AniDB title dump resolver (Tier 4)** — offline `anime-titles.xml.gz` lookup (91 k+ entries, cached 36 h) resolves AniDB ID for standalone anime items even when TVDB/AniList IDs are unknown; enables AnimeTosho to find subtitles for series like "Date A Live" where no external ID is stored

### Fixed
- **AnimeTosho provider** — rewritten with correct two-step API flow (`?show=torrent&id=` to get subtitle attachment list); the old implementation read `files` from the search feed which is no longer included in the AnimeTosho API; result: 72 subtitle results for Date A Live S01E01, 10 for 86: Eighty Six S01E04 (was 0 for both)
- **Provider cache key** — now includes `anidb_id` so a freshly resolved AniDB ID triggers a new provider search instead of returning a stale cache entry
- **Provider search** — fixed occasional hang when a provider thread exceeded its timeout; `ThreadPoolExecutor` is now shut down with `cancel_futures=True` so pending threads do not block the Flask response
- **Vite 8 blank page** — `BUNDLED_DEV` environment variable was not being replaced at build time; switched `manualChunks` from object to function form for rolldown/Vite 8 compatibility
- **Alembic migrations on PostgreSQL** — `env.py` now uses `engine.begin()` to wrap all migration DDL in an explicit transaction; `ALTER COLUMN` for `DateTime` columns now emits `USING` cast clause on PostgreSQL

---

## [0.37.0-beta] - 2026-03-31

### BREAKING CHANGE — Database Migration Required

**All timestamp columns have been migrated from plain TEXT to `DateTime(timezone=True)`.**
The Alembic migration `b0c1d2e3f4a5` reformats stored timestamps from ISO 8601 (`2024-01-15T10:30:00+00:00`) to SQLAlchemy's SQLite format (`2024-01-15 10:30:00`). This runs automatically on startup (`flask db upgrade`). **No manual action required for Docker deployments** — the migration is applied automatically.

Use `scripts/check_datetime_migration.py --db /config/sublarr.db --mode before/after` to verify migration integrity.

### Added
- **ConfirmModal component** — replaces all `window.confirm()` calls with an accessible, styled modal dialog
- **StatisticsRepository** — extracted all statistics queries from route handlers into a dedicated repository
- **`services/retranslation.py`** — business logic for item re-translation extracted from route handlers
- **`scripts/check_datetime_migration.py`** — standalone pre/post migration DB consistency checker (70 columns, 29 tables, row-count snapshot comparison)
- **`useDebounce` hook** — extracted reusable debounce hook into `frontend/src/hooks/useDebounce.ts`
- **`configUtils.ts`** — shared frontend config helpers extracted from settings pages
- **`settingsShared.ts`** — consolidated duplicate `inputStyle` and shared settings UI constants

### Changed
- **TranslationTab refactor** — split 1989-line `TranslationTab.tsx` into 8 focused sub-files under `pages/Settings/translation/` (`TranslationBackendsTab`, `BackendCard`, `PromptPresetsTab`, `GlobalGlossaryPanel`, `TranslationQualitySection`, `TranslationMemorySection`, `OllamaPullSection`, `TemplatePickerModal`)
- **SeriesDetail performance** — episode wanted-items now filtered server-side by `series_id`; eliminates the previous 9999-item full-list fetch
- **`wanted_scanner.py`** moved to `services/wanted_scanner.py` for consistent service-layer placement
- **Session timeout** — now enforced at 8 h by default (was Flask's 31-day default); configurable via `session_timeout_minutes`

### Fixed
- **Security — command injection** — replaced `subprocess(shell=True)` with `shlex.split()` in all subprocess calls
- **Security — IP allowlist** — `allowed_ip_ranges` setting now enforced in `before_request` hook for all non-exempt routes
- **Security — SSRF** — `validate_service_url()` now applied to plugin install URLs and plugin registry fetch
- **Security — webhook auth** — requests are now rejected immediately when no API key is configured
- **Security — path traversal** — `is_safe_path()` added to OCR batch-extract endpoint; corrected reversed argument order in `cleanup_sidecars`
- **Security — health endpoint** — returns HTTP 503 when required services are down (was always 200)
- **`subtitle_processor` route** — removed erroneous `.isoformat()` call when writing to `updated_at` DateTime column
- **Silent error suppression** — replaced bare `except Exception: pass` blocks with `logger.warning()`/`logger.debug()` throughout backend
- **Alembic revision conflict** — resolved duplicate revision ID `a1b2c3d4e5f6`

---

## [0.36.4-beta] - 2026-03-30

### Fixed
- **Health status — Ollama no longer critical** — removed Ollama connectivity from the overall health flag; Ollama is an optional translation backend and its unavailability only affects translation, not core subtitle management; the status bar now correctly shows Online when Sublarr itself is reachable

---

## [0.36.3-beta] - 2026-03-29

### Fixed
- **Preview Player — Firefox subtitle crash (definitive fix)** — replaced `createTrack("/sub.ass")` with `createTrackMem(content, length)` in the libass-wasm worker's `onRuntimeInitialized`; bypasses `ass_read_file()` (which returns NULL in Firefox even with valid WASM FS content) by passing the placeholder ASS directly in memory via `ass_new_track` + `ass_process_data`; real subtitle continues to load post-init via `setTrackByUrl()`

## [0.36.2-beta] - 2026-03-29

### Fixed
- **Preview Player — Firefox subtitle crash** — fixed `ass_read_file` returning NULL in the libass-wasm worker (Firefox); the worker's `onRuntimeInitialized` always calls `createTrack("/sub.ass")` — now initialised with a valid placeholder ASS so the init-time call succeeds; real subtitle is loaded post-init via `setTrackByUrl()` through the worker's message buffer; also fixes CSP `wasm-unsafe-eval` and fallback font (`default.woff2` via `fonts-liberation` in Docker)

## [0.36.1-beta] - 2026-03-29

### Fixed
- **Preview Player — subtitle rendering** — subtitles now render correctly in the preview player; fixed canvas overlay positioning (libass canvasParent inserted inside relative wrapper), worker auth (subContent instead of unauthenticated subUrl), and CJS constructor interop for libass-wasm
- **Preview Player — subtitle toggle latency** — eliminated 10–20 s reappearance delay when toggling subtitles off/on; worker is now kept alive across track changes and reuses `setTrack()`/`freeTrack()` instead of a full WASM worker restart

## [0.36.0-beta] - 2026-03-29

### Added
- **Scoring — video_codec weight** — x264/x265/AV1 codec match adds +2 points to episode and movie scores (Bazarr parity)
- **Language Profiles — mustContain / mustNotContain** — AND-logic filter: only accept subtitles matching ALL mustContain terms; any mustNotContain term rejects (Bazarr parity); new DB columns on `language_profiles`
- **Language Profiles — cutoff** — stop searching for a language once a subtitle is already present on disk
- **Language Profiles — audioExclude** — skip downloading a subtitle if the audio track is already in the target language
- **Provider Infrastructure — CircuitBreaker persistence** — CB OPEN state written to `ProviderStats.disabled_until`; survives application restarts; `is_open` property added
- **Provider Infrastructure — rate-limit throttle** — configurable extended throttle on `ProviderRateLimitError` via `provider_rate_limit_throttle_minutes`
- **Download Quality — upgrade chain tracking** — `upgraded_from_id` foreign key on `subtitle_downloads` records which subtitle was replaced; enables full upgrade audit trail
- **Download Quality — post-download command** — `post_download_command` config executes an arbitrary shell command after each successful download; supports `{subtitle_path}`, `{language}`, `{provider}`, `{score}` variable substitution
- **Sync — manual alass endpoint** — `POST /api/v1/sync/alass` triggers alass subtitle synchronisation on demand

### Added
- **Standalone Mode — Auto-activation** — `is_standalone_mode()` helper auto-activates standalone mode when no *arr is configured; `StandaloneStatus` extended with `arr_configured` and `auto_activated` fields
- **Connections — Standalone scan button** — manual scan button added to the Standalone section in Connection Settings

### Changed
- **Settings — Connections** — removed central API Keys section; API keys are now managed inline within each connection's own settings panel
- **Translation — Beta marking** — Translation card on Settings overview now shows "BETA" pill; Translation Settings page shows a warning banner

### Fixed
- **Language Profiles — mustContain AND logic** — corrected to require ALL terms instead of ANY term (Bazarr parity fix)
- **Post-download hook** — guard added via `getattr(self, 'settings', None)` to prevent crash when settings are not available
- **OpenSubtitles — Anime season-1 collapse** — fallback search now maps S02+ episodes to Season 1 with the original episode number (not absolute episode); `moviehash` stripped from fallback params to allow title-based lookup
- **UI — WebSocket events** — corrected event names (`upgrade_complete`, `wanted_scan_complete`); added `wanted_item_searched` handler
- **UI — Wanted page** — per-row independent loading state (shared `isPending` was spinning all rows simultaneously)
- **UI — Episode Search Panel** — null-safety guards on `target_results` and `source_results`

---

## [0.35.0-beta] - 2026-03-22

### Added
- **Movie Detail — Subtitle Management** — wanted items section below file info shows missing subtitles per language; inline Search / Skip / Re-enable buttons; wired to `/wanted?movie_id=` filter
- **Backend — `/wanted` movie filter** — new `?movie_id=` query param filters wanted items by `standalone_movie_id`; enables movie detail subtitle management without loading the full wanted list

### Changed
- **Series Detail — Episode Grid** — restored full feature set: per-row checkboxes, SubBadge per subtitle language (teal = ASS optimal, purple = SRT upgradeable, orange = missing), audio-track badges, sidecar subtitle actions (delete, download, NFO export, subtitle menu, health badge, preview, edit), batch toolbar (Search / Extract / Translate / Cleanup), Skip / Accept inline actions wired to `useUpdateWantedStatus`
- **Dashboard — AutomationBanner** — subtitle line now shows live "Last completed: X ago" derived from `scannerStatus.last_scan_at`; replaces hardcoded placeholder text
- **Library** — fixed `anime_only=False` filter that was hiding non-anime content; all library entries now visible regardless of type

### Fixed
- **Settings — API Keys** — removed duplicate TMDB and TVDB entries; fixed `updateApiKey` request body format that was causing 400 errors on save
- **Security — CSP / Permissions-Policy** — `Content-Security-Policy` and `Permissions-Policy` response headers added to all responses (F-23)
- **Security — Webhook SSRF** — `validate_service_url()` applied to webhook create and update endpoints; blocks dangerous URL schemes (F-21)
- **Security — Auth warning** — startup `SECURITY WARNING` log emitted when both API key and UI auth are disabled, alerting operators to the open-API exposure (F-17/F-18 root cause)

---

## [0.33.0-beta] - 2026-03-20

### Added
- **Providers — Subf2m** — new subtitle provider supporting 60+ languages via Subf2m.co
- **Providers — Subsource** — new subtitle provider (multi-language, movie & TV)
- **Providers — YIFY Subtitles** — movie-only provider using IMDB-based JSON API
- **Providers — Zimuku** — Chinese subtitle provider (simplified & traditional)
- **Providers — BetaSeries** — French subtitle provider for TV series
- **Providers — Titlovi** — Balkan subtitle provider (Croatian, Serbian, Bosnian, Slovenian, Macedonian)
- **Providers — EmbeddedSubtitles** — integrates embedded subtitle tracks from media files directly into the search and scoring pipeline
- **Subtitle Processing Pipeline** — post-download processing hook; 18 fix functions (HI removal, common formatting corrections, OCR artifact cleanup); configurable per-series via series detail panel
- **Settings — Processing Pipeline** — new settings section for configuring post-processing behavior (fix modules, interjection list)
- **Series Detail — Batch Process** — button to run post-processing on all existing subtitles for a series; progress log modal

### Changed
- **Settings — Fansub / Release Groups** — global release-group preference fields moved from Wanted tab to Scoring tab where they belong conceptually
- **Series Detail — Fansub Preferences** — replaced the always-visible card with a compact toolbar button; active overrides highlighted in accent color; per-series settings in a modal dialog

### Fixed
- **Security — SSRF** — URL validation in `PUT /api/v1/config` now covers dot-notation extension keys (e.g. `whisper.subgen.url`) that previously bypassed the `_URL_FIELDS` check
- **Security — SocketIO log sanitization** — `SocketIOLogHandler` now strips DB-internal error details (table names, column names, query fragments) before emitting to WebSocket clients
- **Backend — startup crash** — `validate_service_url` was imported in `routes/config.py` but never implemented; added full SSRF-safe implementation

---

## [0.32.0-beta] - 2026-03-19

### Changed
- **Settings — Navigation** — Restructured from 7 groups / 23 tabs to 5 logical groups (Connections, Languages & Subtitles, Providers, Automation, System); no tabs removed
- **Providers — Priority** — Replaced move-up/down buttons in edit modal with drag & drop handles on provider tiles

### Added
- **Score Breakdown** — Hover tooltip on score badges in search results shows per-component point breakdown (series title, season, episode, format bonus, provider modifier, etc.)
- **Wanted — Failure Details** — Failed items now show inline error reason, attempt count, and next retry countdown
- **Wanted — Batch Progress** — Progress bar with found/failed counters during "Search All" operation
- **Dashboard — Automation Widget** — New widget showing automation status (enabled/disabled), today's found/failed subtitle stats, last/next run times, and Run Now button
- **Onboarding — Language Step** — New wizard step to configure target and source language during first-time setup
- **Onboarding — Automation Step** — New wizard step to configure automatic search interval and subtitle upgrade behavior

---

## [0.31.0-beta] — 2026-03-19

### Changed
- **Backend — Test Foundation** — added 29 new tests covering `WantedSearchService`, `ProviderManager`, and quality-validation logic; total suite now 736 tests at 47.76% coverage
- **Backend — Type Safety + Lint** — resolved all `ruff` errors and `mypy` type warnings across the entire backend; no new ignores added
- **Backend — File Splits** — 8 oversized files (800–2921 lines) decomposed into focused packages: `routes/hooks/`, `routes/library/`, `routes/wanted/`, `routes/translate/`, `routes/system/`, `routes/tools/`; service packages `translator/` and `wanted_search/`; shared batch state extracted to `routes/batch_state.py`
- **Backend — Architecture** — `providers/registry.py` with `PROVIDER_METADATA` dict replaces three class-level dicts; nested `Settings` views (`GeneralSettings`, `TranslationSettings`, `ProviderSettings`, `MediaServerSettings`, `ScanningSettings`) with read-only delegation; singleton lifecycle via `get_scanner()`/`get_provider_manager()` checking `app.extensions`
- **Frontend — SyncControls split** — `SyncControls.tsx` decomposed into `OffsetTab`, `SpeedTab`, `FramerateTab`, `ChapterTab`, `StandardActions`, `SyncTabBar`; orchestrator retains all state and handlers
- **Frontend — useApi split** — `useApi.ts` decomposed into six domain files: `useLibraryApi`, `useWantedApi`, `useTranslationApi`, `useProvidersApi`, `useIntegrationApi`, `useSystemApi`; barrel re-exports all public hooks
- **Frontend — Error Boundaries** — `ErrorBoundary` component wraps Library, Wanted, and Settings routes; runtime errors are caught per-route instead of crashing the full app

### Fixed
- **Backend — monkeypatch targets** — updated `test_wanted_search_reliability.py` patch paths to point to the submodule where each function is called after the Phase 3 package split
- **Frontend — verbatimModuleSyntax** — added `import type` to all interface-only imports in `VideoPlayer.tsx`, `PlayerModal.tsx`, `SubtitleTrackSelector.tsx` to satisfy `verbatimModuleSyntax: true` in tsconfig
- **Frontend — TypeScript strict errors** — fixed all errors from `tsc --project tsconfig.app.json`: toast call signature (`toast.success/error` → `toast(msg, type)`), `'warning'` toast type (→ `'error'`), missing `RefreshCw` import, `handleDeleteSidecar` return type, duplicate `style` JSX attribute, Recharts `Formatter` type mismatch, duplicate `subscene` provider key, implicit `any` in Logs filter callback, `useSeriesDetail` nullable parameter, missing libass-wasm type declaration

---

## [0.30.0-beta] — 2026-03-16

### Added
- **Standalone — NFO metadata integration** — standalone scanner reads `.nfo` sidecar files to resolve series/movie title, year, TVDB/TMDB ID, and episode metadata without requiring an API lookup; falls back to filename parsing when no NFO is present
- **Standalone — Skip extra files** — trailers, featurettes, samples and other non-episode extras are now excluded from subtitle discovery during standalone filesystem scan; follows Jellyfin/Kodi naming convention (`-trailer`, `-featurette`, `-behindthescenes`, `-deleted`, `-interview`, `-scene`, `-short`, `-sample`, `-theme`); configurable via `standalone_skip_extras` toggle in Settings → Library Sources (advanced)

### Fixed
- **Standalone — symlinks and SQLAlchemy text() compatibility** — `os.walk(followlinks=True)` now follows symlinked directories; raw SQL wrapped in `sqlalchemy.text()` to fix deprecation warnings
- **Standalone — app context** — scanner operations that write to DB now correctly run inside Flask app context to avoid `RuntimeError: No application context`
- **Standalone — library view** — standalone series/movies now appear in Library with correct poster URLs and breadcrumb navigation
- **Standalone — series detail fallback** — SeriesDetail page gracefully handles episodes without a Sonarr instance; subtitle sidecar endpoint falls back to standalone path resolution
- **Standalone — poster endpoint** — path security enforced via `is_safe_path()`; URL generation updated to use `/api/v1/` prefix consistently
- **Standalone — NFO/poster lookup in Season subfolder** — scanner now finds `poster.jpg` and `.nfo` files inside `Season XX/` subdirectories, not only in the series root
- **Settings — nav redirect** — Setup page correctly redirects to `/settings` after initial configuration; `NavLink` `isActive` prop removed (invalid in React Router v6)
- **Wanted — scroll list layout** — replaced hardcoded `calc(100vh - 300px)` with `flex-1 / min-h-0` chain; list now fills the full remaining viewport at any window size

### Changed
- **Dependencies** — jsdom 28 → 29; 13 npm minor/patch updates

---

## [0.29.0-beta] — 2026-03-14

### Added
- **Web Player — Streaming endpoint** — `GET /api/v1/media/stream?path=` serves video files with HTTP 206 range-request support; `is_safe_path()` enforced; `Content-Type` resolved by extension; `SUBLARR_STREAMING_ENABLED` setting (default true) allows disabling the endpoint
- **Web Player — PlayerModal** — portal-based HTML5 `<video>` player with play/pause/seek/volume/fullscreen; opens via "Preview" button on episode cards in SeriesDetail
- **Web Player — ASS/SRT subtitle overlay** — SubtitleOctopus (libass WASM) renders styled ASS subtitles natively in-browser; `subtitles-octopus-worker.js` and `.wasm` served from `/public/`
- **Web Player — Subtitle track selector** — dropdown to switch between all available sidecar subtitle files for the episode; "Off" option disables overlay
- **Web Player — Seek-to-cue** — clicking a cue row in SubtitleEditorModal jumps the player to that timestamp via `onSeekRequest` bridge
- **Web Player — Settings toggle** — `streaming_enabled` toggle in Settings → Automation (advanced section)

---

## [0.28.0-beta] — 2026-03-14

### Added
- **AI Glossary Builder — DB schema** — adds `term_type` (character/place/other), `confidence` (float 0–1), `approved` (boolean) columns to `glossary_entries`; Alembic migration `f1a2b3c4d5e6`
- **AI Glossary Builder — Extractor service** — `glossary_extractor.py` performs frequency analysis over subtitle sidecar files to surface recurring proper-noun candidates without requiring an LLM
- **AI Glossary Builder — Suggest endpoint** — `POST /api/v1/series/<id>/glossary/suggest` triggers auto-detection and returns ranked candidates for human review
- **AI Glossary Builder — TSV export** — `GET /api/v1/glossary/export` downloads all approved glossary terms as a tab-separated file for external use
- **AI Glossary Builder — CRUD extended** — existing `POST/PUT /api/v1/glossary` endpoints accept the new `term_type`, `confidence`, and `approved` fields
- **AI Glossary Builder — Config** — `SUBLARR_GLOSSARY_ENABLED` (default true) and `glossary_max_terms` per-series cap (default 100) in Settings → Translation (advanced section)
- **AI Glossary Builder — LLM injection** — approved terms injected as `<glossary>` system prompt prefix during translation; capped at 50 terms; V8-compatible `term → translation` comma format retained; single-line fast-path added (`Translate to German: {line}`) when subtitle contains exactly one cue
- **AI Glossary Builder — GlossaryPanel UI** — Suggest button (Wand2 icon) triggers candidate detection; candidate list with approve/pre-fill/reject actions; `TermTypeBadge` (character/place/other); Export TSV button; all wired via new `suggestGlossaryTerms` and `exportGlossaryTsv` hooks

---

## [0.27.0-beta] — 2026-03-14

### Added
- **NFO Export — Auto sidecar** — `auto_nfo_export` config flag (off by default) writes an XML `.nfo` file alongside every downloaded or translated subtitle; contains provider, source/target language, score, translation backend, BLEU score, timestamp, and Sublarr version
- **NFO Export — API routes** — `POST /api/v1/subtitles/export-nfo?path=<path>` for single-subtitle export; `POST /api/v1/series/<id>/subtitles/export-nfo` for bulk export of all subtitles in a series; per-file `is_safe_path()` validation enforced on all paths
- **NFO Export — Settings toggle** — `auto_nfo_export` toggle in Settings → Automation (advanced section); expert feature, hidden behind "Show advanced"
- **NFO Export — SeriesDetail button** — `FileCode` button on each subtitle sidecar badge in SeriesDetail triggers single-file NFO export with toast feedback

---

## [0.26.0-beta] — 2026-03-14

### Added
- **Single-Account Login — First-run setup wizard** — on first visit, `/setup` presents two choices: set a password or leave the UI open; no forced registration
- **Single-Account Login — Flask session auth** — `before_request` hook enforces session-or-`X-Api-Key` on all `/api/` routes when enabled; session secret auto-generated and persisted in `config_entries`; bcrypt password hashing
- **Single-Account Login — Auth API** — `GET /api/v1/auth/status`, `POST /auth/setup` (first-run), `POST /auth/login`, `POST /auth/logout`, `POST /auth/change-password`, `POST /auth/toggle`; API key auth (`X-Api-Key`) remains independent
- **Single-Account Login — React routing** — `AuthGuard` component redirects to `/setup` or `/login` as needed; auth pages render full-screen without Sidebar
- **Settings → Security tab** — toggle UI auth on/off; change-password form (shown only when auth enabled)
- **Sidebar — Logout button** — shown when `auth.enabled && auth.authenticated`; navigates to `/login` on success

---

## [0.25.3-beta] — 2026-03-14

### Added
- **List Virtualization — Library table view** — replaced client-side pagination (25/page) with `@tanstack/react-virtual` virtual scroll using the padding-row technique; `<table>/<tr>` DOM structure preserved; sticky header; scroll resets on filter/sort; grid view retains pagination; `VirtualLibraryTable` + `LibraryShared` components extracted to `frontend/src/components/library/`
- **List Virtualization — Wanted list** — Wanted now fetches all matching items in a single request (up to 9 999) and renders with virtual scroll; `useWantedVirtualizer` hook in `frontend/src/components/wanted/VirtualWantedTable.tsx`; removes multi-page navigation

---

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
- **Jellyfin — Play-start webhook** — Sublarr now triggers the subtitle search+translate pipeline automatically when Jellyfin starts playing an episode; receives `PlaybackStart` events from the Jellyfin Webhook Plugin; resolves item path via configured Jellyfin/Emby media server instances
- **Settings → Automation — Jellyfin play-translate** — new toggle enables automatic translation on Jellyfin playback start (`SUBLARR_JELLYFIN_PLAY_TRANSLATE_ENABLED`, default off)

---

## [0.24.4-beta] — 2026-03-13

### Added
- **Chapter Detection — ffprobe-based chapter list** — Sublarr reads chapter metadata from video files; results cached per-file (mtime-invalidated) to avoid repeated `ffprobe` calls; path validated via `is_safe_path()`
- **Advanced Sync — Chapter Range** — offset operations can now be scoped to a chapter window; only subtitle events within the selected chapter are shifted; preview mode samples only in-range events
- **SyncControls — Chapter Tab** — new "Chapter" tab visible when chapters are detected; chapter dropdown (title + timestamps), ±offset presets, preview, and two-step confirm-apply flow

---

## [0.24.3-beta] — 2026-03-13

### Added
- **Fansub Preferences — per-series preferred and excluded groups** — configure preferred and excluded fansub groups per series; preferred groups receive a configurable score bonus, excluded groups are effectively filtered out; accessible from Series Detail
- **SeriesFansubPrefsPanel** — new panel in SeriesDetail with comma-separated preferred/excluded group inputs, bonus score field, and Save/Reset buttons

---

## [0.24.2-beta] — 2026-03-13

### Added
- **SeriesSettings — per-series Whisper audio track** — pin a preferred audio track index for Whisper transcription per series; clearing the setting (set to null) resumes automatic track selection
- **SeriesAudioTrackPicker** — new component in SeriesDetail; lazy-loads available audio tracks via ffprobe; dropdown sets the per-series Whisper transcription preference

---

## [0.24.1-beta] — 2026-03-12

### Added
- **OP/ED Detector** — detects Opening and Ending cue regions in subtitle files using ASS style name matching and position/duration heuristics; read-only detection returns `{type, start_ms, end_ms, event_count, method}` without modifying the file; configurable detection window via `SUBLARR_OP_WINDOW_SEC` (default 300 s)

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

---

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

---

## [0.20.0-beta] — 2026-03-10

### Added
- **PostgreSQL — First-Class Support** — full migration guide, PG-compatible Alembic migrations, dialect-aware health endpoints (`GET /database/health`), VACUUM guard (returns 501 on PostgreSQL); `docker-compose.postgres.yml` for batteries-included PG stack; `docs/POSTGRESQL.md` covers fresh install, SQLite→PG migration via pgloader, pool tuning, backup/restore
- **Incremental Metadata Cache** — ffprobe results cached persistently in DB with mtime-based invalidation; `GET /api/v1/cache/ffprobe/stats` and `POST /api/v1/cache/ffprobe/cleanup` endpoints; batch wanted-scanner probes now use cache (`use_cache=True`); eliminates redundant ffprobe calls on unchanged files
- **Background Wanted Scanner — Batch Commits** — scanner now batches all DB writes per series/movie into a single commit (instead of one commit per episode); thread-local `_batch_mode` flag ensures batch mode in the scanner thread never blocks concurrent API request commits; `SUBLARR_SCAN_YIELD_MS` setting (default: 0) adds optional CPU yield between series to reduce contention
- **Parallel Translation Workers — Configurable Count** — `SUBLARR_TRANSLATION_MAX_WORKERS` setting (default: 4) controls the thread pool size of the in-memory job queue; `/translate` async endpoint now routes through the shared job queue (same as `/translate/sync`) so concurrency is always bounded and observable via `GET /api/v1/jobs`
- **Redis Job Queue** — `backend/worker.py` RQ worker entry point with `AppContextWorker` subclass — each job runs inside a Flask app context; `docker-compose.redis.yml` stack with Redis 7 + Sublarr + `rq-worker`; scale workers with `--scale rq-worker=N`; graceful fallback to `MemoryJobQueue` when Redis is unreachable

---

## [0.19.2-beta] — 2026-03-10

### Fixed
- **Remux Engine — mkvmerge wrong track ID** — `_remux_mkvmerge` was referencing an undefined `stream_index` variable (NameError) and the call site was passing `subtitle_track_index` (0-based subtitle-only index, e.g. `0`) instead of the global ffprobe stream index (e.g. `2`); mkvmerge's `--subtitle-tracks !N` flag uses global Track IDs matching ffprobe's `stream_index` — passing `!0` targeted the video track and left the subtitle untouched; now `_remux_mkvmerge` receives and uses the correct global `stream_index`; validated with mkvmerge v92.0 inside Docker

---

## [0.19.1-beta] — 2026-03-10

### Fixed
- **Dockerfile — mkvtoolnix missing** — added `mkvtoolnix` to the Docker image apt-get install step; without it `mkvmerge` was unavailable inside the container and all MKV stream removal jobs failed with "mkvmerge not found"

---

## [0.19.0-beta] — 2026-03-10

### Added
- **Stream Removal — Safe Remux Engine** — remove embedded subtitle streams from video containers without re-encoding; mkvmerge used for MKV/MK3D, ffmpeg for all other containers (MP4, AVI, etc.); backend auto-detected by file extension; ffprobe verification after remux validates duration (±2s), video/audio stream counts, subtitle count (exactly -1), and file size (≥50% of original)
- **Trash-Folder Backups — Configurable Retention** — original video moved to centralized `<media_root>/<remux_trash_dir>/trash/<YYYY-MM-DD>/<file>.<ts>.bak` before each remux (TinyMediaManager-style); absolute trash path supported; falls back to sibling `.bak` on permission error; CoW reflink attempted first on Btrfs/XFS for near-instant copies; `remux_trash_dir` (default `.sublarr`) and `remux_backup_retention_days` (default 7) configurable in Settings → Automation
- **Async Remux Jobs** — `POST /api/v1/library/episodes/<ep_id>/tracks/<index>/remove-from-container` starts a background job; `GET /api/v1/remux/jobs` and `GET /api/v1/remux/jobs/<job_id>` expose status; real-time updates via Socket.IO `remux_job_update` events; optional Sonarr/Radarr folder-monitoring pause during remux
- **Backup Management API** — `GET /api/v1/remux/backups` lists all `.bak` files in trash directories; `POST /api/v1/remux/backups/cleanup` deletes backups older than retention period (supports `dry_run` mode)
- **Undo / Restore** — `POST /api/v1/remux/backups/restore` atomically restores backup to original video path via `os.replace()`; both paths validated with `is_safe_path()` to prevent path traversal; "Undo" button appears in TrackPanel after successful stream removal and restores in one click

---

## [0.18.0-beta] — 2026-03-10

### Added
- **HI Support — Hearing Impaired Preference** — new `hi_preference` setting (`include` / `prefer` / `exclude` / `only`); provider results scored accordingly: `prefer` adds +30, `exclude` / `only` apply ±999 penalty; `hi_removal_enabled` toggle for future HI-tag stripping
- **Forced Subtitle Support — Forced Preference** — new `forced_preference` setting (`include` / `prefer` / `exclude` / `only`) with same ±30/±999 scoring logic; bonuses stack when both HI and forced preferences match
- **TRaSH Scoring Presets — Importable Community Profiles** — `backend/scoring_presets/` package with three bundled presets (`anime`, `tv`, `movies`); `GET /api/v1/scoring/presets`, `GET /api/v1/scoring/presets/<name>`, `POST /api/v1/scoring/presets/import` endpoints; Settings → Events & Hooks → Scoring tab shows preset selector and custom JSON import; import validates schema and calls `invalidate_scoring_cache()`
- **Anti-Captcha Integration — Provider 403 Bypass** — new `CaptchaSolver` class supporting Anti-Captcha.com and CapMonster via identical `createTask` / `getTaskResult` REST API; `anti_captcha_provider` + `anti_captcha_api_key` settings; Kitsunekko calls `_try_solve_captcha_and_retry()` on HTTP 403 — submits reCAPTCHA v2 token and retries; falls back gracefully if no solver configured; Anti-Captcha section added to Providers tab in Settings

---

## [0.17.0-beta] — 2026-03-10

### Added
- **Duplicate Detection — SHA-256 download dedup** — skips provider downloads when SHA-256 hash matches an existing subtitle in the same directory; stale hash entries are auto-cleaned on startup; toggleable via `SUBLARR_DEDUP_ON_DOWNLOAD`; hash registered on every successful file write
- **Smart Episode Matching — multi-episode + OVA/Special** — multi-episode filenames (`S01E01E02`) parsed to full episode list; OVA/Special/SP detection via guessit + filename regex; `release_group`, `source`, `resolution`, `absolute_episode` propagated to `VideoQuery` for all providers
- **Video Hash Pre-Compute** — `file_hash` computed once in `build_query_from_wanted()` and reused across all providers; eliminates redundant file reads when multiple providers are queried in parallel
- **Release Group Filtering** — include/exclude subtitle results by release group, codec, or source tag; score bonus for preferred groups; release metadata auto-extracted from filename via guessit; configurable at Settings → Wanted
- **Provider Result Re-ranking** — auto-adjusts per-provider score modifiers from download history; formula: success rate + avg score vs. global average + consecutive failure penalty; throttled hourly; preview endpoint and manual trigger available
- **Subtitle Upgrade Scheduler** — periodic re-check for higher-quality subtitles; eligibility: score < 500 OR non-ASS format; configurable `upgrade_scan_interval_hours` at Settings → Automation; manual trigger via `/tasks/upgrade-scan/trigger`
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
- **Provider UI — Disable vs. Remove** — Power button grays out a provider tile in-grid (50% opacity, "Disabled" badge) while Trash button removes it to the `+` pool entirely; new `providers_hidden` config key separates "off but visible" from "removed from grid"
- **Provider — Subscene** — 55-language community subtitle database, no account required; HTML scraping with BeautifulSoup4, rate limit 10/60 s
- **Provider — Addic7ed** — 36 languages, TV-series specialist with episode-exact matching; optional login credentials increase daily download limit; BeautifulSoup4, rate limit 10/60 s
- **Provider — TVSubtitles** — 35 languages, TV-series only, no auth; BeautifulSoup4, rate limit 15/60 s
- **Provider — Turkcealtyazi** — Turkish subtitle community site, login required; BeautifulSoup4, rate limit 10/60 s
- **Language expansion** — `_LANGUAGE_TAGS` expanded from 25 to ~70 ISO 639-1 codes; `SUPPORTED_LANGUAGES` constant with 63 ordered entries served via `GET /api/v1/languages` (cached 1 h)
- **LanguageSelect component** — searchable dropdown for source/target language settings that updates both the language code and `_name` fields simultaneously

### Changed
- **Settings — source/target language** — fields now use the new `LanguageSelect` dropdown instead of plain text inputs
- **Provider reactive health checks** — status is fetched on-demand only (no background polling); `ProviderManager.update_providers()` does selective enable/disable without full reinit; `providers_hidden` key excluded from provider reinit trigger
- **Provider UI grid** — complete tile-grid redesign: ProviderTile shows status badge, success rate, language count, and credential type; AddProviderModal replaces flat list with searchable cards; ProviderEditModal uses structured config_fields; header shows `N active / M configured` counts; `+` tile only visible when hidden providers exist
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
- **Sidecar discovery APIs** — `GET /api/v1/library/series/<id>/subtitles` scans all episode files in parallel (ThreadPoolExecutor) and returns sidecar metadata keyed by Sonarr episode ID; `GET /api/v1/library/episodes/<id>/subtitles` for single-episode scan; response includes path, language, format, size, and mtime for each sidecar file
- **Sidecar delete API** — `DELETE /api/v1/library/subtitles` moves one or more sidecar files to a `.sublarr_trash/` folder (manifest.json per entry) instead of permanently deleting; only files inside `SUBLARR_MEDIA_PATH` are accepted — path-traversal attempts return 403
- **Trash management APIs** — `GET /api/v1/library/trash` lists recoverable files; `POST /api/v1/library/trash/<id>/restore` moves the file back; `DELETE /api/v1/library/trash/<id>` permanently removes it; auto-purge of entries older than `subtitle_trash_retention_days` (default: 7 days) runs on every delete call
- **Batch delete API** — `POST /api/v1/library/series/<id>/subtitles/batch-delete` removes sidecars across all episodes of a series filtered by language and/or format; all deletions go through the trash system
- **Inline sidecar badges** — SeriesDetail episode rows now show a badge for every sidecar file found on disk (language + format label); non-target-language sidecars are displayed in a dimmed style with a × delete button; clicking × soft-deletes the file and immediately refreshes the row
- **Subtitle Cleanup Modal** — series-level "Clean up" button opens a modal grouped by language showing file count and total size per language; "Keep target languages only" quick action pre-selects all non-target languages for deletion; preview shows file count and MB to be moved to trash before confirming
- **Live extraction progress** — `batch-extract-tracks` emits a `batch_extract_progress` WebSocket event after each episode; SeriesDetail shows a progress banner (file name + `X / N episodes`) with a progress bar and animated spinner while extraction is running; Extract button is disabled during the operation
- **Activity page visibility** — `batch-extract-tracks` now creates a DB job record (`running` → `completed`/`failed`) so every extraction run appears on the Activity page with succeeded, failed, and skipped episode counts; the job is visible within one poll cycle (~3 s) of starting
- **Always-visible series toolbar** — new action row pinned to the SeriesDetail hero header containing three buttons: "Extract Tracks" (triggers `batch-extract-tracks` for the whole series, shows live X/N counter), "Clean up" (opens Subtitle Cleanup Modal), and "Search N missing" (moved here from the language row); all three actions are available without selecting individual episodes
- **Auto-cleanup settings** — three new config fields: `auto_cleanup_after_extract` (boolean toggle), `auto_cleanup_keep_languages` (comma-separated ISO 639-1 codes, e.g. `de,en`), `auto_cleanup_keep_formats` (`ass` / `srt` / `any`); when enabled, sidecars not matching the keep rules are moved to trash automatically at the end of each `batch-extract-tracks` run
- **Settings UI** — three new fields added to the Automation tab; `subtitle_trash_retention_days` field also added to control automatic trash purge interval
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
- **Advanced Settings toggle** — global "Advanced" checkbox in the Settings header persisted to localStorage; hides annotated advanced fields by default with orange left-border marker
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

## [0.9.6-beta] — 2026-02-21

### Fixed
- Zombie jobs: jobs stuck in "running" state after backend restart are cleaned up on startup
- Wanted page: pagination counter now reflects active filter, not full DB total
- Duplicate `wanted_items`: `UniqueConstraint(file_path, target_language, subtitle_type)` prevents race-condition duplicates
- `get_series_missing_counts()`: excludes `existing_sub = 'srt'` and `'embedded_srt'` (upgrade candidates) from "missing" count

---

## [0.9.5-beta] — 2026-02-21

### Added
- Global Glossary — per-language term overrides applied during all translations; configurable in Settings → Translation
- Per-Series Glossary — series-specific term overrides; accessible from Series Detail
- Provider test: works without explicit `Content-Type: application/json` header (`force=True` JSON parsing)

---

## [0.9.0-beta] — 2026-02-16

### Added
- Plugin architecture with hot-reload for custom subtitle providers
- Plugin discovery from `/config/plugins/` with manifest validation
- Plugin-specific configuration stored in `config_entries` database table
- Watchdog-based hot-reload with 2-second debounce (opt-in via `plugin_hot_reload`)
- Plugin developer template and documentation

- **Gestdown** — Addic7ed proxy with REST API, covers both Addic7ed and Gestdown content
- **Podnapisi** — Large multilingual database with XML API and lxml parsing
- **Kitsunekko** — Japanese anime subtitles via HTML scraping (BeautifulSoup optional)
- **Napisy24** — Polish subtitles with MD5 file hash matching (first 10MB)
- **Whisper-Subgen** — External ASR integration, returns low-score placeholder in search
- **Titrari** — Romanian subtitles via polite scraping (no auth required)
- **LegendasDivx** — Portuguese subtitles with session authentication and daily limit tracking

- Per-provider response time tracking with weighted running average
- Auto-disable after consecutive failure threshold (default: 10 failures)
- Configurable cooldown period (`provider_auto_disable_cooldown_minutes`, default: 30 min)
- Provider health dashboard with success rate, response time, and download counts

- **DeepL** backend with glossary caching by (source, target) language pair
- **LibreTranslate** backend for self-hosted translation (line-by-line for 1:1 mapping)
- **OpenAI-compatible** backend supporting any OpenAI API endpoint with CJK hallucination detection
- **Google Cloud Translation** backend with fresh client per call for credential rotation
- Per-profile backend selection in language profiles
- Automatic fallback chains with configurable backend priority
- Circuit breakers per translation backend (reuses provider circuit breaker pattern)
- Translation quality metrics tracked per backend

- **Plex** support with lazy `plexapi` connection (optional dependency)
- **Kodi** support with JSON-RPC `VideoLibrary.Scan` (directory-scoped)
- Unified media server settings page with multi-server configuration
- `MediaServerManager.refresh_all()` notifies all configured servers after subtitle changes
- Legacy Jellyfin configuration auto-migrated to new multi-server format

- **faster-whisper** backend with lazy model loading and device/compute_type caching
- **Subgen** backend for external Whisper API integration
- Case D translation pipeline: automatic Whisper fallback when all providers fail
- Whisper job queue with configurable max concurrency and progress via WebSocket
- Audio extraction via ffmpeg pipe (no temp files)
- Language detection validation against expected source language

- Folder-watch operation without Sonarr/Radarr dependency
- **TMDB** metadata lookup (requires API key)
- **AniList** metadata lookup (no API key required, 0.7s rate limiting)
- **TVDB** metadata lookup with 24h JWT token caching
- Anime detection via multi-signal heuristic (bracket groups, fansub groups, CRC32, absolute numbering)
- `guessit`-based filename parsing with anime-aware mode
- `MediaFileWatcher` with per-path debounce and file stability checks
- `StandaloneScanner` groups files by series for efficient metadata lookup
- Standalone items integrate with existing Wanted pipeline

- Multi-signal forced subtitle detection (ffprobe flags, filename patterns, title analysis, ASS style analysis)
- Per-series forced subtitle preference (disabled/separate/auto) in language profiles
- OpenSubtitles `foreign_parts_only` filter for native forced search
- Post-search forced classification for providers without native support
- Forced subtitle type badges and filter buttons in Wanted UI

- Internal event bus using `blinker` with signal isolation namespace
- 22+ business events published (subtitle_downloaded, translation_complete, provider_failed, etc.)
- Shell script hooks with environment variable payload and configurable timeouts
- Outgoing webhooks with HTTP POST, JSON payload, and retry logic on failure
- Event catalog with versioned payload schemas (CATALOG_VERSION=1)
- SocketIO bridge for real-time event forwarding to frontend

- Configurable scoring weights (hash, series, year, season, episode, release_group, ASS bonus)
- Per-provider score modifiers (-100 to +100 range)
- Scoring cache with 60s TTL and config-change invalidation

- English and German translations for entire UI
- `react-i18next` with static JSON imports (no HTTP backend)
- Language preference stored in localStorage (`sublarr-language`)
- `LanguageSwitcher` component in header

- Dark/light theme toggle with system preference detection
- Theme stored in localStorage (`sublarr-theme`) with 3 states: dark, light, system
- Inline script in `index.html` prevents flash of wrong theme before React hydration
- CSS variable-based theming

- Full backup (config + database as ZIP) with in-memory buffer
- Scheduled automatic backups with configurable interval
- Restore from ZIP upload via Settings UI
- Backup rotation with configurable retention count

- Recharts-based charts with responsive containers
- Time-range filters (7d, 30d, 90d, all)
- Daily stats, provider usage, translation backend performance, format distribution
- Subtitle download and upgrade history visualization

- Timing adjustment (centisecond precision, H:MM:SS.cc format)
- Encoding fix (detect and convert to UTF-8)
- Hearing impaired tag removal
- Style stripping (ASS to plain text)
- All tools create `.bak` backup before modification
- Path traversal prevention via `os.path.abspath` validation

- OpenAPI 3.0.3 specification at `/api/v1/openapi.json` with 65+ documented paths
- Swagger UI at `/api/docs` for interactive API exploration
- `apispec` + `apispec-webframeworks` for YAML docstring-based spec generation
- X-Api-Key security scheme for authenticated endpoints

- Incremental wanted scan with timestamp tracking (only rescans modified items)
- Full scan forced every 6th cycle as safety fallback
- Parallel ffprobe via `ThreadPoolExecutor` (max 4 workers per series)
- Parallel wanted search processing (removed 0.5s inter-item delay)
- Route-level code splitting with `React.lazy` for all 13 page components
- `PageSkeleton` loading component for Suspense fallback

- Extended `/health/detailed` with 11 subsystem categories
- Translation backend health checks per instance
- Media server health checks per instance
- Whisper backend health reporting
- Sonarr/Radarr connectivity checks across all configured instances
- Scheduler status reporting

### Changed
- **Architecture** — Application Factory pattern (`create_app()`) with 15 Flask Blueprints (from monolithic `server.py`)
- **Database** — Split `database.py` into `db/` package with 9 domain modules (from monolithic 2153-line file)
- **Frontend** — React 19 + TypeScript + Tailwind v4 (upgraded from React 18 + Tailwind CSS)
- **Translation** — Ollama configuration moved from dedicated tab to unified Translation Backends tab
- **Settings** — Split 4703-line `Settings.tsx` monolith into 7 focused tab modules under `Settings/` directory
- **Version numbering** — Changed from v1.0.0-beta to v0.9.0-beta (standard pre-release convention -- v1.0.0 reserved for stable release)
- **Gunicorn** — Single worker mode required for Flask-SocketIO WebSocket state consistency

### Fixed
- Case-sensitive email uniqueness in provider configurations
- Hardcoded version strings ("0.1.0") replaced with centralized `version.py`
- SPA fallback route now returns correct version string
- Toast message and ThemeToggle label i18n gaps closed
- Pre-existing integration test expectations updated for health endpoint response format


---

## [1.0.0-beta] — 2026-02-14

### Added
- **Provider System** — Direct subtitle sourcing from AnimeTosho, Jimaku, OpenSubtitles, and SubDL
- **Wanted System** — Automatic detection of missing subtitles via Sonarr/Radarr integration
- **Search & Download Workflow** — End-to-end subtitle acquisition without Bazarr
- **Upgrade System** — Automatic SRT-to-ASS upgrades with configurable score delta
- **Language Profiles** — Per-series/movie target language configuration with multi-language support
- **LLM Translation** — Integrated subtitle translation via Ollama (ASS and SRT formats)
- **Glossary System** — Per-series translation glossaries for consistent terminology
- **Prompt Presets** — Customizable translation prompt templates with default preset
- **Blacklist & History** — Track downloads and block unwanted subtitle releases
- **HI Removal** — Hearing impaired marker removal from subtitles before translation
- **Embedded Subtitle Detection** — Extract and translate subtitles embedded in MKV files
- **AniDB Integration** — TVDB-to-AniDB ID mapping for better anime episode matching
- **Webhook Automation** — Sonarr/Radarr webhooks trigger scan-search-translate pipeline
- **Multi-Instance Support** — Configure multiple Sonarr/Radarr instances
- **Notification System** — Apprise-based notifications (Pushover, Discord, Telegram, etc.)
- **Onboarding Wizard** — Guided first-time setup
- **Provider Caching** — TTL-based search result caching per provider
- **Re-Translation** — Detect and re-translate files when model/prompt/language changes
- **Config Export/Import** — Backup and restore application configuration
- **Docker Multi-Arch** — Builds for linux/amd64 and linux/arm64
- **Unraid Template** — Community Applications template for Unraid


