# Phase 25-01: AniDB Absolute Episode Order Backend -- Implementation Summary

**Date:** 2026-02-22
**Status:** Complete

---

## What Was Built

### 1. DB Models -- `backend/db/models/core.py`

Two new SQLAlchemy ORM models appended to core.py:

**`AnidbAbsoluteMapping`** (table: `anidb_absolute_mappings`)
- Stores TVDB season/episode -> AniDB absolute episode number mappings
- Fields: id, tvdb_id, season, episode, anidb_absolute_episode, updated_at, source
- Unique constraint on (tvdb_id, season, episode)
- Index on tvdb_id for fast lookup

**`SeriesSettings`** (table: `series_settings`)
- Per-series flags; primary key is sonarr_series_id
- Fields: sonarr_series_id, absolute_order (int 0/1), updated_at
- Chosen over config_entries because it allows type-safe queries and
  avoids key-pattern parsing; PK gives O(1) lookup

### 2. Repository -- `backend/db/repositories/anidb.py`

`AnidbRepository(BaseRepository)` with methods:
- `get_anidb_absolute(tvdb_id, season, episode)` -> Optional[int]
- `upsert_mapping(tvdb_id, season, episode, anidb_absolute_episode, source)` -> None
- `list_by_tvdb(tvdb_id)` -> list[dict]
- `clear_for_tvdb(tvdb_id)` -> int
- `clear_all()` -> int
- `count_mappings()` -> int
- `get_absolute_order(sonarr_series_id)` -> bool
- `set_absolute_order(sonarr_series_id, enabled)` -> None
- `get_series_settings(sonarr_series_id)` -> Optional[dict]
- `list_series_with_absolute_order()` -> list[int]

Registered in `backend/db/repositories/__init__.py` with convenience functions:
- `get_anidb_absolute()`
- `upsert_anidb_mapping()`
- `list_anidb_mappings()`
- `clear_anidb_mappings_for_tvdb()`
- `get_series_absolute_order()`
- `set_series_absolute_order()`

### 3. Alembic Migration -- `backend/db/migrations/versions/a1b2c3d4e5f6_add_anidb_absolute_mappings.py`

- Creates `anidb_absolute_mappings` table with unique constraint and index
- Creates `series_settings` table with PK on sonarr_series_id
- Chains from `fa890ea72dab` (add_filter_presets)
- Includes downgrade() for safe rollback

### 4. Sync Module -- `backend/anidb_sync.py`

Standalone module responsible for fetching and parsing the anime-lists XML:
- Source: `https://raw.githubusercontent.com/Anime-Lists/anime-lists/master/anime-list.xml`
- Parses mapping elements: token format `anidb_ep-tvdb_ep` separated by semicolons
- Skips season 0 (specials have no standard absolute ordering)
- Skips anime without a valid TVDB ID
- Uses `AnidbRepository.upsert_mapping()` -- incremental upsert; no pre-wipe
- Thread-safe `sync_state` dict exposed for API status endpoint
- `run_sync(app)` is the main entry point; runs in a background thread
- `AnidbSyncScheduler` uses threading.Timer (same pattern as CleanupScheduler)
- `start_anidb_sync_scheduler(app)` is idempotent

### 5. API Routes -- `backend/routes/anidb_mapping.py`

Blueprint: `/api/v1/anidb-mapping`

| Method | Path | Description |
|--------|------|-------------|
| POST   | /refresh | Trigger manual sync (async, returns 202) |
| GET    | /status | Sync state + total_mappings count |
| GET    | /series/<tvdb_id> | List all mappings for a TVDB series |
| DELETE | /series/<tvdb_id> | Clear all mappings for a TVDB series |
| GET    | /settings/<sonarr_series_id> | Get series settings (absolute_order) |
| PUT    | /settings/<sonarr_series_id> | Set absolute_order flag |

Registered in `backend/routes/__init__.py`.

### 6. VideoQuery Extension -- `backend/providers/base.py`

Added `absolute_episode: Optional[int] = None` field to the `VideoQuery` dataclass.
Positioned before `forced_only` in the Forced/signs block.
Providers can inspect this field to search by absolute episode instead of S/E.

### 7. build_query_from_wanted Integration -- `backend/wanted_search.py`

Inserted a resolution block between the metadata collection section and the
`forced_only` assignment:

- Only runs for `item_type == "episode"` with known tvdb_id, season, episode
- Checks `AnidbRepository.get_absolute_order(sonarr_series_id)`
- If True: calls `get_anidb_absolute(tvdb_id, season, episode)`
- If mapping found: sets `query.absolute_episode = <number>`
- If not found: logs debug message, proceeds with normal S/E numbering
- Errors are caught and logged as warnings (never crash the search pipeline)

### 8. Scheduler Registration -- `backend/app.py`

Added in `_start_schedulers()`. Wrapped in try/except so a missing import
does not prevent app startup.

---

## Design Decisions

**`series_settings` table vs `config_entries`**
Chose a dedicated table because:
- Type-safe primary key lookup (O(1) by PK, no key-pattern matching)
- Easier to list all series with the flag set
- Extensible: additional per-series flags can be added as columns

**Incremental upsert vs full wipe-and-replace on sync**
The upsert approach is safer: if the network request fails mid-sync,
previously loaded data remains valid.

**Season 0 skipped**
AniDB specials and OVAs use their own episode numbering and do not map
cleanly to an absolute episode order for regular episodes.

---

## Files Changed

| File | Change |
|------|--------|
| `backend/db/models/core.py` | Added AnidbAbsoluteMapping, SeriesSettings models |
| `backend/db/models/__init__.py` | Import + export new models |
| `backend/db/repositories/anidb.py` | NEW -- AnidbRepository |
| `backend/db/repositories/__init__.py` | Import AnidbRepository + convenience functions |
| `backend/db/migrations/versions/a1b2c3d4e5f6_add_anidb_absolute_mappings.py` | NEW -- Alembic migration |
| `backend/anidb_sync.py` | NEW -- sync logic + scheduler |
| `backend/routes/anidb_mapping.py` | NEW -- API blueprint |
| `backend/routes/__init__.py` | Register anidb_mapping blueprint |
| `backend/app.py` | Register AniDB sync scheduler |
| `backend/providers/base.py` | Added absolute_episode field to VideoQuery |
| `backend/wanted_search.py` | Insert absolute episode resolution in build_query_from_wanted |

---

## Next Steps (Phase 25-02 -- Frontend)

- Settings UI for toggling `absolute_order` per series (in Series Detail view)
- Display `absolute_episode` in Wanted and Library tables when set
- Connect manual refresh button to POST /api/v1/anidb-mapping/refresh
- Show sync status/last_run on Settings > AniDB page

## Next Steps (Phase 25-03 -- Provider Integration)

- Update provider search implementations (Kitsunekko, AniDB provider) to use
  `query.absolute_episode` when set instead of building S/E query strings
