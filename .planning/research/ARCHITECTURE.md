# Architecture Patterns

**Domain:** Subtitle management platform with LLM translation, evolving from monolith to modular architecture
**Researched:** 2026-02-15

## Current Architecture Assessment

Before designing the target architecture, it is critical to understand the existing system's structure and its pain points, because they dictate what can be changed incrementally versus what requires deeper refactoring.

### Current State (v1.0.0-beta)

```
                       +------------------+
                       |   React 19 SPA   |
                       | TanStack Query   |
                       | Socket.IO Client |
                       +--------+---------+
                                |
                    HTTP /api/v1/ + WebSocket
                                |
                       +--------+---------+
                       |   Flask + SocketIO |
                       |   (server.py)      |  <-- 2618 lines, single Blueprint
                       +--------+---------+
                                |
              +---------+-------+--------+---------+
              |         |       |        |         |
        +-----+--+ +---+---+ +-+-----+ ++---------++
        |database| |transla-| |wanted | |providers  |
        |  .py   | |tor.py | |scanner| |/__init__  |
        |(2153ln)| |(885ln) | |(685ln)| |(register) |
        +---+----+ +---+---+ +---+---+ +-----+-----+
            |           |         |           |
        SQLite WAL  ollama    sonarr/     4 providers
        17 tables   _client   radarr      (ABC pattern)
                              _client
```

### Current Structural Problems

1. **server.py monolith (2618 lines):** All API routes, batch state, job execution, and WebSocket events in a single file. Adding features will make this worse.

2. **database.py monolith (2153 lines):** All 17 tables, all CRUD functions, hand-written SQL with manual migrations. No ORM, no migration tool, no multi-database support.

3. **Tight Ollama coupling:** `translator.py` directly calls `ollama_client.py`. No abstraction layer for alternative translation backends (DeepL, LibreTranslate, OpenAI, local Whisper).

4. **No event system:** WebSocket events are emitted inline via `socketio.emit()` scattered through server.py. No central event bus, no hooks, no extensibility.

5. **Singleton pattern everywhere:** `_manager`, `_client`, `_scanner`, `_connection` globals with manual invalidation. Works for one process but blocks scaling.

6. **No plugin boundary:** Providers use a decorator registry (`@register_provider`) but discovery is via hardcoded imports in `_init_providers()`.

### What Works Well (Preserve)

- **Provider ABC pattern:** `SubtitleProvider` base class, `VideoQuery`/`SubtitleResult` dataclasses, scoring system. This is the right abstraction level.
- **Circuit breaker pattern:** Per-provider resilience with `CircuitBreaker` class. Extend to all external services.
- **Error hierarchy:** `SublarrError` with codes, HTTP status, troubleshooting hints. Extend to new subsystems.
- **Config cascade:** Env -> Pydantic Settings -> DB override. Sound pattern, needs to support plugin configs.
- **WebSocket real-time updates:** Socket.IO for job progress, batch updates. Keep but route through event bus.

---

## Recommended Target Architecture

### Guiding Principles

1. **Incremental migration.** Each change must be deployable independently. No "big bang" rewrite.
2. **Existing patterns first.** The provider ABC + registry pattern is proven. Replicate it for translation backends and media servers.
3. **Event-driven internals.** Replace inline `socketio.emit()` with a central event bus. WebSocket, webhooks, and plugins all consume the same events.
4. **Database abstraction before migration.** Introduce a repository layer over the current SQLite before attempting PostgreSQL support.
5. **Optional dependencies.** Redis, PostgreSQL, Whisper, faster-whisper are all optional. The core must always run with SQLite and no Redis.

### High-Level Component Diagram

```
                    +-------------------+
                    |   React 19 SPA    |
                    |  + react-i18next  |
                    |  + Plugin UI Slots|
                    +--------+----------+
                             |
                  HTTP /api/v1/ + WebSocket
                             |
              +--------------+--------------+
              |        Flask App Factory    |
              |   (multiple Blueprints)     |
              +--+---+---+---+---+---+-----+
                 |   |   |   |   |   |
    +------------+   |   |   |   |   +----------+
    |                |   |   |   |              |
+---+---+    +------++  |  ++------+     +------+-----+
| Core  |    |Transl.|  |  |Media  |     |Plugin      |
| API   |    |API    |  |  |Server |     |Manager     |
|Blueprint|  |Blueprint| |  |API BP |     |(discovery, |
+---+---+    +------++  |  ++------+     | lifecycle) |
    |               |   |   |           +------+-----+
    |               |   |   |                  |
    |    +----------+   |   +--------+    +----+------+
    |    |              |            |    |  Plugin   |
    |  +-+----------+   |    +-------+-+  |  Registry |
    |  |Translation |   |    |MediaSrv |  +-----------+
    |  |Backend ABC |   |    |ABC      |
    |  +--+---------+   |    +--+------+
    |     |             |       |
    |  +--+--+--+--+   |    +--+--+--+--+
    |  |Oll- |DL|LT|   |    |JF |Px|Ko|Em|
    |  |ama  |  |  |   |    +---+--+--+--+
    |  +-----+--+--+   |
    |                   |
+---+---+          +----+----+
|Event  | <------> |  Queue  |
|Bus    |          |  Manager|
+---+---+          +----+----+
    |                   |
+---+---+          +----+----+
|Reposit|          |Worker   |
|ory    |          |Pool     |
|Layer  |          |(threads/|
+---+---+          | Redis)  |
    |              +---------+
+---+---+
|SQLite |  (default)
|  or   |
|Postgre|  (optional)
+-------+
```

---

## Component Boundaries

### 1. Flask Application Factory + Blueprint Decomposition

**What:** Refactor the monolithic `server.py` into an application factory pattern with domain-specific Blueprints.

**Boundary:** Each Blueprint owns its routes, request validation, and response formatting. Business logic lives in service modules, not in route handlers.

| Blueprint | URL Prefix | Responsibility | Current Source |
|-----------|------------|----------------|----------------|
| `core_bp` | `/api/v1/` | Health, config, stats, onboarding | server.py lines 286-450 |
| `translation_bp` | `/api/v1/translate` | Jobs, batch, retranslate, sync translate | server.py lines 444-700 |
| `library_bp` | `/api/v1/library` | Library listing, series detail, episodes | server.py lines 700-1000 |
| `wanted_bp` | `/api/v1/wanted` | Wanted items, batch search, refresh | server.py lines 1000-1500 |
| `providers_bp` | `/api/v1/providers` | Provider management, cache, stats | server.py lines 1500-1700 |
| `profiles_bp` | `/api/v1/language-profiles` | Language profiles, glossary, presets | server.py lines 1700-2000 |
| `hooks_bp` | `/api/v1/webhook` | Sonarr/Radarr webhooks | server.py lines 2000-2200 |
| `admin_bp` | `/api/v1/admin` | Backup, health detailed, metrics | server.py lines 2200-2618 |
| `plugins_bp` | `/api/v1/plugins` | Plugin management, lifecycle | NEW |

**Communicates With:** Service layer (translation_service, wanted_service, etc.), Event Bus, Repository Layer.

**Application Factory Pattern:**
```python
# backend/app.py
def create_app(config_override=None):
    app = Flask(__name__, static_folder="static")

    # Config
    settings = load_settings(config_override)
    app.config["SETTINGS"] = settings

    # Extensions
    socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

    # Event bus
    event_bus = EventBus(socketio=socketio)
    app.config["EVENT_BUS"] = event_bus

    # Repository layer
    repo = create_repository(settings)
    app.config["REPO"] = repo

    # Register Blueprints
    from blueprints.core import core_bp
    from blueprints.translation import translation_bp
    # ...
    app.register_blueprint(core_bp)
    app.register_blueprint(translation_bp)

    # Plugin registration (after core Blueprints)
    plugin_manager = PluginManager(app, event_bus)
    plugin_manager.discover_and_load()

    return app, socketio
```

**Build order note:** This refactoring is a prerequisite for nearly everything else. It must come first, but can be done incrementally -- one Blueprint at a time extracted from server.py.

### 2. Event Bus

**What:** A central publish/subscribe system that replaces inline `socketio.emit()` calls. All internal state changes publish events. WebSocket forwarding, webhook delivery, plugin hooks, and logging all consume events.

**Boundary:** The event bus accepts typed events and dispatches to registered handlers. It does not know about Flask, WebSocket, or any specific consumer.

**Architecture:**
```python
# backend/events/bus.py
from dataclasses import dataclass, field
from typing import Callable, Any
from enum import Enum
import threading
import logging

class EventType(str, Enum):
    # Translation
    JOB_CREATED = "job.created"
    JOB_STARTED = "job.started"
    JOB_COMPLETED = "job.completed"
    JOB_FAILED = "job.failed"

    # Batch
    BATCH_STARTED = "batch.started"
    BATCH_PROGRESS = "batch.progress"
    BATCH_COMPLETED = "batch.completed"

    # Wanted
    WANTED_SCAN_COMPLETED = "wanted.scan_completed"
    WANTED_SEARCH_COMPLETED = "wanted.search_completed"

    # Providers
    PROVIDER_SEARCH_COMPLETED = "provider.search_completed"
    SUBTITLE_DOWNLOADED = "subtitle.downloaded"

    # Webhook
    WEBHOOK_RECEIVED = "webhook.received"

    # Config
    CONFIG_UPDATED = "config.updated"

    # Plugin lifecycle
    PLUGIN_LOADED = "plugin.loaded"
    PLUGIN_ERROR = "plugin.error"

@dataclass
class Event:
    type: EventType
    data: dict = field(default_factory=dict)
    source: str = "core"

class EventBus:
    def __init__(self):
        self._handlers: dict[str, list[Callable]] = {}
        self._lock = threading.Lock()

    def subscribe(self, event_type: str | EventType, handler: Callable):
        key = event_type.value if isinstance(event_type, EventType) else event_type
        with self._lock:
            self._handlers.setdefault(key, []).append(handler)

    def publish(self, event: Event):
        key = event.type.value if isinstance(event.type, EventType) else event.type
        with self._lock:
            handlers = list(self._handlers.get(key, []))
            # Also notify wildcard subscribers
            handlers.extend(self._handlers.get("*", []))

        for handler in handlers:
            try:
                handler(event)
            except Exception:
                logging.getLogger(__name__).exception(
                    "Event handler error for %s", key
                )
```

**Built-in Consumers:**
- **WebSocket forwarder:** Subscribes to all events, emits to Socket.IO (replaces scattered `socketio.emit()`)
- **Webhook delivery:** Subscribes to configured event types, delivers HTTP POST to registered URLs
- **Metrics collector:** Subscribes to business events, updates Prometheus counters
- **Notification dispatcher:** Subscribes to configured events, sends via Apprise

**Communicates With:** Every component publishes events. Consumers subscribe. The bus itself has no dependencies.

**Build order note:** Event bus should be introduced early (after Blueprint refactoring) because it decouples everything else. Initially just wrap existing `socketio.emit()` calls.

### 3. Translation Backend Abstraction

**What:** An ABC pattern (mirroring `SubtitleProvider`) that abstracts translation engines. Ollama is the current default; DeepL, LibreTranslate, OpenAI, and Whisper-based STT+translate become additional backends.

**Boundary:** Each backend implements `translate_batch(lines, source_lang, target_lang) -> list[str]` and `health_check() -> (bool, str)`. The orchestrator (translator.py) selects backend per language profile.

**Architecture:**
```python
# backend/translation/backends/base.py
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

@dataclass
class TranslationRequest:
    lines: list[str]
    source_language: str
    target_language: str
    context: Optional[dict] = None  # glossary, style hints, etc.

@dataclass
class TranslationResult:
    translated_lines: list[str]
    backend_name: str
    confidence: float = 1.0
    metadata: dict = None

class TranslationBackend(ABC):
    name: str = "unknown"
    supports_batch: bool = True
    supports_streaming: bool = False

    @abstractmethod
    def translate_batch(self, request: TranslationRequest) -> TranslationResult:
        """Translate a batch of subtitle lines."""
        ...

    @abstractmethod
    def health_check(self) -> tuple[bool, str]:
        """Check if backend is available and configured."""
        ...

    @abstractmethod
    def get_supported_languages(self) -> set[tuple[str, str]]:
        """Return set of (source, target) language pairs."""
        ...

    def get_config_schema(self) -> dict:
        """Return JSON Schema for backend-specific configuration."""
        return {}
```

**Backend Registry (mirrors provider pattern):**
```python
# backend/translation/backends/__init__.py
_BACKEND_CLASSES: dict[str, type[TranslationBackend]] = {}
_manager: Optional["TranslationManager"] = None

def register_backend(cls):
    _BACKEND_CLASSES[cls.name] = cls
    return cls

class TranslationManager:
    def __init__(self, settings, event_bus):
        self._backends: dict[str, TranslationBackend] = {}
        self._fallback_chain: list[str] = []
        self._circuit_breakers: dict[str, CircuitBreaker] = {}

    def translate(self, request: TranslationRequest,
                  preferred_backend: str = None) -> TranslationResult:
        """Translate using preferred backend with fallback chain."""
        chain = [preferred_backend] + self._fallback_chain if preferred_backend else self._fallback_chain

        for backend_name in chain:
            if backend_name not in self._backends:
                continue
            cb = self._circuit_breakers.get(backend_name)
            if cb and cb.is_open:
                continue
            try:
                result = self._backends[backend_name].translate_batch(request)
                if cb:
                    cb.record_success()
                return result
            except Exception as e:
                if cb:
                    cb.record_failure()
                continue

        raise TranslationError("All backends failed")
```

**Concrete Backends:**
| Backend | Module | Dependencies | Notes |
|---------|--------|-------------|-------|
| `OllamaBackend` | `backends/ollama.py` | requests | Existing code moved here |
| `DeepLBackend` | `backends/deepl.py` | deepl | API key required, 500k chars/month free |
| `LibreTranslateBackend` | `backends/libretranslate.py` | requests | Self-hosted, no API limits |
| `OpenAIBackend` | `backends/openai.py` | openai | GPT-4o-mini, cost per token |
| `WhisperBackend` | `backends/whisper.py` | faster-whisper, PyAV | STT, not translation -- see Whisper section |

**Per-Profile Backend Selection:**
Language profiles gain a `translation_backend` field. This allows: "Use Ollama for en->de, use DeepL for en->fr." The fallback chain is global but per-profile overrides are supported.

**Communicates With:** `TranslationManager` is called by `translator.py` (the pipeline orchestrator). It publishes events via EventBus. Circuit breakers are per-backend.

**Build order note:** Depends on Event Bus (for event publishing). Can be done without Blueprint refactoring but benefits from it. Extract `ollama_client.py` into `backends/ollama.py` as the first backend, then add others.

### 4. Plugin System

**What:** Dynamic loading of Python modules that extend Sublarr's functionality. Plugins can add providers, translation backends, API endpoints, event handlers, and UI components.

**Boundary:** Plugins are isolated Python packages in a designated directory (`/config/plugins/`). They declare capabilities via a manifest. The PluginManager handles discovery, lifecycle, and sandboxing.

**Architecture:**
```python
# backend/plugins/base.py
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

@dataclass
class PluginManifest:
    name: str
    version: str
    description: str
    author: str
    min_sublarr_version: str = "0.2.0"

    # Capability declarations
    provides_providers: list[str] = None      # Subtitle provider names
    provides_backends: list[str] = None       # Translation backend names
    provides_media_servers: list[str] = None  # Media server adapter names
    provides_api_routes: bool = False         # Adds custom API endpoints
    subscribes_events: list[str] = None       # Event types to subscribe to
    provides_ui: bool = False                 # Has frontend components

    # Configuration
    config_schema: dict = None  # JSON Schema for plugin settings

class SublarrPlugin(ABC):
    manifest: PluginManifest

    @abstractmethod
    def activate(self, context: "PluginContext"):
        """Called when plugin is loaded. Register providers, backends, routes."""
        ...

    @abstractmethod
    def deactivate(self):
        """Called when plugin is unloaded. Clean up resources."""
        ...

@dataclass
class PluginContext:
    """Provided to plugins during activation. Controlled API surface."""
    register_provider: Callable
    register_backend: Callable
    register_media_server: Callable
    register_blueprint: Callable  # For custom API routes
    subscribe_event: Callable
    publish_event: Callable
    get_config: Callable          # Plugin-specific config from DB
    set_config: Callable
    get_db: Callable              # Read-only DB access via repository
    logger: logging.Logger
```

**Discovery Strategy:**
Use `importlib` + filesystem scanning (not entry_points, because plugins are user-installed, not pip-installed):
```python
# backend/plugins/manager.py
class PluginManager:
    def __init__(self, plugin_dir="/config/plugins"):
        self.plugin_dir = plugin_dir
        self._plugins: dict[str, SublarrPlugin] = {}

    def discover_and_load(self):
        """Scan plugin directory for valid plugins."""
        for item in os.listdir(self.plugin_dir):
            path = os.path.join(self.plugin_dir, item)
            if os.path.isdir(path) and os.path.exists(os.path.join(path, "manifest.json")):
                self._load_plugin(path)

    def _load_plugin(self, path):
        """Load a plugin from its directory."""
        manifest = self._read_manifest(os.path.join(path, "manifest.json"))

        # Version compatibility check
        if not self._check_compatibility(manifest):
            return

        # Import plugin module
        spec = importlib.util.spec_from_file_location(
            manifest.name,
            os.path.join(path, "__init__.py")
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        # Find and instantiate plugin class
        plugin_cls = getattr(module, "Plugin", None)
        if plugin_cls and issubclass(plugin_cls, SublarrPlugin):
            plugin = plugin_cls()
            context = self._create_context(manifest)
            plugin.activate(context)
            self._plugins[manifest.name] = plugin
```

**Sandboxing:** Plugins get a restricted `PluginContext` -- not the raw Flask app. They cannot directly access the database connection, modify core routes, or access other plugins' data. The `get_db` function returns a repository interface, not raw SQL.

**Communicates With:** PluginManager talks to all registries (provider, backend, media server). Plugins communicate via EventBus only.

**Build order note:** Plugin system depends on: (1) Event Bus, (2) Translation Backend abstraction, (3) Provider registry cleanup, (4) Repository layer. It is one of the last components to implement.

### 5. Whisper Integration (Audio-to-Subtitle Pipeline)

**What:** Generate subtitles from audio tracks when no text-based subtitles exist at all. This is distinct from translation -- it is speech-to-text, potentially followed by translation.

**Boundary:** Whisper integration is a new pipeline step in `translator.py` Case C (no target subtitle exists). It extracts audio via PyAV/ffmpeg, runs faster-whisper, produces SRT/ASS, then optionally translates.

**Architecture:**
```
Case C pipeline (extended):
  1. Check embedded subs -> extract if found
  2. Search providers -> download if found
  3. [NEW] Extract audio -> run Whisper STT -> produce source-lang SRT
  4. Translate source-lang SRT -> target-lang ASS/SRT
```

**GPU Queue Manager:**
```python
# backend/whisper/queue.py
import threading
from queue import PriorityQueue
from dataclasses import dataclass, field

@dataclass(order=True)
class WhisperJob:
    priority: int
    file_path: str = field(compare=False)
    target_language: str = field(compare=False)
    callback: Callable = field(compare=False)

class WhisperQueueManager:
    """Manages GPU access for Whisper transcription.

    Only one transcription runs at a time (GPU memory constraint).
    Jobs are prioritized: manual requests > wanted items > batch.
    """

    def __init__(self, model_size="large-v3", device="auto", compute_type="float16"):
        self._queue = PriorityQueue()
        self._worker = None
        self._model = None
        self._model_config = (model_size, device, compute_type)
        self._lock = threading.Lock()

    def _lazy_load_model(self):
        """Load model on first use (heavy: ~3GB VRAM for large-v3)."""
        if self._model is None:
            from faster_whisper import WhisperModel
            self._model = WhisperModel(
                self._model_config[0],
                device=self._model_config[1],
                compute_type=self._model_config[2],
            )

    def enqueue(self, file_path: str, priority: int = 5,
                target_language: str = None, callback=None):
        """Add transcription job to queue."""
        job = WhisperJob(priority, file_path, target_language, callback)
        self._queue.put(job)
        self._ensure_worker()

    def _worker_loop(self):
        """Process jobs sequentially (GPU is the bottleneck)."""
        while True:
            job = self._queue.get()
            if job is None:
                break
            try:
                self._lazy_load_model()
                result = self._transcribe(job)
                if job.callback:
                    job.callback(result)
            except Exception as e:
                logging.exception("Whisper job failed: %s", job.file_path)
```

**Audio Extraction (using PyAV, already bundled by faster-whisper):**
```python
# backend/whisper/audio.py
def extract_audio(video_path: str, output_path: str = None) -> str:
    """Extract audio track from video file.

    Uses PyAV (bundled with faster-whisper) -- no external ffmpeg needed.
    Returns path to extracted WAV file.
    """
    import av
    # ... extract audio to temp WAV
```

**Progress Tracking:**
Whisper transcription is slow (real-time or slower on CPU). Progress events are published via EventBus:
```python
event_bus.publish(Event(
    type=EventType.WHISPER_PROGRESS,
    data={"file": file_path, "percent": 45, "eta_seconds": 120}
))
```

**Communicates With:** Whisper Queue is called by `translator.py` as a fallback in Case C. Publishes progress via EventBus. Results feed back into the translation pipeline.

**Build order note:** Whisper is an independent feature that only needs the Event Bus. It does not depend on plugin system or DB migration. However, it requires optional dependencies (faster-whisper, PyAV) and GPU access, so the Docker image needs a CUDA variant.

### 6. Media Server Abstraction Layer

**What:** A unified interface for refreshing media libraries after new subtitle files are created. Currently only Jellyfin is supported; Plex, Kodi, and Emby need support.

**Boundary:** Each media server adapter implements `refresh_item(file_path)`, `refresh_library()`, and `health_check()`. The existing `jellyfin_client.py` becomes one adapter.

**Architecture:**
```python
# backend/media_servers/base.py
from abc import ABC, abstractmethod

class MediaServerAdapter(ABC):
    name: str = "unknown"

    @abstractmethod
    def initialize(self, config: dict):
        """Configure the adapter with URL, API key, etc."""
        ...

    @abstractmethod
    def refresh_item(self, file_path: str) -> bool:
        """Notify server that a specific file has new subtitles."""
        ...

    @abstractmethod
    def refresh_library(self, library_id: str = None) -> bool:
        """Trigger full library or specific library rescan."""
        ...

    @abstractmethod
    def health_check(self) -> tuple[bool, str]:
        """Check connectivity and authentication."""
        ...

    def get_libraries(self) -> list[dict]:
        """List available media libraries (for UI selection)."""
        return []

# backend/media_servers/__init__.py
_ADAPTER_CLASSES: dict[str, type[MediaServerAdapter]] = {}

def register_adapter(cls):
    _ADAPTER_CLASSES[cls.name] = cls
    return cls
```

**Concrete Adapters:**
| Adapter | Module | API | Library |
|---------|--------|-----|---------|
| `JellyfinAdapter` | `adapters/jellyfin.py` | REST `/Library/Refresh` | requests (existing) |
| `EmbyAdapter` | `adapters/emby.py` | REST (same as Jellyfin) | requests |
| `PlexAdapter` | `adapters/plex.py` | REST `/library/sections/X/refresh` | python-plexapi |
| `KodiAdapter` | `adapters/kodi.py` | JSON-RPC `VideoLibrary.Scan` | requests |

**Multi-Server Support:**
Users often run multiple media servers. The `MediaServerManager` notifies all configured servers:
```python
class MediaServerManager:
    def __init__(self):
        self._servers: list[MediaServerAdapter] = []

    def notify_subtitle_added(self, file_path: str):
        for server in self._servers:
            try:
                server.refresh_item(file_path)
            except Exception:
                logging.exception("Failed to notify %s", server.name)
```

**Communicates With:** Called by translation pipeline after subtitle creation. Subscribes to `SUBTITLE_DOWNLOADED` and `JOB_COMPLETED` events via EventBus.

**Build order note:** Low coupling, low risk. Can be done any time after Event Bus. The existing `jellyfin_client.py` migrates to become the first adapter.

### 7. Repository Layer (Database Abstraction)

**What:** Abstract database access behind a repository pattern to enable SQLite-to-PostgreSQL migration and make the codebase testable.

**Boundary:** Repositories provide domain-specific data access methods. The underlying engine (SQLite or SQLAlchemy+PostgreSQL) is hidden.

**Architecture:**
```python
# backend/repositories/base.py
from abc import ABC, abstractmethod
from typing import Protocol

class JobRepository(Protocol):
    def create_job(self, file_path: str, **kwargs) -> str: ...
    def get_job(self, job_id: str) -> dict | None: ...
    def update_job(self, job_id: str, status: str, **kwargs): ...
    def get_jobs(self, page: int, per_page: int, status: str = None) -> dict: ...

class WantedRepository(Protocol):
    def upsert_wanted_item(self, **kwargs) -> int: ...
    def get_wanted_items(self, page: int, per_page: int, **kwargs) -> dict: ...
    def update_wanted_status(self, item_id: int, status: str): ...

class ConfigRepository(Protocol):
    def get_all_config_entries(self) -> dict: ...
    def get_config_entry(self, key: str) -> str | None: ...
    def save_config_entry(self, key: str, value: str): ...

# backend/repositories/sqlite.py
class SQLiteJobRepository:
    """Current database.py logic wrapped in repository interface."""

    def __init__(self, db_path: str):
        self._db = sqlite3.connect(db_path, check_same_thread=False)
        self._lock = threading.Lock()

    def create_job(self, file_path, **kwargs):
        # Existing create_job logic from database.py
        ...

# backend/repositories/sqlalchemy.py (future)
class SQLAlchemyJobRepository:
    """PostgreSQL support via SQLAlchemy."""

    def __init__(self, session_factory):
        self._session_factory = session_factory

    def create_job(self, file_path, **kwargs):
        with self._session_factory() as session:
            job = Job(file_path=file_path, **kwargs)
            session.add(job)
            session.commit()
            return job.id
```

**Migration Strategy (SQLite -> PostgreSQL):**
1. Phase 1: Wrap existing `database.py` functions in SQLiteRepository classes (no behavior change).
2. Phase 2: Introduce SQLAlchemy models alongside raw SQLite (dual-write for testing).
3. Phase 3: Add Alembic for schema migrations.
4. Phase 4: Implement SQLAlchemyRepository as alternative backend.
5. Phase 5: Config switch: `SUBLARR_DB_URL=postgresql://...` selects SQLAlchemy path.

**Important:** Use Alembic's batch migration mode for SQLite (handles ALTER TABLE limitations). PostgreSQL migrations run normally. Test both paths in CI.

**Communicates With:** All Blueprints and services access data through repositories. Repositories are injected via app factory.

**Build order note:** This is foundational but can be done incrementally. Start by creating repository interfaces that delegate to existing `database.py` functions. The actual SQLAlchemy migration comes much later.

### 8. Standalone Library Management

**What:** Allow Sublarr to manage media libraries directly from filesystem without requiring Sonarr/Radarr. Uses folder watching and metadata resolution.

**Boundary:** The standalone module provides library scanning, file watching, and metadata resolution. It feeds into the same wanted system as Sonarr/Radarr but with a different source.

**Architecture:**
```python
# backend/standalone/watcher.py
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

class MediaFileHandler(FileSystemEventHandler):
    """Watch media directories for new/changed video files."""

    def on_created(self, event):
        if event.is_directory:
            return
        if self._is_media_file(event.src_path):
            self._event_bus.publish(Event(
                type=EventType.MEDIA_FILE_ADDED,
                data={"path": event.src_path}
            ))

    def _is_media_file(self, path):
        return path.lower().endswith(('.mkv', '.mp4', '.avi'))

class StandaloneLibrary:
    """Manages media library from filesystem scanning."""

    def __init__(self, media_paths: list[str], event_bus: EventBus):
        self._paths = media_paths
        self._observer = Observer()
        self._event_bus = event_bus
        self._metadata_resolver = MetadataResolver()

    def scan(self):
        """Full library scan -- find all media files, resolve metadata."""
        for path in self._paths:
            for root, dirs, files in os.walk(path):
                for f in files:
                    if self._is_media_file(f):
                        file_path = os.path.join(root, f)
                        metadata = self._metadata_resolver.resolve(file_path)
                        # Create/update library entry in DB
                        # Check for missing subtitles -> add to wanted

    def start_watching(self):
        """Start filesystem watcher for real-time detection."""
        for path in self._paths:
            self._observer.schedule(
                MediaFileHandler(self._event_bus),
                path, recursive=True
            )
        self._observer.start()

# backend/standalone/metadata.py
class MetadataResolver:
    """Resolve series/movie metadata from filename + external APIs."""

    def resolve(self, file_path: str) -> dict:
        """
        Resolution chain:
        1. Parse filename (series title, S01E01, year)
        2. Look up in local cache
        3. Query TMDB/TVDB API for metadata
        4. Cache result
        """
        parsed = parse_filename(file_path)
        cached = self._cache.get(parsed)
        if cached:
            return cached

        # Try TMDB for movies, TVDB for series
        if parsed.get("season") is not None:
            metadata = self._tvdb.search(parsed)
        else:
            metadata = self._tmdb.search(parsed)

        self._cache.set(parsed, metadata)
        return metadata
```

**Communicates With:** Standalone library feeds into the same WantedRepository as Sonarr/Radarr. Uses EventBus for file detection events. MetadataResolver uses external APIs (TMDB, TVDB) with circuit breakers.

**Build order note:** Depends on Repository Layer (needs `library_items` table) and Event Bus. Independent of plugin system. The `wanted_search.py` already has `_parse_filename_for_metadata()` which serves as a starting point.

### 9. Queue Manager (Redis Integration)

**What:** Replace in-memory threading-based job processing with a proper queue system. Redis is optional -- falls back to in-memory threading queue.

**Boundary:** The Queue Manager provides `enqueue(job)`, `get_status(job_id)`, and worker management. Redis adds persistence, distributed workers, and rate limiting.

**Architecture:**
```python
# backend/queue/manager.py
from abc import ABC, abstractmethod

class QueueBackend(ABC):
    @abstractmethod
    def enqueue(self, job_type: str, payload: dict, priority: int = 5) -> str: ...
    @abstractmethod
    def get_status(self, job_id: str) -> dict: ...
    @abstractmethod
    def get_queue_size(self) -> int: ...

class ThreadQueueBackend(QueueBackend):
    """In-memory queue using ThreadPoolExecutor. Default, no Redis needed."""
    pass  # Current behavior extracted

class RedisQueueBackend(QueueBackend):
    """Redis-backed queue using RQ (Redis Queue)."""
    pass  # Optional, requires redis + rq
```

**Redis Caching Layer (optional):**
```python
# backend/cache/redis_cache.py
class CacheBackend(ABC):
    @abstractmethod
    def get(self, key: str) -> str | None: ...
    @abstractmethod
    def set(self, key: str, value: str, ttl: int = 300): ...

class MemoryCache(CacheBackend):
    """In-memory LRU cache. Default."""
    pass

class RedisCache(CacheBackend):
    """Redis-backed cache. Optional."""
    pass
```

**Redis Rate Limiting:**
```python
# Replace in-memory rate limit tracking in ProviderManager
class RateLimiter:
    def __init__(self, backend: "RedisCache | MemoryCache"):
        self._backend = backend

    def check_rate_limit(self, key: str, max_requests: int, window_seconds: int) -> bool:
        # Redis: INCR + EXPIRE atomic operation
        # Memory: collections.deque with timestamp pruning
        ...
```

**Communicates With:** All job-creating endpoints enqueue through QueueManager. Workers pull jobs and execute. Event Bus receives completion events.

**Build order note:** Redis integration is a cross-cutting concern. Start with abstracting the current ThreadPoolExecutor into `ThreadQueueBackend`. Redis backend comes later. Caching and rate limiting are separate concerns that can be added independently.

### 10. Frontend i18n Architecture

**What:** Internationalize the React frontend using react-i18next with namespace-based translation loading.

**Boundary:** Translation files are organized by namespace (one per page/feature). Loading is lazy -- only the active page's translations are fetched.

**Architecture:**
```
frontend/
  public/
    locales/
      en/
        common.json       # Shared: buttons, labels, status badges
        dashboard.json    # Dashboard-specific
        settings.json     # Settings page
        library.json      # Library + series detail
        wanted.json       # Wanted page
        translation.json  # Translation/jobs/batch
        providers.json    # Provider management
        errors.json       # Error messages, troubleshooting
      de/
        common.json
        dashboard.json
        ...
      ja/
        ...
  src/
    i18n/
      config.ts           # i18next initialization + lazy loading
      index.ts            # Re-export
    hooks/
      useTranslation.ts   # Typed wrapper around react-i18next
```

**Namespace Strategy:**
| Namespace | Scope | Estimated Keys |
|-----------|-------|----------------|
| `common` | Always loaded. Buttons, status labels, navigation | ~80 |
| `dashboard` | Dashboard page | ~30 |
| `settings` | Settings page (largest) | ~150 |
| `library` | Library + SeriesDetail pages | ~60 |
| `wanted` | Wanted page | ~40 |
| `translation` | Jobs, batch, retranslation | ~40 |
| `providers` | Provider management | ~30 |
| `errors` | Error messages, troubleshooting hints | ~50 |

**i18next Configuration:**
```typescript
// frontend/src/i18n/config.ts
import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'
import HttpBackend from 'i18next-http-backend'
import LanguageDetector from 'i18next-browser-languagedetector'

i18n
  .use(HttpBackend)
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    fallbackLng: 'en',
    ns: ['common'],           // Only load common on startup
    defaultNS: 'common',
    backend: {
      loadPath: '/locales/{{lng}}/{{ns}}.json',
    },
    interpolation: { escapeValue: false },
  })
```

**Communicates With:** Pure frontend concern. No backend changes needed except serving locale files from static directory.

**Build order note:** Completely independent. Can be done at any time. Best done before major UI additions (so new UI is born i18n-ready).

---

## Data Flow

### Translation Job Flow (Current + Extensions)

```
User/Webhook/Wanted
       |
       v
  [Queue Manager]  --enqueue--> [Worker Pool]
       |                             |
       |                      [translator.py]
       |                             |
       |              +--------------+---------------+
       |              |              |               |
       |         Case A:        Case B:         Case C:
       |         Target ASS     Target SRT      No target
       |         exists         exists           at all
       |              |              |               |
       |           (skip)     [Provider         [Provider Search]
       |              |        Search]               |
       |              |              |          (if no results)
       |              |         [Download]           |
       |              |              |          [Whisper STT] (NEW)
       |              |              |               |
       |              |     [Translation        [Translation
       |              |      Backend]            Backend]
       |              |       (NEW ABC)          (NEW ABC)
       |              |              |               |
       |              +--------------+---------------+
       |                             |
       |                    [Write subtitle file]
       |                             |
       |                    [Media Server Notify] (NEW)
       |                             |
       v                             v
  [Event Bus] <---- JOB_COMPLETED ----
       |
  +----+--------+--------+
  |    |        |        |
  v    v        v        v
 WS  Webhook  Metrics  Notifier
```

### Configuration Flow

```
Environment Variables (.env / Docker)
       |
       v
  Pydantic Settings (config.py)
       |
       v
  DB config_entries (runtime overrides from UI)
       |
       v
  Plugin configs (in config_entries with prefix)
       |
       v
  Active Settings (merged, cached)
       |
  +----+----+----+
  |    |    |    |
  v    v    v    v
 Core  Plugins  Backends  MediaServers
```

### Event Flow

```
[Source]                    [Event Bus]                    [Consumer]
                                |
translator.py  -- JOB_COMPLETED --> --> WebSocket forwarder --> React SPA
                                |   --> Webhook delivery   --> External URLs
                                |   --> Metrics collector   --> Prometheus
                                |   --> Notification        --> Apprise
                                |   --> Plugin handlers     --> Plugin code
                                |
wanted_scanner -- SCAN_COMPLETE --> --> WebSocket forwarder
                                |   --> Plugin handlers
                                |
PluginX        -- CUSTOM_EVENT  --> --> Other plugins
                                |   --> Webhook delivery
```

---

## Patterns to Follow

### Pattern 1: Registry + ABC (Already Proven)
**What:** Abstract base class defines the contract. Concrete implementations are registered in a dict. Manager iterates registered implementations with circuit breakers.
**When:** Any extensible subsystem (providers, backends, media servers, plugins).
**Example:** `SubtitleProvider` ABC + `@register_provider` decorator + `ProviderManager`.

### Pattern 2: Application Factory
**What:** `create_app()` function builds Flask app with all dependencies injected.
**When:** Required for the Blueprint decomposition and testability.
**Example:** See Flask Application Factory section above.

### Pattern 3: Optional Dependencies with Graceful Degradation
**What:** Import optional packages in try/except. Provide fallback behavior when not installed.
**When:** Redis, faster-whisper, prometheus_client, deepl, python-plexapi.
**Example:** Current `metrics.py` already does this with `METRICS_AVAILABLE = True/False`.

### Pattern 4: Event-Driven Decoupling
**What:** Components publish events, consumers subscribe. No direct coupling between producer and consumer.
**When:** Any cross-cutting concern (notifications, metrics, WebSocket updates, plugin hooks).
**Example:** Replace `socketio.emit("job_update", data)` with `event_bus.publish(Event(JOB_COMPLETED, data))`.

---

## Anti-Patterns to Avoid

### Anti-Pattern 1: God Service Object
**What:** Creating a single "SublarrService" that coordinates everything.
**Why bad:** Recreates the monolith problem. Services should be domain-specific.
**Instead:** Separate services per domain (TranslationService, WantedService, LibraryService) with shared EventBus.

### Anti-Pattern 2: Direct Plugin Database Access
**What:** Giving plugins raw SQL access to the main database.
**Why bad:** Schema coupling, data corruption, upgrade breakage.
**Instead:** Plugins get a repository interface for read operations and publish events for writes that core handles.

### Anti-Pattern 3: Synchronous Whisper in Request Handler
**What:** Running Whisper transcription in an HTTP request thread.
**Why bad:** Whisper takes minutes. Request will timeout. GPU will be blocked.
**Instead:** Always enqueue Whisper jobs. Return job ID immediately. Report progress via WebSocket.

### Anti-Pattern 4: Big Bang Database Migration
**What:** Switching from raw SQLite to SQLAlchemy + PostgreSQL in one step.
**Why bad:** 2153 lines of database.py with 17 tables. Migration errors will break everything.
**Instead:** Incremental: repository interfaces first, then SQLAlchemy models, then Alembic migrations, then optional PostgreSQL.

### Anti-Pattern 5: Multiple Event Systems
**What:** Using blinker signals AND a custom event bus AND Socket.IO events AND webhook dispatch separately.
**Why bad:** Events get lost, order is inconsistent, debugging is impossible.
**Instead:** One EventBus. All consumers (WebSocket, webhooks, plugins, metrics) subscribe to the same bus.

---

## Scalability Considerations

| Concern | At 100 users (Homelab) | At 10K users (Self-hosted community) | At 1M users (Not a target) |
|---------|------------------------|--------------------------------------|-----------------------------|
| Database | SQLite WAL, single file, zero config | SQLite still works for single-instance. PostgreSQL for multi-worker setups. | PostgreSQL with connection pooling |
| Job Queue | ThreadPoolExecutor (current) | Redis Queue (RQ) for persistence and retry | Celery + Redis/RabbitMQ |
| Caching | In-memory dicts (current) | Redis for shared cache across workers | Redis cluster |
| GPU (Whisper) | Single GPU, sequential queue | Single GPU with priority queue | GPU cluster, not in scope |
| Real-time Updates | Socket.IO in-process (current) | Socket.IO with Redis message queue adapter | Socket.IO with Redis adapter |
| Translation | Single Ollama instance | Multiple backend fallback chain | Load-balanced backend pool |

**Key insight:** Sublarr is a homelab/self-hosted tool. The 100-user column is the primary target. Design for it, enable the 10K column, ignore the 1M column.

---

## Suggested Build Order (Dependencies)

```
Phase 1: Foundation Refactoring
  1.1  Flask Application Factory + Blueprint decomposition
  1.2  Event Bus (wrap existing socketio.emit calls)
  1.3  Repository interfaces (wrap existing database.py)

Phase 2: Extensibility Layer
  2.1  Translation Backend ABC (extract ollama_client.py)
  2.2  Media Server abstraction (migrate jellyfin_client.py)
  2.3  Plugin system foundation (discovery, lifecycle, context)

Phase 3: New Capabilities
  3.1  Whisper integration (audio extraction, GPU queue, STT pipeline)
  3.2  Standalone library management (watchdog, metadata resolution)
  3.3  Additional translation backends (DeepL, LibreTranslate)
  3.4  Additional media servers (Plex, Kodi, Emby)

Phase 4: Infrastructure Upgrades
  4.1  Redis integration (optional caching, job queue, rate limiting)
  4.2  Database migration (SQLAlchemy models, Alembic, PostgreSQL option)
  4.3  Frontend i18n (react-i18next, namespace structure)
  4.4  Event hooks + webhook delivery system
  4.5  OpenAPI spec generation (Flask-Smorest or apispec)
```

**Why this order:**
- Phase 1 creates the architectural foundation everything else builds on. Without app factory, you cannot inject dependencies. Without event bus, new features would add more inline coupling. Without repository interfaces, database migration is impossible.
- Phase 2 creates extension points. Translation backend ABC must exist before adding new backends. Media server abstraction must exist before adding Plex/Kodi. Plugin system needs all registries to be in place.
- Phase 3 is independent features that use the Phase 2 extension points. These can be parallelized.
- Phase 4 is infrastructure that improves non-functional properties (performance, scalability, i18n). These are lowest priority because the current infrastructure works fine for the homelab use case.

---

## Sources

- [Flask Application Factory Pattern](https://flask.palletsprojects.com/en/stable/patterns/appfactories/) -- Official Flask docs (HIGH confidence)
- [Flask Blueprints](https://flask.palletsprojects.com/en/stable/blueprints/) -- Official Flask docs (HIGH confidence)
- [Python Plugin Architecture](https://packaging.python.org/en/latest/guides/creating-and-discovering-plugins/) -- Python Packaging User Guide (HIGH confidence)
- [Alembic Batch Migrations for SQLite](https://alembic.sqlalchemy.org/en/latest/batch.html) -- Official Alembic docs (HIGH confidence)
- [faster-whisper](https://github.com/SYSTRAN/faster-whisper) -- Official repository (HIGH confidence)
- [watchdog](https://github.com/gorakhargosh/watchdog) -- Official repository (HIGH confidence)
- [python-plexapi](https://python-plexapi.readthedocs.io/) -- Official docs (HIGH confidence)
- [react-i18next Multiple Translation Files](https://react.i18next.com/guides/multiple-translation-files) -- Official docs (HIGH confidence)
- [bubus Event Bus](https://github.com/browser-use/bubus) -- GitHub (MEDIUM confidence, new library)
- [Redis Rate Limiting Patterns](https://redis.io/learn/howtos/ratelimiting) -- Official Redis docs (HIGH confidence)
- [Bazarr Architecture](https://github.com/morpheus65535/bazarr) -- Reference implementation (MEDIUM confidence)
- [Choosing Whisper Variants](https://modal.com/blog/choosing-whisper-variants) -- Modal blog (MEDIUM confidence)
