# Sublarr - Roadmap

> **Note:** This roadmap reflects intended direction. Items marked checkmark are complete; calendar are planned.

---

## v0.11.x (Current - Bug Fix & Polish)

- Track Manifest - list, extract, and translate embedded subtitle/audio streams
- Video Sync - ffsubsync / alass integration with live progress bar
- Waveform Editor - wavesurfer.js audio visualization with per-cue region markers
- Format Conversion - ASS, SRT, SSA, VTT via pysubs2
- Batch OCR - Tesseract-based text extraction from PGS/VobSub image tracks
- Quality Fixes Toolbar - overlap fix, timing normalize, merge/split lines, spell check
- Bug fix patches for known edge cases

---

## v0.12.0 (Subtitle Intelligence)

Goals: Make Sublarr smarter about what to search for and what to accept.

- Smart Episode Matching - detect multi-episode files, specials, OVAs via guessit
- Provider Result Re-ranking - re-ranking based on download history
- Duplicate Detection - skip downloads when SHA-256 matches existing sub in DB
- Translation Quality Dashboard - per-series quality trend charts in Statistics page
- Custom Post-Processing Scripts - user-supplied shell scripts run after download/translate

---

## v0.13.0 (Collaboration and Export)

Goals: Make Sublarr useful as a subtitle processing pipeline, not just consumer.

- Subtitle Export API - serve processed subtitles via authenticated endpoint for external players
- Batch Export - ZIP export of all subtitles for a series
- Subtitle Diff Viewer Improvements - inline accept/reject for individual changed cues
- Jellyfin SSE Events - consume Jellyfin play-start events to auto-translate on-demand

---

## v0.14.0 (Performance and Scalability)

Goals: Handle larger libraries without degradation.

- PostgreSQL First-Class Support - full migration guide, connection pooling optimized for PG
- Redis Job Queue - move translation jobs to RQ/Celery for multi-worker support
- Incremental Metadata Cache - cache ffprobe output persistently, only rescan changed files
- Background Wanted Scanner - fully async scan without blocking API responses
- Parallel Translation Workers - configurable worker count for concurrent translation jobs

---

## v0.15.0 (Advanced Anime Support)

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
- Stable API (no breaking changes from v0.12+)
- Docker image on GHCR with multi-arch (amd64 + arm64)
- Unraid Community Applications template finalized
- User Guide complete and reviewed
- Load tested with library of 500+ series

---

## Long-Term Ideas (No Version Commitment)

- Web Player Integration - embedded subtitle preview with video playback
- AI-Assisted Glossary Building - auto-detect proper nouns and build glossary from translation history
- Provider Plugin Marketplace - community-submitted provider plugins with sandboxed execution
- Multi-User Support - role-based access control
- Subtitle Quality Score Export - export per-file quality metrics as NFO sidecar

---

## How to Contribute

See [docs/CONTRIBUTING.md](docs/CONTRIBUTING.md) for how to submit features, bug reports, and pull requests.
