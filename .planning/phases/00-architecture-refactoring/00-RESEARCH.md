# Phase 0: Architecture Refactoring - Research

**Researched:** 2026-02-15
**Domain:** Flask Application Factory pattern, Blueprint routing, SQLite database modularization
**Confidence:** HIGH

## Summary

This phase converts a monolithic Flask application (server.py: 2618 lines, 67 routes on a single Blueprint; database.py: 2153 lines, 17 tables, 80+ functions) into the Flask Application Factory pattern with Blueprint-based routing and modular database access. The technology involved is mature, well-documented, and the codebase already uses Flask 3.1.0, Flask-SocketIO 5.4.1, and Blueprints (a single `api` Blueprint) -- so no new dependencies are needed. The work is purely structural.

The primary complexity lies not in the pattern itself (which is straightforward and well-documented) but in the **migration mechanics**: the module-level `settings = get_settings()` singleton, the module-level `socketio = SocketIO(app)` binding, the `global settings` pattern in route handlers, the module-level `_setup_logging()` call, the background thread usage of `socketio.emit()`, and the 14+ external modules that `from database import ...` specific functions. All of these must be rewired without breaking the threading model or the WebSocket event system.

**Primary recommendation:** Use the standard Flask `extensions.py` pattern with `socketio = SocketIO()` (no app binding) and `socketio.init_app(app)` inside `create_app()`. Keep the existing `_db_lock` + singleton SQLite connection pattern (do NOT switch to per-request `g.db`) because background threads (wanted_scanner, webhook pipeline, batch jobs) access the database outside request context. Route files access config via `from flask import current_app` or by calling `get_settings()` directly (the config module is already a standalone singleton).

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

#### Directory layout after refactor

New structure introduces `routes/` and `db/` packages inside `backend/`:

```
backend/
  app.py                    # create_app() factory, extension init
  extensions.py             # socketio, db — lazy init, no app binding
  routes/
    __init__.py             # register_blueprints() helper
    translate.py            # /translate, /batch, /retranslate, /status, /jobs
    providers.py            # /providers, /providers/test, /search, /stats, /cache
    library.py              # /library, /series, /episodes, /sonarr, /radarr
    wanted.py               # /wanted, /wanted/batch-search, /wanted/search-all
    config.py               # /config, /settings, /onboarding, /config/export|import
    webhooks.py             # /webhook/sonarr, /webhook/radarr
    system.py               # /health, /database, /logs, /stats, /notifications
    profiles.py             # /language-profiles, /glossary, /prompt-presets
    blacklist.py            # /blacklist, /history
  db/
    __init__.py             # get_db(), init_db(), schema DDL
    jobs.py                 # jobs, daily_stats tables
    config.py               # config_entries table
    providers.py            # provider_cache, provider_stats tables
    library.py              # subtitle_downloads, upgrade_history tables
    wanted.py               # wanted_items table
    blacklist.py            # blacklist_entries table
    profiles.py             # language_profiles, series/movie_language_profiles
    translation.py          # translation_config_history, glossary, prompt_presets
    cache.py                # ffprobe_cache, anidb_mappings
  providers/                # unchanged (already modular)
  # standalone modules stay flat: translator.py, ollama_client.py,
  # sonarr_client.py, radarr_client.py, jellyfin_client.py,
  # wanted_scanner.py, wanted_search.py, ass_utils.py, etc.
```

- `routes/` not `blueprints/` -- shorter, describes contents
- `db/` not `database/` -- shorter, Flask convention
- `server.py` is removed after migration -- `app.py` replaces it
- Existing standalone modules (translator.py, sonarr_client.py, etc.) stay flat -- already right-sized
- Safety infrastructure (error_handler.py, circuit_breaker.py, transaction_manager.py, etc.) stays flat

#### Route grouping into Blueprints (9 blueprints)

| Blueprint | URL prefix | Routes | Description |
|-----------|-----------|--------|-------------|
| `translate` | `/api/v1` | /translate, /translate/sync, /status/\<id>, /jobs, /jobs/\<id>/retry, /batch, /batch/status, /retranslate/* | Translation jobs and retranslation |
| `providers` | `/api/v1` | /providers, /providers/test/\<name>, /providers/search, /providers/stats, /providers/cache/clear | Provider management and search |
| `library` | `/api/v1` | /library, /library/series/\<id>, /sonarr/*, /radarr/*, /episodes/* | Library browsing and *arr instances |
| `wanted` | `/api/v1` | /wanted, /wanted/summary, /wanted/refresh, /wanted/\<id>/*, /wanted/batch-search/*, /wanted/search-all | Missing subtitle queue |
| `config` | `/api/v1` | /config (GET/PUT), /settings/*, /onboarding/*, /config/export, /config/import | Configuration and onboarding |
| `webhooks` | `/api/v1` | /webhook/sonarr, /webhook/radarr | Incoming webhook handlers |
| `system` | `/api/v1` | /health, /health/detailed, /stats, /database/*, /logs, /notifications/* | System health, DB admin, logs |
| `profiles` | `/api/v1` | /language-profiles/*, /glossary/*, /prompt-presets/* | Language profiles, glossary, presets |
| `blacklist` | `/api/v1` | /blacklist/*, /history/* | Blacklist and download history |

All blueprints share the `/api/v1` prefix. The `app.py` level handles `/metrics` and the SPA fallback route.

#### Database domain boundaries (9 modules)

| Module | Tables | Rationale |
|--------|--------|-----------|
| `db/jobs.py` | jobs, daily_stats | Job lifecycle and aggregate stats |
| `db/config.py` | config_entries | Runtime config overrides |
| `db/providers.py` | provider_cache, provider_stats | Provider caching and metrics |
| `db/library.py` | subtitle_downloads, upgrade_history | Download tracking and upgrades |
| `db/wanted.py` | wanted_items | Missing subtitle queue |
| `db/blacklist.py` | blacklist_entries | Blocked results |
| `db/profiles.py` | language_profiles, series_language_profiles, movie_language_profiles | All profile assignment |
| `db/translation.py` | translation_config_history, glossary_entries, prompt_presets | Translation configuration data |
| `db/cache.py` | ffprobe_cache, anidb_mappings | Ephemeral caches and ID mappings |

Schema DDL stays in `db/__init__.py` -- all tables share one SQLite file, schema should be defined in one place.

#### Backward compatibility scope

- **Tests:** Import path changes are acceptable (mechanical, not logic). All test *assertions* must still pass. Test files may be updated with new import paths.
- **Docker:** Entry point changes from `python server.py` to new app.py entry. Acceptable -- Docker users rebuild images.
- **npm scripts:** `npm run dev:backend` updated to new entry point. Dev workflow preserved.
- **No compatibility shim:** No `server.py` wrapper for old imports. Clean break.
- **API contract unchanged:** All HTTP endpoints remain at same paths with same request/response formats. Zero impact on frontend or external consumers.

### Claude's Discretion

- How to implement `create_app()` internals (extension init order, config loading)
- How to handle the StructuredJSONFormatter and WebSocket log handler migration
- How to wire Socket.IO events into the factory pattern
- Exact `extensions.py` implementation (init_app pattern vs. lazy init)
- How to handle the module-level `settings = get_settings()` pattern across route files
- Migration order (which files to split first)
- Whether to use `flask.current_app` vs. other patterns for accessing app context

### Deferred Ideas (OUT OF SCOPE)

None -- discussion stayed within phase scope.
</user_constraints>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Flask | 3.1.0 | Web framework | Already installed; Application Factory is a first-class Flask pattern |
| Flask-SocketIO | 5.4.1 | WebSocket support | Already installed; supports `init_app()` factory pattern natively |
| gunicorn | 23.0.0 | WSGI server | Already installed; supports `'app:create_app()'` factory syntax |
| simple-websocket | 1.1.0 | WebSocket transport for gthread | Already installed; required for threading async_mode |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pydantic-settings | 2.7.1 | Configuration management | Already used; `get_settings()` singleton stays unchanged |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Module-level singleton DB | Flask `g.db` per-request | Would break background threads (wanted_scanner, webhook pipeline, batch jobs) that access DB outside request context. Keep singleton. |
| `current_app.config` for settings | `get_settings()` standalone | Pydantic Settings already works as a standalone singleton; no benefit to moving it into Flask config |

**Installation:**
```bash
# No new packages needed. All dependencies already in requirements.txt.
```

## Architecture Patterns

### Recommended Project Structure
```
backend/
├── app.py                    # create_app() factory function
├── extensions.py             # SocketIO instance (no app binding)
├── routes/
│   ├── __init__.py           # register_blueprints() helper
│   ├── translate.py          # Translation blueprint
│   ├── providers.py          # Provider management blueprint
│   ├── library.py            # Library browsing blueprint
│   ├── wanted.py             # Wanted queue blueprint
│   ├── config.py             # Configuration blueprint
│   ├── webhooks.py           # Webhook handlers blueprint
│   ├── system.py             # System/health blueprint
│   ├── profiles.py           # Language profiles blueprint
│   └── blacklist.py          # Blacklist/history blueprint
├── db/
│   ├── __init__.py           # get_db(), init_db(), close_db(), SCHEMA, migrations
│   ├── jobs.py               # create_job, update_job, get_job, get_jobs, etc.
│   ├── config.py             # save_config_entry, get_config_entry, get_all_config_entries
│   ├── providers.py          # cache_provider_results, get_cached_results, provider stats
│   ├── library.py            # record_subtitle_download, get_download_history, upgrades
│   ├── wanted.py             # upsert_wanted_item, get_wanted_items, etc.
│   ├── blacklist.py          # add_blacklist_entry, remove, clear, is_blacklisted
│   ├── profiles.py           # language profile CRUD, series/movie assignments
│   ├── translation.py        # translation_config_history, glossary, prompt_presets
│   └── cache.py              # ffprobe_cache, anidb_mappings
├── config.py                 # Settings class, get_settings(), reload_settings() (unchanged)
├── translator.py             # Translation pipeline (unchanged, stays flat)
├── providers/                # Provider system (unchanged)
├── error_handler.py          # Error hierarchy + Flask handlers (unchanged)
├── auth.py                   # API key auth (unchanged, receives app in init_auth)
└── ...                       # Other standalone modules unchanged
```

### Pattern 1: Extensions Module (Lazy Init)
**What:** Instantiate Flask extensions without app binding, then call `init_app()` in factory.
**When to use:** Always, for any Flask extension that needs to be importable before `create_app()` runs.
**Example:**
```python
# Source: Flask-SocketIO official docs, Flask Application Factories docs
# extensions.py
from flask_socketio import SocketIO

socketio = SocketIO()
```

```python
# app.py
from extensions import socketio

def create_app():
    app = Flask(__name__, static_folder="static", static_url_path="")

    # Initialize extensions
    socketio.init_app(app, cors_allowed_origins="*", async_mode="threading")

    # Register blueprints
    from routes import register_blueprints
    register_blueprints(app)

    # Register error handlers
    from error_handler import register_error_handlers
    register_error_handlers(app)

    # Initialize auth
    from auth import init_auth
    init_auth(app)

    # App-level routes (metrics, SPA fallback)
    _register_app_routes(app)

    # Initialize database
    from db import init_db
    init_db()

    # Apply DB config overrides
    from db.config import get_all_config_entries
    from config import reload_settings
    overrides = get_all_config_entries()
    if overrides:
        reload_settings(overrides)

    # Start schedulers
    _start_schedulers(app)

    return app
```

### Pattern 2: Blueprint Registration Helper
**What:** Centralized function that imports and registers all blueprints.
**When to use:** In `routes/__init__.py` to keep `create_app()` clean.
**Example:**
```python
# Source: Flask Blueprints documentation
# routes/__init__.py

def register_blueprints(app):
    """Import and register all API blueprints."""
    from routes.translate import bp as translate_bp
    from routes.providers import bp as providers_bp
    from routes.library import bp as library_bp
    from routes.wanted import bp as wanted_bp
    from routes.config import bp as config_bp
    from routes.webhooks import bp as webhooks_bp
    from routes.system import bp as system_bp
    from routes.profiles import bp as profiles_bp
    from routes.blacklist import bp as blacklist_bp

    for blueprint in [
        translate_bp, providers_bp, library_bp, wanted_bp,
        config_bp, webhooks_bp, system_bp, profiles_bp, blacklist_bp,
    ]:
        app.register_blueprint(blueprint)
```

### Pattern 3: Individual Blueprint File
**What:** Each route file creates its own Blueprint and defines routes.
**When to use:** Every route module.
**Example:**
```python
# Source: Flask Blueprints documentation
# routes/system.py
import logging
from flask import Blueprint, jsonify

from config import get_settings
from db.jobs import get_stats_summary

logger = logging.getLogger(__name__)

bp = Blueprint("system", __name__, url_prefix="/api/v1")

@bp.route("/health", methods=["GET"])
def health():
    """Health check endpoint."""
    from ollama_client import check_ollama_health
    healthy, message = check_ollama_health()
    # ... rest of handler
    return jsonify({"status": "ok" if healthy else "degraded", "services": service_status})
```

### Pattern 4: SocketIO Access from Route Handlers and Background Threads
**What:** Import socketio from extensions.py to emit events; works without request context.
**When to use:** Any route handler or background thread that needs to emit WebSocket events.
**Example:**
```python
# Source: Flask-SocketIO docs - "Emitting from an External Process" section
# routes/translate.py
from extensions import socketio

@bp.route("/translate", methods=["POST"])
def translate_async():
    # ... create job ...
    def _run_job(job_data):
        # This runs in a background thread - no request context
        # But socketio.emit() works because SocketIO stores a reference to the app
        socketio.emit("job_update", {"id": job_data["id"], "status": "running"})

    thread = threading.Thread(target=_run_job, args=(job,), daemon=True)
    thread.start()
    return jsonify({"id": job["id"]}), 202
```

### Pattern 5: Database Module Split with Shared Connection
**What:** Split database functions into domain modules, each importing `get_db()` and `_db_lock` from `db/__init__.py`.
**When to use:** Every `db/*.py` module.
**Example:**
```python
# db/__init__.py
import sqlite3
import threading
import logging
from config import get_settings

logger = logging.getLogger(__name__)

_db_lock = threading.Lock()
_connection = None

SCHEMA = """..."""  # All CREATE TABLE statements

def get_db():
    """Get or create the database connection (thread-safe singleton)."""
    global _connection
    if _connection is not None:
        return _connection
    with _db_lock:
        if _connection is not None:
            return _connection
        settings = get_settings()
        _connection = sqlite3.connect(
            settings.db_path, check_same_thread=False, isolation_level="DEFERRED",
        )
        _connection.row_factory = sqlite3.Row
        _connection.execute("PRAGMA journal_mode=WAL")
        _connection.execute("PRAGMA busy_timeout=5000")
        _connection.executescript(SCHEMA)
        _run_migrations(_connection)
        _connection.commit()
        return _connection

def init_db():
    """Initialize database (called from create_app)."""
    get_db()

def close_db():
    """Close database connection."""
    global _connection
    if _connection:
        _connection.close()
        _connection = None
```

```python
# db/jobs.py
import json
import uuid
import logging
from datetime import datetime, date

from db import get_db, _db_lock

logger = logging.getLogger(__name__)

def create_job(file_path, force=False, arr_context=None):
    """Create a new translation job."""
    job_id = str(uuid.uuid4())[:8]
    now = datetime.utcnow().isoformat()
    context_json = json.dumps(arr_context) if arr_context else ""
    db = get_db()
    with _db_lock:
        db.execute(
            """INSERT INTO jobs (id, file_path, status, force, bazarr_context_json, created_at)
               VALUES (?, ?, 'queued', ?, ?, ?)""",
            (job_id, file_path, int(force), context_json, now),
        )
        db.commit()
    return {"id": job_id, "file_path": file_path, "status": "queued", ...}
```

### Pattern 6: Gunicorn Entry Point with Factory
**What:** Gunicorn directly invokes the factory function.
**When to use:** Docker CMD and production deployment.
**Example:**
```bash
# Source: Flask gunicorn deployment docs
# Old (current Dockerfile CMD):
gunicorn --bind 0.0.0.0:5765 --worker-class gthread --workers 2 --threads 4 --timeout 300 server:app

# New (after refactor):
gunicorn --bind 0.0.0.0:5765 --worker-class gthread --workers 1 --threads 4 --timeout 300 "app:create_app()"
```
**CRITICAL NOTE:** Flask-SocketIO requires `--workers 1` (single worker). The current Dockerfile uses `--workers 2` which is technically incorrect for WebSocket support. The refactor should fix this to `--workers 1` with `--threads` for concurrency.

### Pattern 7: Logging Setup Inside Factory
**What:** Move logging configuration into `create_app()` instead of module-level execution.
**When to use:** The StructuredJSONFormatter and SocketIOLogHandler setup.
**Example:**
```python
# app.py
def create_app():
    app = Flask(__name__, static_folder="static", static_url_path="")

    # Configure logging early
    _setup_logging(app)

    # ... rest of setup ...
    return app

def _setup_logging(app):
    """Configure file and WebSocket log handlers."""
    from config import get_settings
    settings = get_settings()

    log_level = getattr(logging, settings.log_level.upper(), logging.INFO)
    logging.basicConfig(level=log_level, format=LOG_FORMAT)

    root = logging.getLogger()

    # File handler with rotation
    try:
        from logging.handlers import RotatingFileHandler
        fh = RotatingFileHandler(settings.log_file, maxBytes=5*1024*1024, backupCount=3)
        fh.setLevel(log_level)
        use_json = getattr(settings, "log_format", "text").lower() == "json"
        fh.setFormatter(StructuredJSONFormatter() if use_json else logging.Formatter(LOG_FORMAT))
        root.addHandler(fh)
    except Exception as e:
        logging.getLogger(__name__).warning("Could not set up log file: %s", e)

    # WebSocket handler (imports socketio from extensions)
    from extensions import socketio
    ws_handler = SocketIOLogHandler(socketio)
    ws_handler.setLevel(log_level)
    ws_handler.setFormatter(logging.Formatter(LOG_FORMAT))
    root.addHandler(ws_handler)
```

### Anti-Patterns to Avoid
- **Module-level `app = Flask(...)` and `socketio = SocketIO(app)`:** Creates the app at import time. Prevents testing with different configs and causes import side effects. Use the factory pattern instead.
- **`global settings` in route handlers:** Use `get_settings()` function call instead. The `global` keyword was only needed because server.py rebinds the module-level `settings` variable in `update_config()` and `import_config()`. After refactoring, each route file calls `get_settings()` which always returns the current singleton.
- **Importing `app` or `socketio` from `server`:** After refactoring, `socketio` comes from `extensions.py`. No module should import from `app.py` at module level (except `create_app` for the entry point).
- **Circular imports via top-level imports in route files:** Use deferred (function-level) imports for modules that might import from the same route file. The codebase already uses this pattern extensively (e.g., `from database import get_default_profile` inside function bodies).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Extension lazy init | Custom singleton pattern for SocketIO | Flask's `init_app()` pattern | Flask extensions are designed for this; `socketio = SocketIO()` + `socketio.init_app(app)` is idiomatic and handles all edge cases |
| Blueprint registration | Manual `app.register_blueprint()` calls scattered across create_app | Centralized `register_blueprints()` helper in `routes/__init__.py` | Single point of change when adding/removing blueprints |
| Import path compatibility | Re-export shim in old `database.py` location | Update import paths directly in all files | Clean break is simpler than maintaining backward-compat shims; user decision explicitly rejects shims |
| WebSocket emit from threads | Custom event queue or thread-local SocketIO | Direct `socketio.emit()` from extensions module | Flask-SocketIO handles this natively; when called outside request context, `broadcast=True` is assumed |

**Key insight:** Flask's Application Factory pattern is specifically designed for this exact transformation. Every component being changed (Blueprints, SocketIO, error handlers, auth) already has `init_app()` or `register_*()` methods that slot into the factory. No custom infrastructure is needed.

## Common Pitfalls

### Pitfall 1: Circular Imports During Blueprint Registration
**What goes wrong:** Route files import from `db/`, which imports from `config`, which might reference something that hasn't been initialized yet. Import errors at startup.
**Why it happens:** Moving from module-level execution (where import order was implicit) to a factory (where imports happen during `create_app()`).
**How to avoid:** Use deferred imports inside `register_blueprints()` (import blueprints inside the function body, not at module top). The codebase already follows this pattern extensively in server.py (20+ deferred imports inside route handlers).
**Warning signs:** `ImportError` or `AttributeError` at startup; circular import traceback.

### Pitfall 2: Background Threads Losing Database Access
**What goes wrong:** Background threads (wanted_scanner scheduler, webhook pipeline with `time.sleep()`, batch translation threads) that call `db/` functions fail because they run outside Flask request/app context.
**Why it happens:** If anyone switches to Flask's `g.db` per-request pattern, background threads won't have a request context.
**How to avoid:** Keep the existing singleton connection pattern (`get_db()` returns the global `_connection`). Do NOT use Flask `g` for database access. The singleton + `_db_lock` pattern is already thread-safe and works from any thread.
**Warning signs:** `RuntimeError: Working outside of application context` in background threads.

### Pitfall 3: SocketIO LogHandler Circular Reference
**What goes wrong:** The `SocketIOLogHandler` references the `socketio` instance. If logging is set up before `socketio.init_app(app)`, emit calls silently fail or raise errors.
**Why it happens:** In the current code, `socketio` is bound to `app` at module level before the log handler is created. In the factory pattern, the order must be explicit.
**How to avoid:** Initialize `socketio.init_app(app)` BEFORE setting up the `SocketIOLogHandler`. Or make the handler gracefully skip emit when socketio is not yet initialized (current code already has `try/except` in `emit()`).
**Warning signs:** Log entries not appearing in the frontend WebSocket; silent exception in log handler.

### Pitfall 4: Module-Level `settings = get_settings()` Stale Reference
**What goes wrong:** Route handlers that captured `settings` at import time continue using stale settings after `reload_settings()` is called via the config PUT endpoint.
**Why it happens:** Python module-level variables are bound at import time. `settings = get_settings()` captures the object, but `reload_settings()` creates a *new* Settings object and rebinds the module-level singleton. If a route file has `settings = get_settings()` at the top, it holds a reference to the old object.
**How to avoid:** In route handlers, always call `get_settings()` at execution time (inside the function), never cache it at module level. The current `global settings` pattern in server.py was a workaround for this exact issue.
**Warning signs:** Config changes via UI don't take effect until restart; tests pass individually but fail when run together.

### Pitfall 5: Forgetting to Update External Module Imports
**What goes wrong:** Modules like `translator.py`, `wanted_scanner.py`, `wanted_search.py`, `providers/__init__.py`, `ollama_client.py`, `anidb_mapper.py`, and `ass_utils.py` all do `from database import ...` at the top level. After renaming `database.py` to `db/`, these all break.
**Why it happens:** The import path changes from `from database import get_db` to `from db import get_db`.
**How to avoid:** Systematically find and update ALL `from database import` statements across the entire codebase. There are 30+ such imports across 15+ files (see grep results). Create a checklist.
**Warning signs:** `ModuleNotFoundError: No module named 'database'` at startup.

### Pitfall 6: Test Fixtures Importing Module-Level App
**What goes wrong:** `tests/conftest.py` does `from server import app` at module level. After removing `server.py`, all tests break.
**Why it happens:** Test fixtures create the app by importing it. With the factory pattern, they should call `create_app()` instead.
**How to avoid:** Update conftest.py to use `from app import create_app` and create the app instance in the fixture:
```python
@pytest.fixture
def client(temp_db):
    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client
```
**Warning signs:** `ModuleNotFoundError: No module named 'server'` when running tests.

### Pitfall 7: Gunicorn Workers > 1 with SocketIO
**What goes wrong:** The current Dockerfile uses `--workers 2` with gunicorn gthread. With WebSocket connections, this causes connection failures because clients may connect to one worker but subsequent messages go to another.
**Why it happens:** Flask-SocketIO requires single-worker mode unless using a message queue (Redis). The current setup may work by accident because WebSocket upgrade may not always succeed.
**How to avoid:** Change to `--workers 1 --threads 4` in the Dockerfile CMD. This is the documented configuration for Flask-SocketIO with gthread worker.
**Warning signs:** WebSocket connections intermittently failing; 400 bad request errors on socket.io transport upgrade.

### Pitfall 8: Shared Mutable State in Route Modules
**What goes wrong:** `batch_state`, `wanted_batch_state`, `_memory_stats` and their associated locks are module-level dicts in server.py. When split into route files, they become module-level state in individual route modules. If two route modules need to reference the same state (e.g., batch status from a different blueprint), imports get tangled.
**Why it happens:** In-memory state was convenient in a single file but doesn't split cleanly.
**How to avoid:** Keep shared mutable state (batch_state, wanted_batch_state, _memory_stats) in a dedicated module, e.g., keep them in the route module that owns them (translate.py for batch_state, wanted.py for wanted_batch_state). If another blueprint needs to read them, import from the owning module. Alternatively, put shared state in `extensions.py` or a new `state.py`.
**Warning signs:** Circular imports between route modules; stale state reads.

## Code Examples

Verified patterns from official sources:

### create_app() Factory Function
```python
# Source: https://flask.palletsprojects.com/en/stable/patterns/appfactories/
# Source: https://flask-socketio.readthedocs.io/en/latest/getting_started.html
# app.py

import os
import logging

from flask import Flask, send_from_directory, jsonify
from extensions import socketio

LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
logger = logging.getLogger(__name__)


def create_app(testing=False):
    """Application factory for Sublarr."""
    app = Flask(__name__, static_folder="static", static_url_path="")

    # 1. Load config
    from config import get_settings, reload_settings
    settings = get_settings()

    # 2. Configure logging (before anything else uses it)
    _setup_logging(settings)

    # 3. Initialize extensions
    socketio.init_app(app, cors_allowed_origins="*", async_mode="threading")

    # 4. Register error handlers (before blueprints, so they catch all errors)
    from error_handler import register_error_handlers
    register_error_handlers(app)

    # 5. Initialize auth
    from auth import init_auth
    init_auth(app)

    # 6. Initialize database
    from db import init_db
    init_db()

    # 7. Apply DB config overrides
    from db.config import get_all_config_entries
    overrides = get_all_config_entries()
    if overrides:
        logger.info("Applying %d config overrides from database", len(overrides))
        reload_settings(overrides)

    # 8. Register blueprints
    from routes import register_blueprints
    register_blueprints(app)

    # 9. App-level routes
    _register_app_routes(app)

    # 10. Start schedulers (skip in testing)
    if not testing:
        _start_schedulers(settings)

    return app


def _register_app_routes(app):
    """Register app-level routes (metrics, SPA fallback)."""

    @app.route("/metrics", methods=["GET"])
    def prometheus_metrics():
        from metrics import generate_metrics
        from config import get_settings
        body, content_type = generate_metrics(get_settings().db_path)
        from flask import Response
        return Response(body, mimetype=content_type)

    @app.route("/", defaults={"path": ""})
    @app.route("/<path:path>")
    def serve_spa(path):
        static_dir = app.static_folder or "static"
        if path and os.path.exists(os.path.join(static_dir, path)):
            return send_from_directory(static_dir, path)
        index_path = os.path.join(static_dir, "index.html")
        if os.path.exists(index_path):
            return send_from_directory(static_dir, "index.html")
        return jsonify({
            "name": "Sublarr",
            "version": "0.1.0",
            "api": "/api/v1/health",
        })


def _start_schedulers(settings):
    """Start background schedulers."""
    from wanted_scanner import get_scanner
    scanner = get_scanner()
    scanner.start_scheduler(socketio=socketio)

    from database_backup import start_backup_scheduler
    start_backup_scheduler(
        db_path=settings.db_path,
        backup_dir=settings.backup_dir,
    )


def _setup_logging(settings):
    """Configure logging handlers."""
    log_level = getattr(logging, settings.log_level.upper(), logging.INFO)
    logging.basicConfig(level=log_level, format=LOG_FORMAT)
    # File and WebSocket handlers set up here
    # (see Pattern 7 in Architecture Patterns)
```

### Blueprint Route File
```python
# Source: https://flask.palletsprojects.com/en/stable/blueprints/
# routes/system.py

import logging
from flask import Blueprint, jsonify, request

bp = Blueprint("system", __name__, url_prefix="/api/v1")
logger = logging.getLogger(__name__)


@bp.route("/health", methods=["GET"])
def health():
    """Health check endpoint (no auth required)."""
    from ollama_client import check_ollama_health
    from config import get_settings

    healthy, message = check_ollama_health()
    service_status = {"ollama": message}

    # ... provider checks, sonarr checks, etc.

    return jsonify({
        "status": "ok" if healthy else "degraded",
        "services": service_status,
    })


@bp.route("/stats", methods=["GET"])
def get_stats():
    """Get translation statistics."""
    from db.jobs import get_stats_summary
    from config import get_settings

    stats = get_stats_summary()
    settings = get_settings()
    # ... build response
    return jsonify(stats)
```

### SocketIO Event Handlers
```python
# Source: https://flask-socketio.readthedocs.io/en/latest/getting_started.html
# app.py (inside create_app, or in a separate events.py)

from extensions import socketio

@socketio.on("connect")
def handle_connect():
    logger.debug("WebSocket client connected")

@socketio.on("disconnect")
def handle_disconnect():
    logger.debug("WebSocket client disconnected")
```

### Test Fixture with Factory Pattern
```python
# Source: https://flask.palletsprojects.com/en/stable/patterns/appfactories/
# tests/conftest.py

import pytest
import os
import tempfile
from config import reload_settings

@pytest.fixture
def temp_db():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    os.environ["SUBLARR_DB_PATH"] = db_path
    os.environ["SUBLARR_API_KEY"] = ""
    os.environ["SUBLARR_LOG_LEVEL"] = "ERROR"
    reload_settings()
    from db import init_db
    init_db()
    yield db_path
    if os.path.exists(db_path):
        os.unlink(db_path)

@pytest.fixture
def client(temp_db):
    from app import create_app
    application = create_app(testing=True)
    application.config["TESTING"] = True
    with application.test_client() as client:
        yield client
```

### Gunicorn Entry Point
```bash
# Source: https://flask.palletsprojects.com/en/stable/deploying/gunicorn/
# Dockerfile CMD (after refactor):
CMD ["gunicorn", "--bind", "0.0.0.0:5765", "--worker-class", "gthread", "--workers", "1", "--threads", "4", "--timeout", "300", "app:create_app()"]
```

### Dev Server Entry Point
```bash
# npm script (package.json) after refactor:
"dev:backend": "cd backend && cross-env FLASK_APP=app.py FLASK_ENV=development FLASK_DEBUG=1 python -m flask run --host=0.0.0.0 --port=5765 --reload"
```

Note: Flask CLI automatically detects `create_app` factory function in the specified module.

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `app = Flask(__name__)` at module level | `create_app()` factory function | Flask 0.9+ (2012), still current in 3.1 | Enables testing, multiple instances, cleaner imports |
| `SocketIO(app)` direct binding | `socketio = SocketIO()` + `socketio.init_app(app)` | Flask-SocketIO 2.0+ | Required for factory pattern; works with all async modes |
| `from server import app` in gunicorn | `"app:create_app()"` gunicorn syntax | Gunicorn 20+ | Direct factory support without wsgi.py shim |
| `FLASK_APP=server.py` for dev | `FLASK_APP=app.py` with auto-detected `create_app` | Flask 1.0+ CLI | Flask CLI finds `create_app()` or `make_app()` automatically |

**Deprecated/outdated:**
- `server:app` gunicorn syntax with module-level app: Still works but prevents factory benefits. Sublarr currently uses this.
- `--workers 2` with Flask-SocketIO gthread: Technically incorrect; should be `--workers 1`. Multiple workers require message queue (Redis).

## Open Questions

1. **SocketIO Event Handler Registration Location**
   - What we know: `@socketio.on("connect")` and `@socketio.on("disconnect")` currently live in server.py. They can be defined anywhere that imports `socketio` from extensions.py.
   - What's unclear: Whether to put them in `app.py` (inside `create_app`), in a separate `events.py`, or at the bottom of `extensions.py`.
   - Recommendation: Register them inside `create_app()` since they are trivial (2 debug log lines). If they grow, extract to `events.py`. No functional impact either way.

2. **SocketIOLogHandler Receiving socketio Instance**
   - What we know: Currently `SocketIOLogHandler` references the module-level `socketio` variable. After refactoring, it needs the instance from `extensions.py`.
   - What's unclear: Whether to pass `socketio` as a constructor argument or import it inside `emit()`.
   - Recommendation: Pass `socketio` as a constructor argument to `SocketIOLogHandler.__init__()`. This makes the dependency explicit and testable. The handler is created inside `_setup_logging()` which runs inside `create_app()`, so the import is available.

3. **Scheduler Start Timing**
   - What we know: `wanted_scanner.start_scheduler(socketio=socketio)` and `start_backup_scheduler()` currently run at module-level import time. In the factory, they run inside `create_app()`.
   - What's unclear: Whether gunicorn's `--preload` flag (if used) would cause schedulers to start in the master process instead of workers.
   - Recommendation: Always start schedulers inside `create_app()`. With `--workers 1`, there's only one process anyway. Add a `testing` parameter to `create_app()` to skip scheduler startup in tests.

## Sources

### Primary (HIGH confidence)
- [Flask Application Factories](https://flask.palletsprojects.com/en/stable/patterns/appfactories/) - Factory pattern, extension init_app, CLI detection
- [Flask Blueprints](https://flask.palletsprojects.com/en/stable/blueprints/) - Blueprint creation, registration, url_prefix, error handlers
- [Flask Application Context](https://flask.palletsprojects.com/en/stable/appcontext/) - current_app, g, manual context pushing, teardown handlers
- [Flask SQLite3 Pattern](https://flask.palletsprojects.com/en/stable/patterns/sqlite3/) - get_db with g, teardown, row_factory
- [Flask Tutorial: Database](https://flask.palletsprojects.com/en/stable/tutorial/database/) - init_app pattern for database, CLI commands
- [Flask-SocketIO: Getting Started](https://flask-socketio.readthedocs.io/en/latest/getting_started.html) - init_app() pattern, emit from outside handlers
- [Flask-SocketIO: Deployment](https://flask-socketio.readthedocs.io/en/latest/deployment.html) - gunicorn gthread, --workers 1, emit from external process
- [Flask Gunicorn Deployment](https://flask.palletsprojects.com/en/stable/deploying/gunicorn/) - `'app:create_app()'` syntax

### Secondary (MEDIUM confidence)
- Existing codebase analysis (server.py, database.py, conftest.py, auth.py, error_handler.py, wanted_scanner.py) - Current patterns, import structure, thread usage
- [Flask-SocketIO Issue #1347](https://github.com/miguelgrinberg/Flask-SocketIO/issues/1347) - gthread worker 400 bad request with multiple workers

### Tertiary (LOW confidence)
- None - all findings verified with primary sources

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - No new dependencies; all patterns verified in Flask 3.1 official docs
- Architecture: HIGH - Application Factory is Flask's officially recommended pattern; all extension init_app() methods verified
- Pitfalls: HIGH - Derived from direct codebase analysis (30+ import sites, background thread patterns, module-level state) cross-referenced with Flask documentation on context and threading
- Database strategy: HIGH - Decision to keep singleton (not switch to g.db) is driven by verified analysis of background thread usage in wanted_scanner.py, server.py webhook pipeline, and batch job threads

**Research date:** 2026-02-15
**Valid until:** 2026-04-15 (90 days - Flask patterns are extremely stable)
