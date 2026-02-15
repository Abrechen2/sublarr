# Creating a Sublarr Provider Plugin

This guide explains how to create a custom subtitle provider plugin for Sublarr. Plugins are Python files that implement the `SubtitleProvider` interface and are loaded at runtime from the plugins directory.

## Quick Start

1. **Copy the template:**
   ```bash
   cp my_provider.py /config/plugins/my_provider.py
   ```

2. **Rename and modify:**
   - Change `name = "my_provider"` to a unique identifier (e.g., `name = "supersubtitles"`)
   - Update `languages`, `config_fields`, `rate_limit`, `timeout`, `max_retries`
   - Implement `search()` and `download()` with your provider's API

3. **Load the plugin:**
   - Restart Sublarr, OR
   - Call `POST /api/v1/plugins/reload` (no restart needed), OR
   - Enable hot-reload (`SUBLARR_PLUGIN_HOT_RELOAD=true`) for automatic loading on file changes

4. **Configure:**
   - Go to Settings > Providers in the UI
   - Your plugin appears with the config fields you defined
   - Enter API keys and settings, then save

## Plugin Requirements

A valid plugin file must:

- Be a `.py` file in the plugins directory (default: `/config/plugins/`)
- Not start with `_` or `.` (those are skipped)
- Contain exactly one class that extends `SubtitleProvider`
- Have a unique `name` attribute (no conflicts with built-in providers)
- Implement `search()` and `download()` abstract methods

## Provider API Contract

### Required Methods

#### `search(query: VideoQuery) -> list[SubtitleResult]`

Search your provider's API for subtitles matching the query. Return a list of `SubtitleResult` objects. Do not sort results -- the `ProviderManager` handles scoring and sorting.

#### `download(result: SubtitleResult) -> bytes`

Download a subtitle file given a `SubtitleResult` from `search()`. Return raw file content as bytes (UTF-8 encoded). Handle archive extraction (ZIP, RAR, XZ) if your provider returns compressed files.

### Optional Methods

#### `initialize()`

Called once when the provider is loaded. Set up HTTP sessions, authenticate, etc. If your provider needs an API key, check for it here and skip session creation if missing.

#### `terminate()`

Called when the provider is unloaded (app shutdown or plugin reload). Close HTTP sessions and release resources.

#### `health_check() -> tuple[bool, str]`

Check if the provider's API is reachable. Returns `(is_healthy, message)`. Default returns `(True, "OK")`.

## Class Attributes

| Attribute | Type | Default | Description |
|-----------|------|---------|-------------|
| `name` | `str` | `"unknown"` | Unique provider identifier (lowercase, no spaces) |
| `languages` | `set[str]` | `set()` | Supported ISO 639-1 language codes |
| `config_fields` | `list[dict]` | `[]` | Configuration fields for the Settings UI |
| `rate_limit` | `tuple[int, int]` | `(0, 0)` | `(max_requests, window_seconds)`, `(0, 0)` = no limit |
| `timeout` | `int` | `30` | HTTP request timeout in seconds |
| `max_retries` | `int` | `2` | Retry attempts on transient failure |
| `is_plugin` | `bool` | `False` | Set automatically by the plugin system (do not set manually) |

## config_fields Schema

Each config field is a dict with these keys:

```python
{
    "key": "api_key",          # Internal key, passed as kwarg to __init__
    "label": "API Key",        # Human-readable label in the Settings UI
    "type": "password",        # "text", "password", or "number"
    "required": True,          # If True, provider needs this to function
    "default": "",             # Default value (optional)
}
```

Config values are stored in the database under `plugin.<name>.<key>` namespace. Users edit them in the Settings UI.

### Example config_fields

```python
config_fields = [
    {"key": "api_key", "label": "API Key", "type": "password", "required": True},
    {"key": "base_url", "label": "Base URL", "type": "text", "required": False, "default": "https://api.example.com"},
    {"key": "results_per_page", "label": "Results Per Page", "type": "number", "required": False, "default": "50"},
]
```

## VideoQuery Fields Reference

The `VideoQuery` object passed to `search()` contains all available metadata:

| Field | Type | Description |
|-------|------|-------------|
| `file_path` | `str` | Full path to the video file |
| `file_size` | `int` | File size in bytes |
| `file_hash` | `str` | OpenSubtitles-compatible hash |
| `title` | `str` | Movie title |
| `year` | `int\|None` | Release year |
| `imdb_id` | `str` | IMDB ID (e.g., `"tt1234567"`) |
| `tmdb_id` | `int\|None` | The Movie Database ID |
| `genres` | `list[str]` | Movie genres |
| `series_title` | `str` | TV series name |
| `season` | `int\|None` | Season number |
| `episode` | `int\|None` | Episode number |
| `episode_title` | `str` | Episode title |
| `anidb_id` | `int\|None` | AniDB anime ID |
| `anidb_episode_id` | `int\|None` | AniDB episode ID |
| `anilist_id` | `int\|None` | AniList anime ID |
| `tvdb_id` | `int\|None` | TVDB ID |
| `release_group` | `str` | Release group name |
| `source` | `str` | "BluRay", "WEB-DL", etc. |
| `resolution` | `str` | "1080p", "720p", etc. |
| `video_codec` | `str` | "x264", "x265", etc. |
| `languages` | `list[str]` | Requested language codes (ISO 639-1) |

### Computed Properties

- `query.is_episode` -- `True` if `season` and `episode` are set
- `query.is_movie` -- `True` if not an episode and `title` is set
- `query.display_name` -- Human-readable name for logging

## SubtitleResult Fields Reference

Return these from `search()`:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `provider_name` | `str` | Yes | Must be `self.name` |
| `subtitle_id` | `str` | Yes | Provider-specific ID |
| `language` | `str` | Yes | ISO 639-1 code |
| `format` | `SubtitleFormat` | No | `ASS`, `SRT`, `SSA`, `VTT`, or `UNKNOWN` |
| `filename` | `str` | No | Original subtitle filename |
| `download_url` | `str` | No | URL used by `download()` |
| `release_info` | `str` | No | Release info text |
| `hearing_impaired` | `bool` | No | True if HI subtitle |
| `forced` | `bool` | No | True if forced subtitle |
| `fps` | `float\|None` | No | Subtitle framerate |
| `matches` | `set[str]` | No | What matched (see Scoring) |
| `provider_data` | `dict` | No | Extra provider-specific data |

## Scoring System

The `ProviderManager` computes scores automatically based on the `matches` set on each `SubtitleResult`. Set `result.matches` to indicate what metadata your search matched against.

### Score Weights

**Episode Scores:**
| Match Key | Score |
|-----------|-------|
| `hash` | 359 |
| `series` | 180 |
| `year` | 90 |
| `season` | 30 |
| `episode` | 30 |
| `release_group` | 14 |
| `source` | 7 |
| `audio_codec` | 3 |
| `resolution` | 2 |
| `hearing_impaired` | 1 |

**Movie Scores:**
| Match Key | Score |
|-----------|-------|
| `hash` | 119 |
| `title` | 60 |
| `year` | 30 |
| `release_group` | 13 |
| `source` | 7 |
| `audio_codec` | 3 |
| `resolution` | 2 |
| `hearing_impaired` | 1 |

**Format Bonus:** ASS/SSA format automatically receives +50 points (Sublarr prefers styled subtitles).

### Example

```python
# Your search matched the series name, season, and episode
result.matches = {"series", "season", "episode"}
# Score: 180 + 30 + 30 = 240
# If it's ASS format: 240 + 50 = 290
```

## Rate Limiting and Timeouts

### Rate Limiting

Set `rate_limit = (max_requests, window_seconds)` on your class. The `ProviderManager` enforces this limit across all search and download calls. Example:

```python
rate_limit = (5, 1)    # 5 requests per second (OpenSubtitles-style)
rate_limit = (100, 60) # 100 requests per minute
rate_limit = (0, 0)    # No rate limiting
```

The `RetryingSession` from `create_session()` also handles HTTP 429 responses automatically (reads `Retry-After` header).

### Timeouts

Set `timeout` on your class (seconds). This is used:
- By `create_session()` as the default HTTP timeout
- By `ProviderManager` as the search deadline

## Error Handling

Sublarr provides three specialized exceptions in `providers.base`:

```python
from providers.base import (
    ProviderAuthError,       # 401/403 -- authentication failed
    ProviderRateLimitError,  # 429 -- rate limit exceeded
    ProviderTimeoutError,    # Request timed out
    ProviderError,           # Generic provider error (base class)
)
```

**Usage in your provider:**

```python
def search(self, query):
    resp = self.session.get(f"{self.base_url}/search")
    if resp.status_code == 401:
        raise ProviderAuthError("Invalid API key")
    if resp.status_code == 429:
        raise ProviderRateLimitError("Rate limit exceeded")
```

**Note:** The `RetryingSession` from `create_session()` already raises `ProviderAuthError` and `ProviderRateLimitError` automatically for 401/403/429 responses. You only need to raise them manually for non-standard error patterns.

The `ProviderManager` handles errors as follows:
- `ProviderAuthError` -- Stops retrying immediately
- `ProviderRateLimitError` -- Retries with exponential backoff
- Other exceptions -- Retries up to `max_retries` times

## HTTP Sessions

Use `create_session()` from `providers.http_session` for HTTP calls:

```python
from providers.http_session import create_session

def initialize(self):
    self.session = create_session(
        max_retries=self.max_retries,   # From class attribute
        timeout=self.timeout,           # From class attribute
        user_agent="Sublarr-Plugin/1.0",
    )
    # Set authentication headers
    self.session.headers["X-Api-Key"] = self.api_key
```

The session provides:
- Automatic retries on 429, 500, 502, 503, 504
- Exponential backoff between retries
- Rate limit detection via response headers
- Default timeout on all requests

## Common Patterns

### Handling ZIP Archives

```python
import zipfile
import io

def download(self, result):
    resp = self.session.get(result.download_url)
    resp.raise_for_status()
    content = resp.content

    if content[:4] == b'PK\x03\x04':  # ZIP magic bytes
        with zipfile.ZipFile(io.BytesIO(content)) as zf:
            for name in zf.namelist():
                if name.endswith(('.srt', '.ass', '.ssa')):
                    content = zf.read(name)
                    if name.endswith(('.ass', '.ssa')):
                        result.format = SubtitleFormat.ASS
                    break

    result.content = content
    return content
```

### Handling XZ Compression

```python
import lzma

def download(self, result):
    resp = self.session.get(result.download_url)
    resp.raise_for_status()
    content = resp.content

    if content[:6] == b'\xfd7zXZ\x00':  # XZ magic bytes
        content = lzma.decompress(content)

    result.content = content
    return content
```

### Handling RAR Archives

```python
import rarfile
import io

def download(self, result):
    resp = self.session.get(result.download_url)
    resp.raise_for_status()
    content = resp.content

    if content[:4] == b'Rar!':  # RAR magic bytes
        with rarfile.RarFile(io.BytesIO(content)) as rf:
            for name in rf.namelist():
                if name.endswith(('.srt', '.ass', '.ssa')):
                    content = rf.read(name)
                    break

    result.content = content
    return content
```

### Conditional Search (Episode vs Movie)

```python
def search(self, query):
    if query.is_episode:
        return self._search_episode(query)
    elif query.is_movie:
        return self._search_movie(query)
    return []

def _search_episode(self, query):
    params = {
        "series": query.series_title,
        "season": query.season,
        "episode": query.episode,
    }
    # Add optional IDs for more precise matching
    if query.imdb_id:
        params["imdb_id"] = query.imdb_id
    if query.tvdb_id:
        params["tvdb_id"] = query.tvdb_id
    # ... make API call, build results ...
```

## Testing Your Plugin

### Manual Testing

1. Drop your plugin file into the plugins directory
2. Reload plugins:
   ```bash
   curl -X POST http://localhost:5765/api/v1/plugins/reload
   ```
3. Check that your plugin is listed:
   ```bash
   curl http://localhost:5765/api/v1/plugins
   ```
4. Check the logs for any errors:
   ```bash
   curl http://localhost:5765/api/v1/logs
   ```

### Hot-Reload Testing

Enable hot-reload for a faster development cycle:

```env
SUBLARR_PLUGIN_HOT_RELOAD=true
```

With this enabled, saving a `.py` file in the plugins directory automatically triggers a reload (2-second debounce).

### Verify Provider Appears in Search

After configuring your plugin (API key, etc.):

```bash
curl -X POST http://localhost:5765/api/v1/providers/search \
  -H "Content-Type: application/json" \
  -d '{"title": "Test Movie", "languages": ["en"]}'
```

## Docker Volume Mounting

In Docker, the plugins directory is typically `/config/plugins/`. Mount a host directory to provide plugins:

```yaml
# docker-compose.yml
services:
  sublarr:
    image: sublarr:latest
    volumes:
      - ./config:/config
      - ./my-plugins:/config/plugins  # Your custom plugins
    environment:
      - SUBLARR_PLUGIN_HOT_RELOAD=true  # Optional: auto-reload on changes
```

Or mount individual plugin files:

```yaml
volumes:
  - ./my_provider.py:/config/plugins/my_provider.py:ro
```

## Limitations

- **No sandboxing:** Plugins run in the same Python process as Sublarr. A plugin can access the full Python runtime, filesystem, and network. Only install plugins you trust.
- **Single file:** Each plugin must be a single `.py` file. Multi-file packages are not supported. Use inline imports or bundle dependencies.
- **Name uniqueness:** Plugin names must not conflict with built-in providers (`animetosho`, `jimaku`, `opensubtitles`, `subdl`). Built-in providers always win on name collision.
- **No dependency management:** If your plugin requires third-party packages, they must be installed in the Sublarr environment separately.
- **Same thread model:** Plugins are called from the `ProviderManager`'s `ThreadPoolExecutor`. Your `search()` and `download()` methods may be called concurrently. Ensure thread safety if using shared state.

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/v1/plugins` | List all loaded plugins with manifest info |
| `POST` | `/api/v1/plugins/reload` | Re-discover and re-register all plugins |
| `GET` | `/api/v1/plugins/<name>/config` | Get config for a specific plugin |
| `PUT` | `/api/v1/plugins/<name>/config` | Update config for a plugin |
