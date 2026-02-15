# Technology Stack - Phase 2+3 Additions

**Project:** Sublarr - Standalone Subtitle Manager & Translator
**Researched:** 2026-02-15
**Scope:** Libraries needed for Milestones 13-32 (Phase 2: Open Platform + Phase 3: Advanced Features)
**Existing stack preserved:** Flask 3.1, React 19, SQLite WAL, Tailwind v4, TanStack Query, Vite 7

---

## Recommended Stack

### Provider Plugin System (M13)

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| pluggy | 1.6.0 | Hook-based plugin discovery and dispatch | Battle-tested (powers pytest's 1400+ plugins), supports hook specs/impls pattern that maps perfectly to SubtitleProvider ABC. Simpler than stevedore, no setuptools dependency. Drop-in Python files can use `@hookimpl` decorators. | HIGH |
| importlib (stdlib) | -- | Dynamic module loading from plugin directories | Built-in, no dependency. `importlib.import_module()` + `pkgutil.iter_modules()` for scanning `/config/plugins/` directory. | HIGH |

**Not recommended:**
- `stevedore` -- Requires setuptools entry_points, too heavy for drop-in file plugins
- `yapsy` -- Unmaintained since 2020
- Custom `__import__` hacking -- Pluggy provides the same with better error handling and testing support

**Architecture note:** Sublarr already has `_PROVIDER_CLASSES` registry + `@register_provider` decorator in `providers/__init__.py`. Pluggy extends this with a formal hook specification. Existing providers stay as built-in; pluggy adds the plugin directory scanning and validation layer.

### Translation Multi-Backend (M14)

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| deepl | >=1.21.0 | DeepL API client | Official library from DeepL SE. Supports `custom_instructions`, `style_id`, glossaries. Tested with Python 3.9-3.13. Active maintenance (latest release Feb 2026). | HIGH |
| libretranslatepy | >=2.1 | LibreTranslate API client | Lightweight client for self-hosted LibreTranslate instances. `LibreTranslateAPI` class with `translate()`, `detect()`, `languages()`. Keeps self-hosted philosophy. | MEDIUM |
| openai | >=1.60.0 | OpenAI-compatible API client | The `openai` library works with any OpenAI-compatible endpoint (LM Studio, vLLM, text-generation-webui, Ollama's OpenAI-compat mode). Set `base_url` to local server. No need for litellm or any-llm -- openai library alone covers the use case. | HIGH |
| google-cloud-translate | >=3.24.0 | Google Cloud Translation API | Official Google client. Heavy dependency tree (google-auth, grpc), so make this an **optional** extra (`pip install sublarr[google]`). Most users will use Ollama/DeepL/Libre. | MEDIUM |

**Not recommended:**
- `litellm` -- Massive dependency (proxy server, 100+ provider SDKs). Sublarr only needs the `openai` library pointed at local endpoints.
- `deep-translator` -- Unofficial wrapper, less reliable than official `deepl` library
- `any-llm` -- Unnecessary abstraction when `openai` library covers OpenAI-compat endpoints directly

**Architecture note:** Create a `TranslationBackend` ABC (like SubtitleProvider) with `translate_batch(lines, source_lang, target_lang) -> list[str]`. Existing `ollama_client.py` becomes `OllamaBackend`. Each backend is a separate module in `backend/translation_backends/`.

### Whisper Speech-to-Text (M15)

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| faster-whisper | >=1.2.1 | Local Whisper transcription | 4x faster than openai/whisper via CTranslate2. Supports CPU + GPU (CUDA/cuDNN). 8-bit quantization for memory efficiency. Models: tiny to large-v3. Actively maintained. | HIGH |
| stable-ts | >=2.17.0 | Timestamp stabilization | Improves subtitle timing accuracy from Whisper output. Used by Subgen for production subtitle generation. Wraps faster-whisper output. | MEDIUM |
| requests (existing) | 2.32.3 | Subgen API integration | No new dependency needed. Subgen exposes a REST API (`/asr` endpoint) compatible with Bazarr's Whisper provider protocol. Simple POST with file upload. | HIGH |

**Not recommended:**
- `openai-whisper` -- Original OpenAI implementation, 4x slower, more VRAM hungry
- `whisperx` -- WhisperX adds speaker diarization (irrelevant for subtitles), heavier deps
- `insanely-fast-whisper` -- CLI-focused, harder to integrate as library

**Architecture note:** Whisper integration should be **optional** (GPU-heavy). Two modes: (1) Local `faster-whisper` embedded in Sublarr container (requires CUDA runtime in Docker image), (2) External Subgen API (just HTTP calls, no GPU deps in Sublarr container). Default to Subgen API mode; local mode as opt-in for users with GPU.

**Docker consideration:** faster-whisper with GPU requires nvidia-container-toolkit. Create a separate `sublarr:gpu` Docker tag with CUDA runtime, or recommend Subgen as a sidecar container. Do NOT bloat the default image with CUDA dependencies.

### Media-Server Abstraction (M16)

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| plexapi | >=4.18.0 | Plex Media Server integration | Official Python bindings. Covers library scan, item lookup by path, metadata. Well-maintained (PDF docs updated Jan 2026). Supports direct + MyPlex auth. | HIGH |
| requests (existing) | 2.32.3 | Kodi JSON-RPC + Jellyfin/Emby API | Kodi uses JSON-RPC over HTTP. No library needed -- just POST JSON to `http://host:8080/jsonrpc`. Jellyfin client already exists in codebase. | HIGH |

**Not recommended:**
- `kodipydent` -- Inactive/unmaintained (no releases in 12+ months). Kodi's JSON-RPC is simple enough to call directly with `requests`.
- No unified abstraction library exists for Plex+Kodi+Jellyfin. Build a `MediaServerClient` ABC (same pattern as `SubtitleProvider`).

**Architecture note:** Create `backend/media_servers/` directory with `base.py` (ABC: `health_check()`, `refresh_item()`, `refresh_library()`, `search_by_path()`), then `plex.py`, `kodi.py`, `jellyfin.py`. Migrate existing `jellyfin_client.py` into this module.

### Standalone Mode (M17)

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| watchdog | >=6.0.0 | Filesystem monitoring for folder-watch | Cross-platform (Windows/macOS/Linux), Observer + EventHandler pattern. Uses OS-native APIs (inotify, FSEvents, ReadDirectoryChangesW). Debounce needed for batch file operations. | HIGH |
| tmdbv3api | >=1.9.0 | TMDB metadata lookup | Lightweight Python wrapper for TMDb API v3. Movie/TV lookup by name, ID, external IDs. Free API key available. | MEDIUM |
| requests (existing) | 2.32.3 | AniList GraphQL API + TVDB API | AniList uses GraphQL (POST JSON to `https://graphql.anilist.co`). TVDB v4 is REST. No dedicated library needed for either. | HIGH |

**Not recommended:**
- `inotify` (Linux-only) -- watchdog abstracts cross-platform differences
- `tmdbsimple` -- Less maintained than tmdbv3api
- `python-tvdb` / `tvdb_api` -- Outdated, TVDB v4 API is simple enough with `requests`

**Architecture note:** Standalone mode replaces Sonarr/Radarr as metadata source. Create `backend/metadata_providers/` with `tmdb.py`, `anilist.py`, `tvdb.py`. Folder-watch creates `wanted_items` in the same DB table used by *arr integration -- downstream pipeline stays identical.

### Event System + Script Hooks (M19)

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| blinker | >=1.9.0 | In-process signal/event dispatching | Already a Flask dependency (Flask uses blinker for signals). Zero new deps. Named signals, sender-specific subscriptions, async-compatible. | HIGH |
| subprocess (stdlib) | -- | Script hook execution | Built-in. Run user scripts on events with `subprocess.Popen()`. Pass event data as env vars or JSON stdin. Timeout + output capture. | HIGH |
| requests (existing) | 2.32.3 | Outgoing webhooks | POST event payloads to user-configured URLs. Already available. | HIGH |

**Not recommended:**
- `celery` -- Massive overkill for event dispatch. Celery is for distributed task queues, not in-process events.
- `pymitter` / `pyee` -- Unnecessary when blinker is already in the dependency tree via Flask.
- Custom event bus -- blinker already does this well.

**Architecture note:** Define signals in `backend/events.py`: `subtitle_downloaded`, `translation_completed`, `provider_search_completed`, `wanted_item_found`, etc. Hook runners subscribe to signals. Outgoing webhooks subscribe to signals. This is the same pattern Flask uses internally.

### UI Internationalization (M20)

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| i18next | >=25.8.0 | i18n framework core | Industry standard. 25M+ weekly npm downloads. Supports namespaces, interpolation, pluralization, context. React 19 compatible. | HIGH |
| react-i18next | >=16.5.0 | React bindings for i18next | Official React integration. `useTranslation()` hook, `<Trans>` component. Fixed React 19 readonly property warnings. | HIGH |
| i18next-http-backend | >=3.0.0 | Lazy-load translation files | Load JSON translation files on demand. Works with Vite's `public/` directory for language files. | HIGH |
| i18next-browser-languagedetector | >=8.0.0 | Auto-detect user language | Detects from browser settings, localStorage, querystring. Saves user preference. | HIGH |

**Not recommended:**
- `react-intl` (FormatJS) -- More opinionated, less flexible. i18next's ecosystem (plugins, extractors) is superior.
- `lingui` -- Smaller community. i18next has better tooling for extraction and management.

**Translation file structure:**
```
frontend/public/locales/
  en/translation.json
  de/translation.json
```

### OpenAPI/Swagger Documentation (M21)

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| apispec | >=6.9.0 | OpenAPI spec generation from code | Low-level, non-intrusive. Does NOT require restructuring existing Flask routes. Add docstrings + decorators to existing endpoints. Used by flask-smorest and APIFlask under the hood. | HIGH |
| apispec-webframeworks | >=1.2.0 | Flask integration for apispec | Adds `@doc` decorator pattern for existing Flask views. Generates spec from docstrings. | HIGH |

**Not recommended:**
- `flask-smorest` (0.46.2) -- Requires rewriting all routes as `MethodView` classes with marshmallow schemas. Too invasive for an existing 2600-line server.py. Would need a full API refactor.
- `APIFlask` (2.4.0) -- Replaces Flask entirely (`from apiflask import APIFlask`). Even more invasive than flask-smorest.
- `flask-openapi3` -- Requires rewriting routes with Pydantic models as parameters. Too invasive.
- `flasgger` -- Uses YAML inline in docstrings, fragile and hard to maintain.

**Architecture note:** Use `apispec` directly. Define the spec in `backend/openapi.py`, register existing endpoints with path helpers. Serve Swagger UI from `/api/docs/` using swagger-ui-dist (static files). This approach adds documentation without changing any existing endpoint code.

### Database: PostgreSQL Option + Migrations (M23)

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| SQLAlchemy | >=2.0.46 | ORM + database abstraction | Industry standard Python ORM. Supports SQLite + PostgreSQL with same models. 2.0-style API with type hints. Flask-SQLAlchemy 3.1.x integrates it cleanly. | HIGH |
| Flask-SQLAlchemy | >=3.1.2 | Flask integration for SQLAlchemy | Handles session lifecycle, engine creation, model base class. Supports SQLAlchemy 2.0+ API. | HIGH |
| alembic | >=1.18.4 | Database migrations | By the SQLAlchemy author. Autogenerate migrations from model changes. Required for any schema evolution after adding SQLAlchemy. | HIGH |
| psycopg | >=3.3.0 | PostgreSQL adapter | Psycopg 3 is the modern replacement for psycopg2. Pure Python + optional C speedups. Supports async. Released Dec 2025. | HIGH |

**Not recommended:**
- `psycopg2` / `psycopg2-binary` -- Legacy. Psycopg 3 is the successor with better API, async support, and active development.
- `asyncpg` -- Async-only. Flask is synchronous (gthread workers). Would require architectural change.
- Raw SQL migration scripts -- Alembic autogenerate is too valuable to skip.

**Migration strategy:** This is the biggest change in Phase 2. Current `database.py` uses raw sqlite3 with `_db_lock`. Migration path:
1. Define SQLAlchemy models matching existing 17 tables
2. Use Alembic to generate initial migration from models
3. Keep `_db_lock` pattern for SQLite (single-writer), use connection pooling for PostgreSQL
4. Feature flag: `SUBLARR_DATABASE_URL` -- if set, use PostgreSQL; otherwise SQLite (default)

### Caching + Job Queue (M23)

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| redis | >=7.1.1 | Redis client + caching | Official redis-py client. Supports Redis 6+. Used for provider result caching (replaces SQLite cache table) and as RQ broker. | HIGH |
| rq | >=2.6.1 | Background job queue | Simple Python job queue backed by Redis. Lightweight alternative to Celery. Workers process translation jobs, provider searches. Jobs survive restarts (persisted in Redis). | HIGH |
| Flask-Caching | >=2.3.0 | Flask cache integration | Supports Redis, memcached, simple dict backends. Decorator-based caching for expensive API calls. | MEDIUM |

**Not recommended:**
- `celery` -- Too heavy for Sublarr's use case. RQ is simpler, Redis-only (no AMQP), and sufficient for a single-instance app.
- `dramatiq` -- Good alternative to Celery but still more complex than RQ. Sublarr doesn't need distributed task routing.
- `huey` -- Less popular, smaller community than RQ.

**Architecture note:** Redis and RQ are **optional** dependencies. Default mode continues using in-process threading (current behavior). When `SUBLARR_REDIS_URL` is configured, switch to Redis caching + RQ workers. This means the Docker Compose file gets an optional `redis` service.

### Subtitle Editor (M24 - Phase 3)

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| @uiw/react-codemirror | >=4.25.4 | Code editor component | CodeMirror 6 React wrapper. Lighter than Monaco (~300KB vs ~2MB). Supports custom language modes (needed for ASS/SRT syntax highlighting). 100+ language support. Theme system matches Tailwind. | HIGH |

**Not recommended:**
- `@monaco-editor/react` (4.7.0) -- Monaco is ~2MB (loads the full VS Code editor engine). Overkill for subtitle editing. React 19 support only in RC version. Also: Vite compatibility issues with Monaco's web workers require extra configuration.
- `react-ace` -- Based on Ace editor, older architecture than CodeMirror 6.
- `textarea` -- No syntax highlighting, no line numbers, no find/replace.

**Architecture note:** Subtitle editing needs a custom CodeMirror language mode for ASS format (bracket tags `{\tag}`, line timings, style names). This is a CodeMirror 6 extension -- roughly 100-200 lines of code for basic syntax highlighting. SRT mode is simpler (numbered blocks, timestamps, text).

---

## Supporting Libraries (Cross-Cutting)

| Library | Version | Purpose | When to Use | Confidence |
|---------|---------|---------|-------------|------------|
| marshmallow | >=3.23.0 | Schema serialization/validation | If using apispec for OpenAPI (apispec natively supports marshmallow schemas). Also useful for validating plugin configs. | MEDIUM |
| pydantic (existing) | 2.10.6 | Config validation | Already in use. Extend for translation backend configs, plugin manifests. | HIGH |
| click (existing via Flask) | -- | CLI commands | Flask includes click. Add `flask translate`, `flask plugins`, `flask db` CLI commands. | HIGH |
| prometheus_client (existing) | -- | Metrics | Already optional dep. Extend with new metrics for translation backends, Whisper jobs, plugin activity. | HIGH |

---

## Alternatives Considered

| Category | Recommended | Alternative | Why Not |
|----------|-------------|-------------|---------|
| Plugin system | pluggy 1.6.0 | stevedore | Requires setuptools entry_points; too formal for drop-in files |
| Plugin system | pluggy 1.6.0 | Custom importlib | Pluggy adds hook validation, ordering, error handling for free |
| Translation multi-backend | openai lib | litellm | litellm is 50+ MB with proxy server; openai lib alone covers compat endpoints |
| Translation multi-backend | deepl (official) | deep-translator | Official lib has glossary support, custom_instructions, maintained by DeepL |
| Whisper | faster-whisper | openai-whisper | 4x slower, more VRAM, no CTranslate2 optimizations |
| Plex integration | plexapi | custom requests | plexapi handles auth flow, MyPlex, tokens; non-trivial to replicate |
| Kodi integration | raw requests | kodipydent | kodipydent unmaintained; JSON-RPC is trivial with requests |
| Media server abstraction | custom ABC | no unified lib | No library exists that wraps Plex+Kodi+Jellyfin. Must build abstraction. |
| File watching | watchdog 6.0.0 | inotify | watchdog is cross-platform (important for Docker + native dev) |
| Event system | blinker 1.9.0 | custom EventEmitter | blinker already in Flask deps; adding custom would duplicate |
| OpenAPI | apispec 6.9.0 | flask-smorest | flask-smorest requires rewriting all routes as MethodView classes |
| OpenAPI | apispec 6.9.0 | APIFlask | APIFlask replaces Flask import entirely; too invasive |
| Database ORM | SQLAlchemy 2.0 | peewee | SQLAlchemy is industry standard, better PostgreSQL support, alembic |
| Database ORM | SQLAlchemy 2.0 | tortoise-orm | Async-only, Flask is sync |
| PostgreSQL driver | psycopg 3.3 | psycopg2 | psycopg2 is legacy; psycopg3 has better API and async support |
| Job queue | rq 2.6.1 | celery | Celery is too heavy; RQ matches Sublarr's single-instance model |
| Subtitle editor | @uiw/react-codemirror | @monaco-editor/react | Monaco is 2MB+, Vite worker issues, React 19 only in RC |
| i18n | react-i18next | react-intl | i18next has superior plugin ecosystem and extraction tooling |
| Metadata (TMDB) | tmdbv3api | tmdbsimple | tmdbv3api more actively maintained |

---

## Installation Plan

### Phase 2 Core (M13-M18)

```bash
# Backend - Plugin System + Translation Backends
pip install pluggy>=1.6.0
pip install deepl>=1.21.0
pip install openai>=1.60.0

# Backend - Whisper (optional, GPU image only)
pip install faster-whisper>=1.2.1
pip install stable-ts>=2.17.0

# Backend - Media Servers
pip install plexapi>=4.18.0

# Backend - Standalone Mode
pip install watchdog>=6.0.0
pip install tmdbv3api>=1.9.0

# Frontend - i18n
npm install i18next react-i18next i18next-http-backend i18next-browser-languagedetector
```

### Phase 2 Infrastructure (M19-M23)

```bash
# Backend - OpenAPI
pip install apispec>=6.9.0
pip install apispec-webframeworks>=1.2.0
pip install marshmallow>=3.23.0

# Backend - Database upgrade
pip install SQLAlchemy>=2.0.46
pip install Flask-SQLAlchemy>=3.1.2
pip install alembic>=1.18.4
pip install psycopg[binary]>=3.3.0  # optional: PostgreSQL support

# Backend - Caching + Job Queue (optional)
pip install redis>=7.1.1
pip install rq>=2.6.1
pip install Flask-Caching>=2.3.0

# Backend - Translation (optional cloud providers)
pip install google-cloud-translate>=3.24.0  # optional: Google Cloud
pip install libretranslatepy>=2.1            # optional: LibreTranslate
```

### Phase 3 (M24+)

```bash
# Frontend - Subtitle Editor
npm install @uiw/react-codemirror @codemirror/lang-json
```

---

## Docker Image Impact

### Default Image (sublarr:latest)

New system packages: **none** (all Python/npm packages)

Estimated size increase:
- pluggy, deepl, openai, watchdog, tmdbv3api, blinker: ~15MB
- SQLAlchemy + alembic + psycopg: ~25MB
- plexapi: ~5MB
- i18next frontend bundle: ~50KB gzipped
- **Total: ~45MB increase** (current image ~450MB estimated)

### GPU Image (sublarr:gpu) -- New tag

Additional packages: CUDA runtime, cuDNN, faster-whisper, stable-ts
Estimated size: **~2.5GB additional** (CUDA runtime alone is ~1.8GB)

Recommendation: Keep GPU image as separate Dockerfile (`Dockerfile.gpu`). Most users should use Subgen as a sidecar container instead.

### Optional Dependencies Strategy

Use Python extras for optional heavy dependencies:

```toml
# pyproject.toml
[project.optional-dependencies]
google = ["google-cloud-translate>=3.24.0"]
whisper = ["faster-whisper>=1.2.1", "stable-ts>=2.17.0"]
postgres = ["psycopg[binary]>=3.3.0"]
redis = ["redis>=7.1.1", "rq>=2.6.1", "Flask-Caching>=2.3.0"]
all = ["sublarr[google,postgres,redis]"]
```

---

## Version Compatibility Matrix

| Library | Min Python | Flask 3.1 | SQLAlchemy 2.0 | Notes |
|---------|-----------|-----------|----------------|-------|
| pluggy 1.6.0 | 3.9 | N/A | N/A | Pure Python, no framework deps |
| deepl >=1.21 | 3.9 | N/A | N/A | Uses requests >=2.32.4 |
| openai >=1.60 | 3.9 | N/A | N/A | httpx-based (separate from requests) |
| faster-whisper 1.2.1 | 3.9 | N/A | N/A | CTranslate2 backend |
| plexapi 4.18.0 | 3.8 | N/A | N/A | Uses requests |
| watchdog 6.0.0 | 3.9 | N/A | N/A | OS-native file events |
| tmdbv3api 1.9.0 | 3.6 | N/A | N/A | Uses requests |
| blinker 1.9.0 | 3.9 | Yes (dep) | N/A | Flask dependency |
| apispec 6.9.0 | 3.9 | Via plugin | N/A | Framework-agnostic |
| SQLAlchemy 2.0.46 | 3.7 | Via ext | Yes | Core ORM |
| Flask-SQLAlchemy 3.1.2 | 3.8 | Yes | Yes | Requires SA 2.0.16+ |
| alembic 1.18.4 | 3.9 | N/A | Yes | Requires SA 1.4+ |
| psycopg 3.3 | 3.8 | N/A | Yes | Via SA dialect |
| redis 7.1.1 | 3.10 | N/A | N/A | Raises min Python to 3.10 if used |
| rq 2.6.1 | 3.9 | N/A | N/A | Uses redis-py |
| react-i18next 16.5 | N/A | N/A | N/A | React 19 compatible |
| @uiw/react-codemirror 4.25 | N/A | N/A | N/A | CodeMirror 6, React 18/19 |

**Python version note:** redis-py 7.1.x requires Python 3.10+. Since Sublarr uses Python 3.11-slim as Docker base, this is fine for production. But document that redis support requires Python 3.10+ for developers running natively.

---

## Sources

### Verified (HIGH confidence)
- [pluggy PyPI](https://pypi.org/project/pluggy/) -- v1.6.0, May 2025
- [pluggy GitHub](https://github.com/pytest-dev/pluggy) -- MIT license, Python 3.9+
- [deepl PyPI](https://pypi.org/project/deepl/) -- Official DeepL library, Feb 2026
- [faster-whisper PyPI](https://pypi.org/project/faster-whisper/) -- v1.2.1, Oct 2025
- [faster-whisper GitHub](https://github.com/SYSTRAN/faster-whisper) -- CTranslate2 backend
- [PlexAPI PyPI](https://pypi.org/project/PlexAPI/) -- v4.18.0
- [watchdog PyPI](https://pypi.org/project/watchdog/) -- v6.0.0, Nov 2025
- [SQLAlchemy PyPI](https://pypi.org/project/SQLAlchemy/) -- v2.0.46, Jan 2026
- [Flask-SQLAlchemy docs](https://flask-sqlalchemy.readthedocs.io/en/stable/) -- v3.1.x
- [alembic PyPI](https://pypi.org/project/alembic/) -- v1.18.4
- [psycopg docs](https://www.psycopg.org/psycopg3/) -- v3.3, Dec 2025
- [redis-py PyPI](https://pypi.org/project/redis/) -- v7.1.1, Feb 2026
- [RQ PyPI](https://pypi.org/project/rq/) -- v2.6.1
- [apispec docs](https://apispec.readthedocs.io/) -- v6.9.0
- [react-i18next npm](https://www.npmjs.com/package/react-i18next) -- v16.5.4
- [i18next npm](https://www.npmjs.com/package/i18next) -- v25.8.7
- [@uiw/react-codemirror npm](https://www.npmjs.com/package/@uiw/react-codemirror) -- v4.25.4
- [blinker PyPI](https://pypi.org/project/blinker/) -- v1.9.0, Flask dependency
- [tmdbv3api PyPI](https://pypi.org/project/tmdbv3api/) -- v1.9.0
- [google-cloud-translate PyPI](https://pypi.org/project/google-cloud-translate/) -- v3.24.0

### Community-verified (MEDIUM confidence)
- [Subgen GitHub](https://github.com/McCloudS/subgen) -- Whisper provider for Bazarr, uses faster-whisper + stable-ts
- [LibreTranslate-py GitHub](https://github.com/argosopentech/LibreTranslate-py) -- Python bindings
- [kodipydent GitHub](https://github.com/haikuginger/kodipydent) -- Confirmed inactive/unmaintained
- [Flask signals docs](https://flask.palletsprojects.com/en/stable/signals/) -- blinker integration
- [apispec-webframeworks GitHub](https://github.com/marshmallow-code/apispec-webframeworks) -- Flask plugin

---

*Stack research: 2026-02-15*
