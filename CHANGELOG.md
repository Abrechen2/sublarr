# Changelog

All notable changes to Sublarr are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
