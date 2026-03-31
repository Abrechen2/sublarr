# Timestamp Migration Plan: Text ISO Strings → DateTime(timezone=True)

**Date:** 2026-03-31
**Target:** `backend/` — all SQLAlchemy ORM timestamp columns
**Breaking change:** YES — existing DB rows contain `"2024-01-15T10:30:00+00:00"` format;
SQLAlchemy DateTime stores `"2024-01-15 10:30:00.000000"`. An Alembic migration rewrites
all existing rows. **Prod DB at CT 101 (192.168.178.194) will be modified in place.**
**Announce to users before deploying.**

---

## What We're Changing (and Why)

Currently every timestamp column is `Mapped[str]` / `mapped_column(Text)` with values like
`"2024-01-15T10:30:00+00:00"`. That means:
- `_now()` returns a string — callers that need `datetime` arithmetic call `fromisoformat()` manually
- String comparisons (`>`, `<`) in WHERE clauses work only by accident (lexicographic ≈ chronological for ISO format)
- After migration: columns hold Python `datetime` objects, ORM comparisons use real datetime semantics,
  `_now()` returns `datetime`, no more `isoformat()` / `fromisoformat()` noise

**SQLite technical note:** `DateTime(timezone=True)` on SQLite is still TEXT under the hood —
SQLAlchemy stores `"YYYY-MM-DD HH:MM:SS.ffffff"` (space separator, no offset). The Alembic
migration is therefore a string-reformat UPDATE, not a schema type change.

**Not changed:** `DailyStats.date` (date PK `"2024-01-15"`), all non-timestamp Text fields.

---

## Column Inventory

### `backend/db/models/core.py`

| Model | Columns to change |
|-------|-------------------|
| `Job` | `created_at`, `completed_at` |
| `ConfigEntry` | `updated_at` |
| `WantedItem` | `last_search_at`, `added_at`, `updated_at`, `retry_after` |
| `UpgradeHistory` | `upgraded_at` |
| `LanguageProfile` | `created_at`, `updated_at` |
| `FfprobeCache` | `cached_at` |
| `ChapterCache` | `cached_at` |
| `BlacklistEntry` | `added_at` |
| `FilterPreset` | `created_at`, `updated_at` |
| `AnidbAbsoluteMapping` | `updated_at` |
| `SeriesSettings` | `updated_at` |
| `FansubPreference` | `updated_at` |

### `backend/db/models/cleanup.py`

| Model | Columns to change |
|-------|-------------------|
| `SubtitleHash` | `last_scanned` |
| `CleanupRule` | `last_run_at`, `created_at`, `updated_at` |
| `CleanupHistory` | `performed_at` |

### `backend/db/models/hooks.py`

| Model | Columns to change |
|-------|-------------------|
| `HookConfig` | `last_triggered_at`, `created_at`, `updated_at` |
| `WebhookConfig` | `last_triggered_at`, `created_at`, `updated_at` |
| `HookLog` | `triggered_at` |

### `backend/db/models/notifications.py`

| Model | Columns to change |
|-------|-------------------|
| `NotificationTemplate` | `created_at`, `updated_at` |
| `NotificationHistory` | `sent_at` |
| `QuietHoursConfig` | `created_at`, `updated_at` |

### `backend/db/models/providers.py`

| Model | Columns to change |
|-------|-------------------|
| `ProviderCache` | `cached_at`, `expires_at` |
| `SubtitleDownload` | `downloaded_at` |
| `ProviderStats` | `last_success_at`, `last_failure_at`, `updated_at`, `disabled_until` |
| `ProviderScoreModifier` | `updated_at` |
| `ScoringWeights` | `updated_at` |

### `backend/db/models/standalone.py`

| Model | Columns to change |
|-------|-------------------|
| `WatchedFolder` | `last_scan_at`, `created_at`, `updated_at` |
| `StandaloneSeries` | `created_at`, `updated_at` |
| `StandaloneMovie` | `created_at`, `updated_at` |
| `MetadataCache` | `cached_at`, `expires_at` |
| `AnidbMapping` | `created_at`, `last_used` |

### `backend/db/models/translation.py`

| Model | Columns to change |
|-------|-------------------|
| `TranslationConfigHistory` | `first_used_at`, `last_used_at` |
| `GlossaryEntry` | `created_at`, `updated_at` |
| `PromptPreset` | `created_at`, `updated_at` |
| `TranslationBackendStats` | `last_success_at`, `last_failure_at`, `updated_at` |
| `WhisperJob` | `created_at`, `started_at`, `completed_at` |
| `TranslationMemory` | `created_at` |

### `backend/db/models/plugins.py`

| Model | Columns to change |
|-------|-------------------|
| `InstalledPlugin` (or equivalent) | `installed_at` |

---

## Step-by-Step Implementation

---

### STEP 1 — Alembic Migration (data conversion)

**File to create:**
`backend/db/migrations/versions/a1b2c3d4e5f6_migrate_timestamps_to_datetime.py`

This must run before any model changes are deployed. It rewrites existing TEXT data to the
format SQLAlchemy's DateTime processor expects (`"YYYY-MM-DD HH:MM:SS[.ffffff]"`).

**Conversion logic:**
- Input: `"2024-01-15T10:30:00+00:00"` or `"2024-01-15T10:30:00.123456+00:00"` or `"2024-01-15T10:30:00"`
- Output: `"2024-01-15 10:30:00"` or `"2024-01-15 10:30:00.123456"`
- SQL: `REPLACE(REPLACE(col, 'T', ' '), '+00:00', '')`
  - Replaces `T` separator with space
  - Strips UTC offset `+00:00`
  - Microseconds survive intact (only the suffix is stripped)

**Empty string / NULL handling:** Many nullable columns default to `""` (empty string).
After migration these must become `NULL`, not `""`:
```sql
UPDATE tablename SET col = NULL WHERE col = '';
```

**Migration file content:**

```python
"""Migrate timestamp columns from ISO string to SQLAlchemy DateTime format

Revision ID: a1b2c3d4e5f6
Revises: e4f5a6b7c8d9
Create Date: 2026-03-31

Converts all timestamp TEXT columns from "YYYY-MM-DDTHH:MM:SS+00:00" to
"YYYY-MM-DD HH:MM:SS[.ffffff]" format that SQLAlchemy DateTime expects.
Empty strings are converted to NULL for nullable columns.

BREAKING: This migration modifies existing data. All timestamps remain
functionally identical — only the string representation changes.
"""

from alembic import op

revision = "a1b2c3d4e5f6"
down_revision = "e4f5a6b7c8d9"
branch_labels = None
depends_on = None


def _reformat(table: str, col: str, nullable: bool = True) -> None:
    """Reformat a single timestamp column in place."""
    # Step 1: Convert ISO format to SQLAlchemy DateTime format
    op.execute(
        f"UPDATE {table} SET {col} = REPLACE(REPLACE({col}, 'T', ' '), '+00:00', '') "
        f"WHERE {col} IS NOT NULL AND {col} != ''"
    )
    # Step 2: Convert empty strings to NULL (only for nullable columns)
    if nullable:
        op.execute(f"UPDATE {table} SET {col} = NULL WHERE {col} = ''")


def upgrade() -> None:
    # --- jobs ---
    _reformat("jobs", "created_at", nullable=False)
    _reformat("jobs", "completed_at", nullable=True)

    # --- config_entries ---
    _reformat("config_entries", "updated_at", nullable=False)

    # --- wanted_items ---
    _reformat("wanted_items", "last_search_at", nullable=True)
    _reformat("wanted_items", "added_at", nullable=False)
    _reformat("wanted_items", "updated_at", nullable=False)
    _reformat("wanted_items", "retry_after", nullable=True)

    # --- upgrade_history ---
    _reformat("upgrade_history", "upgraded_at", nullable=False)

    # --- language_profiles ---
    _reformat("language_profiles", "created_at", nullable=False)
    _reformat("language_profiles", "updated_at", nullable=False)

    # --- ffprobe_cache ---
    _reformat("ffprobe_cache", "cached_at", nullable=False)

    # --- chapter_cache ---
    _reformat("chapter_cache", "cached_at", nullable=False)

    # --- blacklist_entries ---
    _reformat("blacklist_entries", "added_at", nullable=False)

    # --- filter_presets ---
    _reformat("filter_presets", "created_at", nullable=False)
    _reformat("filter_presets", "updated_at", nullable=False)

    # --- anidb_absolute_mappings ---
    _reformat("anidb_absolute_mappings", "updated_at", nullable=False)

    # --- series_settings ---
    _reformat("series_settings", "updated_at", nullable=False)

    # --- fansub_preferences ---
    _reformat("fansub_preferences", "updated_at", nullable=False)

    # --- subtitle_hashes ---
    _reformat("subtitle_hashes", "last_scanned", nullable=False)

    # --- cleanup_rules ---
    _reformat("cleanup_rules", "last_run_at", nullable=True)
    _reformat("cleanup_rules", "created_at", nullable=False)
    _reformat("cleanup_rules", "updated_at", nullable=False)

    # --- cleanup_history ---
    _reformat("cleanup_history", "performed_at", nullable=False)

    # --- hook_configs ---
    _reformat("hook_configs", "last_triggered_at", nullable=True)
    _reformat("hook_configs", "created_at", nullable=False)
    _reformat("hook_configs", "updated_at", nullable=False)

    # --- webhook_configs ---
    _reformat("webhook_configs", "last_triggered_at", nullable=True)
    _reformat("webhook_configs", "created_at", nullable=False)
    _reformat("webhook_configs", "updated_at", nullable=False)

    # --- hook_log ---
    _reformat("hook_log", "triggered_at", nullable=False)

    # --- notification_templates ---
    _reformat("notification_templates", "created_at", nullable=False)
    _reformat("notification_templates", "updated_at", nullable=False)

    # --- notification_history ---
    _reformat("notification_history", "sent_at", nullable=False)

    # --- quiet_hours_config ---
    _reformat("quiet_hours_config", "created_at", nullable=False)
    _reformat("quiet_hours_config", "updated_at", nullable=False)

    # --- provider_cache ---
    _reformat("provider_cache", "cached_at", nullable=False)
    _reformat("provider_cache", "expires_at", nullable=False)

    # --- subtitle_downloads ---
    _reformat("subtitle_downloads", "downloaded_at", nullable=False)

    # --- provider_stats ---
    _reformat("provider_stats", "last_success_at", nullable=True)
    _reformat("provider_stats", "last_failure_at", nullable=True)
    _reformat("provider_stats", "updated_at", nullable=False)
    _reformat("provider_stats", "disabled_until", nullable=True)

    # --- provider_score_modifiers ---
    _reformat("provider_score_modifiers", "updated_at", nullable=False)

    # --- scoring_weights ---
    _reformat("scoring_weights", "updated_at", nullable=False)

    # --- watched_folders ---
    _reformat("watched_folders", "last_scan_at", nullable=True)
    _reformat("watched_folders", "created_at", nullable=False)
    _reformat("watched_folders", "updated_at", nullable=False)

    # --- standalone_series ---
    _reformat("standalone_series", "created_at", nullable=False)
    _reformat("standalone_series", "updated_at", nullable=False)

    # --- standalone_movies ---
    _reformat("standalone_movies", "created_at", nullable=False)
    _reformat("standalone_movies", "updated_at", nullable=False)

    # --- metadata_cache ---
    _reformat("metadata_cache", "cached_at", nullable=False)
    _reformat("metadata_cache", "expires_at", nullable=False)

    # --- anidb_mappings ---
    _reformat("anidb_mappings", "created_at", nullable=True)
    _reformat("anidb_mappings", "last_used", nullable=True)

    # --- translation_config_history ---
    _reformat("translation_config_history", "first_used_at", nullable=False)
    _reformat("translation_config_history", "last_used_at", nullable=False)

    # --- glossary_entries ---
    _reformat("glossary_entries", "created_at", nullable=False)
    _reformat("glossary_entries", "updated_at", nullable=False)

    # --- prompt_presets ---
    _reformat("prompt_presets", "created_at", nullable=False)
    _reformat("prompt_presets", "updated_at", nullable=False)

    # --- translation_backend_stats ---
    _reformat("translation_backend_stats", "last_success_at", nullable=True)
    _reformat("translation_backend_stats", "last_failure_at", nullable=True)
    _reformat("translation_backend_stats", "updated_at", nullable=False)

    # --- whisper_jobs ---
    _reformat("whisper_jobs", "created_at", nullable=False)
    _reformat("whisper_jobs", "started_at", nullable=True)
    _reformat("whisper_jobs", "completed_at", nullable=True)

    # --- translation_memory ---
    _reformat("translation_memory", "created_at", nullable=False)

    # --- installed_plugins (check actual table name in plugins.py) ---
    _reformat("installed_plugins", "installed_at", nullable=False)


def downgrade() -> None:
    # Downgrade is not safe to automate: the T separator and +00:00 offset
    # were stripped. Re-adding them would require knowing the original format.
    # For a beta product, downgrade = restore from backup.
    raise NotImplementedError(
        "Timestamp migration downgrade is not supported. Restore from backup."
    )
```

**Verify the table name for plugins:** Before writing the migration, run:
```bash
cd backend && python -c "from db.models.plugins import *; print([m.__tablename__ for m in [InstalledPlugin] if hasattr(m, '__tablename__')])"
```
Adjust the `installed_plugins` table name in the migration if different.

---

### STEP 2 — Model Changes

For every column identified in the inventory:
1. Remove `Text` import reference for timestamp columns (keep `Text` for other columns)
2. Add `DateTime` import
3. Change `Mapped[str]` → `Mapped[datetime | None]` for nullable, `Mapped[datetime]` for non-nullable
4. Change `mapped_column(Text, ...)` → `mapped_column(DateTime(timezone=True), ...)`

**Import change pattern for each model file:**

```python
# BEFORE
from sqlalchemy import ..., Text, ...

# AFTER
from datetime import datetime
from sqlalchemy import ..., DateTime, Text, ...  # keep Text for non-timestamp Text fields
```

**Column type change pattern:**

```python
# BEFORE
created_at: Mapped[str] = mapped_column(Text, nullable=False)
completed_at: Mapped[str | None] = mapped_column(Text, default="")
last_triggered_at: Mapped[str | None] = mapped_column(Text, default="")

# AFTER
created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
last_triggered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
```

**Key rules:**
- Columns that had `default=""` and were nullable → `nullable=True`, no default (NULL is correct)
- Columns that had `nullable=False` stay `nullable=False`, no default (repo always sets them)
- `WantedItem.retry_after` was `nullable=True, default=None` → stays `nullable=True`
- Do NOT add `server_default` or Python-level `default=func.now()` — repositories always set these explicitly

**File-by-file change list:**

`db/models/core.py` — add `from datetime import datetime` and `DateTime` to sqlalchemy imports.
Change: `Job.created_at`, `Job.completed_at`, `ConfigEntry.updated_at`,
`WantedItem.last_search_at`, `WantedItem.added_at`, `WantedItem.updated_at`, `WantedItem.retry_after`,
`UpgradeHistory.upgraded_at`, `LanguageProfile.created_at`, `LanguageProfile.updated_at`,
`FfprobeCache.cached_at`, `ChapterCache.cached_at`, `BlacklistEntry.added_at`,
`FilterPreset.created_at`, `FilterPreset.updated_at`, `AnidbAbsoluteMapping.updated_at`,
`SeriesSettings.updated_at`, `FansubPreference.updated_at`.

`db/models/cleanup.py` — add imports. Change: `SubtitleHash.last_scanned`,
`CleanupRule.last_run_at`, `CleanupRule.created_at`, `CleanupRule.updated_at`,
`CleanupHistory.performed_at`.

`db/models/hooks.py` — add imports. Change: `HookConfig.last_triggered_at`,
`HookConfig.created_at`, `HookConfig.updated_at`, `WebhookConfig.last_triggered_at`,
`WebhookConfig.created_at`, `WebhookConfig.updated_at`, `HookLog.triggered_at`.

`db/models/notifications.py` — add imports. Change: `NotificationTemplate.created_at`,
`NotificationTemplate.updated_at`, `NotificationHistory.sent_at`,
`QuietHoursConfig.created_at`, `QuietHoursConfig.updated_at`.

`db/models/providers.py` — add imports. Change: `ProviderCache.cached_at`,
`ProviderCache.expires_at`, `SubtitleDownload.downloaded_at`, `ProviderStats.last_success_at`,
`ProviderStats.last_failure_at`, `ProviderStats.updated_at`, `ProviderStats.disabled_until`,
`ProviderScoreModifier.updated_at`, `ScoringWeights.updated_at`.

`db/models/standalone.py` — add imports. Change: `WatchedFolder.last_scan_at`,
`WatchedFolder.created_at`, `WatchedFolder.updated_at`, `StandaloneSeries.created_at`,
`StandaloneSeries.updated_at`, `StandaloneMovie.created_at`, `StandaloneMovie.updated_at`,
`MetadataCache.cached_at`, `MetadataCache.expires_at`, `AnidbMapping.created_at`,
`AnidbMapping.last_used`.

`db/models/translation.py` — add imports. Change: `TranslationConfigHistory.first_used_at`,
`TranslationConfigHistory.last_used_at`, `GlossaryEntry.created_at`, `GlossaryEntry.updated_at`,
`PromptPreset.created_at`, `PromptPreset.updated_at`, `TranslationBackendStats.last_success_at`,
`TranslationBackendStats.last_failure_at`, `TranslationBackendStats.updated_at`,
`WhisperJob.created_at`, `WhisperJob.started_at`, `WhisperJob.completed_at`,
`TranslationMemory.created_at`.

`db/models/plugins.py` — add imports. Change: `InstalledPlugin.installed_at` (or whatever the
column is named — check the file).

---

### STEP 3 — Repository: `_now()` helper

**File:** `backend/db/repositories/base.py`

```python
# BEFORE
def _now(self) -> str:
    """Return current UTC time as ISO format string."""
    return datetime.now(UTC).isoformat()

# AFTER
def _now(self) -> datetime:
    """Return current UTC time as timezone-aware datetime."""
    return datetime.now(UTC)
```

Change the return type annotation from `str` to `datetime`. The `datetime` import is already
present in `base.py` (`from datetime import UTC, datetime`).

---

### STEP 4 — Repository: Remove `.isoformat()` writes and `.fromisoformat()` reads

For every occurrence of `_now()` being assigned to a timestamp field: no change needed —
`_now()` now returns `datetime` and the column type is `DateTime`, so assignment works as-is.

The changes needed are where code does NOT use `_now()` but constructs ISO strings directly.

#### `db/repositories/presets.py` — lines 55, 81
```python
# BEFORE
now = datetime.now(UTC).isoformat()
row.updated_at = datetime.now(UTC).isoformat()

# AFTER
now = datetime.now(UTC)
row.updated_at = datetime.now(UTC)
```

#### `db/repositories/series_audio.py` — line 30
```python
# BEFORE
now = datetime.utcnow().isoformat()

# AFTER
now = datetime.now(UTC)
```

#### `db/repositories/providers.py` — multiple locations

Lines 41-42 (cache_results):
```python
# BEFORE
cached_at_str = now.isoformat()
expires_str = expires.isoformat()
# ...
existing.cached_at = cached_at_str
existing.expires_at = expires_str
# ...
ProviderCache(cached_at=cached_at_str, expires_at=expires_str, ...)

# AFTER
# now is already datetime.now(UTC), expires is now + timedelta(...)
existing.cached_at = now
existing.expires_at = expires
ProviderCache(cached_at=now, expires_at=expires, ...)
```

Lines 76, 92, 98 — `now = datetime.now(UTC).isoformat()` → `now = datetime.now(UTC)`

Lines 374, 380, 386 — `.isoformat()` calls on datetime objects for `disabled_until` and `updated_at`:
```python
# BEFORE
disabled_until = (now + timedelta(minutes=cooldown_minutes)).isoformat()
existing.updated_at = now.isoformat()
updated_at=now.isoformat()

# AFTER
disabled_until = now + timedelta(minutes=cooldown_minutes)
existing.updated_at = now
updated_at=now
```

Line 424 — `now = datetime.now(UTC).isoformat()` → `now = datetime.now(UTC)`

Lines 443, 465 — cutoff comparisons:
```python
# BEFORE
cutoff = (datetime.now(UTC) - timedelta(days=days)).isoformat()
# ... WHERE col < cutoff  (string comparison)

# AFTER
cutoff = datetime.now(UTC) - timedelta(days=days)
# ... WHERE col < cutoff  (datetime comparison — SQLAlchemy handles it correctly)
```

#### `db/repositories/cache.py` — lines 244-245, 288

Line 244:
```python
# BEFORE
last_used = datetime.fromisoformat(mapping.last_used)
age_days = (datetime.utcnow() - last_used).days

# AFTER
# mapping.last_used is now datetime — no fromisoformat needed
# BUT: utcnow() returns naive, last_used is aware (UTC) — use aware comparison:
age_days = (datetime.now(UTC) - mapping.last_used).days
```

Line 288:
```python
# BEFORE
cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()

# AFTER
cutoff = datetime.now(UTC) - timedelta(days=days)
```

#### `db/repositories/providers.py` — `get_cached_results` (line 76) and `cleanup_expired_cache` (line 92)

These compare `ProviderCache.expires_at > now` where `now` was an ISO string. After the change,
`now` is a `datetime` and `ProviderCache.expires_at` is `DateTime`. SQLAlchemy handles the
comparison natively — no change needed to the WHERE clause structure, just to how `now` is computed.

#### `db/repositories/cleanup.py` — line 380
```python
# BEFORE
CleanupHistory.performed_at > (datetime.now(UTC) - timedelta(days=30)).isoformat()

# AFTER
CleanupHistory.performed_at > (datetime.now(UTC) - timedelta(days=30))
```

#### `db/repositories/hooks.py` — line 350
```python
# BEFORE
cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()

# AFTER
cutoff = datetime.now(UTC) - timedelta(days=days)
```

#### `db/repositories/jobs.py` — line 131
```python
# BEFORE
cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()

# AFTER
cutoff = datetime.now(UTC) - timedelta(days=days)
```

Note: Lines 171 and 263 use `date.today().isoformat()` as a key for `DailyStats.date` — this is
the DATE primary key, not a datetime column. **Leave these unchanged.**

#### `db/repositories/library.py` — lines 137, 146
```python
# BEFORE
.where(SubtitleDownload.downloaded_at > (now - timedelta(days=1)).isoformat())
.where(SubtitleDownload.downloaded_at > (now - timedelta(days=7)).isoformat())

# AFTER
.where(SubtitleDownload.downloaded_at > (now - timedelta(days=1)))
.where(SubtitleDownload.downloaded_at > (now - timedelta(days=7)))
```
Where `now` should be `datetime.now(UTC)` (check what `now` is assigned to in that context
at line 173: `now = self._now()` — after Step 3 this is already a `datetime`).

#### `db/repositories/standalone.py` — lines 278, 291-292, 313, 351
```python
# BEFORE (line 278)
now = datetime.utcnow().isoformat()

# AFTER
now = datetime.now(UTC)
```

Lines 291-292:
```python
# BEFORE
cached_at = now.isoformat()
expires_at = (now + timedelta(days=ttl_days)).isoformat()

# AFTER — now is already datetime
cached_at = now
expires_at = now + timedelta(days=ttl_days)
```

Line 313:
```python
# BEFORE
now = datetime.utcnow().isoformat()

# AFTER
now = datetime.now(UTC)
```

Line 351:
```python
# BEFORE
cutoff = (datetime.utcnow() - timedelta(days=ttl_days)).isoformat()

# AFTER
cutoff = datetime.now(UTC) - timedelta(days=ttl_days)
```

#### `db/repositories/quality.py` — line 97
```python
# BEFORE
> (datetime.now(UTC) - timedelta(days=days)).isoformat()

# AFTER
> (datetime.now(UTC) - timedelta(days=days))
```

#### `services/github_registry.py` — lines 43, 102
```python
# BEFORE (line 43)
cutoff = (datetime.now(UTC) - timedelta(hours=CACHE_TTL_HOURS)).isoformat()

# AFTER
cutoff = datetime.now(UTC) - timedelta(hours=CACHE_TTL_HOURS)
```
Line 102:
```python
# BEFORE
now = datetime.now(UTC).isoformat()

# AFTER
now = datetime.now(UTC)
```
Note: `github_registry.py` writes to a model column — verify which model and column; if it's a
DateTime column after Step 2, the datetime value is correct. If it writes to a Text column,
keep `.isoformat()`.

---

### STEP 5 — SQL Query Rewrites

#### `db/repositories/statistics.py` — `get_quality_trend()` (lines 77-98)

This raw SQL uses `substr(downloaded_at, 1, 10)` for date grouping and
`WHERE downloaded_at >= date('now', :offset)` for the cutoff.

After migration, `downloaded_at` stores `"2024-01-15 10:30:00"` — `substr(..., 1, 10)` still
extracts `"2024-01-15"` correctly (space at position 11, same as T before). **No change needed
to `substr(downloaded_at, 1, 10)`.**

The `WHERE downloaded_at >= date('now', :offset)` comparison: SQLite `date('now', '-30 days')`
returns `"2026-01-01"` (10-char date string). Comparing against `"2026-01-01 10:30:00"` works
correctly lexicographically. **No change needed.**

`get_series_quality()` uses `MAX(sd.downloaded_at)` — returns a datetime string from SQLite,
which SQLAlchemy will NOT auto-convert to `datetime` in raw SQL result rows. The returned value
`row[3]` is passed directly as `"last_download"` in the dict. This is API output — it will now
be a space-separated datetime string instead of ISO T format.
**Action:** Either accept the new format, or format explicitly:
```python
"last_download": row[3].replace(" ", "T") + "Z" if row[3] else None,
```
Check if any frontend component parses this field strictly; if so, normalize the output.

---

### STEP 6 — Services: `wanted_scanner.py`

**Lines 265, 966, 1062** — `self._last_scan_at` and `self._last_search_at` are in-memory
instance variables (not DB columns). Check how they're used:
- If they're written to a DB column → must be `datetime` after Step 2
- If they're only used in-memory or returned via API as strings → keep `.isoformat()` for
  the in-memory var, or change the API serializer

**Lines 507, 773** — `since_iso = since.isoformat() + "Z"` builds ISO strings for Sonarr/Radarr
API calls (external HTTP requests). These are NOT DB writes — `since` is a `datetime` object.
**Leave unchanged** (external API requires ISO format strings).

**Lines 941, 954** — `datetime.fromisoformat(retry_after_str)` and `datetime.fromisoformat(last_str)`:
After migration, `WantedItem.retry_after` and `WantedItem.last_search_at` are `datetime | None`
objects read from the ORM. These lines read from `item` (a dict from `_to_dict()`).

`_to_dict()` in `BaseRepository` iterates `model_instance.__table__.columns` and returns
`getattr(model_instance, col)`. For a `DateTime` column, this returns a `datetime` object
(or None). So `item["retry_after"]` and `item["last_search_at"]` will be `datetime | None`.

```python
# BEFORE
retry_after_str = item.get("retry_after")
if retry_after_str:
    retry_at = datetime.fromisoformat(retry_after_str)

# AFTER
retry_at = item.get("retry_after")  # already datetime | None
if retry_at:
    if retry_at.tzinfo is None:
        retry_at = retry_at.replace(tzinfo=UTC)
    # ... rest of logic unchanged
```

Apply same pattern to `last_str` / `last` on lines 952-956.

---

### STEP 7 — API Serialization (JSON responses)

`datetime` objects are not JSON-serializable by default. The existing code relied on
`_to_dict()` returning ISO strings for timestamp fields — now it returns `datetime` objects.

**Check Flask's JSON encoder setup in `app.py`:**

```bash
grep -n "json_encoder\|JSONEncoder\|default.*datetime\|flask_json" backend/app.py backend/extensions.py
```

If there is no custom JSON encoder, Flask's default `jsonify` will raise `TypeError` when
serializing `datetime` objects. You must add one.

**Action — add to `app.py` or a `json_utils.py`:**

```python
from flask.json.provider import DefaultJSONProvider
from datetime import datetime

class SublarrJSONProvider(DefaultJSONProvider):
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)

# In create_app():
app.json_provider_class = SublarrJSONProvider
app.json = SublarrJSONProvider(app)
```

This ensures all `datetime` objects in API responses serialize as ISO strings (same format
as before from the client's perspective).

**Alternative (simpler):** Override `_to_dict()` in `BaseRepository` to serialize datetimes:

```python
def _to_dict(self, model_instance, columns=None):
    if model_instance is None:
        return None
    if columns is None:
        columns = [c.key for c in model_instance.__table__.columns]
    result = {}
    for col in columns:
        val = getattr(model_instance, col)
        if isinstance(val, datetime):
            result[col] = val.isoformat()
        else:
            result[col] = val
    return result
```

This approach is safer: only affects dict serialization, not every JSON response path.
Recommended over the global JSON provider change unless there are non-`_to_dict()` response
paths that also expose datetime fields directly.

---

### STEP 8 — Test Updates

**Files needing changes:**

#### `tests/test_upgrade_chain.py` — lines 22, 49
```python
# BEFORE
repo._now = lambda: "2026-03-28T12:00:00"

# AFTER
from datetime import UTC, datetime
repo._now = lambda: datetime(2026, 3, 28, 12, 0, 0, tzinfo=UTC)
```

#### `tests/test_upgrade_scheduler.py` — lines 32, 183, 192
```python
# Line 32 — dl.downloaded_at is now datetime | None
dl.downloaded_at = downloaded_at or (datetime.now(UTC) - timedelta(days=14))
# Remove .isoformat() call

# Lines 183, 192 — last_search_at in item dict (dict from _to_dict)
# If _to_dict now returns ISO strings (per Step 7 approach), keep as-is
# If _to_dict returns datetime objects, change to:
recent_search = datetime.now(UTC) - timedelta(hours=1)
old_search = datetime.now(UTC) - timedelta(hours=48)
```

#### `tests/test_chapters.py` — lines 101, 135
```python
# BEFORE
cached_at=datetime.utcnow().isoformat()

# AFTER
from datetime import UTC, datetime
cached_at=datetime.now(UTC)
```

#### `tests/test_batch_process.py` — line 11
```python
# BEFORE
def _now() -> str:
    return datetime.now(UTC).isoformat()

# AFTER
def _now() -> datetime:
    return datetime.now(UTC)
```
Check how `_now()` is used in that test — if the result is compared to a string assertion,
the assertion must also change to `datetime`.

#### `tests/test_wanted_search.py` — lines 65, 77, 87
These call `datetime.fromisoformat(result)` where `result` comes from `_compute_retry_after()`.
Check if `_compute_retry_after()` is in `services/wanted_scanner.py` or a utils file —
after the migration it should return `datetime`, not a string. Update the test accordingly:
```python
# BEFORE
ts = datetime.fromisoformat(result)

# AFTER
ts = result  # already datetime
```

#### `tests/test_github_registry.py` — lines 45, 49
```python
# BEFORE
def _fresh_timestamp() -> str:
    return datetime.now(UTC).isoformat()

def _stale_timestamp() -> str:
    return (datetime.now(UTC) - timedelta(hours=2)).isoformat()

# AFTER — if github_registry columns are DateTime:
def _fresh_timestamp() -> datetime:
    return datetime.now(UTC)

def _stale_timestamp() -> datetime:
    return datetime.now(UTC) - timedelta(hours=2)
```

#### `tests/test_marketplace_db.py` and `tests/test_marketplace_routes.py`
These use ISO string literals like `"2026-03-11T00:00:00Z"` and `"2026-03-11T00:00:00+00:00"`.
After migration, model columns expect `datetime` objects. Change fixture assignments to:
```python
from datetime import UTC, datetime
installed_at=datetime(2026, 3, 11, 0, 0, 0, tzinfo=UTC)
last_fetched=datetime(2026, 3, 11, 0, 0, 0, tzinfo=UTC)
```

#### `tests/test_series_audio_pref.py` — line 10
```python
# BEFORE
ss = SeriesSettings(sonarr_series_id=1, absolute_order=0, updated_at="2026-01-01")

# AFTER
from datetime import UTC, datetime
ss = SeriesSettings(sonarr_series_id=1, absolute_order=0,
                    updated_at=datetime(2026, 1, 1, tzinfo=UTC))
```

#### `tests/test_cli_status.py` — lines 18, 30
These use ISO string literals in mock return dicts (`"created_at": "2026-03-13T10:00:00"`).
If the mocked function returns a plain dict (not from `_to_dict()`), and the test only checks
string presence, may not need changes. Verify by running the test after implementation.

---

### STEP 9 — CHANGELOG and VERSION

**File:** `backend/CHANGELOG.md`

Add a new section (or append to the current unreleased section):

```markdown
### Breaking Changes
- **Database timestamp format migration**: All internal timestamp columns have been migrated
  from ISO 8601 text strings (`"2024-01-15T10:30:00+00:00"`) to SQLAlchemy DateTime format
  (`"2024-01-15 10:30:00"`). This is handled automatically by the Alembic migration on first
  startup. **No user action required for Docker deployments.** If you manage the database
  manually, run `flask db upgrade` before starting the new version.
```

**File:** `backend/VERSION`

Bump to the next beta version (check current version first: `cat backend/VERSION`).

---

### STEP 10 — Verification

#### 10a. Ruff (run on entire backend/)
```bash
cd backend && ruff check . && ruff format --check .
```
Fix any issues — common ones after this change:
- `UTC` not imported in files that now use it
- `datetime` not imported in model files
- `isoformat`/`fromisoformat` calls that were missed

#### 10b. Test suite
```bash
cd backend && python -m pytest --tb=short -q \
  --ignore=tests/performance \
  --ignore=tests/integration/test_provider_pipeline.py \
  --ignore=tests/test_video_sync.py \
  --ignore=tests/test_translation_backends.py \
  -k "not (test_sonarr_download_webhook or test_radarr_download_webhook or test_parse_llm_response_too_many_merge or test_record_backend_success)"
```

Expected failures on first run: any test that still compares `datetime` objects to string
literals or calls `fromisoformat()` on a `datetime`. Fix each failure per Step 8 patterns.

#### 10c. Manual DB check (dev DB)
```bash
cd backend && python - <<'EOF'
from app import create_app
app = create_app()
with app.app_context():
    from extensions import db
    from db.models.core import Job
    j = db.session.query(Job).first()
    if j:
        print(type(j.created_at), repr(j.created_at))
    else:
        print("No jobs in DB yet")
EOF
```
Expected output: `<class 'datetime.datetime'> datetime.datetime(2024, 1, 15, 10, 30, 0, tzinfo=...)`

#### 10d. Migration dry-run on a copy of prod DB
Before deploying to CT 101:
```bash
# On dev machine, copy prod DB and test migration
scp root@192.168.178.194:/opt/sublarr/data/sublarr.db /tmp/sublarr-prod-copy.db
cp /tmp/sublarr-prod-copy.db /tmp/sublarr-test.db
SUBLARR_DATABASE_PATH=/tmp/sublarr-test.db cd backend && flask db upgrade
# Then spot-check:
sqlite3 /tmp/sublarr-test.db "SELECT created_at FROM jobs LIMIT 3;"
# Expected: "2024-01-15 10:30:00.000000" or similar (no T, no +00:00)
```

#### 10e. Post-deploy API smoke test (CT 101)
```bash
curl -s http://192.168.178.194:5765/api/v1/health
curl -s http://192.168.178.194:5765/api/v1/jobs | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['jobs'][0]['created_at'] if d.get('jobs') else 'no jobs')"
```
The `created_at` in API responses should still be ISO format (`"T"` separator) thanks to
the JSON serialization in Step 7.

---

## Execution Order

```
1. Create Alembic migration (Step 1)
2. Change model files (Step 2)
3. Change BaseRepository._now() (Step 3)
4. Change all repository files (Step 4) — can be done in parallel with Step 2
5. Rewrite raw SQL queries (Step 5)
6. Fix services/wanted_scanner.py (Step 6)
7. Add JSON serialization for datetime (Step 7)  ← CRITICAL, do before testing
8. Update tests (Step 8)
9. Run ruff + pytest (Step 10a, 10b) — iterate until clean
10. Bump CHANGELOG + VERSION (Step 9)
11. Dry-run on prod DB copy (Step 10d)
12. Deploy
```

---

## Risk Register

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Missed column (not in this plan) | Low | Medium | Grep for remaining `Text` columns with `_at` suffix after implementation |
| Empty-string to NULL breaks NOT NULL constraint | Low | High | All `NOT NULL` columns have `nullable=False`; migration only NULLs empty strings on nullable columns |
| Raw SQL `MAX(downloaded_at)` returns wrong type | Medium | Low | Returns string from SQLite; format it in Python if needed |
| `_compute_retry_after()` in wanted_scanner returns string | Medium | Medium | Check and update to return `datetime` |
| JSON serialization path outside `_to_dict()` | Medium | High | Grep for `.isoformat()` in routes/ after implementation |
| Alembic downgrade not possible | Certain | Medium | Accepted; beta product; backup before deploy |

---

## Post-Migration Cleanup

After confirming the migration is stable (1-2 weeks):
- Remove any remaining `fromisoformat()` defensive guards that were added as shims
- Grep for `str` type hints on `_at` / `_used` fields — all should be gone
- Consider adding `timezone=True` check to a pre-commit hook to prevent regression
