# API Reference — Sublarr

All endpoints use the prefix `/api/v1/`. Authentication is via `X-Api-Key` header or UI session cookie unless noted otherwise.

---

## Auth

| Method | Path | Auth | Rate Limit | Description |
|--------|------|------|------------|-------------|
| GET | `/auth/status` | No | — | Check auth state (configured, enabled, authenticated) |
| POST | `/auth/setup` | No | — | First-run: set password (`action: "set_password"`) or disable auth (`action: "disable"`) |
| POST | `/auth/login` | No | 10/min, 30/hour | Verify password and create session |
| POST | `/auth/logout` | Session | — | Clear session |
| POST | `/auth/change-password` | Session | — | Update password (min 12 chars) |
| POST | `/auth/toggle` | Session or API key | — | Enable/disable UI auth |

---

## Library

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/library` | Yes | List all series (Sonarr) and movies (Radarr) with profile assignments and missing counts |
| GET | `/library/series/<series_id>` | Yes | [PLEASE VERIFY] Series detail with episodes |
| GET | `/library/episodes/<ep_id>/subtitles` | Yes | List subtitle sidecar files for one episode |
| GET | `/library/series/<series_id>/subtitles` | Yes | List subtitle sidecars for all episodes in a series |
| DELETE | `/library/subtitles` | Yes | Move one or more sidecar files to trash |
| POST | `/library/series/<series_id>/subtitles/batch-delete` | Yes | Batch-trash by language/format filter |
| GET | `/library/trash` | Yes | List all trash batches |
| POST | `/library/trash/<batch_id>/restore` | Yes | Restore a trash batch |
| DELETE | `/library/trash/<batch_id>` | Yes | Permanently delete a trash batch |

---

## Search

| Method | Path | Auth | Rate Limit | Description |
|--------|------|------|------------|-------------|
| GET | `/search` | Yes | 60/min | Full-text search across series, episodes, and subtitles (FTS5 trigram). Params: `q` (min 2 chars), `limit` (max 50) |
| POST | `/search/rebuild-index` | Yes | 5/min | Rebuild FTS5 search index from current DB state |

---

## Subtitles

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/subtitles/download` | Yes | Download a subtitle file by path (query param `path`) |
| GET | `/series/<series_id>/subtitles/export` | Yes | Export series subtitles as ZIP |
| POST | `/subtitles/export-nfo` | Yes | Export NFO sidecar for a single subtitle (query param `path`) |
| POST | `/series/<series_id>/subtitles/export-nfo` | Yes | Bulk NFO export for all subtitles in a series |

---

## Translation

| Method | Path | Auth | Rate Limit | Description |
|--------|------|------|------------|-------------|
| POST | `/translate` | Yes | 30/min | Start async translation job. Returns job ID |
| POST | `/translate/sync` | Yes | 30/min | Synchronous translation (blocks until complete) |
| GET | `/status/<job_id>` | Yes | — | Get translation job status |
| GET | `/jobs` | Yes | — | List translation jobs |
| POST | `/jobs/<job_id>/retry` | Yes | — | Retry a failed translation job |
| POST | `/translate/batch` | Yes | 5/min | Batch translate multiple files |
| GET | `/translate/batch/status` | Yes | — | Batch translation status |
| POST | `/translate/retranslate/<job_id>` | Yes | — | Re-translate a completed job |
| POST | `/translate/retranslate/batch` | Yes | — | Batch re-translate |
| GET | `/translate/retranslate/status` | Yes | — | Re-translate batch status |
| GET | `/translate/backends` | Yes | — | List available translation backends and status |
| POST | `/translate/backends/test/<name>` | Yes | — | Test a specific backend |
| GET | `/translate/backends/<name>/config` | Yes | — | Get backend config |
| PUT | `/translate/backends/<name>/config` | Yes | — | Update backend config |
| GET | `/translate/backends/templates` | Yes | — | Get backend config templates |
| POST | `/translate/backends/ollama/pull` | Yes | — | Pull an Ollama model |
| GET | `/translate/backends/stats` | Yes | — | Backend performance stats |
| GET | `/translate/translation-memory/stats` | Yes | — | Translation memory cache stats |
| DELETE | `/translate/translation-memory/cache` | Yes | — | Clear translation memory cache |

Note: Translation routes are registered under the `/api/v1/translate` blueprint. [PLEASE VERIFY] exact prefix for nested routes like `/backends` and `/translation-memory`.

---

## Wanted

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/wanted` | Yes | Paginated list of wanted subtitle items. Params: `page`, `per_page`, `type`, `status`, `series_id`, `subtitle_type` |
| POST | `/wanted/batch-search` | Yes | Batch search providers for wanted items. Accepts `item_ids` or `series_ids` |
| POST | `/wanted/batch-translate` | Yes | Batch translate multiple wanted items |

---

## Webhooks

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/webhook/sonarr` | HMAC signature | Sonarr download/upgrade webhook — triggers scan/search/translate pipeline |
| POST | `/webhook/radarr` | HMAC signature | Radarr download/upgrade webhook — triggers scan/search/translate pipeline |
| POST | `/webhook/jellyfin` | HMAC signature | Jellyfin playback-start webhook — triggers subtitle search on play |

Webhook auth: Exempt from API key check. Each handler validates HMAC signature from the `X-Webhook-Signature` header using `hmac.compare_digest()`.

---

## Tools

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/tools/remove-hi` | Yes | Remove hearing-impaired markers from a subtitle file |
| POST | `/tools/adjust-timing` | Yes | Adjust subtitle timing (offset) |
| POST | `/tools/common-fixes` | Yes | Apply common subtitle fixes |
| POST | `/tools/preview` | Yes | Preview subtitle content |
| POST | `/tools/content` | Yes | [PLEASE VERIFY] Get subtitle content |
| POST | `/tools/backup` | Yes | Create subtitle backup |
| POST | `/tools/validate` | Yes | Validate subtitle file |
| POST | `/tools/parse` | Yes | Parse subtitle file |
| POST | `/tools/health-check` | Yes | Subtitle health check |
| POST | `/tools/health-fix` | Yes | Auto-fix subtitle health issues |
| POST | `/tools/auto-sync` | Yes | Sync subtitle timing to video (ffsubsync/alass) |
| POST | `/tools/compare` | Yes | Compare two subtitle files |
| POST | `/tools/diff` | Yes | Compute cue-level diff between two subtitle versions |
| POST | `/tools/diff/apply` | Yes | Apply accepted/rejected diff changes |
| POST | `/tools/remove-credits` | Yes | Detect and remove credit lines |
| POST | `/tools/detect-opening-ending` | Yes | Detect OP/ED regions in subtitle file |
| POST | `/tools/advanced-sync` | Yes | Advanced sync with chapter range support |
| GET | `/tools/quality-trends` | Yes | [PLEASE VERIFY] Subtitle quality trend data |

---

## Config

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/config` | Yes | Get current configuration (secrets masked with `***configured***`) |
| PUT | `/config` | Yes | Update configuration values. Validates enum fields and URL fields (SSRF protection) |
| POST | `/settings/path-mapping/test` | Yes | Test a Sonarr/Radarr path mapping |
| POST | `/config/export` | Yes | [PLEASE VERIFY] Export configuration |
| POST | `/config/import` | Yes | [PLEASE VERIFY] Import configuration |

---

## System / Health

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/health` | No | Health check — status, version (auth-gated since 0.31.0), service connectivity |
| GET | `/health/detailed` | Yes | Detailed health with per-service breakdown |
| GET | `/update` | Yes | Check for new version via GitHub releases |
| GET | `/stats` | Yes | System statistics |
| GET | `/statistics` | Yes | Detailed usage statistics |
| GET | `/statistics/export` | Yes | Export statistics as CSV |
| GET | `/logs` | Yes | Recent log entries |
| GET | `/logs/download` | Yes | Download log file |
| GET | `/logs/rotation` | Yes | Get log rotation config |
| PUT | `/logs/rotation` | Yes | Update log rotation config |
| GET | `/database/health` | Yes | Database health status |
| POST | `/database/backup` | Yes | Create database backup |
| GET | `/database/backups` | Yes | List database backups |
| POST | `/database/restore` | Yes | Restore database from backup |
| POST | `/database/vacuum` | Yes | Run VACUUM on database |
| POST | `/backup/full` | Yes | Full backup (DB + config + subtitles) |
| GET | `/backup/full/download/<filename>` | Yes | Download a full backup file |
| POST | `/backup/full/restore` | Yes | Restore from full backup |
| GET | `/backup/full/list` | Yes | List full backups |
| GET | `/cache/ffprobe/stats` | Yes | ffprobe cache statistics |
| POST | `/cache/ffprobe/cleanup` | Yes | Clean up ffprobe cache |
| GET | `/tasks` | Yes | List background tasks and their state |
| POST | `/tasks/<name>/cancel` | Yes | Cancel a background task |
| POST | `/tasks/cleanup/trigger` | Yes | Trigger cleanup task |
| POST | `/tasks/upgrade-scan/trigger` | Yes | Trigger upgrade scan task |
| POST | `/tasks/cleanup-jobs` | Yes | Clean up old translation jobs |
| GET | `/notifications/test` | Yes | [PLEASE VERIFY] Test notification delivery |
| GET | `/notifications/status` | Yes | Notification system status |
| GET | `/openapi.json` | Yes | OpenAPI spec (auto-generated) |

---

## Metrics

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/metrics` | Yes | Prometheus metrics endpoint. Exposes system (CPU, memory, disk), business (translation counts/duration), queue, database, cache, Redis, HTTP, and circuit breaker metrics |

---

## Media

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/media/stream` | API key required | Stream video file with HTTP 206 range support. Query param: `path`. Requires `streaming_enabled` setting. `is_safe_path()` enforced |

---

## WebSocket

| Protocol | Path | Auth | Description |
|----------|------|------|-------------|
| Socket.IO (EIO4) | `/socket.io` | API key on connect | Real-time events: translation progress, webhook pipeline status, log messages, task updates. Namespace connect requires valid API key |

---

## Additional Route Groups

These routes exist but are not documented in detail here. See the corresponding route files for specifics.

| Route file | Prefix | Purpose |
|------------|--------|---------|
| `providers.py` | `/providers` | Subtitle provider management, stats, search |
| `profiles.py` | `/profiles` | Language profile CRUD |
| `languages.py` | `/languages` | Available language list |
| `plugins.py` | `/plugins` | Plugin management |
| `marketplace.py` | `/marketplace` | Plugin marketplace (GitHub discovery, install, uninstall) |
| `glossary` (in library.py) | `/glossary` | Glossary term CRUD, suggest, export |
| `api_keys.py` | `/api-keys` | Service API key management, import/export |
| `standalone.py` | `/standalone` | Standalone mode scanner and library |
| `whisper.py` | `/whisper` | Whisper transcription endpoints |
| `video_sync.py` | `/video-sync` | Video-based subtitle sync |
| `audio.py` | `/audio` | Audio waveform and extraction |
| `ocr.py` | `/ocr` | OCR subtitle extraction |
| `hooks.py` | `/hooks` | Lifecycle hook management |
| `blacklist.py` | `/blacklist` | Provider result blacklist |
| `filter_presets.py` | `/filter-presets` | Saved filter preset CRUD |
| `fansub_prefs.py` | `/fansub-prefs` | Per-series fansub group preferences |
| `anidb_mapping.py` | `/anidb` | AniDB-TVDB mapping management |
| `tracks.py` | `/tracks` | [PLEASE VERIFY] Media track info |
| `remux.py` | `/remux` | [PLEASE VERIFY] Remux operations |
| `nfo.py` | `/nfo` | NFO metadata endpoints |
| `mediaservers.py` | `/mediaservers` | Media server (Jellyfin/Emby) management |
| `integrations.py` | `/integrations` | External integration management |
| `notifications_mgmt.py` | `/notifications` | Notification channel management |
| `spell.py` | `/spell` | Spell checking |
| `cleanup.py` | `/cleanup` | [PLEASE VERIFY] Cleanup operations |
| `video.py` | `/video` | [PLEASE VERIFY] Video file operations |
| `series_audio.py` | `/series-audio` | Per-series audio track preferences |
