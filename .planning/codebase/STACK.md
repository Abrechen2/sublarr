# Technology Stack

**Analysis Date:** 2026-02-15

## Languages

**Primary:**
- Python 3.11+ - Backend API, translation pipeline, provider integrations, database layer
- TypeScript 5.9 - Frontend application, type-safe React components

**Secondary:**
- JavaScript (Node.js 20) - Build tooling, development scripts, package management

## Runtime

**Environment:**
- Python 3.11-slim (Docker base image)
- Node.js 20-alpine (Docker build stage)

**Package Manager:**
- Python: pip (no lockfile, uses `requirements.txt`)
- Node.js: npm (lockfile: `package-lock.json` present)
- Root coordinator: npm (manages concurrent dev servers)

## Frameworks

**Core:**
- Flask 3.1.0 - Backend web server, REST API (`/api/v1/`), Blueprint routing
- Flask-SocketIO 5.4.1 - WebSocket real-time communication (job status, logs)
- React 19.2.0 - Frontend UI library
- React Router DOM 7.13.0 - Client-side routing

**Testing:**
- Backend: pytest 8.3.4 with pytest-cov 6.0.0 (80% coverage requirement, `backend/pytest.ini`)
- Frontend: vitest 4.0.18 with @vitest/coverage-v8, @testing-library/react 16.3.2
- E2E: Playwright 1.48.0
- Load testing: Locust 2.24.0 (`backend/locustfile.py`)

**Build/Dev:**
- Vite 7.3.1 - Frontend dev server (:5173) and production bundler
- Tailwind CSS 4.1.18 via @tailwindcss/vite - Utility-first styling
- Gunicorn 23.0.0 - Production WSGI server (2 workers, 4 threads, gthread worker class)
- concurrently 9.1.2 - Parallel dev server orchestration (backend + frontend)
- cross-env 7.0.3 - Cross-platform environment variable management

**Code Quality:**
- ruff 0.8.0+ - Python linting and formatting
- mypy 1.11.0+ - Python type checking
- ESLint 9.39.1 - JavaScript/TypeScript linting
- Prettier 3.4.2 with prettier-plugin-tailwindcss - Code formatting
- pre-commit 3.8.0 - Git hook automation
- vulture 2.10 - Dead code detection (Python)
- ts-prune 0.10.3 - Dead code detection (TypeScript)
- bandit[toml] 1.7.5 - Python security linter
- radon 6.0.1 - Python code complexity analysis

## Key Dependencies

**Critical:**
- pysubs2 2.7.3 - ASS/SRT subtitle parsing and manipulation
- requests 2.32.3 - HTTP client for all external API calls
- pydantic 2.10.6 + pydantic-settings 2.7.1 - Configuration validation, Settings class with `SUBLARR_` prefix
- @tanstack/react-query 5.90.21 - Server state management, caching, optimistic updates
- axios 1.13.5 - Frontend HTTP client
- socket.io-client 4.8.3 - Frontend WebSocket client

**Infrastructure:**
- sqlite3 (stdlib) - Database (WAL mode, 17+ tables, thread-safe with `_db_lock`)
- python-dotenv 1.0.1 - Environment variable loading from `.env`
- simple-websocket 1.1.0 - Flask-SocketIO dependency
- rarfile 4.2 - RAR archive extraction for subtitle provider downloads
- apprise 1.9.2 - Unified notification system (Pushover, Discord, Telegram, Gotify, etc.)
- lucide-react 0.564.0 - Icon library for frontend UI

**Development:**
- pytest-mock 3.14.0 - Mock objects for testing
- pytest-benchmark 4.0.0 - Performance benchmarking
- jsdom 28.0.0 - DOM emulation for frontend tests
- @testing-library/user-event 14.6.1 - User interaction simulation
- pip-tools 7.4.0 - Requirements management
- pip-audit 2.7.0 - Dependency security auditing
- liccheck 0.9.0 - License compliance checking
- license-checker 25.0.1 - Frontend license checking
- @lhci/cli 0.13.0 - Lighthouse CI (optional dependency)

## Configuration

**Environment:**
- `.env` file with `SUBLARR_` prefix for all variables
- `.env.example` provided with 85+ lines of documented configuration options
- Runtime override via `config_entries` database table (see `backend/config.py`)
- Config cascade: Env → Pydantic Settings → DB runtime overrides

**Build:**
- `vite.config.ts` - Vite configuration with React plugin, Tailwind, path aliases (`@/`), dev proxy
- `tsconfig.json` - TypeScript compiler options
- `docker-compose.yml` - Production deployment (port 5765, volumes: `/config`, `/media`)
- `Dockerfile` - Multi-stage build (frontend build stage + Python runtime stage)

**Key Configuration Files:**
- `backend/config.py` - Pydantic Settings class with 80+ fields
- `backend/pytest.ini` - Test configuration (80% coverage requirement)
- Frontend ESLint: `eslint.config.js` (ESLint 9.x flat config format)
- Frontend TypeScript: `tsconfig.json` with `compilerOptions` for React 19

## Platform Requirements

**Development:**
- Python 3.11+ with pip
- Node.js 20+ with npm
- ffmpeg (for ASS style analysis via `backend/ass_utils.py`)
- unrar or unrar-free (for RAR archive extraction)

**Production:**
- Docker with docker-compose
- Optional: PUID/PGID build args for file permission mapping (defaults: 1000/1000)
- Resource limits: 2 CPU cores max, 4GB RAM max (reservations: 0.5 CPU, 512MB)
- Security: non-root user (sublarr), no-new-privileges, minimal capabilities (CHOWN, DAC_OVERRIDE, SETGID, SETUID)

**External Services (all optional):**
- Ollama server (required for LLM translation, default: `http://localhost:11434`)
- Sonarr v3 API (optional, for series management)
- Radarr v3 API (optional, for movie management)
- Jellyfin/Emby API (optional, for library refresh notifications)
- Subtitle providers requiring API keys: OpenSubtitles.com, Jimaku, SubDL (AnimeTosho requires no auth)

---

*Stack analysis: 2026-02-15*
