# Codebase Structure

**Analysis Date:** 2026-02-15

## Directory Layout

```
sublarr/
├── backend/                # Flask API + Translation Engine (Python 3.11)
│   ├── providers/          # Subtitle provider implementations
│   ├── tests/              # Pytest unit + integration tests
│   ├── server.py           # Flask app with Blueprint API (2618 lines)
│   ├── database.py         # SQLite with 17 tables (2153 lines)
│   ├── translator.py       # Three-case translation pipeline (885 lines)
│   ├── config.py           # Pydantic Settings
│   └── *.py                # Domain logic modules (22 total)
├── frontend/               # React 19 + TypeScript + Tailwind v4 SPA
│   ├── src/
│   │   ├── api/            # Axios API client + types
│   │   ├── components/     # Layout + shared components
│   │   ├── hooks/          # React Query + WebSocket hooks
│   │   ├── pages/          # Route pages (Dashboard, Wanted, Settings, etc.)
│   │   ├── lib/            # Types, utils
│   │   └── test/           # Vitest unit tests
│   ├── e2e/                # Playwright E2E tests
│   ├── dist/               # Production build output (served by Flask)
│   └── package.json        # Frontend dependencies
├── docs/                   # Markdown documentation
├── scripts/                # Setup scripts (PowerShell, Bash)
├── unraid/                 # Unraid template
├── .planning/codebase/     # GSD codebase analysis docs
├── Dockerfile              # Multi-stage: Node 20 → Python 3.11
├── docker-compose.yml      # Production deployment config
├── package.json            # Root scripts (dev, build)
└── .env.example            # Environment variable template
```

## Directory Purposes

**backend/**
- Purpose: Flask API server, translation orchestration, provider system, database
- Contains: 22 Python modules (core logic), providers/ subpackage, tests/ directory
- Key files:
  - `server.py` — All `/api/v1/` endpoints, WebSocket, SPA routing
  - `database.py` — SQLite schema (17 tables) with thread-safe access
  - `translator.py` — Three-case translation pipeline
  - `config.py` — Pydantic Settings with env var support
  - `providers/__init__.py` — ProviderManager (parallel search, scoring)

**backend/providers/**
- Purpose: Subtitle provider implementations (AnimeTosho, Jimaku, OpenSubtitles, SubDL)
- Contains:
  - `base.py` — SubtitleProvider ABC, VideoQuery, SubtitleResult, scoring algorithm
  - `animetosho.py`, `jimaku.py`, `opensubtitles.py`, `subdl.py` — Provider classes
  - `http_session.py` — RetryingSession with rate limiting
- Pattern: All providers inherit from SubtitleProvider, registered via decorator

**backend/tests/**
- Purpose: Pytest test suite (unit, integration, performance)
- Contains:
  - `test_*.py` — Unit tests for server, database, config, auth, ass_utils
  - `integration/` — Integration tests (provider search, translation end-to-end)
  - `performance/` — Load tests (Locust)
  - `fixtures/` — Test data (sample subtitles, JSON payloads)
  - `conftest.py` — Pytest fixtures (test database, mock config)

**frontend/**
- Purpose: React 19 SPA with Vite build system
- Contains: `src/` (TypeScript source), `dist/` (build output), `e2e/` (Playwright tests), `public/` (static assets)
- Build: Vite → `dist/` → copied to Docker image as `backend/static/`

**frontend/src/api/**
- Purpose: API client and TypeScript type definitions
- Contains:
  - `client.ts` — Axios instance with API key interceptor + all API functions (440 lines)
  - Typed functions for every `/api/v1/` endpoint

**frontend/src/components/layout/**
- Purpose: Layout components (Sidebar, Header)
- Contains:
  - `Sidebar.tsx` — Navigation sidebar (*arr-style teal theme, lucide-react icons)

**frontend/src/components/shared/**
- Purpose: Reusable UI components
- Contains:
  - `StatusBadge.tsx` — Status indicators (queued, processing, success, failed)
  - `ProgressBar.tsx` — Progress visualization
  - `Toast.tsx` — Toast notifications
  - `ErrorBoundary.tsx` — React error boundary

**frontend/src/hooks/**
- Purpose: Custom React hooks
- Contains:
  - `useApi.ts` — TanStack Query wrappers for API calls
  - `useWebSocket.ts` — Socket.IO connection with event handlers

**frontend/src/pages/**
- Purpose: Route pages (one component per route)
- Contains:
  - `Dashboard.tsx` — Stats overview, recent jobs
  - `Activity.tsx` — Translation job queue/history
  - `Wanted.tsx` — Missing subtitle items with search actions
  - `Queue.tsx` — Active translation queue
  - `Library.tsx` — Sonarr/Radarr series listing
  - `SeriesDetail.tsx` — Per-series episodes with subtitle status
  - `Settings.tsx` — Configuration UI (Ollama, providers, *arr integrations)
  - `Logs.tsx` — Real-time log viewer (WebSocket)
  - `History.tsx` — Download history
  - `Blacklist.tsx` — Blacklisted subtitles
  - `Onboarding.tsx` — Initial setup wizard
  - `NotFound.tsx` — 404 page

**frontend/src/lib/**
- Purpose: Shared utilities and types
- Contains:
  - `types.ts` — TypeScript interfaces for all API responses
  - `utils.ts` — Helper functions (date formatting, status mapping)

**docs/**
- Purpose: Project documentation (Markdown)
- Contains:
  - `API.md` — API endpoint reference
  - `ARCHITECTURE.md` — High-level architecture overview
  - `PROVIDERS.md` — Provider system guide
  - `CONTRIBUTING.md` — Contribution guidelines
  - `TROUBLESHOOTING.md` — Common issues and solutions

**scripts/**
- Purpose: Development setup automation
- Contains:
  - `setup-dev.ps1` — Windows PowerShell setup (Python venv, npm install, .env creation)
  - `setup-dev.sh` — Linux/Mac bash setup script

**unraid/**
- Purpose: Unraid Community Applications template
- Contains: XML template for Unraid deployment

**.planning/codebase/**
- Purpose: GSD (Get Stuff Done) codebase analysis documents
- Contains: This file (STRUCTURE.md), ARCHITECTURE.md, future analysis docs
- Used by: `/gsd:plan-phase` and `/gsd:execute-phase` commands

## Key File Locations

**Entry Points:**
- `backend/server.py` — Flask app with Blueprint API + WebSocket + SPA routing
- `frontend/src/main.tsx` — React app entry point (ReactDOM.render)
- `frontend/src/App.tsx` — React Router setup + QueryClient provider
- `Dockerfile` — Multi-stage build (Node → Python)
- `docker-compose.yml` — Production deployment (ports, volumes, env)

**Configuration:**
- `.env` — Environment variables (not committed, use `.env.example`)
- `backend/config.py` — Pydantic Settings schema
- `backend/pytest.ini` — Pytest configuration
- `frontend/vite.config.ts` — Vite build config (proxy `/api/v1/` to `:5765`)
- `frontend/tsconfig.json` — TypeScript compiler options
- `frontend/tailwind.config.js` — Tailwind CSS v4 config

**Core Logic:**
- `backend/translator.py` — Translation pipeline (extract → translate → reassemble)
- `backend/providers/__init__.py` — ProviderManager (search, score, download)
- `backend/wanted_scanner.py` — Scheduled scan for missing subtitles
- `backend/wanted_search.py` — Provider search for wanted items
- `backend/ollama_client.py` — LLM translation via Ollama
- `backend/ass_utils.py` — ASS style classification, tag extraction/restoration
- `backend/upgrade_scorer.py` — SRT→ASS upgrade decision logic

**Database:**
- `backend/database.py` — Schema definition (17 tables), all CRUD functions
- `backend/database_backup.py` — SQLite backup API with rotation
- `backend/database_health.py` — Integrity check, vacuum, stats

**Resilience:**
- `backend/error_handler.py` — SublarrError hierarchy, Flask error handlers
- `backend/circuit_breaker.py` — Circuit breaker pattern for providers
- `backend/transaction_manager.py` — Database transaction context manager
- `backend/metrics.py` — Prometheus metrics (graceful degradation)

**External Integrations:**
- `backend/sonarr_client.py` — Sonarr v3 API client (series, episodes, rescan)
- `backend/radarr_client.py` — Radarr v3 API client (movies)
- `backend/jellyfin_client.py` — Jellyfin/Emby library refresh
- `backend/anidb_mapper.py` — AniDB episode ID mapping
- `backend/notifier.py` — Apprise notifications (push, email, Discord, etc.)
- `backend/hi_remover.py` — Hearing-impaired tag removal

**Testing:**
- `backend/tests/test_*.py` — Pytest unit tests
- `backend/tests/integration/` — Integration tests (requires live Ollama)
- `backend/tests/performance/` — Locust performance tests
- `frontend/src/test/*.test.ts(x)` — Vitest component/unit tests
- `frontend/e2e/*.spec.ts` — Playwright E2E tests

## Naming Conventions

**Files:**
- Backend: `snake_case.py` (e.g., `wanted_scanner.py`, `ollama_client.py`)
- Frontend: `PascalCase.tsx` for components/pages (e.g., `Dashboard.tsx`, `StatusBadge.tsx`)
- Frontend: `camelCase.ts` for non-component files (e.g., `client.ts`, `utils.ts`)
- Tests: `test_*.py` (backend), `*.test.ts(x)` (frontend)
- Config: `lowercase-hyphen` (e.g., `docker-compose.yml`, `pytest.ini`)

**Directories:**
- Backend: `snake_case` (e.g., `providers`, `tests`)
- Frontend: `camelCase` (e.g., `components`, `hooks`) or `lowercase` (e.g., `pages`, `lib`)

**Python Code:**
- Modules: `snake_case` (e.g., `translator.py`)
- Classes: `PascalCase` (e.g., `SubtitleProvider`, `CircuitBreaker`)
- Functions: `snake_case` (e.g., `translate_file()`, `get_provider_manager()`)
- Constants: `UPPER_SNAKE_CASE` (e.g., `REQUEST_TIMEOUT`, `MIN_FREE_SPACE_MB`)
- Private: `_leading_underscore` (e.g., `_db_lock`, `_extract_series_id()`)

**TypeScript Code:**
- Components: `PascalCase` (e.g., `Dashboard`, `StatusBadge`)
- Functions: `camelCase` (e.g., `getJobs`, `translateFile`)
- Interfaces/Types: `PascalCase` (e.g., `HealthStatus`, `Job`, `VideoQuery`)
- Hooks: `use` prefix + `camelCase` (e.g., `useWebSocket`, `useApi`)
- Constants: `UPPER_SNAKE_CASE` (rare) or `camelCase` (common)

**Database Tables:**
- `snake_case` with descriptive names (e.g., `wanted_items`, `language_profiles`, `subtitle_downloads`)
- Join tables: `entity1_entity2` (e.g., `series_language_profiles`)

**API Endpoints:**
- Pattern: `/api/v1/{resource}[/{id}][/{action}]`
- Examples:
  - `GET /api/v1/jobs` — List jobs
  - `GET /api/v1/status/{job_id}` — Get job status
  - `POST /api/v1/wanted/{id}/search` — Search for wanted item
  - `POST /api/v1/providers/test/{name}` — Test provider

## Where to Add New Code

**New Subtitle Provider:**
- Primary code: `backend/providers/{provider_name}.py`
- Inherit from: `backend/providers/base.py::SubtitleProvider`
- Register: Use `@register_provider` decorator
- Tests: `backend/tests/integration/test_provider_{name}.py`

**New API Endpoint:**
- Implementation: `backend/server.py` (add to existing Blueprint)
- Pattern: Define route with Blueprint decorator `@api_bp.route('/path', methods=['GET'])`
- Frontend client: Add typed function to `frontend/src/api/client.ts`
- Frontend types: Add response type to `frontend/src/lib/types.ts`

**New UI Page:**
- Primary code: `frontend/src/pages/{PageName}.tsx`
- Add route: `frontend/src/App.tsx` (add `<Route path="/page" element={<PageName />} />`)
- Navigation: `frontend/src/components/layout/Sidebar.tsx` (add menu item)
- API integration: Use `useApi` hook from `frontend/src/hooks/useApi.ts`

**New Translation Feature:**
- Core logic: `backend/translator.py` (modify pipeline) or new module in `backend/`
- If new module: Import into `backend/server.py` and integrate into existing endpoints
- Configuration: Add setting to `backend/config.py::Settings` class
- Database: Add table/column in `backend/database.py::SCHEMA`

**New Configuration Option:**
- Backend: Add field to `backend/config.py::Settings` (Pydantic will auto-generate env var `SUBLARR_{FIELD}`)
- Frontend UI: Add form field to `frontend/src/pages/Settings.tsx`
- Runtime override: Save to `config_entries` table via `save_config_entry()` in `backend/database.py`

**New WebSocket Event:**
- Backend: Emit in relevant module via `socketio.emit('event_name', data)` (import from `backend/server.py`)
- Frontend: Add handler to `frontend/src/hooks/useWebSocket.ts` (add to `events` array)
- Frontend consumer: Add callback prop to `useWebSocket()` call (e.g., `onNewEvent`)

**New External Integration (*arr, Media Server):**
- Client: Create `backend/{service}_client.py` (e.g., `plex_client.py`)
- Pattern: Follow `sonarr_client.py` structure (client class, singleton getter, multi-instance support)
- Configuration: Add URL/API key fields to `backend/config.py::Settings`
- Frontend settings: Add section to `frontend/src/pages/Settings.tsx`

**New Database Table:**
- Schema: Add `CREATE TABLE` in `backend/database.py::SCHEMA`
- CRUD functions: Add to `backend/database.py` (e.g., `get_items()`, `add_item()`, `update_item()`)
- Thread safety: Always use `with _db_lock:` around database operations
- Tests: Add tests to `backend/tests/test_database.py`

**Utilities:**
- Backend shared helpers: `backend/{module_name}_utils.py` (e.g., `ass_utils.py`)
- Frontend shared helpers: `frontend/src/lib/utils.ts`
- Type definitions: `frontend/src/lib/types.ts`

**New Test Suite:**
- Backend unit tests: `backend/tests/test_{module}.py`
- Backend integration tests: `backend/tests/integration/test_{feature}.py`
- Frontend component tests: `frontend/src/test/{Component}.test.tsx`
- Frontend E2E tests: `frontend/e2e/{feature}.spec.ts`

## Special Directories

**backend/__pycache__/**
- Purpose: Python bytecode cache
- Generated: Yes (automatically by Python interpreter)
- Committed: No (in `.gitignore`)

**frontend/node_modules/**
- Purpose: npm package dependencies
- Generated: Yes (`npm install`)
- Committed: No (in `.gitignore`)

**frontend/dist/**
- Purpose: Vite production build output
- Generated: Yes (`npm run build`)
- Committed: No (copied to Docker image during build)

**backend/static/**
- Purpose: Served React SPA (in Docker only)
- Generated: Yes (Dockerfile copies `frontend/dist/` here)
- Committed: No (only exists in Docker image)

**.planning/**
- Purpose: GSD codebase analysis and planning documents
- Generated: Manually by `/gsd:map-codebase` command
- Committed: Yes (for future reference)

**backend/tests/fixtures/**
- Purpose: Test data (sample subtitles, mock API responses)
- Generated: Manually
- Committed: Yes

**frontend/e2e/**
- Purpose: Playwright end-to-end tests
- Generated: Manually
- Committed: Yes

**unraid/**
- Purpose: Unraid Community Applications template
- Generated: Manually
- Committed: Yes

**scripts/**
- Purpose: Development environment setup scripts
- Generated: Manually
- Committed: Yes

**docs/**
- Purpose: Project documentation
- Generated: Manually
- Committed: Yes

**/config/** (runtime only, Docker volume)
- Purpose: Runtime data (database, logs, backups)
- Generated: At runtime by application
- Committed: No (Docker volume mount)
- Contents: `sublarr.db`, `sublarr.log`, `backups/*.db`

**/media/** (runtime only, Docker volume)
- Purpose: Media files (MKV with embedded subs, output subtitles)
- Generated: External (Sonarr/Radarr downloads)
- Committed: No (Docker volume mount)

---

*Structure analysis: 2026-02-15*
