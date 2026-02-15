# Phase 3: Media-Server Abstraction - Research

**Researched:** 2026-02-15
**Domain:** Media server APIs (Plex, Kodi, Jellyfin/Emby), multi-server orchestration, Python ABC pattern
**Confidence:** HIGH

## Summary

Phase 3 abstracts media server library refresh notifications behind a common ABC interface -- the exact same pattern already proven in Phase 1 (SubtitleProvider) and Phase 2 (TranslationBackend). The codebase has a mature pattern for this: ABC base class with declarative `config_fields`, a Manager singleton with lazy instance creation, circuit breakers, config stored in `config_entries` DB with namespaced keys (`mediaserver.<type>.<instance>.<key>`), and a collapsible card UI with test buttons.

The existing `jellyfin_client.py` is a 200-line module with `health_check()`, `refresh_item()`, `search_item_by_path()`, and `refresh_library()` -- exactly the methods the ABC needs. Plex uses the well-maintained `python-plexapi` library (v4.18.0, updated Jan 2026). Kodi uses a simple JSON-RPC HTTP API with no good maintained Python library, so a lightweight raw `requests` client is the correct approach (all existing Kodi Python wrappers are abandoned).

**Primary recommendation:** Follow the TranslationManager pattern exactly -- MediaServer ABC with `config_fields`, a `MediaServerManager` singleton, `mediaserver.<name>.<instance>` namespaced config in `config_entries`, and a new "Media Servers" tab in Settings using the existing `BackendCard`-style collapsible pattern. Store multi-server config as a JSON array in `config_entries` (same pattern as `sonarr_instances_json`).

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| plexapi | 4.18.0 | Plex server communication | Official Python bindings, actively maintained (Jan 2026), `item.refresh()`, `section.update()`, `locations` property, file path search via `Media__Part__file__startswith` |
| requests | 2.32.3 | Kodi JSON-RPC HTTP client | Already in requirements.txt, Kodi JSON-RPC is simple HTTP POST -- no need for a dedicated library |
| requests | 2.32.3 | Jellyfin/Emby REST API | Already used by existing `jellyfin_client.py` |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| circuit_breaker.py | (existing) | Per-server circuit breaker | Same pattern as TranslationManager -- skip OPEN servers |
| abc | (stdlib) | Abstract base class | MediaServer ABC definition |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| plexapi | Raw HTTP requests | plexapi handles auth, pagination, item lookup by file, metadata refresh -- reimplementing is error-prone and wasteful |
| kodi-json (PyPI) | Raw requests | kodi-json v1.0.0 last updated Aug 2016, abandoned; raw requests for JSON-RPC 2.0 is trivial (~30 lines) |
| kodipydent | Raw requests | Last updated 2017, abandoned |

**Installation:**
```bash
pip install PlexAPI>=4.18.0
```
Only `PlexAPI` is a new dependency. Kodi uses existing `requests`. Jellyfin/Emby already works with existing `requests`.

## Architecture Patterns

### Recommended Project Structure
```
backend/
  mediaserver/
    __init__.py          # MediaServerManager singleton, get_media_server_manager()
    base.py              # MediaServer ABC, MediaServerType enum, config_fields pattern
    jellyfin.py          # JellyfinServer (migrated from jellyfin_client.py)
    emby.py              # EmbyServer (split from jellyfin -- share base class or keep unified)
    plex.py              # PlexServer backend (uses plexapi library)
    kodi.py              # KodiServer backend (raw JSON-RPC via requests)
  routes/
    mediaservers.py      # New blueprint: /api/v1/mediaservers/* endpoints
```

### Pattern 1: MediaServer ABC (mirrors TranslationBackend)
**What:** Abstract base class all media server backends implement
**When to use:** Every media server type (Jellyfin, Emby, Plex, Kodi)
**Example:**
```python
# Source: Adapted from backend/translation/base.py pattern
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

@dataclass
class RefreshResult:
    success: bool
    message: str
    item_id: Optional[str] = None

class MediaServer(ABC):
    """Abstract base class for media server backends.

    Class-level attributes (same pattern as TranslationBackend):
        name: Unique backend identifier (lowercase, e.g. "jellyfin", "plex")
        display_name: Human-readable name for Settings UI
        config_fields: Declarative config field definitions for dynamic UI forms
    """
    name: str = "unknown"
    display_name: str = "Unknown"
    config_fields: list[dict] = []

    def __init__(self, **config):
        self.config = config

    @abstractmethod
    def health_check(self) -> tuple[bool, str]:
        """Check connectivity. Returns (is_healthy, message)."""
        ...

    @abstractmethod
    def refresh_item(self, file_path: str, item_type: str = "") -> RefreshResult:
        """Refresh metadata for a specific item by file path.

        Args:
            file_path: Path to the media file (used to find item in server)
            item_type: "episode" or "movie" hint
        Returns:
            RefreshResult with success status
        """
        ...

    @abstractmethod
    def refresh_library(self) -> RefreshResult:
        """Trigger a full library scan (fallback)."""
        ...

    @abstractmethod
    def get_config_fields(self) -> list[dict]:
        """Return config field definitions for the Settings UI."""
        ...
```

### Pattern 2: MediaServerManager (mirrors TranslationManager)
**What:** Singleton that manages multiple server instances, dispatches refresh to all
**When to use:** Called after subtitle download/translation to notify all servers
**Example:**
```python
# Source: Adapted from backend/translation/__init__.py pattern
class MediaServerManager:
    """Manages media server backends and dispatches refresh notifications.

    Unlike TranslationManager (which has fallback chains), MediaServerManager
    notifies ALL configured servers (not just the first success).
    """
    def __init__(self):
        self._server_classes: dict[str, type[MediaServer]] = {}
        self._instances: dict[str, list[MediaServer]] = {}  # type -> list of instances
        self._circuit_breakers: dict[str, CircuitBreaker] = {}

    def register_server_type(self, cls: type[MediaServer]) -> None:
        """Register a server type class."""
        self._server_classes[cls.name] = cls

    def refresh_all(self, file_path: str, item_type: str = "") -> list[RefreshResult]:
        """Notify ALL configured media servers about a new subtitle.

        Unlike translation (try until one succeeds), media servers are
        all-notify: every configured server gets the refresh.
        """
        results = []
        for instance_key, instances in self._instances.items():
            for instance in instances:
                cb = self._get_circuit_breaker(instance_key)
                if not cb.allow_request():
                    continue
                try:
                    result = instance.refresh_item(file_path, item_type)
                    if result.success:
                        cb.record_success()
                    else:
                        cb.record_failure()
                    results.append(result)
                except Exception as e:
                    cb.record_failure()
                    results.append(RefreshResult(success=False, message=str(e)))
        return results
```

### Pattern 3: Multi-Instance Config Storage
**What:** JSON array in `config_entries` DB, same as Sonarr/Radarr instances
**When to use:** Users can configure multiple servers of the same type
**Example:**
```python
# Config stored as: mediaserver.instances = JSON array
# [
#   {"type": "jellyfin", "name": "Main Jellyfin", "url": "http://...", "api_key": "..."},
#   {"type": "plex", "name": "Plex Server", "url": "http://...", "token": "..."},
#   {"type": "kodi", "name": "Living Room Kodi", "url": "http://...", "username": "...", "password": "..."}
# ]
#
# Stored in config_entries as key="media_servers_json", value=JSON string
# This mirrors the sonarr_instances_json / radarr_instances_json pattern
```

### Anti-Patterns to Avoid
- **Separate config keys per server type:** Do NOT store `plex_url`, `kodi_url`, etc. as separate Pydantic Settings fields. This was the old Jellyfin approach and does not scale to multi-instance. Use JSON array in `config_entries`.
- **Library-wide refresh as primary:** Always try item-specific refresh first (by file path lookup), fall back to library refresh only when item cannot be found. Full library scans are expensive.
- **Blocking refresh calls:** Media server refresh should be fire-and-forget from the translation pipeline perspective. Use try/except and log errors, never let a media server failure block subtitle processing.
- **Single-type assumption:** The architecture must support multiple instances of the SAME type (e.g., 2 Jellyfin servers) AND multiple types simultaneously.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Plex server communication | Custom HTTP client with token auth, item search, metadata refresh | `plexapi` library (PlexServer, section.update(), item.refresh(), locations) | Plex API is complex (token auth, XML responses, pagination, multiple auth methods). plexapi handles all of this. |
| Kodi JSON-RPC protocol | Custom JSON-RPC 2.0 framing | Simple requests wrapper (~30 lines) but follow JSON-RPC 2.0 spec exactly | Kodi JSON-RPC is simple enough to not need a library, but the framing (jsonrpc version, id, method, params) must be correct |
| Circuit breaker per server | Custom failure tracking | Existing `circuit_breaker.py` module | Already proven in providers and translation backends |
| Config field UI forms | Custom per-server-type form | Declarative `config_fields` + existing `BackendCard` pattern | Phase 2 already solved this -- reuse the pattern |

**Key insight:** The codebase already has TWO proven implementations of the plugin/backend pattern (providers + translation). Media servers are the third instance of the same pattern. The architecture is well-understood; this phase is primarily about implementing the specific API clients, not inventing new patterns.

## Common Pitfalls

### Pitfall 1: Plex Token Auth Confusion
**What goes wrong:** Plex has multiple authentication methods (token, MyPlex account, managed users). Users get confused about which token to use.
**Why it happens:** Plex tokens can be: server token (from Preferences.xml), user token (from plex.tv/api/resources), or claim token (for new servers).
**How to avoid:** Accept only the direct server token (`X-Plex-Token`). Provide clear help text: "Find your token in Plex Settings > Troubleshooting > View XML > X-Plex-Token parameter". The `plexapi` library handles all token passing automatically when constructed with `PlexServer(url, token)`.
**Warning signs:** 401/403 errors on initial connection test.

### Pitfall 2: File Path Mismatch Between Sublarr and Media Server
**What goes wrong:** Sublarr knows the file path as seen from its container/host, but the media server sees a different path (different mount points, different OS).
**Why it happens:** Docker volume mappings differ between Sublarr and the media server. E.g., Sublarr sees `/media/Anime/...` but Plex sees `/data/Anime/...`.
**How to avoid:** Add an optional `path_mapping` field per media server instance (same pattern as Sonarr/Radarr instances). Transform the file path before searching in the media server.
**Warning signs:** Item-specific refresh always fails, fallback to full library scan every time.

### Pitfall 3: Kodi Authentication Complexity
**What goes wrong:** Kodi JSON-RPC can require HTTP Basic Auth, and users may not have it enabled.
**Why it happens:** Kodi's web interface authentication is a separate setting that users often don't configure.
**How to avoid:** Make username/password optional in config_fields. Try unauthenticated first, fall back to Basic Auth. Document that users need to enable "Allow remote control via HTTP" in Kodi settings.
**Warning signs:** Connection refused (Kodi web server not enabled) vs 401 (auth required but not configured).

### Pitfall 4: Plex Item Lookup Performance
**What goes wrong:** Searching all library sections for an item by file path is slow when users have large libraries.
**Why it happens:** Plex has no direct "find by file path" API. Need to iterate library sections or use search.
**How to avoid:** Use `plexapi`'s `section.all()` with `Media__Part__file__startswith` filter, which pushes the filter server-side. Also, iterate only the relevant section type (TV Shows for episodes, Movies for movies).
**Warning signs:** Refresh taking > 5 seconds per item.

### Pitfall 5: Migration Breaking Existing Jellyfin Users
**What goes wrong:** Existing users have `jellyfin_url` and `jellyfin_api_key` in their config. Migration to the new JSON-array format loses their settings.
**Why it happens:** Config format changes without a migration path.
**How to avoid:** Implement backward-compatible config loading: check for legacy `jellyfin_url`/`jellyfin_api_key` settings and auto-migrate them to the new `media_servers_json` array on first read (same pattern as `get_sonarr_instances()` which falls back to legacy single-instance config).
**Warning signs:** Users report Jellyfin refresh stopped working after update.

### Pitfall 6: Emby vs Jellyfin API Divergence
**What goes wrong:** Treating Emby and Jellyfin as identical when they have diverged in some API behaviors.
**Why it happens:** Jellyfin forked from Emby years ago. Most API endpoints are identical, but there are subtle differences in authentication headers and response formats.
**How to avoid:** Keep Jellyfin and Emby as a single backend class (they share 95% of code), but allow a `server_type` flag ("jellyfin" or "emby") for the few differences (auth header: `X-Emby-Token` vs `X-MediaBrowser-Token`, though both work on Jellyfin). The existing `jellyfin_client.py` already uses `X-MediaBrowser-Token` which works for both.
**Warning signs:** One works and the other doesn't with identical configuration.

## Code Examples

Verified patterns from official sources:

### Plex: Connect and Refresh Item
```python
# Source: https://python-plexapi.readthedocs.io/en/latest/introduction.html
# Source: https://python-plexapi.readthedocs.io/en/latest/modules/library.html
from plexapi.server import PlexServer

plex = PlexServer('http://plex:32400', 'mytoken')

# Health check
system = plex.systemInfo  # Raises if unreachable

# Find item by file path in a specific section
movies = plex.library.section('Movies')
# Server-side filter by file path prefix
results = movies.search(filters={"Media__Part__file__startswith": "/data/Movies/MyMovie"})

# Alternative: Check item.locations property
for movie in movies.all():
    if '/data/Movies/MyMovie.mkv' in movie.locations:
        movie.refresh()  # Trigger metadata refresh
        break

# Refresh an entire library section
movies.update()  # Triggers a section scan

# Direct item refresh by ratingKey
item = plex.fetchItem(12345)
item.refresh()
```

### Kodi: JSON-RPC Refresh Episode
```python
# Source: https://kodi.wiki/view/JSON-RPC_API/v12
# Source: https://xbmc.github.io/docs.kodi.tv/master/kodi-base/d4/d32/class_j_s_o_n_r_p_c_1_1_c_video_library.html
import requests
import json

def kodi_rpc(url, method, params=None, username=None, password=None):
    """Send a JSON-RPC 2.0 request to Kodi."""
    payload = {
        "jsonrpc": "2.0",
        "method": method,
        "id": 1,
    }
    if params:
        payload["params"] = params

    auth = (username, password) if username else None
    resp = requests.post(
        f"{url}/jsonrpc",
        json=payload,
        headers={"Content-Type": "application/json"},
        auth=auth,
        timeout=15,
    )
    resp.raise_for_status()
    result = resp.json()
    if "error" in result:
        raise Exception(f"Kodi RPC error: {result['error']}")
    return result.get("result")

# Health check
kodi_rpc("http://kodi:8080", "JSONRPC.Ping")  # Returns "pong"

# Scan specific directory
kodi_rpc("http://kodi:8080", "VideoLibrary.Scan", {"directory": "/media/Anime/"})

# Refresh specific episode (requires knowing episodeid)
kodi_rpc("http://kodi:8080", "VideoLibrary.RefreshEpisode", {
    "episodeid": 1234,
    "ignorenfo": False,
})

# Get episodes to find by file path
episodes = kodi_rpc("http://kodi:8080", "VideoLibrary.GetEpisodes", {
    "properties": ["file", "title", "season", "episode"],
})
# Filter locally by file path match
```

### Jellyfin: Existing Pattern (to migrate)
```python
# Source: backend/jellyfin_client.py (existing codebase)
# The existing JellyfinClient already implements the exact ABC interface needed:
# - health_check() -> tuple[bool, str]
# - refresh_item(item_id, item_type) -> bool
# - search_item_by_path(file_path) -> str | None
# - refresh_library() -> bool
#
# Migration: wrap in MediaServer ABC, add config_fields, move to mediaserver/ package
```

### Notification Dispatch (replacing _notify_integrations)
```python
# Source: backend/translator.py:951 (existing call site)
# Current code (to replace):
#   from jellyfin_client import get_jellyfin_client
#   jellyfin = get_jellyfin_client()
#   if jellyfin and file_path:
#       item_id = jellyfin.search_item_by_path(file_path)
#       ...
#
# New code:
def _notify_integrations(context, file_path=None):
    """Notify ALL configured media servers about new subtitle."""
    if not context or not file_path:
        return

    item_type = ""
    if context.get("sonarr_series_id") or context.get("sonarr_episode_id"):
        item_type = "episode"
    elif context.get("radarr_movie_id"):
        item_type = "movie"

    from mediaserver import get_media_server_manager
    manager = get_media_server_manager()
    results = manager.refresh_all(file_path, item_type)
    for r in results:
        if r.success:
            logger.info("Media server refresh: %s", r.message)
        else:
            logger.warning("Media server refresh failed: %s", r.message)
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Single Jellyfin client singleton | MediaServer ABC + Manager (to implement) | Phase 3 | Supports Plex, Kodi, multi-instance |
| `jellyfin_url` + `jellyfin_api_key` flat config | JSON array `media_servers_json` in config_entries | Phase 3 | Multi-server, multi-type |
| Hardcoded Jellyfin notification in translator.py | Manager.refresh_all() dispatches to all servers | Phase 3 | Decoupled, extensible |
| plexapi 4.15.x | plexapi 4.18.0 | Jan 2026 | Latest stable, Python 3.10+ |
| kodi-json library (2016) | Raw requests JSON-RPC | N/A | kodi-json abandoned, raw HTTP is simpler |

**Deprecated/outdated:**
- `kodi-json` PyPI package: Last release Aug 2016, abandoned. Use raw requests.
- `kodipydent` PyPI package: Last release 2017, abandoned.
- `kodirpc` (GitHub): Minimal activity, not on PyPI.

## Integration Points Summary

The following files must be modified or created:

**New files:**
- `backend/mediaserver/__init__.py` - MediaServerManager singleton
- `backend/mediaserver/base.py` - MediaServer ABC + RefreshResult
- `backend/mediaserver/jellyfin.py` - Migrated from jellyfin_client.py
- `backend/mediaserver/plex.py` - PlexAPI-based backend
- `backend/mediaserver/kodi.py` - JSON-RPC backend
- `backend/routes/mediaservers.py` - Blueprint for media server API endpoints
- `frontend/src/pages/Settings.tsx` - New "Media Servers" tab (replaces "Jellyfin" tab)

**Modified files:**
- `backend/translator.py` - Replace `_notify_integrations()` to use MediaServerManager
- `backend/routes/__init__.py` - Register mediaservers blueprint
- `backend/routes/config.py` - Invalidate media server manager on config change
- `backend/routes/system.py` - Health check reports all media servers
- `backend/app.py` - Initialize media server manager in create_app()
- `backend/config.py` - Add `media_servers_json` setting (legacy fallback)
- `backend/db/__init__.py` - Migration for media_servers table (if needed) or use config_entries
- `backend/requirements.txt` - Add PlexAPI>=4.18.0
- `frontend/src/pages/Onboarding.tsx` - Add media server step
- `frontend/src/lib/types.ts` - Add MediaServerInfo, MediaServerInstance types
- `frontend/src/hooks/useApi.ts` - Add media server API hooks

**Deleted files:**
- `backend/jellyfin_client.py` - Migrated to mediaserver/jellyfin.py (keep as deprecated wrapper if needed for tests)

## Open Questions

1. **Emby vs Jellyfin: Single or Separate Backend?**
   - What we know: APIs are ~95% identical, both use `X-MediaBrowser-Token` auth header. Existing code already works for both.
   - What's unclear: Whether users expect separate "Jellyfin" and "Emby" entries in the type dropdown, or a single "Jellyfin/Emby" entry.
   - Recommendation: Single backend class `JellyfinEmbyServer` with a `server_type` config field ("jellyfin" or "emby") that shows in the dropdown as two entries but shares implementation. This matches user expectations (they see their server type) without code duplication.

2. **Path Mapping Scope: Per-Instance or Global?**
   - What we know: Sonarr/Radarr instances already have per-instance `path_mapping`. The global `path_mapping` setting exists too.
   - What's unclear: Whether media servers need their own path mapping or should reuse the global one.
   - Recommendation: Add optional `path_mapping` per media server instance. If not set, use the global `path_mapping`. This is the same approach as Sonarr/Radarr instances.

3. **Kodi Item Lookup Strategy**
   - What we know: Kodi JSON-RPC has `VideoLibrary.GetEpisodes` and `VideoLibrary.GetMovies` with `file` property, but no direct "find by file path" filter in older API versions.
   - What's unclear: Whether Kodi v20+ (Nexus) or v21+ (Omega) added better file path filtering.
   - Recommendation: For Kodi, prefer `VideoLibrary.Scan` with a directory parameter (scans the parent directory of the subtitle file) as the primary approach. This is simpler and more reliable than looking up specific episode/movie IDs. Use `VideoLibrary.RefreshEpisode`/`VideoLibrary.RefreshMovie` only if the item ID is somehow known (e.g., cached from a previous lookup).

## Sources

### Primary (HIGH confidence)
- python-plexapi docs: https://python-plexapi.readthedocs.io/en/latest/ -- Connection, server methods, library methods, video methods, refresh/analyze
- PlexAPI PyPI: https://pypi.org/project/PlexAPI/ -- v4.18.0, Jan 2026, Python >=3.10
- Plex API refresh: https://www.plexopedia.com/plex-media-server/api/library/refresh-metadata/ -- Raw HTTP endpoint format
- Kodi JSON-RPC API: https://kodi.wiki/view/JSON-RPC_API/v12 -- Stable API spec for Kodi v19+
- Kodi CVideoLibrary: https://xbmc.github.io/docs.kodi.tv/master/kodi-base/d4/d32/class_j_s_o_n_r_p_c_1_1_c_video_library.html -- Scan, RefreshMovie, RefreshEpisode, Get* methods
- Kodi JSON-RPC schema: https://github.com/xbmc/xbmc/blob/master/xbmc/interfaces/json-rpc/schema/methods.json -- Exact method signatures
- Existing codebase: `backend/jellyfin_client.py`, `backend/translation/base.py`, `backend/translation/__init__.py`, `backend/providers/base.py` -- Proven ABC patterns

### Secondary (MEDIUM confidence)
- kodi-json PyPI: https://pypi.org/project/kodi-json/ -- v1.0.0, Aug 2016, confirmed abandoned
- Bazarr Plex integration: https://wiki.bazarr.media/Additional-Configuration/Plex/ -- Confirms Plex metadata refresh approach
- plexapi GitHub: https://github.com/pkkid/python-plexapi -- Active development, MIT license

### Tertiary (LOW confidence)
- Kodi file path filtering in VideoLibrary.GetEpisodes -- exact filter syntax unverified for newer Kodi versions; directory-based scan is the safer approach

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - plexapi is well-documented, Kodi JSON-RPC is stable, Jellyfin/Emby is already working
- Architecture: HIGH - Exact same pattern as TranslationBackend (Phase 2), proven in production
- Pitfalls: HIGH - File path mismatch and migration are well-understood from Sonarr/Radarr instance work
- Plex API specifics: MEDIUM - plexapi docs verified, but `Media__Part__file__startswith` filter needs runtime validation
- Kodi item lookup: MEDIUM - VideoLibrary.Scan with directory is documented, but per-item refresh requires ID lookup that may be slow

**Research date:** 2026-02-15
**Valid until:** 2026-04-15 (90 days -- stable APIs, no breaking changes expected)
