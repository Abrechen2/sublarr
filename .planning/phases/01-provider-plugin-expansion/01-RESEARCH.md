# Phase 1: Provider Plugin + Expansion - Research

**Researched:** 2026-02-15
**Domain:** Python plugin architecture, subtitle provider APIs, provider health monitoring
**Confidence:** HIGH

## Summary

Phase 1 transforms Sublarr's hardcoded provider system into a plugin-based architecture and adds 8 new built-in providers. The current codebase already has a solid foundation: a `SubtitleProvider` ABC, a `register_provider` decorator pattern, a `ProviderManager` with parallel search, circuit breakers, rate limiting, and provider stats tracking in SQLite. The work divides into three clear streams: (1) building the plugin infrastructure (auto-discovery from a directory, manifest validation, hot-reload, dynamic config), (2) implementing 8 new providers against diverse APIs (REST, XML, web scraping, file-hash lookup, and external service delegation), and (3) upgrading the health monitoring dashboard.

The plugin system should use Python's `importlib.util.spec_from_file_location` for file-based auto-discovery -- scanning a configurable plugins directory for `.py` files, importing them, and checking for `SubtitleProvider` subclasses. This is the right approach for Sublarr's Docker-based deployment model where users mount a plugins volume. The existing `register_provider` decorator and `_PROVIDER_CLASSES` registry need only minor extension to support external plugins alongside built-in providers. Hot-reload can be achieved via a dedicated API endpoint that clears and re-imports the plugins module, with an optional `watchdog` file watcher for development convenience.

The 8 new providers span a wide complexity range: Gestdown and Podnapisi have proper REST/XML APIs and are straightforward. Addic7ed, Kitsunekko, Titrari, and LegendasDivx require HTML scraping with BeautifulSoup. Napisy24 uses a custom hash-based POST API. Whisper-Subgen delegates to an external ASR service. All follow the existing provider contract (search + download methods) but require new dependencies (beautifulsoup4, lxml) and careful rate-limit/session management.

**Primary recommendation:** Build the plugin infrastructure first (PLUG-01 through PLUG-05), then implement providers in batches grouped by API type (REST first, then scraping, then specialized), and finish with the health dashboard upgrade.

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| importlib (stdlib) | Python 3.11 | Plugin auto-discovery and dynamic module loading | Standard library, no dependency; `spec_from_file_location` is the canonical approach for loading modules from arbitrary file paths |
| watchdog | 6.0+ | Optional file-system watcher for hot-reload | De facto standard for Python file monitoring; cross-platform; 42M+ downloads/month on PyPI |
| beautifulsoup4 | 4.12+ | HTML parsing for scraping-based providers | Industry standard for web scraping; used by Bazarr for the same providers |
| lxml | 5.1+ | Fast HTML/XML parser backend for BeautifulSoup and Podnapisi XML API | C-accelerated; 10-100x faster than html.parser for large docs |
| requests | 2.32.3 | HTTP client (already in requirements) | Already used by all existing providers via RetryingSession |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| rarfile | 4.2 | RAR archive extraction (already in requirements) | Jimaku, Titrari, LegendasDivx provide RAR archives |
| guessit | 3.8+ | Release name parsing for episode matching | Titrari and LegendasDivx need it for matching episodes within archives |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| importlib file scan | entry_points/pkg metadata | Entry points require pip-installed packages; file-drop is simpler for Docker users who just mount a volume |
| watchdog | polling with os.stat | Watchdog is event-driven and efficient; polling wastes CPU and has latency |
| beautifulsoup4 | scrapy/selectolax | BS4 is lighter weight and matches the single-page scraping pattern; scrapy is overkill for simple scraping |
| guessit | manual regex | guessit handles edge cases in release naming that regex misses; already battle-tested in Bazarr |

**Installation:**
```bash
pip install beautifulsoup4 lxml watchdog guessit
```

Add to `backend/requirements.txt`:
```
beautifulsoup4>=4.12.0
lxml>=5.1.0
watchdog>=6.0.0
guessit>=3.8.0
```

## Architecture Patterns

### Recommended Project Structure
```
backend/
  providers/
    __init__.py          # ProviderManager + _PROVIDER_CLASSES registry (existing)
    base.py              # SubtitleProvider ABC (existing, extended with config_fields)
    http_session.py      # RetryingSession (existing)
    # --- Built-in providers ---
    animetosho.py        # (existing)
    jimaku.py            # (existing)
    opensubtitles.py     # (existing)
    subdl.py             # (existing)
    addic7ed.py          # NEW: via Gestdown API proxy
    podnapisi.py         # NEW: XML API
    gestdown.py          # NEW: REST API (Addic7ed proxy)
    kitsunekko.py        # NEW: HTML scraping
    whisper_subgen.py    # NEW: external ASR service delegation
    napisy24.py          # NEW: hash-based POST API
    titrari.py           # NEW: HTML scraping
    legendasdivx.py      # NEW: HTML scraping + session auth
  plugins/
    __init__.py          # PluginManager: discovery, loading, validation, hot-reload
    manifest.py          # PluginManifest dataclass + validation logic
    loader.py            # importlib-based module loader with sandboxing
    watcher.py           # Optional watchdog-based file watcher for hot-reload
    template/            # Template files for plugin developers
      my_provider.py     # Annotated template with docstrings
      manifest.json      # Example manifest
  routes/
    providers.py         # Extended: plugin management endpoints
    plugins.py           # NEW: plugin-specific routes (list, reload, enable/disable)
  db/
    providers.py         # Extended: response_time_ms tracking
    plugins.py           # NEW: plugin registry persistence (enabled state, config)
```

### Pattern 1: Plugin Auto-Discovery via importlib
**What:** Scan a directory for Python files, import each as a module, find SubtitleProvider subclasses, and register them in `_PROVIDER_CLASSES`.
**When to use:** On application startup and on hot-reload trigger.
**Example:**
```python
# Source: Python official docs + packaging guide pattern
import importlib.util
import inspect
import sys
from pathlib import Path

def discover_plugins(plugins_dir: str) -> dict[str, type]:
    """Scan directory for SubtitleProvider subclasses."""
    discovered = {}
    plugins_path = Path(plugins_dir)

    if not plugins_path.is_dir():
        return discovered

    for py_file in plugins_path.glob("*.py"):
        if py_file.name.startswith(("_", ".")):
            continue

        module_name = f"plugins.{py_file.stem}"

        try:
            spec = importlib.util.spec_from_file_location(module_name, py_file)
            if spec is None or spec.loader is None:
                continue

            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)

            # Find SubtitleProvider subclasses
            for name, obj in inspect.getmembers(module, inspect.isclass):
                if (issubclass(obj, SubtitleProvider)
                    and obj is not SubtitleProvider
                    and hasattr(obj, 'name')):
                    discovered[obj.name] = obj

        except Exception as e:
            logger.error("Failed to load plugin %s: %s", py_file.name, e)

    return discovered
```

### Pattern 2: Plugin Manifest for Validation
**What:** Each plugin declares metadata (name, version, author, required config fields) either as class attributes or a companion JSON file.
**When to use:** During plugin loading, to validate compatibility and prevent name collisions.
**Example:**
```python
# Source: Based on Python packaging patterns
from dataclasses import dataclass, field

@dataclass
class PluginManifest:
    name: str                       # Unique provider name (lowercase, no spaces)
    version: str                    # SemVer string
    author: str = ""
    description: str = ""
    min_sublarr_version: str = ""   # Minimum compatible Sublarr version
    config_fields: list[dict] = field(default_factory=list)
    languages: list[str] = field(default_factory=list)
    requires_auth: bool = False

def validate_plugin(cls: type, existing_names: set[str]) -> tuple[bool, str]:
    """Validate a plugin class before registration."""
    if not hasattr(cls, 'name') or not cls.name:
        return False, "Plugin must define 'name' class attribute"
    if cls.name in existing_names:
        return False, f"Name collision: '{cls.name}' already registered"
    if not hasattr(cls, 'search') or not callable(cls.search):
        return False, "Plugin must implement search() method"
    if not hasattr(cls, 'download') or not callable(cls.download):
        return False, "Plugin must implement download() method"
    return True, "OK"
```

### Pattern 3: Dynamic Config Fields from Provider
**What:** Each provider declares its configuration requirements as structured field definitions, which the Settings UI renders automatically.
**When to use:** For plugin-specific settings that vary per provider.
**Example:**
```python
# Source: Existing _get_provider_config_fields pattern, generalized
class SubtitleProvider(ABC):
    name: str = "unknown"
    languages: set[str] = set()

    # NEW: Declarative config field definitions
    config_fields: list[dict] = []
    # Example: [
    #   {"key": "api_key", "label": "API Key", "type": "password", "required": True},
    #   {"key": "username", "label": "Username", "type": "text", "required": False},
    # ]
```

### Pattern 4: Hot-Reload via API + Optional Watcher
**What:** An API endpoint that triggers plugin re-discovery without app restart; optionally backed by watchdog for automatic reload on file change.
**When to use:** During development or when users add/update plugins.
**Example:**
```python
# API endpoint for manual reload
@bp.route("/api/v1/plugins/reload", methods=["POST"])
def reload_plugins():
    from plugins import get_plugin_manager
    manager = get_plugin_manager()
    loaded, errors = manager.reload()
    return jsonify({"loaded": loaded, "errors": errors})

# Optional watchdog watcher (runs in background thread)
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

class PluginWatcher(FileSystemEventHandler):
    def on_modified(self, event):
        if event.src_path.endswith('.py'):
            logger.info("Plugin file changed: %s, triggering reload", event.src_path)
            # Debounce and reload
```

### Anti-Patterns to Avoid
- **Exec/eval for plugin loading:** Never use `exec()` or `eval()` on plugin code; always use `importlib` for proper module loading with standard Python import semantics.
- **Global mutable state in plugins:** Plugins should not modify `_PROVIDER_CLASSES` directly; the PluginManager should control registration to prevent name collisions and enable clean unloading.
- **Blocking file I/O in hot-reload:** Plugin loading must not block the main request-handling thread; use background threading or debounced scheduling.
- **Hardcoded config in ProviderManager:** The current `_get_provider_config` switch/case pattern must be replaced with provider-declared `config_fields` for plugin support.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Module loading from file paths | Custom `open()` + `exec()` loader | `importlib.util.spec_from_file_location` | Handles sys.modules, __spec__, proper import semantics; avoids security footguns |
| File system monitoring | Polling loop with os.stat | `watchdog` library | Event-driven, cross-platform (inotify/kqueue/ReadDirectoryChanges), handles race conditions |
| HTML parsing for scraping | Regex on HTML strings | `beautifulsoup4` + `lxml` | HTML is not regular; BS4 handles malformed HTML, encoding, nested structures correctly |
| Release name parsing | Custom regex for episode/season | `guessit` library | Handles thousands of edge cases in release naming conventions (SubGroup, codec, resolution) |
| XML parsing for Podnapisi | Manual string parsing | `lxml.etree` or stdlib `xml.etree.ElementTree` | Handles namespaces, encoding, entity escaping; immune to XML injection |
| Rate limiting with timestamps | Custom timestamp tracking (current pattern) | Keep existing pattern but move to per-provider class attribute | Current implementation works but rate limits are hardcoded in ProviderManager; should be declarative per provider |

**Key insight:** The existing provider system is well-designed but monolithic -- config, rate limits, timeouts, and retries are all centralized in ProviderManager with switch/case statements. The plugin system must invert this so providers declare their own requirements and the manager reads from them.

## Common Pitfalls

### Pitfall 1: Plugin Name Collisions
**What goes wrong:** Two plugins (or a plugin and a built-in provider) declare the same `name`, silently overwriting each other in `_PROVIDER_CLASSES`.
**Why it happens:** The current `register_provider` decorator blindly sets `_PROVIDER_CLASSES[cls.name] = cls` with no collision check.
**How to avoid:** Validate uniqueness before registration. Built-in providers always win; plugins get an error message. Namespace plugin names with a prefix (e.g., `plugin_myname`).
**Warning signs:** Provider suddenly stops working after adding a plugin; API returns wrong provider type for a name.

### Pitfall 2: Plugin Import Side Effects
**What goes wrong:** A plugin's module-level code crashes (missing dependency, syntax error, network call), bringing down the entire app.
**Why it happens:** `exec_module()` runs all module-level code at import time.
**How to avoid:** Wrap each plugin import in try/except. Log errors but continue loading other plugins. Never let a bad plugin prevent startup.
**Warning signs:** App fails to start after adding a plugin file; "ModuleNotFoundError" in startup logs.

### Pitfall 3: Hot-Reload Module Cache Pollution
**What goes wrong:** After reloading a plugin, stale references from `sys.modules` or `_PROVIDER_CLASSES` cause confusing behavior (old code running with new config).
**Why it happens:** Python caches modules in `sys.modules`; simply re-importing does not clear the old module.
**How to avoid:** On reload: (1) remove old module from `sys.modules`, (2) unregister old provider from `_PROVIDER_CLASSES`, (3) terminate old provider instance, (4) re-import. Use a dedicated reload function that handles all cleanup.
**Warning signs:** Changes to plugin code have no effect until full app restart; provider instances hold stale config.

### Pitfall 4: Scraping Providers Breaking on Site Changes
**What goes wrong:** Addic7ed, Kitsunekko, Titrari, or LegendasDivx change their HTML structure, breaking CSS selectors.
**Why it happens:** Web scraping is inherently fragile; these sites have no API stability guarantees.
**How to avoid:** Use robust selectors (semantic IDs > positional CSS); add health checks that verify expected HTML structure; log warnings on parse failures instead of crashing. Consider Gestdown API as a proxy for Addic7ed instead of direct scraping.
**Warning signs:** Provider returns 0 results consistently; health check reports "parse error"; provider stats show 100% failure rate.

### Pitfall 5: LegendasDivx Session Management
**What goes wrong:** Session cookies expire mid-search, causing auth errors. Re-authentication loop burns through rate limits.
**Why it happens:** LegendasDivx uses PHP session cookies with short TTLs; the 145 searches/day limit is strict.
**How to avoid:** Cache session cookies persistently (in DB or file); detect 302 redirects as session expiration signals; implement exponential backoff on auth failures; track daily search count.
**Warning signs:** Provider alternates between working and "authentication failed"; daily download count depletes quickly.

### Pitfall 6: Whisper-Subgen Timeout Underestimation
**What goes wrong:** Transcription requests time out because default HTTP timeout is too short for audio processing.
**Why it happens:** Whisper transcription of a 24-min anime episode can take 30-300 seconds depending on model size and hardware.
**How to avoid:** Use configurable long timeouts (default: 600s) separate from provider search timeouts. Show progress in UI via WebSocket. The Subgen endpoint streams, so use streaming response handling.
**Warning signs:** All Whisper results are timeout errors; circuit breaker trips immediately.

### Pitfall 7: Provider Config Not Persisting to DB
**What goes wrong:** User configures a plugin's API key in Settings UI, but after restart the key is gone because plugin config has no Pydantic field mapping.
**Why it happens:** The current config cascade (Env -> Pydantic -> DB) does not know about plugin-specific keys. Plugin config needs a separate storage path.
**How to avoid:** Store plugin config in the `config_entries` table with a namespaced key pattern (e.g., `plugin.myprovider.api_key`). The PluginManager reads these on init and passes them to the provider constructor.
**Warning signs:** Plugin works until restart; "API key not configured" after every container recreation.

## Code Examples

Verified patterns from the existing codebase and provider research:

### Gestdown Provider (REST API Pattern)
```python
# Source: Gestdown API docs at gestdown.readme.io
# Base URL: https://api.gestdown.info

class GestdownProvider(SubtitleProvider):
    name = "gestdown"
    languages = {"en", "de", "fr", "es", "it", "pt", "nl", "pl", "sv", ...}
    config_fields = []  # No auth required

    def search(self, query: VideoQuery) -> list[SubtitleResult]:
        # Step 1: Look up show by TVDB ID (most accurate)
        if query.tvdb_id:
            resp = self.session.get(f"{API_BASE}/shows/external/tvdb/{query.tvdb_id}")
        else:
            # Fallback: search by name
            resp = self.session.get(f"{API_BASE}/shows/search/{query.series_title}")

        # Step 2: Get subtitles for specific episode
        for show in shows:
            show_id = show["id"]  # UUID
            for lang in query.languages:
                resp = self.session.get(
                    f"{API_BASE}/subtitles/get/{show_id}/{query.season}/{query.episode}/{lang}"
                )
                # Filter to completed=True only

    def download(self, result: SubtitleResult) -> bytes:
        # Direct download via downloadUri from search results
        resp = self.session.get(result.download_url, allow_redirects=True)
        return resp.content
```

### Podnapisi Provider (XML API Pattern)
```python
# Source: Podnapisi.net API (subliminal issue #916)
# Endpoint: https://podnapisi.net/subtitles/search/old?sXML=1

class PodnapisiProvider(SubtitleProvider):
    name = "podnapisi"
    languages = {"en", "de", "fr", "es", "it", "pt", "sl", "hr", "sr", "bs", ...}
    config_fields = []  # No auth required

    def search(self, query: VideoQuery) -> list[SubtitleResult]:
        params = {"sXML": 1, "sK": query.series_title or query.title}
        if query.languages:
            params["sL"] = query.languages[0]
        if query.season is not None:
            params["sTS"] = query.season
        if query.episode is not None:
            params["sTE"] = query.episode
        if query.year:
            params["sY"] = query.year

        resp = self.session.get(f"{API_BASE}/search/old", params=params)
        # Parse XML response with lxml
        from lxml import etree
        tree = etree.fromstring(resp.content)
        for subtitle in tree.findall(".//subtitle"):
            pid = subtitle.findtext("pid")
            # Build SubtitleResult...

    def download(self, result: SubtitleResult) -> bytes:
        # Download ZIP archive
        resp = self.session.get(f"{API_BASE}/{result.subtitle_id}/download")
        # Extract from ZIP
```

### Napisy24 Provider (Hash-Based POST API Pattern)
```python
# Source: Bazarr subliminal_patch/providers/napisy24.py (GPL-3.0)
# Endpoint: http://napisy24.pl/run/CheckSubAgent.php

class Napisy24Provider(SubtitleProvider):
    name = "napisy24"
    languages = {"pl"}  # Polish only
    config_fields = [
        {"key": "username", "label": "Username", "type": "text", "required": False},
        {"key": "password", "label": "Password", "type": "password", "required": False},
    ]

    def search(self, query: VideoQuery) -> list[SubtitleResult]:
        # Requires file hash (napisy24 algorithm) + file size
        if not query.file_path or not os.path.exists(query.file_path):
            return []

        file_hash = self._compute_napisy24_hash(query.file_path)
        file_size = os.path.getsize(query.file_path)

        data = {
            "postAction": "CheckSub",
            "ua": self.username or "subliminal",
            "ap": self.password or "lanimilbus",
            "fs": file_size,
            "fh": file_hash,
            "fn": os.path.basename(query.file_path),
        }
        resp = self.session.post(API_ENDPOINT, data=data)
        # Parse pipe-delimited response...
```

### Whisper-Subgen Provider (External Service Pattern)
```python
# Source: McCloudS/subgen API analysis
# Endpoint: configurable, e.g., http://subgen:9000/asr

class WhisperSubgenProvider(SubtitleProvider):
    name = "whisper_subgen"
    languages = {"en", "ja", "de", "fr", ...}  # All Whisper-supported
    config_fields = [
        {"key": "endpoint", "label": "Subgen URL", "type": "text", "required": True},
        {"key": "timeout", "label": "Timeout (seconds)", "type": "number", "required": False},
    ]

    def search(self, query: VideoQuery) -> list[SubtitleResult]:
        # Whisper generates subs, it doesn't search
        # Return a placeholder result that indicates generation is possible
        if not query.file_path or not os.path.exists(query.file_path):
            return []
        # Return a "generatable" result with low priority
        return [SubtitleResult(
            provider_name=self.name,
            subtitle_id=f"whisper:{query.file_path}",
            language=query.languages[0] if query.languages else "en",
            format=SubtitleFormat.SRT,
            score=10,  # Very low score -- last resort
        )]

    def download(self, result: SubtitleResult) -> bytes:
        # Extract audio -> WAV -> POST to Subgen /asr
        audio_data = self._extract_audio(result.provider_data["file_path"])
        resp = self.session.post(
            f"{self.endpoint}/asr",
            params={"task": "transcribe", "language": result.language, "output": "srt"},
            files={"audio_file": ("audio.wav", audio_data, "audio/wav")},
            timeout=self.timeout,
        )
        return resp.content
```

### Plugin Config Storage Pattern
```python
# Pattern for storing plugin-specific config in config_entries table
# Namespaced keys: "plugin.<provider_name>.<field_key>"

def get_plugin_config(provider_name: str) -> dict:
    """Read plugin config from DB config_entries."""
    prefix = f"plugin.{provider_name}."
    db = get_db()
    with _db_lock:
        rows = db.execute(
            "SELECT key, value FROM config_entries WHERE key LIKE ?",
            (f"{prefix}%",)
        ).fetchall()
    return {row[0].removeprefix(prefix): row[1] for row in rows}

def set_plugin_config(provider_name: str, key: str, value: str):
    """Write plugin config to DB config_entries."""
    full_key = f"plugin.{provider_name}.{key}"
    now = datetime.utcnow().isoformat()
    db = get_db()
    with _db_lock:
        db.execute(
            "INSERT OR REPLACE INTO config_entries (key, value, updated_at) VALUES (?, ?, ?)",
            (full_key, value, now)
        )
        db.commit()
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Addic7ed direct scraping | Gestdown API proxy | 2022 (Gestdown launch) | Gestdown provides a stable REST API over Addic7ed's scraping-hostile site; Bazarr switched to Gestdown |
| Kitsunekko as primary JP subs | Jimaku (kitsunekko successor) | 2023 | Jimaku has an API; Kitsunekko requires scraping. Both can be supported but Jimaku is preferred |
| subliminal XML-RPC for OpenSubtitles | OpenSubtitles REST API v2 | 2023-2024 | Old XML-RPC deprecated; REST v2 is current standard (already implemented in Sublarr) |
| Monolithic provider config in Settings | Dynamic config_fields per provider | Current best practice | Enables plugin-specific settings without code changes to the Settings UI |
| File hash via OpenSubtitles hash only | Multiple hash algorithms per provider | Ongoing | Napisy24 uses its own hash; OpenSubtitles uses their format; hash method should be provider-specific |
| Subgen direct API | Subgen as Bazarr-compatible provider | 2024-2025 | Subgen's /asr endpoint is a stable interface; Bazarr's whisperai pattern is the reference implementation |

**Deprecated/outdated:**
- **Addic7ed direct scraping:** Site actively blocks automated access; use Gestdown API proxy instead
- **OpenSubtitles XML-RPC:** Fully deprecated; use REST API v2 (already done)
- **Napiprojekt (napi.sh):** Different service from Napisy24; do not confuse them. Napisy24 has its own CheckSubAgent API

## Provider Implementation Details

### Provider Complexity Matrix

| Provider | API Type | Auth | Rate Limit | Format | Difficulty | Notes |
|----------|----------|------|------------|--------|------------|-------|
| Gestdown | REST | None | 429 handling | SRT | LOW | Addic7ed proxy; UUID-based show lookup via TVDB |
| Podnapisi | XML | None | 429 handling | ZIP(SRT) | LOW | European language focus; sXML=1 param for XML response |
| Addic7ed (via Gestdown) | REST | None | HTTP 423 retry | SRT | LOW | Same as Gestdown; TV shows only, no movies |
| Kitsunekko | HTML Scraping | None | Polite delay | ASS/SRT | MEDIUM | Japanese anime only; directory listing scraping |
| Whisper-Subgen | External Service | Endpoint URL | Concurrent limit | SRT | MEDIUM | Requires ffmpeg for audio extraction; long timeouts |
| Napisy24 | POST (hash) | Default creds | Unknown | ZIP(SRT) | MEDIUM | Polish only; requires file hash computation; custom binary protocol |
| Titrari | HTML Scraping | None (UA spoofing) | IP-based | RAR/ZIP | HIGH | Romanian; complex HTML table parsing; BeautifulSoup + lxml |
| LegendasDivx | HTML Scraping | Username/Password | 145 searches/day | RAR/ZIP | HIGH | Portuguese; PHP session management; cookie persistence; daily limit |

### Note on Addic7ed vs Gestdown
Gestdown IS the Addic7ed proxy API. Rather than implementing both as separate providers, implement Gestdown as the provider and document that it provides Addic7ed subtitles. This avoids duplicate work and avoids Addic7ed's anti-scraping measures. The roadmap lists both PROV-01 (Addic7ed) and PROV-03 (Gestdown) but they should be merged into a single Gestdown provider that covers both requirements.

## Provider Health Monitoring Enhancements (PROV-09, PROV-10)

The existing system already tracks:
- `provider_stats` table: total_searches, successful_downloads, failed_downloads, avg_score, consecutive_failures
- CircuitBreaker: per-provider CLOSED/OPEN/HALF_OPEN state
- provider_cache: per-provider cache stats
- subtitle_downloads: per-provider download history

What needs to be added for PROV-09 and PROV-10:
1. **Response time tracking:** Add `avg_response_time_ms` and `last_response_time_ms` to `provider_stats` table
2. **Auto-disable with cooldown:** Extend circuit breaker to support configurable thresholds per provider (some providers are flakier than others)
3. **Dashboard data endpoint:** Aggregate stats for the frontend health dashboard (already partially in `/providers/stats`)
4. **Per-provider health history:** Time-series data for graphing success rates over time (daily aggregates)

## Plugin Config System (PLUG-04) Design

The current architecture has a split between:
1. **Built-in provider config:** Hardcoded in `Settings` Pydantic model (e.g., `opensubtitles_api_key`)
2. **Dynamic config display:** `_get_provider_config_fields` in ProviderManager returns UI field definitions
3. **Config persistence:** `config_entries` DB table for runtime overrides

For plugins, the design must:
1. Move `config_fields` from ProviderManager switch/case into the provider class itself (declarative)
2. Store plugin config in `config_entries` with namespaced keys (`plugin.<name>.<field>`)
3. The Settings UI reads `config_fields` from the provider status API and renders forms dynamically
4. On save, config values go to `config_entries` table and the provider is re-initialized

This is already partially implemented -- the `config_fields` key exists in the provider status API response and the Settings UI renders it. The main work is: (a) moving field definitions into provider classes, (b) adding namespaced DB storage, (c) wiring up save/reload for plugin configs.

## Open Questions

1. **Addic7ed vs Gestdown Deduplication**
   - What we know: Gestdown IS the Addic7ed proxy. Bazarr uses Gestdown to access Addic7ed subs.
   - What's unclear: Should we implement one provider (Gestdown) or two separate ones? The roadmap lists both.
   - Recommendation: Implement one `gestdown` provider. Count it as satisfying both PROV-01 and PROV-03 since Gestdown provides Addic7ed subs. Document this decision clearly.

2. **Plugin Isolation Level**
   - What we know: Plugins run in the same Python process as the main app. Full sandboxing would require subprocess or container isolation, which is very complex.
   - What's unclear: How much validation/restriction is sufficient? Should plugins be allowed to import any Python module?
   - Recommendation: Validate the interface contract (has search/download methods, has name attribute). Log all imports. Do NOT attempt subprocess isolation -- it breaks the provider manager's ThreadPoolExecutor parallel search pattern. Accept that plugins can do anything Python can do (same as Bazarr's model).

3. **Whisper-Subgen Provider vs Phase 4 (Whisper Speech-to-Text)**
   - What we know: Phase 4 is a full Whisper integration with faster-whisper local processing. PROV-05 is specifically about using an EXTERNAL Subgen instance as a provider.
   - What's unclear: How much of the Whisper infrastructure to build now vs. defer to Phase 4.
   - Recommendation: PROV-05 should ONLY implement the external Subgen API client (POST to /asr endpoint). No local Whisper processing, no audio extraction pipeline. Keep it minimal: ffmpeg audio extraction + HTTP POST. Phase 4 will build the local Whisper backend.

4. **Kitsunekko Site Stability**
   - What we know: Kitsunekko.net has had availability issues. Jimaku is its spiritual successor with an API.
   - What's unclear: Is Kitsunekko.net still reliably available?
   - Recommendation: Implement the provider but with robust error handling and a note in docs that Jimaku (already built-in) is the preferred source for Japanese anime subs. Kitsunekko is supplementary.

## Sources

### Primary (HIGH confidence)
- Sublarr codebase: `backend/providers/base.py`, `__init__.py`, existing provider implementations
- Sublarr codebase: `backend/config.py`, `backend/db/__init__.py`, `backend/routes/providers.py`
- [Python Packaging Guide - Creating and Discovering Plugins](https://packaging.python.org/en/latest/guides/creating-and-discovering-plugins/)
- [Python importlib documentation](https://docs.python.org/3/library/importlib.html)
- [Gestdown API Documentation](https://gestdown.readme.io/reference/get_subtitles-get-showuniqueid-season-episode-language)
- [McCloudS/subgen source code](https://github.com/McCloudS/subgen/blob/main/subgen.py) - ASR endpoint specification

### Secondary (MEDIUM confidence)
- [Bazarr provider implementations](https://github.com/morpheus65535/bazarr) - napisy24.py, gestdown.py, titrari.py, legendasdivx.py, whisperai.py, podnapisi.py
- [Podnapisi.NET JSON API (subliminal issue #916)](https://github.com/Diaoul/subliminal/issues/916) - XML endpoint details
- [Kitsunekko Scraper tools](https://github.com/HunterKing/Kitsunekko_Scraper) - site structure patterns
- [watchdog PyPI](https://pypi.org/project/watchdog/) - file watcher library
- [Bazarr Whisper Provider Setup](https://wiki.bazarr.media/Additional-Configuration/Whisper-Provider/) - Subgen integration pattern

### Tertiary (LOW confidence)
- Titrari.ro HTML structure - Based on Bazarr commits, not verified against live site
- LegendasDivx daily search limits (145/day) - From Bazarr implementation, may have changed
- Napisy24 default credentials ("subliminal"/"lanimilbus") - From Bazarr source, needs verification against current API

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - importlib, watchdog, beautifulsoup4 are well-established patterns; existing codebase already demonstrates the provider pattern clearly
- Architecture: HIGH - Plugin system design follows established Python patterns; existing SubtitleProvider ABC is a solid foundation requiring minimal changes
- Provider APIs: MEDIUM - Gestdown, Podnapisi, Subgen endpoints are documented; scraping providers (Titrari, LegendasDivx, Kitsunekko) are fragile and details come from Bazarr's GPL-3.0 implementations
- Pitfalls: HIGH - Based on real issues encountered in Bazarr and standard Python plugin architecture challenges

**Research date:** 2026-02-15
**Valid until:** 2026-03-15 (30 days; provider APIs may change but plugin architecture patterns are stable)
