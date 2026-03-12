# Configuration Reference

## Quick start — minimal `.env`

Only a handful of settings need to be in your `.env` file. Everything else
is configured in the **Settings UI** after the container starts
(`http://localhost:<SUBLARR_PORT>`).

```env
# Docker / Compose
VERSION=0.1.0      # must match backend/VERSION
PUID=1000
PGID=1000

# Server
SUBLARR_PORT=5765

# Paths (must match docker-compose.yml volume mounts)
SUBLARR_MEDIA_PATH=/media
SUBLARR_DB_PATH=/config/sublarr.db

# LLM service endpoint (infrastructure — not in Settings UI)
SUBLARR_OLLAMA_URL=http://ollama:11434

# Optional: API key auth
# SUBLARR_API_KEY=
```

Copy `.env.example` to `.env` and you're ready to start.

---

## How settings work

All `SUBLARR_` variables can be set via three layers (highest priority first):

1. **Environment variable / `.env`** — used for infrastructure and secrets
2. **Settings UI** — runtime config stored in `config_entries` DB table
3. **Built-in default** — safe value for every field

The tables below are the complete reference. The **UI** column indicates
whether a setting is also exposed in the Settings UI (and therefore does
**not** need to be in `.env` for day-to-day use).

---

## Core

| Variable | Default | UI | Description |
|---|---|:---:|---|
| `SUBLARR_MEDIA_PATH` | `/media` | ✅ | Root path of your media library |
| `SUBLARR_DB_PATH` | `/config/sublarr.db` | ✅ | SQLite database location |
| `SUBLARR_DATABASE_URL` | *(empty)* | — | Full SQLAlchemy URL (e.g. `postgresql://...`). Overrides `DB_PATH` when set |
| `SUBLARR_PORT` | `5765` | ✅ | HTTP port |
| `SUBLARR_API_KEY` | *(empty)* | ✅ | Optional API key for auth (`X-Api-Key` header). Empty = no auth |
| `SUBLARR_CORS_ORIGINS` | `http://localhost:5173,http://localhost:5765` | — | Allowed CORS/WebSocket origins (comma-separated). Set `*` only in fully trusted environments |
| `SUBLARR_LOG_LEVEL` | `INFO` | ✅ | Log level: `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `SUBLARR_LOG_FILE` | `log/sublarr.log` | — | Log file path. Docker default: `/config/sublarr.log` |
| `SUBLARR_LOG_FORMAT` | `text` | — | Log format: `text` or `json` (structured for log aggregation) |
| `PUID` / `PGID` | `1000` | — | Container user/group IDs for volume file permissions |

---

## Translation

| Variable | Default | UI | Description |
|---|---|:---:|---|
| `SUBLARR_OLLAMA_URL` | `http://localhost:11434` | — | Ollama base URL — set in `.env` (infrastructure endpoint) |
| `SUBLARR_OLLAMA_MODEL` | `qwen2.5:14b-instruct` | — | Default model for translation. Recommended: `hf.co/Sublarr/anime-translator-v6-GGUF:Q4_K_M` (custom fine-tuned, EN→DE anime subtitles — see [huggingface.co/Sublarr](https://huggingface.co/Sublarr)) |
| `SUBLARR_SOURCE_LANGUAGE` | `en` | ✅ | Source subtitle language code |
| `SUBLARR_TARGET_LANGUAGE` | `de` | ✅ | Default target language code |
| `SUBLARR_SOURCE_LANGUAGE_NAME` | `English` | ✅ | Human-readable source language name (used in prompts) |
| `SUBLARR_TARGET_LANGUAGE_NAME` | `German` | ✅ | Human-readable target language name (used in prompts) |
| `SUBLARR_BATCH_SIZE` | `15` | — | Subtitle cues per LLM call |
| `SUBLARR_REQUEST_TIMEOUT` | `90` | — | LLM request timeout in seconds |
| `SUBLARR_TEMPERATURE` | `0.3` | — | LLM temperature (lower = more consistent) |
| `SUBLARR_MAX_RETRIES` | `3` | — | Max retries on LLM failure |
| `SUBLARR_PROMPT_TEMPLATE` | *(empty)* | — | Custom prompt template. Empty = auto-generated |
| `SUBLARR_TRANSLATION_MAX_WORKERS` | `4` | — | Parallel worker threads in the job queue thread pool. Increase for higher translation throughput; decrease on memory-constrained systems. Applies to `MemoryJobQueue` (in-process); with Redis+RQ, scale workers via `--scale rq-worker=N` instead |

---

## Provider System

| Variable | Default | UI | Description |
|---|---|:---:|---|
| `SUBLARR_PROVIDER_PRIORITIES` | `animetosho,jimaku,opensubtitles,subdl` | — | Provider search order (comma-separated) |
| `SUBLARR_PROVIDERS_ENABLED` | *(empty)* | — | Explicit list of enabled providers. Empty = all registered |
| `SUBLARR_PROVIDER_SEARCH_TIMEOUT` | `30` | — | Global fallback timeout per provider (seconds) |
| `SUBLARR_PROVIDER_CACHE_TTL_MINUTES` | `5` | — | Cache TTL for provider search results |
| `SUBLARR_PROVIDER_AUTO_PRIORITIZE` | `true` | — | Auto-prioritize providers based on success rate |
| `SUBLARR_PROVIDER_RATE_LIMIT_ENABLED` | `true` | — | Enable per-provider rate limiting |
| `SUBLARR_PROVIDER_DYNAMIC_TIMEOUT_ENABLED` | `true` | — | Use response time history for dynamic timeouts |
| `SUBLARR_PROVIDER_DYNAMIC_TIMEOUT_MULTIPLIER` | `3.0` | — | Timeout = avg_response_time × multiplier |
| `SUBLARR_PROVIDER_DYNAMIC_TIMEOUT_MIN_SECS` | `5` | — | Minimum dynamic timeout |
| `SUBLARR_PROVIDER_DYNAMIC_TIMEOUT_MAX_SECS` | `30` | — | Maximum dynamic timeout |

### Provider API Keys

Provider credentials can be entered in **Settings → Providers** (API Keys tab) and are
stored encrypted in the database. Environment variables override UI values if set.

| Variable | UI | Provider |
|---|:---:|---|
| `SUBLARR_OPENSUBTITLES_API_KEY` | ✅ | [OpenSubtitles](https://www.opensubtitles.com/en/consumers) |
| `SUBLARR_OPENSUBTITLES_USERNAME` | ✅ | OpenSubtitles account username |
| `SUBLARR_OPENSUBTITLES_PASSWORD` | ✅ | OpenSubtitles account password |
| `SUBLARR_JIMAKU_API_KEY` | ✅ | [Jimaku](https://jimaku.cc/) |
| `SUBLARR_SUBDL_API_KEY` | ✅ | [SubDL](https://subdl.com/) |

AnimeTosho, Gestdown, Podnapisi, and Titrari work without an API key.

---

## Sonarr & Radarr

Configure in **Settings → Sonarr / Radarr**. Environment variables are only needed
for scripted/headless deployments.

| Variable | Default | UI | Description |
|---|---|:---:|---|
| `SUBLARR_SONARR_URL` | *(empty)* | ✅ | Sonarr base URL |
| `SUBLARR_SONARR_API_KEY` | *(empty)* | ✅ | Sonarr API key |
| `SUBLARR_SONARR_INSTANCES_JSON` | *(empty)* | — | JSON array of multiple Sonarr instances |
| `SUBLARR_RADARR_URL` | *(empty)* | ✅ | Radarr base URL |
| `SUBLARR_RADARR_API_KEY` | *(empty)* | ✅ | Radarr API key |
| `SUBLARR_RADARR_INSTANCES_JSON` | *(empty)* | — | JSON array of multiple Radarr instances |
| `SUBLARR_PATH_MAPPING` | *(empty)* | — | Path remapping. Format: `remote=local;remote2=local2` |

Multi-instance JSON format:

```json
[{"name": "Main", "url": "http://sonarr:8989", "api_key": "abc123"}]
```

---

## Media Servers

Configure in **Settings → Media Servers**. Prefer the UI over environment variables —
multi-instance configuration is easier to manage there.

| Variable | Default | UI | Description |
|---|---|:---:|---|
| `SUBLARR_JELLYFIN_URL` | *(empty)* | — | Jellyfin base URL (legacy single-instance) |
| `SUBLARR_JELLYFIN_API_KEY` | *(empty)* | — | Jellyfin API key (legacy) |
| `SUBLARR_MEDIA_SERVERS_JSON` | *(empty)* | ✅ | JSON array of all media server instances |

Media servers JSON format:

```json
[
  {"type": "jellyfin", "name": "Main", "url": "http://jellyfin:8096", "api_key": "abc123"},
  {"type": "plex", "name": "Plex", "url": "http://plex:32400", "token": "xyz789"},
  {"type": "kodi", "name": "Living Room", "url": "http://kodi:8080", "username": "kodi", "password": ""}
]
```

---

## Wanted System & Automation

Configure in **Settings → Automation**. All user-facing toggles and intervals
are available there; the tuning knobs below remain env-only.

| Variable | Default | UI | Description |
|---|---|:---:|---|
| `SUBLARR_WANTED_SCAN_INTERVAL_HOURS` | `0` | ✅ | How often to scan for missing subs. `0` = disabled (event-driven via webhooks) |
| `SUBLARR_WANTED_SCAN_ON_STARTUP` | `false` | ✅ | Run wanted scan when container starts |
| `SUBLARR_WANTED_ANIME_ONLY` | `true` | ✅ | Only scan anime series |
| `SUBLARR_WANTED_ANIME_MOVIES_ONLY` | `false` | ✅ | Filter Radarr movies by anime tag (separate from `WANTED_ANIME_ONLY`) |
| `SUBLARR_WANTED_MAX_SEARCH_ATTEMPTS` | `3` | ✅ | Max provider search attempts per wanted item |
| `SUBLARR_WANTED_AUTO_EXTRACT` | `false` | ✅ | Auto-extract embedded subs during wanted scan |
| `SUBLARR_WANTED_AUTO_TRANSLATE` | `false` | ✅ | Auto-translate after auto-extract during wanted scan |
| `SUBLARR_WANTED_SKIP_SRT_ON_NO_ASS` | `true` | — | Skip SRT steps if no ASS found in steps 1+2 |
| `SUBLARR_WANTED_SEARCH_INTERVAL_HOURS` | `24` | ✅ | Auto-search interval. `0` = disabled |
| `SUBLARR_WANTED_SEARCH_ON_STARTUP` | `false` | ✅ | Run wanted search on container start |
| `SUBLARR_WANTED_SEARCH_MAX_ITEMS_PER_RUN` | `50` | ✅ | Max items to search per scheduler run |
| `SUBLARR_WANTED_ADAPTIVE_BACKOFF_ENABLED` | `true` | — | Exponentially back off for items that keep failing |
| `SUBLARR_WANTED_BACKOFF_BASE_HOURS` | `1.0` | — | Backoff base interval in hours |
| `SUBLARR_WANTED_BACKOFF_CAP_HOURS` | `168` | — | Max backoff cap (7 days) |
| `SUBLARR_USE_EMBEDDED_SUBS` | `true` | — | Check embedded subtitle streams in MKV files |
| `SUBLARR_SCAN_METADATA_ENGINE` | `auto` | — | Metadata scan engine: `ffprobe`, `mediainfo`, or `auto` |
| `SUBLARR_SCAN_METADATA_MAX_WORKERS` | `4` | — | Parallel workers for batch metadata scans |
| `SUBLARR_SCAN_YIELD_MS` | `0` | — | Sleep between series/movies (ms) during wanted scan to yield CPU to API threads. Default `0` (no yield). Try `5`–`10` on heavily loaded single-core systems |

---

## Webhook Automation

Configure in **Settings → Automation**.

| Variable | Default | UI | Description |
|---|---|:---:|---|
| `SUBLARR_WEBHOOK_DELAY_MINUTES` | `5` | ✅ | Wait after Sonarr/Radarr webhook before processing |
| `SUBLARR_WEBHOOK_AUTO_SCAN` | `true` | ✅ | Auto-scan file after webhook |
| `SUBLARR_WEBHOOK_AUTO_SEARCH` | `true` | ✅ | Auto-search providers after webhook |
| `SUBLARR_WEBHOOK_AUTO_TRANSLATE` | `true` | ✅ | Auto-translate after webhook download |

---

## Upgrade System

Configure in **Settings → Automation**.

| Variable | Default | UI | Description |
|---|---|:---:|---|
| `SUBLARR_UPGRADE_ENABLED` | `true` | ✅ | Replace low-quality subs when better version found |
| `SUBLARR_UPGRADE_MIN_SCORE_DELTA` | `50` | ✅ | Minimum score improvement required for upgrade |
| `SUBLARR_UPGRADE_WINDOW_DAYS` | `7` | ✅ | Recent subs within this window require 2x delta |
| `SUBLARR_UPGRADE_PREFER_ASS` | `true` | ✅ | Always upgrade SRT to ASS when available |

---

## Video Sync

Env-only — no UI configuration yet.

| Variable | Default | UI | Description |
|---|---|:---:|---|
| `SUBLARR_AUTO_SYNC_AFTER_DOWNLOAD` | `false` | — | Auto-sync subtitle timing against video after download |
| `SUBLARR_AUTO_SYNC_ENGINE` | `ffsubsync` | — | Sync engine: `ffsubsync` or `alass` |

---

## Notifications (Apprise)

Env-only — configure via Apprise URL strings.

| Variable | Default | UI | Description |
|---|---|:---:|---|
| `SUBLARR_NOTIFICATION_URLS_JSON` | *(empty)* | — | JSON array of Apprise notification URLs |
| `SUBLARR_NOTIFY_ON_DOWNLOAD` | `true` | — | Notify on subtitle download |
| `SUBLARR_NOTIFY_ON_UPGRADE` | `true` | — | Notify on subtitle upgrade |
| `SUBLARR_NOTIFY_ON_BATCH_COMPLETE` | `true` | — | Notify when batch search/translate completes |
| `SUBLARR_NOTIFY_ON_ERROR` | `true` | — | Notify on errors |
| `SUBLARR_NOTIFY_MANUAL_ACTIONS` | `false` | — | Notify on manual user-triggered actions |

---

## Circuit Breaker

Env-only — tuning knobs for provider failure handling.

| Variable | Default | UI | Description |
|---|---|:---:|---|
| `SUBLARR_CIRCUIT_BREAKER_FAILURE_THRESHOLD` | `5` | — | Consecutive failures before opening circuit |
| `SUBLARR_CIRCUIT_BREAKER_COOLDOWN_SECONDS` | `60` | — | Seconds in OPEN state before half-open probe |
| `SUBLARR_PROVIDER_AUTO_DISABLE_COOLDOWN_MINUTES` | `30` | — | Minutes before auto-disabled provider is re-enabled |

---

## Backup

Env-only — backup directory and retention policy.

| Variable | Default | UI | Description |
|---|---|:---:|---|
| `SUBLARR_BACKUP_DIR` | `/config/backups` | — | Backup storage directory |
| `SUBLARR_BACKUP_RETENTION_DAILY` | `7` | — | Keep last N daily backups |
| `SUBLARR_BACKUP_RETENTION_WEEKLY` | `4` | — | Keep last N weekly backups |
| `SUBLARR_BACKUP_RETENTION_MONTHLY` | `3` | — | Keep last N monthly backups |

---

## Standalone Mode (no Sonarr/Radarr)

Configure in **Settings → Library Sources**.

| Variable | Default | UI | Description |
|---|---|:---:|---|
| `SUBLARR_STANDALONE_ENABLED` | `false` | ✅ | Enable folder-watch mode without Sonarr/Radarr |
| `SUBLARR_STANDALONE_SCAN_INTERVAL_HOURS` | `6` | ✅ | Folder scan interval in hours. `0` = disabled |
| `SUBLARR_STANDALONE_DEBOUNCE_SECONDS` | `10` | ✅ | Seconds to wait after a new file is detected before processing |
| `SUBLARR_TMDB_API_KEY` | *(empty)* | ✅ | TMDB API v3 bearer token (for metadata lookup) |
| `SUBLARR_TVDB_API_KEY` | *(empty)* | ✅ | TVDB API v4 key (optional) |
| `SUBLARR_TVDB_PIN` | *(empty)* | ✅ | TVDB PIN (optional, for subscriber features) |
| `SUBLARR_METADATA_CACHE_TTL_DAYS` | `30` | — | Days to cache metadata responses |

---

## AniDB Integration

Env-only — controls AniDB ID resolution for absolute anime episode ordering.

| Variable | Default | UI | Description |
|---|---|:---:|---|
| `SUBLARR_ANIDB_ENABLED` | `true` | — | Enable AniDB ID resolution for absolute episode ordering |
| `SUBLARR_ANIDB_CACHE_TTL_DAYS` | `30` | — | Cache TTL for TVDB to AniDB mappings |
| `SUBLARR_ANIDB_CUSTOM_FIELD_NAME` | `anidb_id` | — | Custom field name in Sonarr for AniDB ID |
| `SUBLARR_ANIDB_FALLBACK_TO_MAPPING` | `true` | — | Use cached mapping as fallback when AniDB is unreachable |

---

## Database and Redis (Advanced)

Env-only — infrastructure-level backend selection. Most deployments use the SQLite default.

| Variable | Default | UI | Description |
|---|---|:---:|---|
| `SUBLARR_DATABASE_URL` | *(empty)* | — | SQLAlchemy URL. Empty = SQLite at `DB_PATH` |
| `SUBLARR_DB_POOL_SIZE` | `5` | — | SQLAlchemy pool_size (ignored for SQLite) |
| `SUBLARR_DB_POOL_MAX_OVERFLOW` | `10` | — | SQLAlchemy max_overflow (ignored for SQLite) |
| `SUBLARR_DB_POOL_RECYCLE` | `3600` | — | Recycle connections after N seconds |
| `SUBLARR_REDIS_URL` | *(empty)* | — | Redis URL (e.g. `redis://localhost:6379/0`). Empty = no Redis; falls back to in-process `MemoryJobQueue` + in-memory provider cache automatically |
| `SUBLARR_REDIS_CACHE_ENABLED` | `true` | — | Use Redis for provider search cache (when redis_url set). Disable to keep Redis only for the job queue |
| `SUBLARR_REDIS_QUEUE_ENABLED` | `true` | — | Use Redis+RQ for job queue (when redis_url set). Requires a separate `rq worker` process — use `docker-compose.redis.yml` or run `python backend/worker.py`. Scale with `docker compose ... --scale rq-worker=N` |

---

## Stream Removal / Remux

Configure in **Settings → Automation → Stream Removal**.

| Variable | Default | UI | Description |
|---|---|:---:|---|
| `SUBLARR_REMUX_TRASH_DIR` | `.sublarr` | ✅ | Relative (to media root) or absolute path for the remux backup trash folder. Backups land in `<trash_dir>/trash/<YYYY-MM-DD>/<file>.<ts>.bak` |
| `SUBLARR_REMUX_BACKUP_RETENTION_DAYS` | `7` | ✅ | Days to keep remux backups. `0` = keep forever |
| `SUBLARR_REMUX_USE_REFLINK` | `true` | ✅ | Attempt CoW reflink for zero-cost backups on Btrfs/XFS before falling back to a regular copy |
| `SUBLARR_REMUX_ARR_PAUSE_ENABLED` | `true` | ✅ | Pause Sonarr/Radarr folder monitoring during the remux operation |

**Backend selection:** mkvmerge (MKV/MK3D) or ffmpeg (MP4, AVI, all others) — auto-detected by file extension. If mkvmerge is not available, falls back to ffmpeg with a warning (install `mkvtoolnix` for better MKV support). mkvtoolnix is included in the official Docker image.

---

## Sidecar Auto-Cleanup

Automatically delete extra-language sidecar files after batch-extract to keep the media directory tidy.
Configure in **Settings → Automation**.

| Variable | Default | UI | Description |
|---|---|:---:|---|
| `SUBLARR_AUTO_CLEANUP_AFTER_EXTRACT` | `false` | ✅ | Delete extra-language sidecars after batch-extract |
| `SUBLARR_AUTO_CLEANUP_KEEP_LANGUAGES` | *(empty)* | ✅ | Comma-separated ISO-639-1 codes to keep (empty = nothing deleted) |
| `SUBLARR_AUTO_CLEANUP_KEEP_FORMATS` | `any` | ✅ | `ass`, `srt`, or `any` — delete SRT when ASS exists for same lang |

---

## Subtitle Trash

Soft-delete for subtitles. Trashed files are moved to a `.trash` directory and auto-purged after N days.
Configure in **Settings → Automation**.

| Variable | Default | UI | Description |
|---|---|:---:|---|
| `SUBLARR_SUBTITLE_TRASH_RETENTION_DAYS` | `7` | ✅ | Days to keep trashed files before auto-purge. `0` = keep forever |

---

## Hearing Impaired

Configure in **Settings → Translation**.

| Variable | Default | UI | Description |
|---|---|:---:|---|
| `SUBLARR_HI_REMOVAL_ENABLED` | `false` | ✅ | Strip hearing-impaired annotations from subtitles on download |

---

## Credit Filtering

Configure in **Settings → Translation**.

| Variable | Default | UI | Description |
|---|---|:---:|---|
| `SUBLARR_CREDIT_THRESHOLD_SEC` | `90` | ✅ | Seconds from the end of a subtitle file treated as the credits region by the duration heuristic in credit detection. |

---

## Plugin System

Env-only — plugin directory is infrastructure; hot-reload is a dev convenience.

| Variable | Default | UI | Description |
|---|---|:---:|---|
| `SUBLARR_PLUGINS_DIR` | `/config/plugins` | — | Provider plugin directory |
| `SUBLARR_PLUGIN_HOT_RELOAD` | `false` | — | Enable watchdog file watcher for live plugin reload |

---

See [.env.example](.env.example) for the minimal deployment template.
