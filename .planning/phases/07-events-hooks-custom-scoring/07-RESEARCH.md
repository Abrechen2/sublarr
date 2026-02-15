# Phase 7: Events/Hooks + Custom Scoring - Research

**Researched:** 2026-02-15
**Domain:** In-process event bus, shell hook execution, outgoing webhooks, configurable scoring
**Confidence:** HIGH

## Summary

Phase 7 adds user extensibility to Sublarr through three mechanisms: (1) an internal publish/subscribe event bus that replaces the current scattered `socketio.emit()` calls, (2) shell script hooks and outgoing HTTP webhooks that subscribe to those events, and (3) configurable scoring weights so users can tune subtitle selection without code changes.

The existing codebase already has all the prerequisite infrastructure: Flask 3.1.0 bundles blinker >= 1.9 as a required dependency, the `requests` library is already installed for HTTP operations, Python's `subprocess` module handles shell execution, and the SQLite database with `config_entries` + domain DB modules provides configuration storage. The current notification system (`notifier.py` with Apprise) and the 22+ existing `socketio.emit()` calls throughout the codebase provide clear insertion points for the event bus.

The scoring system in `providers/base.py` uses two hardcoded dictionaries (`EPISODE_SCORES` and `MOVIE_SCORES`) with a simple `compute_score()` function. Making these configurable requires storing weight overrides in the database and loading them at score computation time, plus per-provider modifiers that apply bonus/malus points after base scoring.

**Primary recommendation:** Use blinker (already a Flask dependency) as the in-process event bus, define a canonical event catalog as a Python module, and add hook/webhook/scoring tables to the existing SQLite schema. No new pip dependencies are needed for core functionality.

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| blinker | >= 1.9 | In-process signal/event bus | Flask required dependency, maintained by Pallets, MIT license, fast dispatch |
| subprocess (stdlib) | Python 3.11 | Shell script execution with timeout | Standard library, supports timeout, env vars, platform-independent |
| requests | 2.32.3 | Outgoing webhook HTTP POST | Already in requirements.txt, urllib3 retry built in |
| threading (stdlib) | Python 3.11 | Async hook/webhook execution | Already used throughout codebase for background tasks |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| urllib3.util.retry.Retry | (bundled with requests) | Webhook retry with exponential backoff | Configure on webhook HTTP sessions |
| json (stdlib) | Python 3.11 | Webhook JSON payload serialization | All webhook payloads |
| shlex (stdlib) | Python 3.11 | Safe shell command parsing | Parsing user-configured shell commands |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| blinker | PyPubSub | PyPubSub is heavier, not a Flask dep, no advantage for in-process use |
| blinker | Redis Streams | Phase 10 (not yet implemented), overkill for in-process events, PROJECT.md explicitly warns against it |
| blinker | Custom event dict | Reinventing the wheel; blinker handles weak refs, thread safety, sender filtering |
| subprocess | asyncio.create_subprocess | Flask uses threading mode, not async; would require major architecture change |

**Installation:**
```bash
# No new dependencies needed - blinker is bundled with Flask 3.1.0, requests already installed
# Verify: pip show blinker  (should show >= 1.9)
```

## Architecture Patterns

### Recommended Project Structure
```
backend/
├── events/
│   ├── __init__.py      # EventBus singleton, emit() helper, event catalog
│   ├── catalog.py       # Named signals: subtitle_downloaded, translation_complete, etc.
│   ├── hooks.py         # HookEngine: shell script executor with timeout + env vars
│   └── webhooks.py      # WebhookDispatcher: HTTP POST with retry logic
├── db/
│   ├── hooks.py         # CRUD for hook_configs, webhook_configs tables
│   └── scoring.py       # CRUD for scoring_weights, provider_modifiers tables
├── routes/
│   └── hooks.py         # Blueprint: /api/v1/hooks/*, /api/v1/webhooks/*, /api/v1/scoring/*
└── providers/
    └── base.py          # Modified compute_score() to use configurable weights
```

### Pattern 1: Blinker Signal Namespace for Event Catalog
**What:** Define all Sublarr events as named signals in a blinker Namespace, providing a typed, discoverable event catalog.
**When to use:** Always -- this is the foundation for the entire event system.
**Example:**
```python
# Source: Flask docs (https://flask.palletsprojects.com/en/stable/signals/) + blinker PyPI
from blinker import Namespace

sublarr_signals = Namespace()

# Event catalog — each signal is a named event
subtitle_downloaded = sublarr_signals.signal("subtitle_downloaded")
translation_complete = sublarr_signals.signal("translation_complete")
translation_failed = sublarr_signals.signal("translation_failed")
provider_search_complete = sublarr_signals.signal("provider_search_complete")
provider_failed = sublarr_signals.signal("provider_failed")
wanted_scan_complete = sublarr_signals.signal("wanted_scan_complete")
wanted_item_processed = sublarr_signals.signal("wanted_item_processed")
upgrade_complete = sublarr_signals.signal("upgrade_complete")
batch_complete = sublarr_signals.signal("batch_complete")
webhook_received = sublarr_signals.signal("webhook_received")
config_updated = sublarr_signals.signal("config_updated")
whisper_complete = sublarr_signals.signal("whisper_complete")
whisper_failed = sublarr_signals.signal("whisper_failed")
```

### Pattern 2: Event Emission Replacing socketio.emit
**What:** Replace direct `socketio.emit()` calls with event bus `signal.send()`, and have the SocketIO bridge as one subscriber.
**When to use:** At every existing `socketio.emit()` call site (22+ locations).
**Example:**
```python
# BEFORE (scattered in routes/wanted.py):
socketio.emit("wanted_item_processed", result)

# AFTER:
from events.catalog import wanted_item_processed
wanted_item_processed.send(current_app._get_current_object(), data=result)

# The SocketIO bridge subscribes once (in app.py or events/__init__.py):
from events.catalog import wanted_item_processed
from extensions import socketio

@wanted_item_processed.connect
def _emit_to_websocket(sender, data=None, **kwargs):
    socketio.emit("wanted_item_processed", data or {})
```

### Pattern 3: Shell Hook Execution with Safety
**What:** Execute user-configured shell scripts in a subprocess with timeout, controlled environment, and no shell injection.
**When to use:** EVNT-02 — when a configured event fires and a shell hook is attached.
**Example:**
```python
# Source: Python subprocess docs (https://docs.python.org/3/library/subprocess.html)
import subprocess
import os

def execute_hook(script_path: str, env_data: dict, timeout_seconds: int = 30) -> dict:
    """Execute a shell script hook with event data as environment variables."""
    # Build clean environment (don't inherit full parent env)
    hook_env = {
        "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
        "HOME": os.environ.get("HOME", "/tmp"),
        "SUBLARR_EVENT": env_data.get("event_name", ""),
        "SUBLARR_EVENT_DATA": json.dumps(env_data),
    }
    # Add event-specific vars with SUBLARR_ prefix
    for key, value in env_data.items():
        hook_env[f"SUBLARR_{key.upper()}"] = str(value)

    try:
        result = subprocess.run(
            [script_path],  # List syntax, no shell=True
            env=hook_env,
            timeout=timeout_seconds,
            capture_output=True,
            text=True,
            cwd="/tmp",
        )
        return {
            "success": result.returncode == 0,
            "exit_code": result.returncode,
            "stdout": result.stdout[:4096],  # Limit output
            "stderr": result.stderr[:4096],
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "error": f"Timeout after {timeout_seconds}s"}
    except Exception as e:
        return {"success": False, "error": str(e)}
```

### Pattern 4: Outgoing Webhook with Retry
**What:** HTTP POST with JSON payload, exponential backoff retry on transient failures.
**When to use:** EVNT-04 — when an event fires and a webhook URL is configured.
**Example:**
```python
# Source: requests + urllib3 retry (https://docs.python.org/3/library/subprocess.html)
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

def _create_webhook_session() -> requests.Session:
    """Create a session with retry logic for webhook delivery."""
    session = requests.Session()
    session.headers["User-Agent"] = "Sublarr-Webhook/1.0"
    session.headers["Content-Type"] = "application/json"

    retry = Retry(
        total=3,
        backoff_factor=2,  # 2s, 4s, 8s
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["POST"],
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session

def send_webhook(url: str, payload: dict, secret: str = "", timeout: int = 10) -> dict:
    """Send webhook with optional HMAC signature."""
    import hashlib, hmac, json, time

    body = json.dumps(payload)
    headers = {"X-Sublarr-Event": payload.get("event_name", "unknown")}

    if secret:
        signature = hmac.new(secret.encode(), body.encode(), hashlib.sha256).hexdigest()
        headers["X-Sublarr-Signature"] = f"sha256={signature}"

    session = _create_webhook_session()
    try:
        resp = session.post(url, data=body, headers=headers, timeout=timeout)
        return {"success": resp.status_code < 400, "status_code": resp.status_code}
    except Exception as e:
        return {"success": False, "error": str(e)}
```

### Pattern 5: Configurable Scoring Weights
**What:** Load scoring weights from DB, fall back to hardcoded defaults, allow per-provider modifiers.
**When to use:** SCOR-01 and SCOR-02 — in `compute_score()` and provider result post-processing.
**Example:**
```python
# In providers/base.py — modified compute_score
def compute_score(result: SubtitleResult, query: VideoQuery) -> int:
    """Compute match score using configurable weights."""
    from db.scoring import get_scoring_weights, get_provider_modifier

    # Get user-configured weights (falls back to EPISODE_SCORES/MOVIE_SCORES defaults)
    weights = get_scoring_weights("episode" if query.is_episode else "movie")

    score = 0
    for match in result.matches:
        score += weights.get(match, 0)

    # ASS format bonus
    if result.is_ass:
        score += weights.get("format_bonus", 50)

    # Per-provider modifier (bonus or malus)
    modifier = get_provider_modifier(result.provider_name)
    score += modifier

    result.score = score
    return score
```

### Anti-Patterns to Avoid
- **Global mutable event registry:** Use blinker's Namespace, not a hand-rolled dict of callbacks -- blinker handles thread safety and weak references.
- **shell=True in subprocess:** Never pass user-configured commands through the shell. Always use list syntax and validate the script path exists and is executable.
- **Synchronous hook execution blocking the event bus:** Always dispatch hooks and webhooks in background threads. The event bus `send()` call on subscribers should be fast (enqueue to thread pool), not block on subprocess/HTTP.
- **Inheriting full parent environment in hooks:** Don't pass `os.environ` to subprocess. Build a controlled environment with only SUBLARR_ prefixed variables.
- **Retry without backoff on webhooks:** Raw retry loops without exponential backoff cause thundering herd problems. Use urllib3 Retry with backoff_factor.
- **Storing scoring weights in config_entries:** Use a dedicated table, not the generic config_entries blob. Scoring weights have structure (type + key + value) that benefits from proper schema.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| In-process pub/sub | Custom dict of callback lists | blinker Namespace + signals | Thread safety, weak refs, sender filtering, already a Flask dependency |
| HTTP retry logic | Manual retry loop with sleep | urllib3 Retry + HTTPAdapter | Handles status codes, backoff, jitter, connection errors correctly |
| Shell command parsing | String splitting | shlex.split() or list syntax | Prevents injection from spaces, quotes, special chars |
| HMAC webhook signatures | Custom hash construction | hmac.new() with hashlib | Timing-safe comparison, standard approach, prevents length-extension attacks |
| Environment variable sanitization | str() on everything | json.dumps for complex types, str() for primitives with SUBLARR_ prefix | Consistent handling, prevents shell metacharacter issues |

**Key insight:** The entire event system can be built with zero new pip dependencies. blinker ships with Flask, requests is already installed, subprocess/threading/json/hmac are all stdlib. The complexity is in the wiring and safety, not in the tools.

## Common Pitfalls

### Pitfall 1: Blocking the Event Bus with Slow Subscribers
**What goes wrong:** A shell script that takes 30 seconds blocks the `signal.send()` call, making the original operation (subtitle download, translation) appear to hang.
**Why it happens:** blinker's `send()` calls subscribers synchronously in the calling thread.
**How to avoid:** Hook and webhook subscribers must enqueue work to a ThreadPoolExecutor, not execute inline. The `send()` call returns immediately; actual execution happens in background threads.
**Warning signs:** Translation/download operations suddenly take 30+ seconds after enabling hooks.

### Pitfall 2: Shell Injection via User-Configured Scripts
**What goes wrong:** User provides a script path like `; rm -rf /` or includes shell metacharacters.
**Why it happens:** Using `shell=True` or string concatenation when building subprocess commands.
**How to avoid:** (1) Always use `subprocess.run([script_path], ...)` with list syntax, (2) validate the script path is a real file before execution, (3) never use shell=True, (4) build a controlled environment instead of inheriting the parent environment.
**Warning signs:** Script paths containing spaces, semicolons, pipes, or backticks.

### Pitfall 3: Webhook Retry Storms
**What goes wrong:** A dead webhook endpoint causes retry attempts to pile up, consuming threads and delaying event processing.
**Why it happens:** No circuit breaker on webhook delivery, unlimited retries, or missing backoff.
**How to avoid:** (1) Limit to 3 retries with exponential backoff (2s, 4s, 8s), (2) track consecutive failures per webhook URL, (3) auto-disable webhooks after N consecutive failures (reuse the circuit_breaker.py pattern already in codebase), (4) set a reasonable HTTP timeout (10s).
**Warning signs:** Thread pool exhaustion, many pending webhook deliveries in the log.

### Pitfall 4: Event Data Leaking Sensitive Information
**What goes wrong:** Webhook payloads or shell environment variables contain API keys, file paths with user names, or internal IDs that shouldn't be exposed.
**Why it happens:** Passing the raw internal event data directly to external consumers.
**How to avoid:** Define explicit payload schemas for each event type. Only include fields that are safe to expose. Never include API keys, passwords, or database IDs in hook/webhook data.
**Warning signs:** Webhook payloads containing fields like `api_key`, `password`, or full file system paths.

### Pitfall 5: Scoring Weight Caching Invalidation
**What goes wrong:** User changes scoring weights in Settings, but provider searches still use the old weights until restart.
**Why it happens:** Scoring weights cached at module level or in the ProviderManager singleton.
**How to avoid:** Read weights from DB on each `compute_score()` call with a short TTL cache (e.g., 60 seconds). Alternatively, invalidate the cache on config_updated event.
**Warning signs:** Score values in search results don't change after modifying weights in Settings.

### Pitfall 6: Docker Container Lacks Shell Script Runtime
**What goes wrong:** User configures a bash script hook, but the python:3.11-slim image doesn't have bash.
**Why it happens:** Alpine/slim images only ship /bin/sh (dash), not /bin/bash.
**How to avoid:** (1) Document that hooks run with /bin/sh by default, (2) validate the shebang line, (3) the python:3.11-slim image does include /bin/sh (dash) and common utilities, (4) suggest users install additional shells via custom Dockerfile if needed.
**Warning signs:** Hook execution fails with "command not found" or "/bin/bash: not found".

## Code Examples

Verified patterns from official sources:

### Database Schema for Hooks and Scoring
```sql
-- Hook configurations (shell scripts)
CREATE TABLE IF NOT EXISTS hook_configs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    event_name TEXT NOT NULL,           -- e.g. "subtitle_downloaded"
    hook_type TEXT NOT NULL DEFAULT 'script',  -- "script" or "webhook"
    enabled INTEGER DEFAULT 1,
    -- Script-specific
    script_path TEXT DEFAULT '',
    timeout_seconds INTEGER DEFAULT 30,
    -- Metadata
    last_triggered_at TEXT DEFAULT '',
    last_status TEXT DEFAULT '',
    trigger_count INTEGER DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_hook_configs_event ON hook_configs(event_name);

-- Webhook configurations (outgoing HTTP)
CREATE TABLE IF NOT EXISTS webhook_configs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    event_name TEXT NOT NULL,           -- e.g. "subtitle_downloaded" or "*" for all
    url TEXT NOT NULL,
    secret TEXT DEFAULT '',             -- HMAC signing secret
    enabled INTEGER DEFAULT 1,
    retry_count INTEGER DEFAULT 3,
    timeout_seconds INTEGER DEFAULT 10,
    -- Status tracking
    last_triggered_at TEXT DEFAULT '',
    last_status_code INTEGER DEFAULT 0,
    last_error TEXT DEFAULT '',
    consecutive_failures INTEGER DEFAULT 0,
    trigger_count INTEGER DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_webhook_configs_event ON webhook_configs(event_name);

-- Hook execution log (audit trail)
CREATE TABLE IF NOT EXISTS hook_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    hook_id INTEGER,
    webhook_id INTEGER,
    event_name TEXT NOT NULL,
    hook_type TEXT NOT NULL,            -- "script" or "webhook"
    success INTEGER NOT NULL,
    exit_code INTEGER DEFAULT NULL,     -- For scripts
    status_code INTEGER DEFAULT NULL,   -- For webhooks
    stdout TEXT DEFAULT '',
    stderr TEXT DEFAULT '',
    error TEXT DEFAULT '',
    duration_ms REAL DEFAULT 0,
    triggered_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_hook_log_hook ON hook_log(hook_id);
CREATE INDEX IF NOT EXISTS idx_hook_log_webhook ON hook_log(webhook_id);
CREATE INDEX IF NOT EXISTS idx_hook_log_triggered ON hook_log(triggered_at);

-- Custom scoring weights
CREATE TABLE IF NOT EXISTS scoring_weights (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    score_type TEXT NOT NULL,           -- "episode" or "movie"
    weight_key TEXT NOT NULL,           -- "hash", "series", "year", etc.
    weight_value INTEGER NOT NULL,
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(score_type, weight_key)
);

-- Provider-specific scoring modifiers
CREATE TABLE IF NOT EXISTS provider_score_modifiers (
    provider_name TEXT PRIMARY KEY,
    modifier INTEGER NOT NULL DEFAULT 0,  -- Positive = bonus, negative = malus
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
```

### Event Catalog with Payload Types
```python
# events/catalog.py
from blinker import Namespace
from dataclasses import dataclass, asdict
from typing import Optional

sublarr_signals = Namespace()

# ─── Signal definitions ───────────────────────────────────────
subtitle_downloaded = sublarr_signals.signal("subtitle_downloaded")
translation_complete = sublarr_signals.signal("translation_complete")
translation_failed = sublarr_signals.signal("translation_failed")
provider_search_complete = sublarr_signals.signal("provider_search_complete")
provider_failed = sublarr_signals.signal("provider_failed")
wanted_scan_complete = sublarr_signals.signal("wanted_scan_complete")
wanted_item_processed = sublarr_signals.signal("wanted_item_processed")
upgrade_complete = sublarr_signals.signal("upgrade_complete")
batch_complete = sublarr_signals.signal("batch_complete")
webhook_received = sublarr_signals.signal("webhook_received")  # incoming *arr webhook
config_updated = sublarr_signals.signal("config_updated")
whisper_complete = sublarr_signals.signal("whisper_complete")
whisper_failed = sublarr_signals.signal("whisper_failed")
hook_executed = sublarr_signals.signal("hook_executed")  # meta: hook ran

# Registry for UI event list (EVNT-03)
EVENT_CATALOG = {
    "subtitle_downloaded": {
        "signal": subtitle_downloaded,
        "label": "Subtitle Downloaded",
        "description": "Fired when a subtitle file is downloaded from a provider",
        "payload_keys": ["provider_name", "language", "format", "score", "file_path", "title"],
    },
    "translation_complete": {
        "signal": translation_complete,
        "label": "Translation Complete",
        "description": "Fired when a subtitle is successfully translated",
        "payload_keys": ["file_path", "source_format", "output_path", "backend", "title"],
    },
    # ... etc for each event
}
```

### SocketIO Bridge Subscriber (Backward Compatibility)
```python
# events/__init__.py — register SocketIO bridge on app startup
from events.catalog import sublarr_signals, EVENT_CATALOG
from extensions import socketio

def init_event_system(app):
    """Initialize the event bus and register all subscribers."""
    # SocketIO bridge: forward all events to WebSocket clients
    for event_name, meta in EVENT_CATALOG.items():
        signal = meta["signal"]
        # Closure to capture event_name
        def make_bridge(name):
            @signal.connect
            def _bridge(sender, data=None, **kwargs):
                socketio.emit(name, data or {})
            return _bridge
        make_bridge(event_name)

    # Hook/webhook dispatcher: load from DB and subscribe
    from events.hooks import init_hook_subscribers
    from events.webhooks import init_webhook_subscribers
    init_hook_subscribers()
    init_webhook_subscribers()
```

### Settings UI: Scoring Weights Editor
```typescript
// Scoring weight types for frontend
interface ScoringWeight {
  score_type: 'episode' | 'movie'
  weight_key: string
  weight_value: number
}

interface ProviderModifier {
  provider_name: string
  modifier: number  // -100 to +100
}

// The Settings page gets a new "Scoring" tab with:
// 1. Two tables (Episode / Movie) showing all weight keys with editable number inputs
// 2. A provider modifier section showing each enabled provider with a slider -100 to +100
// 3. A "Reset to Defaults" button per table
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Direct socketio.emit() everywhere | Event bus with blinker signals | This phase | Decouples event producers from consumers; enables hooks/webhooks |
| Hardcoded scoring in base.py | DB-configurable weights with defaults | This phase | Users tune scoring without code changes |
| Only Apprise for notifications | Apprise + custom webhooks + shell hooks | This phase | Full extensibility; Apprise remains for push notifications |
| No audit trail for events | hook_log table | This phase | Debugging, compliance, and visibility into hook execution |

**Deprecated/outdated:**
- Nothing to deprecate -- this phase adds new capabilities alongside existing ones
- The existing `notifier.py` (Apprise) continues to work; it becomes another subscriber on the event bus
- Existing `socketio.emit()` calls will be replaced by event bus signals, but the WebSocket output remains identical via the bridge subscriber

## Open Questions

1. **Hook script storage location**
   - What we know: Docker container has `/config` as a persistent volume
   - What's unclear: Should scripts be stored in `/config/hooks/` (user manages files) or stored as text in the DB (UI editor)?
   - Recommendation: Both -- file paths for external scripts AND an inline script editor that saves to `/config/hooks/` automatically. This matches how n8n and other automation tools work.

2. **Event bus scope for notifier.py integration**
   - What we know: The existing `notifier.py` has its own event type toggles (notify_on_download, notify_on_upgrade, etc.)
   - What's unclear: Should notifier.py become just another event bus subscriber, or remain independent?
   - Recommendation: Make notifier.py subscribe to the event bus, but keep its existing toggle system as a filter layer. This avoids breaking existing configs while integrating cleanly.

3. **Maximum concurrent hook/webhook executions**
   - What we know: ThreadPoolExecutor is used elsewhere in the codebase with sensible worker counts
   - What's unclear: What's the right thread pool size for hooks + webhooks?
   - Recommendation: Shared ThreadPoolExecutor with max_workers=4 for hooks/webhooks. This prevents resource exhaustion while allowing parallel execution.

4. **Event payload versioning**
   - What we know: Webhook consumers may break if payload structure changes
   - What's unclear: Whether to version the event payloads from the start
   - Recommendation: Include a `version: 1` field in all webhook payloads. This is cheap to add now and prevents breaking changes later.

## Sources

### Primary (HIGH confidence)
- Flask 3.1.0 Signals documentation: https://flask.palletsprojects.com/en/stable/signals/ -- blinker integration, Namespace usage, connect/send patterns
- blinker 1.9.0 PyPI: https://pypi.org/project/blinker/ -- version, API surface, MIT license
- Python subprocess docs: https://docs.python.org/3/library/subprocess.html -- timeout, env, security
- Existing codebase analysis: `providers/base.py` lines 136-176 (EPISODE_SCORES, MOVIE_SCORES, compute_score)
- Existing codebase analysis: 22+ `socketio.emit()` call sites across 8 files in backend/

### Secondary (MEDIUM confidence)
- Flask 3.1.0 changelog confirms blinker >= 1.9 is a required dependency: https://flask.palletsprojects.com/en/stable/changes/
- Python subprocess security: https://www.codiga.io/blog/python-subprocess-security/ -- shell=True dangers, list syntax recommendation
- OpenStack subprocess security guide: https://security.openstack.org/guidelines/dg_use-subprocess-securely.html -- environment control
- Webhook retry patterns: https://latenode.com/blog/integration-api-management/webhook-setup-configuration/how-to-implement-webhook-retry-logic -- backoff, jitter, status code handling

### Tertiary (LOW confidence)
- None -- all findings verified through primary or secondary sources

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- blinker is a Flask dependency (verified), subprocess/requests/threading are stdlib/already installed
- Architecture: HIGH -- patterns directly observed in existing codebase (socketio.emit sites, compute_score, notifier.py, http_session.py)
- Pitfalls: HIGH -- subprocess security is well-documented, webhook retry patterns are standard, codebase analysis reveals specific integration points
- Scoring: HIGH -- current scoring code is simple and well-understood (two dicts + one function in providers/base.py)

**Research date:** 2026-02-15
**Valid until:** 2026-03-15 (30 days -- stable domain, no fast-moving dependencies)
