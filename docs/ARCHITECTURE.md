# Architecture Overview

Sublarr is a standalone subtitle manager and translator built with a modern web stack. This document describes the system architecture, data flow, and key components.

## High-Level Architecture

```
Frontend (React + TypeScript)
    |
    | HTTP/WebSocket
    v
Backend (Flask + Flask-SocketIO)
    |
    +-- SQLite Database (WAL mode)
    +-- Provider System (AnimeTosho, Jimaku, OpenSubtitles, SubDL)
    +-- Translation Pipeline (Ollama LLM)
    +-- Scheduler (Wanted Scanner, Upgrades)
    |
    v
External Services
    +-- Sonarr/Radarr (webhooks, API)
    +-- Jellyfin/Emby (library refresh)
    +-- Ollama (LLM translation)
```

## Backend Architecture

### Core Components

**Flask Application (app.py)**
- Blueprint-based routing under `/api/v1/`
- Flask-SocketIO for real-time WebSocket updates
- Gunicorn WSGI server (2 workers, 4 threads, 300s timeout)
- Optional API key authentication via `auth.py`
- Health check endpoint (no auth required)

**Configuration System (config.py)**
- Pydantic Settings for type-safe configuration
- Environment variables with `SUBLARR_` prefix
- Runtime config overrides stored in `config_entries` table
- Validation on startup and config updates
- Secrets never exposed in API responses

**Database Layer (db/)**
- SQLite with WAL (Write-Ahead Logging) mode
- Connection pooling with thread-local storage
- Schema migrations via version tracking

#### Database Tables

| Table | Purpose |
|-------|---------|
| `jobs` | Translation job tracking, status, statistics, error messages |
| `daily_stats` | Aggregated daily statistics for dashboard |
| `config_entries` | Runtime configuration overrides (key-value) |
| `provider_cache` | Cached subtitle search results (TTL-based expiration) |
| `subtitle_downloads` | Download history per provider (for stats) |
| `language_profiles` | Multi-language profile definitions (name, source, targets) |
| `series_language_profiles` | Profile assignment per Sonarr series |
| `movie_language_profiles` | Profile assignment per Radarr movie |
| `wanted_items` | Missing subtitles queue (episode/movie, language, status) |
| `blacklist_entries` | Rejected subtitle downloads (provider, hash, reason) |
| `download_history` | Subtitle download audit log |
| `glossary_entries` | User-defined translation glossary (term pairs) |
| `prompt_presets` | Saved Ollama prompt templates |

### Provider System (providers/)

**Architecture Pattern**
- Singleton `ProviderManager` orchestrates all providers
- Abstract base class `SubtitleProvider` defines interface
- Shared `RetryingSession` for HTTP requests with rate-limit handling
- Priority-based search with configurable provider order

**Provider Registry**
```python
PROVIDER_REGISTRY = {
    "animetosho": AnimeToshoProvider,
    "jimaku": JimakuProvider,
    "opensubtitles": OpenSubtitlesProvider,
    "subdl": SubDLProvider,
}
```

**Search Flow**
1. User/System requests subtitles for a video file
2. `ProviderManager.search()` queries all enabled providers in parallel
3. Results scored using weighted algorithm (see PROVIDERS.md)
4. Best match selected (ASS format gets +50 bonus)
5. Subtitle downloaded and cached
6. Downloaded file processed (extracted from ZIP/RAR/XZ if needed)

**Provider Interface**
```python
class SubtitleProvider(ABC):
    @abstractmethod
    def search(self, query: VideoQuery) -> List[SubtitleResult]:
        pass

    @abstractmethod
    def download(self, result: SubtitleResult, dest: Path) -> Path:
        pass

    @abstractmethod
    def health_check(self) -> bool:
        pass
```

**Cache Invalidation**
- Config changes call `invalidate_manager()` to recreate provider instances
- Provider cache entries have TTL (default 1 hour)
- Manual cache clear endpoint available

### Translation Pipeline (translator.py)

**Three-Stage Priority Chain**

The translation system uses a cascading priority system to minimize unnecessary work and prefer high-quality formats:

**Case A: Target Subtitle Exists**
- Check if target language ASS or SRT already exists
- Action: Skip translation
- Reason: Already have what we need

**Case B: Target SRT Exists, Upgrade Attempt**
- Have target SRT, want to upgrade to ASS
- B1: Search providers for target language ASS
- B2: If source ASS embedded, translate to target ASS
- B3: No upgrade possible, keep existing SRT
- Reason: ASS format preferred for anime (styling, positioning)

**Case C: No Target Subtitle, Full Pipeline**
- C1: Source ASS embedded -> translate to target ASS
- C2: Source SRT (embedded/external) -> translate to target SRT
- C3: Search providers for source subtitle -> download -> translate
- C4: Nothing found -> fail with detailed error
- Reason: Build target subtitle from any available source

**ASS Translation Process (ass_utils.py)**
- Parse ASS file structure (Styles, Events sections)
- Classify styles: Dialog vs Signs/Songs
  - Dialog styles: >80% plain dialogue events -> translate
  - Signs/Songs styles: >80% positioned/complex events -> preserve
- Extract dialogue lines, preserve formatting codes
- Send to Ollama with style-aware prompt
- Inject translated text back into ASS structure
- Update Language field in Script Info section

**SRT Translation Process**
- Parse SRT format (sequence number, timestamps, text)
- Extract text blocks, preserve timing
- Send to Ollama with context prompt
- Reconstruct SRT with translated text

**Glossary Integration**
- User-defined term pairs loaded from database
- Injected into Ollama prompt template
- Applied during translation for consistency

### Wanted System (wanted_scanner.py, wanted_search.py)

**Scanner Architecture**
- Periodic task (default: every 6 hours)
- Queries Sonarr/Radarr for all series/movies with Sublarr tag
- For each item:
  - Check language profile assignment
  - Iterate through target languages
  - Scan media directory for existing subtitles
  - Create wanted_items entry if missing
- Tracks scan history, monitors for new episodes

**Search & Process Flow**
1. Wanted item created by scanner
2. Background task or manual trigger calls `wanted_search.py`
3. Build `VideoQuery` from item metadata
4. Search providers for target AND source languages
5. If target found: download -> save
6. If only source found: download -> translate -> save
7. Update wanted_item status (COMPLETED/FAILED)
8. Notify Jellyfin to refresh library
9. Record download in history

**Batch Operations**
- WebSocket progress updates during batch search
- Parallel processing with configurable concurrency
- Dry-run mode for testing queries

### API Endpoints

All endpoints prefixed with `/api/v1/`

**Request/Response Format**
- JSON payloads
- Standard HTTP status codes
- Error responses: `{"error": "message", "details": {...}}`
- Success responses: `{"success": true, "data": {...}}`

**Authentication**
- Optional API key via `SUBLARR_API_KEY` env var
- Header: `X-Api-Key: <key>`
- Query param: `?apikey=<key>`
- Exempt endpoints: `/health`, webhooks

**Real-Time Updates (WebSocket)**
- Namespace: `/socket.io/`
- Events:
  - `job_update`: Translation job status changes
  - `batch_progress`: Batch operation progress
  - `wanted_batch_progress`: Wanted search batch progress
  - `scan_progress`: Library scan progress

### Integration Clients

**Sonarr Client (sonarr_client.py)**
- API v3 calls with `X-Api-Key` header
- Fetch series list, episode details, file paths
- Tag-based filtering (only series with Sublarr tag)
- Parse video file metadata (episode number, season, release group)

**Radarr Client (radarr_client.py)**
- API v3 calls with `X-Api-Key` header
- Fetch movie list, file paths, quality profiles
- Tag-based filtering
- Parse video file metadata (year, resolution, source)

**Jellyfin Client (jellyfin_client.py)**
- Library scan trigger after new subtitles added
- Token-based auth: `X-MediaBrowser-Token` header
- Graceful fallback if Jellyfin not configured

**Ollama Client (ollama_client.py)**
- HTTP API calls to Ollama server
- Dynamic prompt template from config
- Streaming response support (for future UI feature)
- Model selection via `SUBLARR_OLLAMA_MODEL`
- Glossary injection into system prompt

### Scheduler & Background Tasks

**APScheduler Integration**
- Background scheduler runs in main process
- Jobs configured via environment variables

**Scheduled Jobs**
1. **Wanted Scanner**: Every N hours (configurable)
   - Scans Sonarr/Radarr for missing subtitles
   - Creates wanted_items entries
2. **Upgrade Scanner**: Daily (optional)
   - Scans for SRT subtitles within upgrade window
   - Attempts upgrade to ASS format
3. **Cache Cleanup**: Daily
   - Removes expired provider cache entries
   - Prunes old job history (configurable retention)

## Frontend Architecture

### Technology Stack
- React 18 (functional components, hooks)
- TypeScript (strict mode)
- Tailwind CSS (utility-first styling)
- React Router v6 (client-side routing)
- TanStack Query (React Query) (server state management)
- Socket.IO Client (real-time updates)
- Vite (development server, HMR, bundler)

### Directory Structure
```
frontend/src/
├── App.tsx                 # Router, QueryClient provider
├── main.tsx                # Entry point
├── index.css               # Tailwind imports, arr-style CSS variables
├── api/
│   └── client.ts           # Axios instance, type-safe API calls
├── hooks/
│   ├── useApi.ts           # React Query hooks for all endpoints
│   └── useWebSocket.ts     # Socket.IO integration, event handlers
├── components/
│   ├── layout/
│   │   └── Sidebar.tsx     # Navigation, teal arr-style theme
│   └── shared/
│       ├── StatusBadge.tsx # Color-coded status indicators
│       ├── ProgressBar.tsx # Visual progress component
│       ├── Toast.tsx       # Notification system
│       └── ErrorBoundary.tsx # React error handling
└── pages/
    ├── Dashboard.tsx       # Stats overview, recent activity
    ├── Activity.tsx        # Live job monitoring, WebSocket updates
    ├── Library.tsx         # Series/movie list, subtitle status
    ├── Wanted.tsx          # Missing subtitles queue
    ├── History.tsx         # Download/translation history
    ├── Blacklist.tsx       # Rejected subtitles
    ├── Settings.tsx        # Config editor, provider management
    ├── Logs.tsx            # Paginated log viewer
    └── NotFound.tsx        # 404 page
```

### State Management

**Server State (React Query)**
- All API calls wrapped in `useQuery` or `useMutation` hooks
- Automatic caching, refetching, error handling
- Optimistic updates for instant UI feedback
- Query invalidation on mutations (e.g., config update -> refetch config)

**UI State (React Hooks)**
- Local component state with `useState`
- Form state with controlled inputs
- Modal/dialog state with `useReducer` for complex flows

**Real-Time State (Socket.IO)**
- `useWebSocket` hook connects to backend
- Listens for events: job_update, batch_progress, etc.
- Invalidates React Query cache on relevant events
- Automatic reconnection on disconnect

### Routing

**Routes**
- `/` - Dashboard
- `/activity` - Active jobs
- `/library` - Series/movie list
- `/wanted` - Missing subtitles
- `/history` - Download history
- `/blacklist` - Rejected subtitles
- `/settings` - Configuration
- `/logs` - System logs
- `*` - 404 Not Found

**Navigation**
- Sidebar with active route highlighting
- Breadcrumbs for deep navigation (future)
- Back button for detail views

### Styling

**Tailwind Configuration**
- Custom color palette (teal primary: #1DB8D4)
- Dark mode support (prefers-color-scheme)
- Responsive breakpoints (sm, md, lg, xl)
- Custom animations for loading states

**CSS Variables (arr-style)**
```css
:root {
  --color-primary: #1DB8D4;
  --color-success: #27AE60;
  --color-warning: #F39C12;
  --color-danger: #E74C3C;
  --sidebar-width: 200px;
}
```

## Data Flow

### Download Event Flow (Webhooks)
```
Sonarr/Radarr downloads episode
    |
    | OnDownload webhook
    v
Sublarr receives webhook
    |
    | Delay N minutes (configurable)
    v
Wanted scanner triggered
    |
    | Scan episode directory
    v
Check language profile
    |
    | Missing target subtitle?
    v
Create wanted_item entry
    |
    | Auto-search enabled?
    v
Provider search (target + source languages)
    |
    | Best result selected
    v
Download subtitle
    |
    | Target found? -> Save
    | Source found? -> Translate -> Save
    v
Update wanted_item status
    |
    | Notify Jellyfin
    v
WebSocket update to frontend
```

### Manual Translation Flow
```
User uploads file via frontend
    |
    | POST /api/v1/translate
    v
Create job entry in database
    |
    | Return job_id immediately
    v
Background worker starts
    |
    | Parse video file
    v
Extract/search for source subtitle
    |
    | Found?
    v
Translate via Ollama
    |
    | Apply glossary
    v
Save target subtitle
    |
    | Update job status
    v
WebSocket job_update event
    |
    v
Frontend receives update, displays result
```

### Batch Processing Flow
```
User clicks "Search All" in Wanted page
    |
    | POST /api/v1/wanted/batch-search
    v
Queue all wanted_items
    |
    | Return batch_id
    v
Background worker processes queue
    |
    | For each item:
    |   - Search providers
    |   - Download best match
    |   - Translate if needed
    |   - Update status
    |   - Emit WebSocket progress
    v
Batch complete
    |
    | Final WebSocket event
    v
Frontend updates UI, shows summary
```

## Docker Deployment

### Multi-Stage Build

**Stage 1: Frontend Build**
- Base: `node:20-alpine`
- Copy `frontend/package*.json`, install dependencies
- Copy `frontend/src`, build with Vite
- Output: Optimized static files in `dist/`

**Stage 2: Backend Runtime**
- Base: `python:3.11-slim`
- Install system dependencies: ffmpeg, unrar-free, mediainfo
- Copy `backend/requirements.txt`, install Python packages
- Copy backend source code
- Copy frontend build output from Stage 1
- Set up entrypoint: gunicorn with config

**Volumes**
- `/config` - SQLite database, logs, cache
- `/media` - Sonarr/Radarr media files (read/write)

**Environment Variables**
- All config via `SUBLARR_` prefixed env vars
- Secrets via `.env` file, never in docker-compose.yml
- Config validation on container start

**Networking**
- Expose port 5765
- Optional custom port via `SUBLARR_PORT` env var

**Health Check**
- Endpoint: `http://localhost:5765/api/v1/health`
- Interval: 30s
- Timeout: 10s
- Retries: 3

## Security Considerations

1. **API Authentication**: Optional but recommended API key
2. **Input Validation**: Pydantic models for all API inputs
3. **Path Traversal**: All file operations validated against media directory
4. **SQL Injection**: Parameterized queries, no string interpolation
5. **XSS Prevention**: React auto-escapes, no dangerouslySetInnerHTML
6. **Secrets Management**: Never log or return API keys/tokens in responses
7. **Rate Limiting**: Provider sessions handle rate limits gracefully
8. **Docker Isolation**: Container runs as non-root user (future improvement)

## Performance Optimizations

1. **Database**: WAL mode for concurrent reads, indexed foreign keys
2. **Provider Cache**: 1-hour TTL reduces redundant searches
3. **HTTP Session Pooling**: Reuse connections to providers
4. **WebSocket**: Batch progress updates (max 1/second)
5. **Frontend Code Splitting**: Lazy-loaded routes
6. **React Query Cache**: Minimize API calls, stale-while-revalidate
7. **Gunicorn Workers**: 2 workers × 4 threads = 8 concurrent requests
8. **Static File Serving**: Nginx recommended for production (future)

## Monitoring & Observability

**Logging**
- Python logging module, configurable level via `SUBLARR_LOG_LEVEL`
- File handler: `/config/sublarr.log` (rotated daily)
- Console handler: stdout (Docker logs)
- Format: `[timestamp] [level] [module] message`

**Metrics (via /stats endpoint)**
- Total jobs: completed, failed, pending
- Provider statistics: searches, downloads, success rate
- Translation statistics: ASS vs SRT, average duration
- Daily aggregates: jobs per day, episodes processed

**Health Checks**
- `/api/v1/health` returns status of all services
- Checks: Database connectivity, Ollama reachability, provider health
- Used by Docker healthcheck and monitoring tools

## Scalability Considerations

**Current Limitations**
- Single SQLite database (not suitable for high concurrency)
- In-process job queue (lost on restart)
- Single-instance deployment

**Future Improvements**
- PostgreSQL for multi-instance deployments
- Redis/Celery for distributed task queue
- Horizontal scaling with load balancer
- S3/object storage for subtitle files
- Prometheus metrics export (Grafana dashboards in `monitoring/grafana/`)

## Development Workflow

**Local Development**
1. Backend: `npm run dev:backend` (Flask dev server on port 5765)
2. Frontend: `cd frontend && npm run dev` (Vite HMR on port 3000)
3. Frontend proxies API calls to backend (port 5765)

**Production Build**
1. `docker build -t sublarr:latest .`
2. `docker-compose up -d`

**Code Organization**
- Backend: Feature-based modules (translator, providers, clients)
- Frontend: Component-based structure (pages, hooks, components)
- Shared types: TypeScript interfaces mirror Pydantic models
