# Database Schema

Sublarr uses SQLite by default (PostgreSQL supported via `SUBLARR_DATABASE_URL`).

The database is at `/config/sublarr.db` inside the container.

---

## Core Tables

### `jobs`

Tracks all background jobs (translation, search, sync, OCR).

| Column | Type | Description |
|---|---|---|
| `id` | TEXT | UUID primary key |
| `type` | TEXT | Job type: `translate`, `search`, `sync`, `ocr`, `batch` |
| `status` | TEXT | `pending`, `running`, `done`, `error` |
| `file_path` | TEXT | Target file path |
| `progress` | INTEGER | 0–100 progress percentage |
| `error_msg` | TEXT | Error message if status = `error` |
| `created_at` | DATETIME | Job creation timestamp |
| `updated_at` | DATETIME | Last status update |
| `result_json` | TEXT | JSON blob with job results |

### `daily_stats`

Aggregates subtitle activity per day for the Statistics page.

| Column | Type | Description |
|---|---|---|
| `date` | TEXT | ISO date string `YYYY-MM-DD` |
| `downloads` | INTEGER | Subtitles downloaded that day |
| `translations` | INTEGER | Translations completed |
| `upgrades` | INTEGER | Subtitle upgrades performed |
| `failures` | INTEGER | Failed operations |

### `config_entries`

Runtime configuration overrides that take precedence over environment variables.
Edited via the Settings UI.

| Column | Type | Description |
|---|---|---|
| `key` | TEXT | Setting key (e.g. `ollama_model`) |
| `value` | TEXT | Setting value as string |
| `updated_at` | DATETIME | Last update timestamp |

### `wanted_items`

Queue of episodes/movies that need subtitles.

| Column | Type | Description |
|---|---|---|
| `id` | INTEGER | Auto-increment primary key |
| `file_path` | TEXT | Absolute path to video file |
| `series_id` | INTEGER | Sonarr/Radarr series ID |
| `episode_id` | INTEGER | Sonarr episode ID (NULL for movies) |
| `title` | TEXT | Series/movie title |
| `season` | INTEGER | Season number |
| `episode` | INTEGER | Episode number |
| `target_language` | TEXT | Target subtitle language |
| `subtitle_type` | TEXT | `ass`, `srt`, or `any` |
| `existing_sub` | TEXT | Path to existing subtitle (empty = missing) |
| `attempts` | INTEGER | Number of search attempts made |
| `next_attempt_at` | DATETIME | Adaptive backoff: earliest next attempt time |
| `created_at` | DATETIME | When the item was first detected |
| `updated_at` | DATETIME | Last update |

Unique constraint: `(file_path, target_language, subtitle_type)` prevents duplicates.

### `upgrade_history`

Records every subtitle upgrade performed.

| Column | Type | Description |
|---|---|---|
| `id` | INTEGER | Auto-increment primary key |
| `file_path` | TEXT | Video file path |
| `old_subtitle` | TEXT | Path to replaced subtitle |
| `new_subtitle` | TEXT | Path to replacement subtitle |
| `old_score` | INTEGER | Score of replaced subtitle |
| `new_score` | INTEGER | Score of replacement subtitle |
| `reason` | TEXT | Upgrade reason (e.g. `SRT->ASS format upgrade`) |
| `created_at` | DATETIME | Timestamp |

---

## Language Profiles

### `language_profiles`

Named language profile definitions.

| Column | Type | Description |
|---|---|---|
| `id` | INTEGER | Auto-increment primary key |
| `name` | TEXT | Profile name (unique) |
| `target_language` | TEXT | ISO 639-1 target language code |
| `source_language` | TEXT | ISO 639-1 source language code |
| `format_preference` | TEXT | `ass`, `srt`, or `any` |
| `translation_backend` | TEXT | Backend name: `ollama`, `deepl`, `libretranslate`, etc. |
| `prompt_preset_id` | INTEGER | FK to `prompt_presets` |
| `upgrade_enabled` | BOOLEAN | Whether to auto-upgrade subs in this profile |
| `created_at` | DATETIME | Creation timestamp |

### `series_language_profiles`

Maps Sonarr series IDs to language profiles.

| Column | Type | Description |
|---|---|---|
| `series_id` | INTEGER | Sonarr series ID |
| `profile_id` | INTEGER | FK to `language_profiles` |

### `movie_language_profiles`

Maps Radarr movie IDs to language profiles.

| Column | Type | Description |
|---|---|---|
| `movie_id` | INTEGER | Radarr movie ID |
| `profile_id` | INTEGER | FK to `language_profiles` |

---

## Provider System

### `blacklist_entries`

Subtitles that have been manually or automatically blacklisted.

| Column | Type | Description |
|---|---|---|
| `id` | INTEGER | Auto-increment primary key |
| `file_path` | TEXT | Video file path |
| `subtitle_hash` | TEXT | SHA-256 of blacklisted subtitle |
| `provider` | TEXT | Provider that supplied the subtitle |
| `reason` | TEXT | Blacklist reason |
| `created_at` | DATETIME | Timestamp |

### `filter_presets`

Saved search filter configurations for the Wanted page.

| Column | Type | Description |
|---|---|---|
| `id` | INTEGER | Auto-increment primary key |
| `name` | TEXT | Preset name |
| `filter_json` | TEXT | JSON blob of filter settings |
| `created_at` | DATETIME | Timestamp |

---

## Translation

### `prompt_presets`

Translation prompt templates (built-in + user-created).

| Column | Type | Description |
|---|---|---|
| `id` | INTEGER | Auto-increment primary key |
| `name` | TEXT | Preset name (unique) |
| `prompt_template` | TEXT | Template text with `{source_language}` and `{target_language}` placeholders |
| `is_default` | BOOLEAN | Whether this is the active default preset |
| `is_builtin` | BOOLEAN | Whether this is a built-in template |
| `created_at` | DATETIME | Creation timestamp |

Built-in presets: Anime, Documentary, Casual, Literal, Dubbed.

---

## Metadata

### `ffprobe_cache`

Caches ffprobe metadata results to avoid repeated scans.

| Column | Type | Description |
|---|---|---|
| `file_path` | TEXT | Absolute path to video file (primary key) |
| `mtime` | FLOAT | File modification time at cache time |
| `metadata_json` | TEXT | JSON ffprobe output |
| `cached_at` | DATETIME | Cache timestamp |

Cache invalidation: mtime changes trigger a rescan.

---

## AniDB

### `anidb_absolute_mappings`

Maps TVDB series/episode IDs to AniDB absolute episode numbers.

| Column | Type | Description |
|---|---|---|
| `tvdb_series_id` | INTEGER | TVDB series ID |
| `tvdb_season` | INTEGER | TVDB season number |
| `tvdb_episode` | INTEGER | TVDB episode number |
| `anidb_aid` | INTEGER | AniDB anime ID |
| `absolute_episode` | INTEGER | Absolute episode number in AniDB order |
| `updated_at` | DATETIME | Last sync timestamp |

This table is populated by the weekly AniDB sync (`anidb_sync.py`).

---

## Series Settings

### `series_settings`

Per-series configuration overrides.

| Column | Type | Description |
|---|---|---|
| `series_id` | INTEGER | Sonarr series ID (primary key) |
| `glossary_json` | TEXT | JSON array of term overrides for this series |
| `forced_sub_preference` | TEXT | `disabled`, `separate`, or `auto` |
| `updated_at` | DATETIME | Last update |

---

## Backups

SQLite backups are stored as `.db` files in `SUBLARR_BACKUP_DIR`. Each backup is a full SQLite hot copy created via the SQLite backup API (no interruption to active reads/writes).

For PostgreSQL, use standard `pg_dump` — Sublarr does not manage PostgreSQL backups.
