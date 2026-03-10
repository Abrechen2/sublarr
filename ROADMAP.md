# Sublarr - Roadmap

> **Note:** This roadmap reflects intended direction. Items marked checkmark are complete; calendar are planned.

---

## Ongoing — UI/UX

> Not tied to any version. Implemented as soon as a good solution is found.

The current UI is functional but not final. The goal is a clean, modern interface that feels native — not a dashboard. No specific framework or design system is locked in yet; the right solution will be implemented when it emerges.

- Responsive layout improvements (mobile / tablet)
- Consistent component library across all pages
- Better empty states, loading skeletons, and error feedback
- Keyboard navigation and accessibility (a11y)

---

## v0.11.0 ✅ (Complete)

- Track Manifest - list, extract, and translate embedded subtitle/audio streams
- Video Sync - ffsubsync / alass integration with live progress bar
- Waveform Editor - wavesurfer.js audio visualization with per-cue region markers
- Format Conversion - ASS, SRT, SSA, VTT via pysubs2
- Batch OCR - Tesseract-based text extraction from PGS/VobSub image tracks
- Quality Fixes Toolbar - overlap fix, timing normalize, merge/split lines, spell check

---

## v0.12.0 ✅ (Complete)

- Settings UX Redesign - SettingsCard, AdvancedSettingsContext, InfoTooltip, per-field descriptions
- arr-style UI Redesign - Sonarr/Radarr aesthetic, teal accent, neutral dark palette

---

## v0.13.0 ✅ (Complete)

- Sidecar Subtitle Management - inline sidecar badges (language + format) per episode with × delete button
- Series/Episode Subtitles API - parallel filesystem scan keyed by Sonarr episode ID
- Delete & Batch-Delete API - path-traversal-safe sidecar deletion by path or language/format filter
- Sidecar Cleanup Modal - language-grouped overview, file count + size preview, "Nur Target-Sprachen behalten"
- Auto-Cleanup after Batch Extract - three new settings run cleanup automatically after track extraction
- Dynamic UNTERTITEL column - grows with content instead of fixed 160 px

---

## v0.14.0 ✅ (Complete)

- Provider UI Redesign — Bazarr-style tile grid; Deaktivieren grays tile in place (50% opacity), Entfernen removes to `+` pool; `providers_hidden` config key; reactive health checks on demand only
- Provider — Subscene — 55-language community subtitle database, no account required
- Provider — Addic7ed — 36 languages, TV-series specialist with episode-exact matching, optional login
- Provider — TVSubtitles — 35 languages, TV-series only, no auth
- Provider — Turkcealtyazi — Turkish subtitles, login required
- Language Expansion — `_LANGUAGE_TAGS` 25 → ~70 languages; `GET /api/v1/languages` endpoint; searchable `LanguageSelect` dropdown for source/target language settings

---

## v0.15.0 ✅ (Complete — Current)

- Sidebar — Update available badge — pulsing badge appears when a newer GitHub release exists; fetched from GitHub Releases API once on load and cached; clicking opens the release page
- Library — Grid/Thumbnail view — toggle button (table ↔ grid); poster images from Sonarr/Radarr with missing-count badge; preference persisted in localStorage; fallback film-slate SVG
- Library — Status and profile filters — filter by status (all / has missing / complete) and by profile name; client-side filtering via useMemo
- Wanted — Extracted status + Sidecar Cleanup — extracting an embedded subtitle now sets status `extracted` instead of removing the item; new cleanup endpoint deletes non-target-language sidecars; teal badge + filter tab in UI
- Wanted — Error and retry display — failed items show failure reason as tooltip; upcoming retry time shown below badge
- Settings — Search field — real-time filter for settings tabs
- SeriesDetail — EpisodeActionMenu — replaces icon-only buttons with labelled primary + `⋯ More` dropdown grouped by category
- Fix: Wanted search and download — broken by missing Flask app context in background threads and stale provider cache
- Fix: PostgreSQL startup — `rowid` → `id` in dedup query; `MIN(title)` aggregate in search index; pre-Alembic column patch for `source`; SPA 404 on page reload

---

## v0.16.0 ✅ (Complete)

- ZIP Slip Prevention — wire existing `safe_zip_extract()` into all providers (animetosho, jimaku, subdl, kitsunekko, legendasdivx, napisy24, podnapisi, titrari); replace per-provider inline extraction
- Download Size Limits — 5 MB per subtitle file, 20 MB per archive; reject oversized downloads before disk write
- ZIP Bomb Protection — limit total extracted size to 50 MB; abort extraction when compression ratio exceeds 100:1
- ASS Sanitizer — parse with pysubs2, strip Lua scripts, external includes, and dangerous override tags; re-serialize clean file before saving
- SRT/VTT Sanitizer — strip all HTML except `<i>`, `<b>`, `<u>`; remove embedded scripts, event handlers, and data URIs
- Central `sanitize_subtitle()` Gate — single function called after every provider download, before file is written to disk
- Content-Type Validation — verify downloaded bytes match expected subtitle format; reject binary, executable, or unrecognized content
- Provider Archive Consolidation — replace 8 independent extraction implementations with shared `extract_archive()` utility using `safe_zip_extract()` and `safe_rar_extract()`

---

## v0.17.0 (Subtitle Intelligence — In Progress)

Goals: Make Sublarr smarter about what to search for and what to accept.

- ✅ Duplicate Detection — skip downloads when SHA-256 matches existing sub in same directory; stale hash entries auto-cleaned; `SUBLARR_DEDUP_ON_DOWNLOAD` toggle; hash registered on every successful write
- ✅ Smart Episode Matching — multi-episode files (`S01E01E02`) parsed to full episode list; OVA/Special/SP detection via guessit + filename regex; `release_group`, `source`, `resolution`, `absolute_episode` propagated to `VideoQuery`
- ✅ Video Hash Pre-Compute — `file_hash` computed once in `build_query_from_wanted()` and shared across all providers (no redundant file reads per provider)
- ✅ Release Group Filtering — include/exclude subtitle results by release group, codec, or source tag; score bonus for preferred groups; release metadata auto-extracted from filename via guessit
- Provider Result Re-ranking — re-ranking based on download history
- Subtitle Upgrade Scheduler — periodic re-check for higher-quality subs (configurable lookback window)
- Translation Quality Dashboard — per-series quality trend charts in Statistics page
- Custom Post-Processing Scripts — user-supplied shell scripts run after download/translate

---

## v0.18.0 (Provider Maturity)

Goals: Close remaining gap to Bazarr in provider coverage, subtitle type handling, and community integration.

- Additional Providers - Supersubtitles and further community providers
- Hearing Impaired Support - HI detection, preference setting (prefer/exclude/only), HI-tag stripping from dialogue
- Forced Subtitle Support - detect and download forced subs for foreign-audio scenes
- Anti-Captcha Integration - Anti-Captcha.com / CapMonster support for captcha-protected providers
- TRaSH-Compatible Scoring Presets - importable community-maintained scoring profiles

---

## v0.19.0 (Stream Removal — Safe Remux)

Goals: Safely remove embedded subtitle streams from video files after extraction, with full rollback capability.

- Remux Engine - mkvmerge (MKV) / ffmpeg (MP4) remux excluding selected subtitle streams, no re-encoding
- Verification Pipeline - compare duration, video/audio stream count, and file size plausibility before swap
- Atomic File Swap - write to temp file, rename original to `.bak`, rename temp to original name
- Backup Retention - configurable `.bak` retention period (default 7 days), automatic cleanup scheduler
- CoW/Reflink Detection - detect Btrfs/XFS and use `cp --reflink=auto` for zero-cost backups
- *arr Pause Integration - pause Sonarr/Radarr folder monitoring via API during remux to prevent import loops
- Track Panel UI - "Remove from container" action in Track Manifest after successful extraction, with confirmation dialog

---

## v0.20.0 (Collaboration and Export)

Goals: Make Sublarr useful as a subtitle processing pipeline, not just consumer.

- Subtitle Export API - serve processed subtitles via authenticated endpoint for external players
- Batch Export - ZIP export of all subtitles for a series
- Subtitle Diff Viewer Improvements - inline accept/reject for individual changed cues
- Jellyfin SSE Events - consume Jellyfin play-start events to auto-translate on-demand
- CLI Mode - `sublarr search`, `sublarr translate`, `sublarr sync` commands for scripting and cron jobs

---

## v0.21.0 (Performance and Scalability)

Goals: Handle larger libraries without degradation.

- PostgreSQL First-Class Support - full migration guide, connection pooling optimized for PG
- Redis Job Queue - move translation jobs to RQ/Celery for multi-worker support
- Incremental Metadata Cache - cache ffprobe output persistently, only rescan changed files
- Background Wanted Scanner - fully async scan without blocking API responses
- Parallel Translation Workers - configurable worker count for concurrent translation jobs

---

## v0.22.0 (Advanced Anime Support)

Goals: First-class support for complex anime subtitle scenarios.

- Fansub Preference Rules - per-series preferred fansub group ordering
- Chapter-Aware Sync - align subtitle timing to chapter markers in MKV
- Opening/Ending Skip Detection - mark OP/ED cues for optional skip during translation
- Staff Credit Filtering - detect and optionally strip credits-only subtitle lines
- Multi-Audio Track Support - select correct audio track for Whisper transcription per series

---

## v1.0.0 (Stable Release)

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

- Web Player Integration - embedded subtitle preview with video playback
- AI-Assisted Glossary Building - auto-detect proper nouns and build glossary from translation history
- Provider Plugin Marketplace - community-submitted provider plugins with sandboxed execution
- Single-Account Login - optional password protection for the web UI (no multi-user/RBAC)
- Subtitle Quality Score Export - export per-file quality metrics as NFO sidecar

---

## How to Contribute

See [docs/CONTRIBUTING.md](docs/CONTRIBUTING.md) for how to submit features, bug reports, and pull requests.
