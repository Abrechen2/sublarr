# Sublarr — Roadmap

> Completed versions are marked ✅. The current release is **v0.23.0-beta**. Planned versions reflect intended direction and may shift.

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

## v0.23.0 ✅ — Batch Operations & Smart Filter *(current)*

Goals: Multi-select workflows across Library and Wanted; auto-extract-on-scan; saved filter presets.

- Auto-Extract on Scan — `scan_auto_extract` + `scan_auto_translate` settings; scanner extracts embedded subs on first detection
- `POST /wanted/batch-extract` — extract embedded subs for multiple wanted items in one request
- `POST /wanted/batch-search` extended — accepts `series_ids` array for multi-series search
- SeriesDetail — episode checkboxes + floating batch toolbar (Search / Extract)
- Library — series checkboxes + batch toolbar ("Search All Missing")
- Filter Presets — save/load named filter configurations on Library, Wanted, History pages
- Global Search (Ctrl+K) — fuzzy search across series, episodes, and subtitles

---

## v0.24.0 — Staff Credit Filtering

Goals: Detect and strip credits-only subtitle lines from downloaded subtitles.

- `credit_remover.py` — detect credit lines by regex patterns, duration heuristic, role markers
- `POST /api/v1/tools/remove-credits` — strip detected credits; returns removed count
- Quality Tools panel — Credit Filter button alongside existing Remove HI button

---

## v0.24.1 — Opening/Ending Skip Detection

Goals: Mark OP/ED cue regions in subtitle files for optional skip during translation.

- OP/ED detection by style name, duration heuristic (OP ≈ 90s, ED ≈ 130s), and content patterns
- `POST /api/v1/tools/mark-opening-ending` — annotate OP/ED boundaries in ASS/SRT files
- Quality Tools panel — Detect OP/ED button with preview of detected ranges

---

## v0.24.2 — Multi-Audio Track Support for Whisper

Goals: Select the correct audio track per series for Whisper transcription.

- Per-series audio track preference stored in DB (extend `series_language_profiles`)
- `POST /whisper/transcribe` extended with optional `audio_track_index` parameter
- SeriesDetail — audio track picker showing available tracks with language/codec info

---

## ~~v0.24.3 — Fansub Preference Rules~~ Complete

Goals: Per-series preferred fansub group ordering with score bonuses.

- `SeriesFansubPreference` DB table — preferred groups list + bonus int per series
- Scoring hook in `wanted_search.py` — apply fansub bonus/penalty at result ranking
- SeriesDetail — Fansub Preferences panel (preferred groups, excluded groups, bonus value)
- `GET/PUT /api/v1/series/<id>/fansub-prefs` endpoints

---

## v0.24.4 — Chapter-Aware Sync

Goals: Align subtitle timing to chapter markers in MKV files.

- Chapter extraction via mkvtoolnix/ffprobe; cache in DB per video file
- Per-chapter sync using pysubs2 to apply offset corrections per chapter segment
- `POST /tools/video-sync` extended with optional `chapter_id` parameter
- Sync modal — chapter selector dropdown when chapters are detected

---

## v0.25.0 — Pipeline & Integrations

Goals: Make Sublarr useful as a processing pipeline, not just a UI-driven tool.

- Jellyfin SSE Events — consume Jellyfin play-start events to auto-translate on-demand
- CLI Mode — `sublarr search`, `sublarr translate`, `sublarr sync` for scripting and cron jobs
- Subtitle Diff Viewer — inline accept/reject for individual changed cues (upgrade from full-replace)
- List Virtualization — `@tanstack/react-virtual` for Library and Wanted (requires div-based layout refactor)

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

## Long-Term Ideas (No Version Commitment)

- Web Player Integration — embedded subtitle preview with video playback
- AI-Assisted Glossary Building — auto-detect proper nouns from translation history
- Single-Account Login — optional password protection for the web UI (no multi-user/RBAC)
- Subtitle Quality Score Export — export per-file quality metrics as NFO sidecar

---

## How to Contribute

See [docs/CONTRIBUTING.md](docs/CONTRIBUTING.md) for how to submit features, bug reports, and pull requests.
