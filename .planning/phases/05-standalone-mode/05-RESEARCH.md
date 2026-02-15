# Phase 5: Standalone Mode - Research

**Researched:** 2026-02-15
**Domain:** Filesystem watching, media file parsing, metadata lookup APIs (TMDB, AniList, TVDB)
**Confidence:** HIGH

## Summary

Phase 5 enables Sublarr to operate without Sonarr/Radarr by letting users point at media folders directly. This requires four major subsystems: (1) a filesystem watcher using `watchdog` (already a dependency, v6.0+) to detect new media files, (2) a media file parser using `guessit` (already a dependency, v3.8+) to extract title/season/episode metadata from filenames, (3) metadata enrichment clients for TMDB, AniList, and TVDB to resolve proper series/movie IDs and poster URLs, and (4) a standalone library manager that stores discovered items in new DB tables and feeds them into the existing wanted_items pipeline.

The codebase already has strong patterns to follow: the plugin watcher (`providers/plugins/watcher.py`) demonstrates watchdog with debouncing, the `wanted_scanner.py` shows how to populate wanted_items with file paths, and `build_query_from_wanted()` in `wanted_search.py` already has filename-parsing fallback. The `mediaserver/` package shows the pattern for multi-backend managers with config stored as JSON in config_entries. The key architectural challenge is ensuring standalone items flow through the same wanted/search/translate pipeline as Sonarr/Radarr items without requiring those services.

**Primary recommendation:** Build a `StandaloneManager` class following the existing singleton/manager pattern, with a `MediaFileWatcher` (watchdog), `MediaFileParser` (guessit), and three thin API clients (TMDB, AniList, TVDB) using raw `requests` -- no third-party wrapper libraries needed since the APIs are simple REST/GraphQL.

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| watchdog | >=6.0.0 | Filesystem monitoring for media folder changes | Already in requirements.txt, proven pattern in plugin watcher |
| guessit | >=3.8.0 | Parse media filenames into structured metadata | Already in requirements.txt, industry standard (used by Medusa, Bazarr, SickGear) |
| requests | 2.32.3 | HTTP client for TMDB/AniList/TVDB API calls | Already in requirements.txt, used by all existing clients |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| N/A (raw requests) | - | TMDB API v3 client | Direct REST calls, no wrapper needed for 3-4 endpoints |
| N/A (raw requests) | - | AniList GraphQL client | Direct POST to graphql.anilist.co, 2-3 queries |
| N/A (raw requests) | - | TVDB API v4 client | Direct REST calls with JWT auth |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Raw requests for TMDB | tmdbv3api (PyPI) | Extra dependency for 4 API calls; raw requests matches existing codebase pattern (sonarr_client, radarr_client all use raw requests) |
| Raw requests for TVDB | tvdb_v4_official (PyPI) | Extra dependency; last release 2022, stale; raw requests is safer |
| Raw requests for AniList | anilistwrappy (PyPI) | Small/unmaintained; GraphQL is just a POST request with a query string |

**Installation:**
```bash
# No new dependencies needed -- all libraries already in requirements.txt
```

## Architecture Patterns

### Recommended Project Structure
```
backend/
  standalone/               # New package for standalone mode
    __init__.py             # StandaloneManager singleton
    watcher.py              # MediaFileWatcher (watchdog Observer)
    parser.py               # MediaFileParser (guessit wrapper + anime patterns)
    scanner.py              # StandaloneScanner (full directory scan, like wanted_scanner)
  metadata/                 # New package for metadata lookup clients
    __init__.py             # MetadataResolver (orchestrates TMDB/AniList/TVDB)
    tmdb_client.py          # TMDB API v3 client
    anilist_client.py       # AniList GraphQL client
    tvdb_client.py          # TVDB API v4 client
  db/
    standalone.py           # New: DB operations for standalone_series, standalone_movies, watched_folders
  routes/
    standalone.py           # New Blueprint: /api/v1/standalone/*
  # Modified files:
  config.py                 # Add standalone_* settings
  wanted_scanner.py         # Extend scan_all() to include standalone items
  wanted_search.py          # Extend build_query_from_wanted() for standalone metadata
  routes/library.py         # Extend /library to include standalone items
  routes/__init__.py        # Register standalone blueprint
  app.py                    # Start standalone watcher in _start_schedulers()

frontend/src/
  pages/Settings.tsx        # Add "Library Sources" tab for folder watch config
  pages/Onboarding.tsx      # Add standalone setup path (skip Sonarr/Radarr step)
  api/client.ts             # Add standalone API functions
  hooks/useApi.ts           # Add standalone React Query hooks
  lib/types.ts              # Add standalone TypeScript interfaces
```

### Pattern 1: Filesystem Watcher with Debounce (follows plugin watcher pattern)
**What:** Monitor configured directories for new/modified/deleted video files
**When to use:** Always running when standalone mode is enabled
**Example:**
```python
# Source: existing pattern from providers/plugins/watcher.py
from watchdog.observers import Observer
from watchdog.events import PatternMatchingEventHandler

VIDEO_EXTENSIONS = ['*.mkv', '*.mp4', '*.avi', '*.m4v', '*.wmv', '*.flv', '*.webm']

class MediaFileWatcher(PatternMatchingEventHandler):
    """Watches media directories for video file changes."""

    def __init__(self, on_new_file, debounce_seconds=5.0):
        super().__init__(patterns=VIDEO_EXTENSIONS, ignore_directories=True)
        self.on_new_file = on_new_file
        self._debounce_seconds = debounce_seconds
        self._pending = {}  # path -> Timer
        self._lock = threading.Lock()

    def on_created(self, event):
        self._schedule_process(event.src_path)

    def on_moved(self, event):
        self._schedule_process(event.dest_path)

    def _schedule_process(self, path):
        with self._lock:
            if path in self._pending:
                self._pending[path].cancel()
            timer = threading.Timer(
                self._debounce_seconds, self._process_file, args=(path,)
            )
            timer.daemon = True
            timer.start()
            self._pending[path] = timer

    def _process_file(self, path):
        with self._lock:
            self._pending.pop(path, None)
        self.on_new_file(path)
```

### Pattern 2: Guessit Media File Parser
**What:** Parse video filenames into structured metadata
**When to use:** When a new file is detected or during full directory scan
**Example:**
```python
# Source: guessit v3.8 API + existing codebase patterns
from guessit import guessit

def parse_media_file(file_path: str) -> dict:
    """Parse a media file path into structured metadata."""
    filename = os.path.basename(file_path)

    # Try episode detection first (anime-aware)
    result = guessit(filename, {'type': 'episode', 'episode_prefer_number': True})

    if result.get('type') == 'episode':
        return {
            'type': 'episode',
            'title': result.get('title', ''),
            'season': result.get('season'),
            'episode': result.get('episode'),
            'absolute_episode': result.get('absolute_episode'),
            'year': result.get('year'),
            'release_group': result.get('release_group', ''),
            'source': result.get('source', ''),
            'resolution': result.get('screen_size', ''),
            'video_codec': result.get('video_codec', ''),
        }

    # Fallback: try as movie
    result = guessit(filename, {'type': 'movie'})
    return {
        'type': 'movie',
        'title': result.get('title', ''),
        'year': result.get('year'),
        'release_group': result.get('release_group', ''),
        'source': result.get('source', ''),
        'resolution': result.get('screen_size', ''),
        'video_codec': result.get('video_codec', ''),
    }
```

### Pattern 3: Metadata Resolution Chain
**What:** Look up series/movie metadata from external APIs
**When to use:** After parsing filename, to get TMDB/AniList IDs, poster URLs, episode counts
**Example:**
```python
# MetadataResolver orchestrates the lookup chain
class MetadataResolver:
    """Resolves metadata from TMDB, AniList, and TVDB."""

    def resolve_series(self, title: str, year: int = None, is_anime: bool = False) -> dict:
        """Try AniList first for anime, then TMDB, then TVDB."""
        if is_anime:
            result = self.anilist.search_anime(title)
            if result:
                return self._normalize_anilist(result)

        result = self.tmdb.search_tv(title, year=year)
        if result:
            return self._normalize_tmdb_tv(result)

        result = self.tvdb.search_series(title, year=year)
        if result:
            return self._normalize_tvdb(result)

        return {'title': title, 'year': year, 'source': 'filename'}
```

### Pattern 4: Standalone Items in Wanted Pipeline
**What:** Standalone-discovered items reuse the existing wanted_items table
**When to use:** When standalone scanner finds files missing target language subtitles
**Example:**
```python
# Follows exact same pattern as wanted_scanner._scan_sonarr_series
# but without Sonarr dependency
upsert_wanted_item(
    item_type="episode",          # or "movie"
    file_path=mapped_path,
    title=f"{series_title} - S{season:02d}E{episode:02d}",
    season_episode=f"S{season:02d}E{episode:02d}",
    existing_sub=existing_sub,
    missing_languages=[target_lang],
    sonarr_series_id=None,        # No Sonarr ID
    sonarr_episode_id=None,       # No Sonarr ID
    standalone_series_id=series_id,  # New field: standalone series reference
    target_language=target_lang,
    instance_name="standalone",    # Mark as standalone source
)
```

### Anti-Patterns to Avoid
- **Re-implementing the translation pipeline:** Standalone items MUST flow through existing wanted_search.process_wanted_item() -- do NOT create a separate pipeline
- **Polling the filesystem instead of watching:** watchdog is event-driven; use Observer, do NOT use os.walk() on a timer for change detection (still need initial scan though)
- **Storing metadata in a separate database:** Use the same SQLite DB with new tables; standalone items must be queryable alongside Sonarr/Radarr items
- **Using guessit without the directory context:** The parent directory often contains the series name; parse the full path, not just the filename
- **Blocking the watcher thread with API calls:** Queue file events and process metadata lookups asynchronously in a worker thread

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Filename parsing (S01E02, release groups, codecs) | Custom regex patterns | guessit library | Thousands of edge cases; guessit handles ~50 naming conventions |
| Filesystem event monitoring | os.walk() polling loop | watchdog Observer | Kernel-level inotify/kqueue/ReadDirectoryChanges; efficient, debounced |
| Anime title matching | Fuzzy string matching | AniList GraphQL search | AniList has romaji/english/native title variants, handles partial matches |
| Video file detection | Hardcoded extension list | guessit + MIME type check | guessit knows all container formats |
| TMDB/AniList/TVDB caching | Custom cache dict | DB-backed cache table | Persistent across restarts, TTL-based expiration, already have pattern in provider_cache |

**Key insight:** The existing wanted_scanner + wanted_search pipeline already handles ~80% of what standalone mode needs. The main new work is file detection and metadata enrichment -- the subtitle search/download/translate flow is unchanged.

## Common Pitfalls

### Pitfall 1: Anime Absolute Episode Numbering
**What goes wrong:** Anime files use absolute episode numbers (e.g., "Title - 153.mkv") instead of S01E01 format. guessit may parse "153" as something other than an episode number.
**Why it happens:** guessit defaults to SxE parsing; anime uses absolute numbering heavily.
**How to avoid:** Use `episode_prefer_number=True` in guessit options. Also parse `absolute_episode` field from guessit output. When looking up metadata, use the absolute episode to map to season+episode via TMDB/AniList.
**Warning signs:** Anime files showing up as "Unknown" or with wrong season/episode numbers.

### Pitfall 2: Duplicate Detection on Watchdog Events
**What goes wrong:** watchdog fires multiple events for a single file operation (create + modify + modify for large file copies). Processing each event separately causes duplicate wanted items and wasted API calls.
**Why it happens:** File copy operations trigger create, then multiple modify events as data is written. NFS/CIFS network shares are even worse.
**How to avoid:** Implement debounce (5-10 seconds) per file path. Check file size stability before processing (wait until file stops growing). The existing plugin watcher pattern in `providers/plugins/watcher.py` already demonstrates the debounce pattern.
**Warning signs:** Same file appearing multiple times in the processing queue.

### Pitfall 3: Directory Structure Ambiguity
**What goes wrong:** Standalone folders may have flat structures (all files in one folder) or nested structures (Series/Season X/file.mkv). Without Sonarr's metadata, grouping files into series becomes guesswork.
**Why it happens:** No standard for media folder organization. Users have wildly different layouts.
**How to avoid:** Support BOTH flat and nested structures. Use guessit on the full relative path (not just filename) to extract series name from parent directories. Provide manual override in UI for series assignment.
**Warning signs:** Files from different series being grouped together, or same series split into multiple entries.

### Pitfall 4: TMDB/AniList API Rate Limits
**What goes wrong:** Large initial scan triggers hundreds of API calls, hitting rate limits and getting temporarily banned.
**Why it happens:** TMDB allows ~40 requests per 10 seconds. AniList has rate limits too. A media library with 100+ series will exceed this during first scan.
**How to avoid:** Cache metadata aggressively in DB (30-day TTL). Batch lookups by unique series title (not per-episode). Rate-limit API calls (1-2/second). Queue metadata resolution and process in background.
**Warning signs:** HTTP 429 responses, empty metadata for many items.

### Pitfall 5: Wanted Scanner Coupling to Sonarr/Radarr
**What goes wrong:** The existing `wanted_scanner.scan_all()` only scans Sonarr and Radarr instances. Adding standalone scanning requires modifying this without breaking existing behavior.
**Why it happens:** The scanner was designed with Sonarr/Radarr as the only data sources.
**How to avoid:** Add a `_scan_standalone()` method to WantedScanner that follows the same pattern as `_scan_sonarr()` and `_scan_radarr()`. Call it in `scan_all()` alongside the existing scans. Use `instance_name="standalone"` to distinguish items. The cleanup logic in `_cleanup()` should also handle standalone items.
**Warning signs:** Standalone items being cleaned up during Sonarr/Radarr scans (because they have no sonarr_series_id).

### Pitfall 6: File Stability Check (Incomplete Copies)
**What goes wrong:** watchdog detects a file that's still being copied. Processing starts on an incomplete file, ffprobe fails, metadata is wrong.
**Why it happens:** Large video files take minutes to copy. watchdog fires created event immediately.
**How to avoid:** After debounce, check file size at two intervals 2 seconds apart. Only process when file size is stable. This is especially important for Docker volumes with network storage.
**Warning signs:** ffprobe failures on newly detected files, zero-byte file entries.

## Code Examples

### TMDB API Client (Verified API structure)
```python
# Source: TMDB API v3 docs (developer.themoviedb.org)
import requests
import logging

logger = logging.getLogger(__name__)

class TMDBClient:
    """TMDB API v3 client for series/movie metadata lookup."""

    BASE_URL = "https://api.themoviedb.org/3"

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.session = requests.Session()
        self.session.headers["Authorization"] = f"Bearer {api_key}"

    def search_tv(self, query: str, year: int = None) -> dict | None:
        """Search for a TV series by title."""
        params = {"query": query, "language": "en-US", "page": 1}
        if year:
            params["first_air_date_year"] = year
        resp = self.session.get(f"{self.BASE_URL}/search/tv", params=params)
        resp.raise_for_status()
        results = resp.json().get("results", [])
        return results[0] if results else None

    def search_movie(self, query: str, year: int = None) -> dict | None:
        """Search for a movie by title."""
        params = {"query": query, "language": "en-US", "page": 1}
        if year:
            params["year"] = year
        resp = self.session.get(f"{self.BASE_URL}/search/movie", params=params)
        resp.raise_for_status()
        results = resp.json().get("results", [])
        return results[0] if results else None

    def get_tv_details(self, tv_id: int) -> dict:
        """Get TV series details including seasons/episodes."""
        resp = self.session.get(f"{self.BASE_URL}/tv/{tv_id}", params={"language": "en-US"})
        resp.raise_for_status()
        return resp.json()

    def get_tv_external_ids(self, tv_id: int) -> dict:
        """Get external IDs (IMDB, TVDB) for a TV series."""
        resp = self.session.get(f"{self.BASE_URL}/tv/{tv_id}/external_ids")
        resp.raise_for_status()
        return resp.json()  # {"imdb_id": "tt...", "tvdb_id": 123, ...}

    def get_tv_season(self, tv_id: int, season_number: int) -> dict:
        """Get season details including episode list."""
        resp = self.session.get(
            f"{self.BASE_URL}/tv/{tv_id}/season/{season_number}",
            params={"language": "en-US"}
        )
        resp.raise_for_status()
        return resp.json()
```

### AniList GraphQL Client
```python
# Source: AniList API docs (docs.anilist.co)
import requests
import logging

logger = logging.getLogger(__name__)

ANILIST_URL = "https://graphql.anilist.co"

SEARCH_QUERY = """
query ($search: String!, $type: MediaType) {
  Page(perPage: 5) {
    media(search: $search, type: $type) {
      id
      idMal
      title {
        romaji
        english
        native
      }
      format
      status
      episodes
      seasonYear
      coverImage { large }
      externalLinks {
        site
        url
      }
    }
  }
}
"""

class AniListClient:
    """AniList GraphQL API client for anime metadata lookup.

    No API key required -- AniList is free and public.
    Rate limit: ~90 requests per minute.
    """

    def __init__(self):
        self.session = requests.Session()

    def search_anime(self, title: str) -> dict | None:
        """Search AniList for an anime by title."""
        variables = {"search": title, "type": "ANIME"}
        resp = self.session.post(
            ANILIST_URL,
            json={"query": SEARCH_QUERY, "variables": variables},
        )
        resp.raise_for_status()
        media_list = resp.json().get("data", {}).get("Page", {}).get("media", [])
        return media_list[0] if media_list else None
```

### TVDB API v4 Client
```python
# Source: TVDB API v4 docs (github.com/thetvdb/v4-api)
import requests
import time
import logging

logger = logging.getLogger(__name__)

class TVDBClient:
    """TVDB API v4 client for series metadata lookup.

    Requires API key. Optional PIN for user-specific features.
    JWT token-based auth with refresh support.
    """

    BASE_URL = "https://api4.thetvdb.com/v4"

    def __init__(self, api_key: str, pin: str = ""):
        self.api_key = api_key
        self.pin = pin
        self.session = requests.Session()
        self._token = ""
        self._token_expires = 0

    def _ensure_auth(self):
        """Authenticate if token is missing or expired."""
        if self._token and time.time() < self._token_expires:
            return
        payload = {"apikey": self.api_key}
        if self.pin:
            payload["pin"] = self.pin
        resp = self.session.post(f"{self.BASE_URL}/login", json=payload)
        resp.raise_for_status()
        data = resp.json().get("data", {})
        self._token = data.get("token", "")
        self._token_expires = time.time() + 86400  # 24h validity
        self.session.headers["Authorization"] = f"Bearer {self._token}"

    def search_series(self, query: str, year: int = None) -> dict | None:
        """Search for a series by name."""
        self._ensure_auth()
        params = {"query": query, "type": "series"}
        if year:
            params["year"] = str(year)
        resp = self.session.get(f"{self.BASE_URL}/search", params=params)
        resp.raise_for_status()
        results = resp.json().get("data", [])
        return results[0] if results else None

    def get_series(self, series_id: int) -> dict:
        """Get series info by TVDB ID."""
        self._ensure_auth()
        resp = self.session.get(f"{self.BASE_URL}/series/{series_id}")
        resp.raise_for_status()
        return resp.json().get("data", {})

    def get_series_episodes(self, series_id: int, page: int = 0) -> dict:
        """Get episodes for a series."""
        self._ensure_auth()
        resp = self.session.get(
            f"{self.BASE_URL}/series/{series_id}/episodes/default",
            params={"page": page}
        )
        resp.raise_for_status()
        return resp.json().get("data", {})
```

### DB Schema for Standalone Tables
```sql
-- Watched folders configured by user
CREATE TABLE IF NOT EXISTS watched_folders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    path TEXT NOT NULL UNIQUE,
    label TEXT DEFAULT '',
    media_type TEXT DEFAULT 'auto',  -- 'auto', 'tv', 'movie'
    enabled INTEGER DEFAULT 1,
    last_scan_at TEXT DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Standalone-discovered series (no Sonarr dependency)
CREATE TABLE IF NOT EXISTS standalone_series (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    year INTEGER,
    folder_path TEXT NOT NULL,
    tmdb_id INTEGER,
    tvdb_id INTEGER,
    anilist_id INTEGER,
    imdb_id TEXT DEFAULT '',
    poster_url TEXT DEFAULT '',
    is_anime INTEGER DEFAULT 0,
    episode_count INTEGER DEFAULT 0,
    season_count INTEGER DEFAULT 0,
    metadata_source TEXT DEFAULT '',  -- 'tmdb', 'anilist', 'tvdb', 'filename'
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(folder_path)
);

CREATE INDEX IF NOT EXISTS idx_standalone_series_tmdb ON standalone_series(tmdb_id);
CREATE INDEX IF NOT EXISTS idx_standalone_series_anilist ON standalone_series(anilist_id);

-- Standalone-discovered movies (no Radarr dependency)
CREATE TABLE IF NOT EXISTS standalone_movies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    year INTEGER,
    file_path TEXT NOT NULL UNIQUE,
    tmdb_id INTEGER,
    imdb_id TEXT DEFAULT '',
    poster_url TEXT DEFAULT '',
    metadata_source TEXT DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_standalone_movies_tmdb ON standalone_movies(tmdb_id);

-- Metadata cache (for rate-limit protection)
CREATE TABLE IF NOT EXISTS metadata_cache (
    cache_key TEXT PRIMARY KEY,
    provider TEXT NOT NULL,  -- 'tmdb', 'anilist', 'tvdb'
    response_json TEXT NOT NULL,
    cached_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_metadata_cache_expires ON metadata_cache(expires_at);
```

### Wanted Items Integration
```python
# The wanted_items table already has the needed columns:
# - sonarr_series_id / sonarr_episode_id / radarr_movie_id can be NULL
# - instance_name can be "standalone"
# - item_type is "episode" or "movie" (already supported)
#
# Add via migration:
# ALTER TABLE wanted_items ADD COLUMN standalone_series_id INTEGER;
# ALTER TABLE wanted_items ADD COLUMN standalone_movie_id INTEGER;
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| guessit 2.x with custom rebulk rules | guessit 3.8 with episode_prefer_number | 2023 | Better anime support, cleaner API |
| TMDB API key in query param | TMDB Bearer token in header | 2023 | More secure, same functionality |
| TVDB API v3 (deprecated) | TVDB API v4 with JWT auth | 2022 | v3 no longer available, v4 required |
| AniList REST API v1 (removed) | AniList GraphQL API v2 | 2018 | GraphQL is the only option now |
| Manual folder scanning only | watchdog event-driven + initial scan | Current | Event-driven for real-time, scan for startup |

**Deprecated/outdated:**
- TVDB API v3: Completely removed, must use v4
- TMDB API key in URL parameter: Still works but deprecated; use Bearer token header
- AniList REST API: Does not exist, only GraphQL

## Open Questions

1. **Anime detection heuristic: how to decide if a series is anime?**
   - What we know: guessit can detect release groups commonly associated with fansubs (e.g., HorribleSubs, SubsPlease). AniList search can confirm if a title is anime.
   - What's unclear: Should we always try AniList first for all titles, or only when anime is suspected?
   - Recommendation: Check for anime indicators first (square bracket release group `[Group]`, absolute numbering, known anime release groups), then try AniList. Fall back to TMDB for non-anime. This avoids unnecessary AniList calls for Western media.

2. **Handling mixed media folders (TV + movies in same folder)**
   - What we know: guessit can distinguish episodes from movies based on filename patterns. The `media_type` on watched_folders can be set to 'auto', 'tv', or 'movie'.
   - What's unclear: How reliable is guessit's auto-detection for edge cases?
   - Recommendation: Use guessit auto-detection in 'auto' mode but allow user to constrain folder type. Log ambiguous cases for user review.

3. **TVDB API key requirement: free tier vs subscription**
   - What we know: TVDB v4 requires an API key. Free project keys exist but have limitations. End users may need their own subscription PIN.
   - What's unclear: Exact rate limits and whether a single project key works for all end users.
   - Recommendation: Make TVDB optional (TMDB + AniList cover most needs). Only use TVDB as fallback when TMDB/AniList fail. User provides their own API key if they want TVDB.

4. **Language profile assignment for standalone series**
   - What we know: series_language_profiles uses sonarr_series_id as PK. standalone series need their own profile assignment.
   - What's unclear: Should we add standalone_series_id to the profiles table or create a new junction table?
   - Recommendation: Create `standalone_series_profiles` and `standalone_movie_profiles` junction tables, mirroring the existing pattern. The default profile applies automatically.

## Sources

### Primary (HIGH confidence)
- Existing codebase: `providers/plugins/watcher.py` -- watchdog + debounce pattern
- Existing codebase: `wanted_scanner.py` -- scanning and wanted_items population pattern
- Existing codebase: `wanted_search.py` -- build_query_from_wanted() with filename fallback
- Existing codebase: `config.py` -- settings and config cascade pattern
- Existing codebase: `db/__init__.py` -- SQLite schema and migration pattern
- Existing codebase: `mediaserver/__init__.py` -- manager singleton pattern
- [guessit GitHub](https://github.com/guessit-io/guessit) -- v3.8.0, properties, episode_prefer_number
- [AniList API Docs](https://docs.anilist.co/) -- GraphQL API, media search, no auth required
- [TMDB API Docs](https://developer.themoviedb.org/docs/search-and-query-for-details) -- Search-then-detail pattern
- [TMDB TV External IDs](https://developer.themoviedb.org/reference/tv-series-external-ids) -- IMDB/TVDB cross-reference
- [TVDB v4 Python](https://github.com/thetvdb/tvdb-v4-python) -- API structure, JWT auth

### Secondary (MEDIUM confidence)
- [watchdog PyPI](https://pypi.org/project/watchdog/) -- v6.0.0 confirmed, PatternMatchingEventHandler
- [TVDB API Swagger](https://thetvdb.github.io/v4-api/) -- Endpoint structure
- [guessit anime support issue](https://github.com/guessit-io/guessit/issues/127) -- anime pattern handling

### Tertiary (LOW confidence)
- AniList externalLinks field structure -- NOT verified via docs, based on community reports
- TVDB rate limits -- Not documented officially, assumed similar to TMDB

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - all libraries already in requirements.txt, verified versions
- Architecture: HIGH - follows established codebase patterns closely (watchdog watcher, scanner singleton, DB domain modules, Blueprint routes)
- Pitfalls: HIGH - common watchdog/filesystem pitfalls well-documented; anime parsing edge cases verified via guessit issue tracker
- API clients: MEDIUM - TMDB and AniList API structures verified via official docs; TVDB v4 structure based on GitHub README (last updated 2022)
- DB schema: HIGH - follows existing patterns exactly (config_entries, provider_cache, wanted_items)

**Research date:** 2026-02-15
**Valid until:** 2026-03-15 (30 days -- stable libraries, stable APIs)
