# Configuration Reference

All Sublarr settings use the `SUBLARR_` prefix and can be set via:

1. **Environment variables** (highest priority): `SUBLARR_PORT=8080`
2. **`.env` file** in the working directory
3. **Settings UI** at runtime (stored in the `config_entries` database table)

---

## Core

| Variable | Default | Description |
|---|---|---|
| `SUBLARR_MEDIA_PATH` | `/media` | Root path of your media library |
| `SUBLARR_DB_PATH` | `/config/sublarr.db` | SQLite database location |
| `SUBLARR_DATABASE_URL` | *(empty)* | Full SQLAlchemy URL (e.g. `postgresql://...`). Overrides `DB_PATH` when set |
| `SUBLARR_PORT` | `5765` | HTTP port |
| `SUBLARR_API_KEY` | *(empty)* | Optional API key for auth (`X-Api-Key` header). Empty = no auth |
| `SUBLARR_LOG_LEVEL` | `INFO` | Log level: `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `SUBLARR_LOG_FILE` | `log/sublarr.log` | Log file path. Docker default: `/config/sublarr.log` |
| `SUBLARR_LOG_FORMAT` | `text` | Log format: `text` or `json` (structured for log aggregation) |
| `PUID` / `PGID` | `1000` | Container user/group IDs for volume file permissions |

---

## Translation

| Variable | Default | Description |
|---|---|---|
| `SUBLARR_OLLAMA_URL` | `http://localhost:11434` | Ollama base URL |
| `SUBLARR_OLLAMA_MODEL` | `qwen2.5:14b-instruct` | Model for translation. Recommended: `hf.co/Sublarr/anime-translator-v6-GGUF:Q4_K_M` (custom fine-tuned, EN→DE anime subtitles — see [huggingface.co/Sublarr](https://huggingface.co/Sublarr)) |
| `SUBLARR_SOURCE_LANGUAGE` | `en` | Source subtitle language code |
| `SUBLARR_TARGET_LANGUAGE` | `de` | Default target language code |
| `SUBLARR_SOURCE_LANGUAGE_NAME` | `English` | Human-readable source language name (used in prompts) |
| `SUBLARR_TARGET_LANGUAGE_NAME` | `German` | Human-readable target language name (used in prompts) |
| `SUBLARR_BATCH_SIZE` | `15` | Subtitle cues per LLM call |
| `SUBLARR_REQUEST_TIMEOUT` | `90` | LLM request timeout in seconds |
| `SUBLARR_TEMPERATURE` | `0.3` | LLM temperature (lower = more consistent) |
| `SUBLARR_MAX_RETRIES` | `3` | Max retries on LLM failure |
| `SUBLARR_PROMPT_TEMPLATE` | *(empty)* | Custom prompt template. Empty = auto-generated |

---

## Provider System

| Variable | Default | Description |
|---|---|---|
| `SUBLARR_PROVIDER_PRIORITIES` | `animetosho,jimaku,opensubtitles,subdl` | Provider search order (comma-separated) |
| `SUBLARR_PROVIDERS_ENABLED` | *(empty)* | Explicit list of enabled providers. Empty = all registered |
| `SUBLARR_PROVIDER_SEARCH_TIMEOUT` | `30` | Global fallback timeout per provider (seconds) |
| `SUBLARR_PROVIDER_CACHE_TTL_MINUTES` | `5` | Cache TTL for provider search results |
| `SUBLARR_PROVIDER_AUTO_PRIORITIZE` | `true` | Auto-prioritize providers based on success rate |
| `SUBLARR_PROVIDER_RATE_LIMIT_ENABLED` | `true` | Enable per-provider rate limiting |
| `SUBLARR_PROVIDER_DYNAMIC_TIMEOUT_ENABLED` | `true` | Use response time history for dynamic timeouts |
| `SUBLARR_PROVIDER_DYNAMIC_TIMEOUT_MULTIPLIER` | `3.0` | Timeout = avg_response_time × multiplier |
| `SUBLARR_PROVIDER_DYNAMIC_TIMEOUT_MIN_SECS` | `5` | Minimum dynamic timeout |
| `SUBLARR_PROVIDER_DYNAMIC_TIMEOUT_MAX_SECS` | `30` | Maximum dynamic timeout |

### Provider API Keys

| Variable | Provider |
|---|---|
| `SUBLARR_OPENSUBTITLES_API_KEY` | [OpenSubtitles](https://www.opensubtitles.com/en/consumers) |
| `SUBLARR_OPENSUBTITLES_USERNAME` | OpenSubtitles account username |
| `SUBLARR_OPENSUBTITLES_PASSWORD` | OpenSubtitles account password |
| `SUBLARR_JIMAKU_API_KEY` | [Jimaku](https://jimaku.cc/) |
| `SUBLARR_SUBDL_API_KEY` | [SubDL](https://subdl.com/) |

AnimeTosho, Gestdown, Podnapisi, and Titrari work without an API key.

---

## Sonarr & Radarr

| Variable | Default | Description |
|---|---|---|
| `SUBLARR_SONARR_URL` | *(empty)* | Sonarr base URL |
| `SUBLARR_SONARR_API_KEY` | *(empty)* | Sonarr API key |
| `SUBLARR_SONARR_INSTANCES_JSON` | *(empty)* | JSON array of multiple Sonarr instances |
| `SUBLARR_RADARR_URL` | *(empty)* | Radarr base URL |
| `SUBLARR_RADARR_API_KEY` | *(empty)* | Radarr API key |
| `SUBLARR_RADARR_INSTANCES_JSON` | *(empty)* | JSON array of multiple Radarr instances |
| `SUBLARR_PATH_MAPPING` | *(empty)* | Path remapping. Format: `remote=local;remote2=local2` |

Multi-instance JSON format:

```json
[{"name": "Main", "url": "http://sonarr:8989", "api_key": "abc123"}]
```

---

## Media Servers

| Variable | Default | Description |
|---|---|---|
| `SUBLARR_JELLYFIN_URL` | *(empty)* | Jellyfin base URL (legacy single-instance) |
| `SUBLARR_JELLYFIN_API_KEY` | *(empty)* | Jellyfin API key (legacy) |
| `SUBLARR_MEDIA_SERVERS_JSON` | *(empty)* | JSON array of all media server instances |

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

| Variable | Default | Description |
|---|---|---|
| `SUBLARR_WANTED_SCAN_INTERVAL_HOURS` | `6` | How often to scan for missing subs. `0` = disabled |
| `SUBLARR_WANTED_SCAN_ON_STARTUP` | `true` | Run wanted scan when container starts |
| `SUBLARR_WANTED_ANIME_ONLY` | `true` | Only scan anime series |
| `SUBLARR_WANTED_MAX_SEARCH_ATTEMPTS` | `3` | Max provider search attempts per wanted item |
| `SUBLARR_WANTED_SEARCH_INTERVAL_HOURS` | `24` | Auto-search interval. `0` = disabled |
| `SUBLARR_WANTED_SEARCH_MAX_ITEMS_PER_RUN` | `50` | Max items to search per scheduler run |
| `SUBLARR_WANTED_ADAPTIVE_BACKOFF_ENABLED` | `true` | Exponentially back off for items that keep failing |
| `SUBLARR_WANTED_BACKOFF_CAP_HOURS` | `168` | Max backoff cap (7 days) |
| `SUBLARR_USE_EMBEDDED_SUBS` | `true` | Check embedded subtitle streams in MKV files |
| `SUBLARR_SCAN_METADATA_MAX_WORKERS` | `4` | Parallel workers for batch metadata scans |

---

## Webhook Automation

| Variable | Default | Description |
|---|---|---|
| `SUBLARR_WEBHOOK_DELAY_MINUTES` | `5` | Wait after Sonarr/Radarr webhook before processing |
| `SUBLARR_WEBHOOK_AUTO_SCAN` | `true` | Auto-scan file after webhook |
| `SUBLARR_WEBHOOK_AUTO_SEARCH` | `true` | Auto-search providers after webhook |
| `SUBLARR_WEBHOOK_AUTO_TRANSLATE` | `true` | Auto-translate after webhook download |

---

## Upgrade System

| Variable | Default | Description |
|---|---|---|
| `SUBLARR_UPGRADE_ENABLED` | `true` | Replace low-quality subs when better version found |
| `SUBLARR_UPGRADE_MIN_SCORE_DELTA` | `50` | Minimum score improvement required for upgrade |
| `SUBLARR_UPGRADE_WINDOW_DAYS` | `7` | Recent subs within this window require 2x delta |
| `SUBLARR_UPGRADE_PREFER_ASS` | `true` | Always upgrade SRT to ASS when available |

---

## Video Sync

| Variable | Default | Description |
|---|---|---|
| `SUBLARR_AUTO_SYNC_AFTER_DOWNLOAD` | `false` | Auto-sync subtitle timing against video after download |
| `SUBLARR_AUTO_SYNC_ENGINE` | `ffsubsync` | Sync engine: `ffsubsync` or `alass` |

---

## Notifications (Apprise)

| Variable | Default | Description |
|---|---|---|
| `SUBLARR_NOTIFICATION_URLS_JSON` | *(empty)* | JSON array of Apprise notification URLs |
| `SUBLARR_NOTIFY_ON_DOWNLOAD` | `true` | Notify on subtitle download |
| `SUBLARR_NOTIFY_ON_UPGRADE` | `true` | Notify on subtitle upgrade |
| `SUBLARR_NOTIFY_ON_BATCH_COMPLETE` | `true` | Notify when batch search/translate completes |
| `SUBLARR_NOTIFY_ON_ERROR` | `true` | Notify on errors |

---

## Circuit Breaker

| Variable | Default | Description |
|---|---|---|
| `SUBLARR_CIRCUIT_BREAKER_FAILURE_THRESHOLD` | `5` | Consecutive failures before opening circuit |
| `SUBLARR_CIRCUIT_BREAKER_COOLDOWN_SECONDS` | `60` | Seconds in OPEN state before half-open probe |
| `SUBLARR_PROVIDER_AUTO_DISABLE_COOLDOWN_MINUTES` | `30` | Minutes before auto-disabled provider is re-enabled |

---

## Backup

| Variable | Default | Description |
|---|---|---|
| `SUBLARR_BACKUP_DIR` | `/config/backups` | Backup storage directory |
| `SUBLARR_BACKUP_RETENTION_DAILY` | `7` | Keep last N daily backups |
| `SUBLARR_BACKUP_RETENTION_WEEKLY` | `4` | Keep last N weekly backups |
| `SUBLARR_BACKUP_RETENTION_MONTHLY` | `3` | Keep last N monthly backups |

---

## Standalone Mode (no Sonarr/Radarr)

| Variable | Default | Description |
|---|---|---|
| `SUBLARR_STANDALONE_ENABLED` | `false` | Enable folder-watch mode without Sonarr/Radarr |
| `SUBLARR_STANDALONE_SCAN_INTERVAL_HOURS` | `6` | Folder scan interval in hours |
| `SUBLARR_TMDB_API_KEY` | *(empty)* | TMDB API v3 bearer token (for metadata lookup) |
| `SUBLARR_TVDB_API_KEY` | *(empty)* | TVDB API v4 key (optional) |
| `SUBLARR_METADATA_CACHE_TTL_DAYS` | `30` | Days to cache metadata responses |

---

## AniDB Integration

| Variable | Default | Description |
|---|---|---|
| `SUBLARR_ANIDB_ENABLED` | `true` | Enable AniDB ID resolution for absolute episode ordering |
| `SUBLARR_ANIDB_CACHE_TTL_DAYS` | `30` | Cache TTL for TVDB to AniDB mappings |
| `SUBLARR_ANIDB_CUSTOM_FIELD_NAME` | `anidb_id` | Custom field name in Sonarr for AniDB ID |

---

## Database and Redis (Advanced)

| Variable | Default | Description |
|---|---|---|
| `SUBLARR_DATABASE_URL` | *(empty)* | SQLAlchemy URL. Empty = SQLite at `DB_PATH` |
| `SUBLARR_DB_POOL_SIZE` | `5` | SQLAlchemy pool_size (ignored for SQLite) |
| `SUBLARR_DB_POOL_MAX_OVERFLOW` | `10` | SQLAlchemy max_overflow (ignored for SQLite) |
| `SUBLARR_DB_POOL_RECYCLE` | `3600` | Recycle connections after N seconds |
| `SUBLARR_REDIS_URL` | *(empty)* | Redis URL (e.g. `redis://localhost:6379/0`). Empty = no Redis |
| `SUBLARR_REDIS_CACHE_ENABLED` | `true` | Use Redis for provider search cache (when redis_url set) |
| `SUBLARR_REDIS_QUEUE_ENABLED` | `true` | Use Redis+RQ for job queue (when redis_url set) |

---

## Plugin System

| Variable | Default | Description |
|---|---|---|
| `SUBLARR_PLUGINS_DIR` | `/config/plugins` | Provider plugin directory |
| `SUBLARR_PLUGIN_HOT_RELOAD` | `false` | Enable watchdog file watcher for live plugin reload |

---

See [.env.example](.env.example) for a complete annotated template.
