# Coding Conventions

**Analysis Date:** 2026-02-15

## Naming Patterns

**Files (Backend):**
- Modules: `snake_case.py` (e.g., `error_handler.py`, `ollama_client.py`, `database_backup.py`)
- Tests: `test_<module>.py` (e.g., `test_server.py`, `test_database.py`)
- Integration tests: `tests/integration/test_<feature>_<scope>.py`
- Fixtures: `tests/fixtures/<name>.py`

**Files (Frontend):**
- Components: `PascalCase.tsx` (e.g., `StatusBadge.tsx`, `Dashboard.tsx`)
- Hooks: `use<Name>.ts` (e.g., `useApi.ts`, `useWebSocket.ts`)
- Utilities: `camelCase.ts` (e.g., `client.ts`, `utils.ts`)
- Types: `types.ts` (single file for all interfaces)
- Tests: `<ComponentName>.test.tsx` (e.g., `StatusBadge.test.tsx`)

**Functions (Backend):**
- Public functions: `snake_case` (e.g., `translate_file`, `get_settings`, `record_stat`)
- Private helpers: `_snake_case` with leading underscore (e.g., `_extract_series_id`, `_get_language_tags`, `_has_app_context`)
- Flask routes: verb + noun pattern (e.g., `get_health`, `update_config`, `start_batch`)

**Functions (Frontend):**
- Components: `PascalCase` (e.g., `StatusBadge`, `StatCard`, `SkeletonCard`)
- Hooks: `use<Name>` (e.g., `useHealth`, `useStats`, `useWantedSummary`)
- Utilities: `camelCase` (e.g., `formatDuration`, `truncatePath`)
- API client functions: `camelCase` async (e.g., `getHealth`, `updateConfig`, `translateFile`)

**Variables (Backend):**
- Constants: `SCREAMING_SNAKE_CASE` (e.g., `LOG_FORMAT`, `MIN_FREE_SPACE_MB`, `ENGLISH_MARKER_WORDS`)
- Module-level config: `snake_case` (e.g., `logger`, `settings`, `_db_lock`)
- Local variables: `snake_case` (e.g., `db_path`, `job_id`, `target_language`)

**Variables (Frontend):**
- Constants: `camelCase` objects or `PascalCase` for configs (e.g., `statusStyles`)
- State variables: `camelCase` (e.g., `currentUptime`, `initialUptimeRef`)
- Props: `camelCase` with interface suffix `Props` (e.g., `StatusBadgeProps`)

**Types (Backend):**
- Classes: `PascalCase` (e.g., `SublarrError`, `TranslationError`, `ProviderManager`)
- Dataclasses: `PascalCase` (e.g., `VideoQuery`, `SubtitleResult`, `Settings`)
- Enums: `PascalCase` class, `SCREAMING_SNAKE_CASE` members (e.g., `SubtitleFormat.ASS`)

**Types (Frontend):**
- Interfaces: `PascalCase` (e.g., `Job`, `HealthStatus`, `PaginatedJobs`)
- Type aliases: `PascalCase` (e.g., `Stats`, `BatchState`)
- Props interfaces: `<ComponentName>Props` (e.g., `StatusBadgeProps`)

## Code Style

**Formatting (Backend):**
- Indentation: 4 spaces
- Line length: Soft limit at 100 characters (pragmatic, not enforced)
- Docstrings: Triple-quoted strings immediately after function/class definition
- String quotes: Double quotes for strings, single quotes rare

**Formatting (Frontend):**
- Tool: Prettier (package.json scripts: `format`, `format:check`)
- Plugin: `prettier-plugin-tailwindcss` for class sorting
- Indentation: 2 spaces
- Line length: Flexible (typical ~80-100 chars)
- String quotes: Single quotes for strings, double for JSX attributes
- Arrow functions: Always use for components and utilities

**Linting (Backend):**
- Tools: `ruff>=0.8.0`, `mypy>=1.11.0` (in requirements.txt)
- Static analysis: `vulture` (dead code), `bandit[toml]` (security), `radon` (complexity)
- Pre-commit: `pre-commit>=3.8.0` configured
- No explicit `.flake8` or `.pylintrc` — relying on ruff defaults

**Linting (Frontend):**
- Tool: ESLint 9 with flat config (`eslint.config.js`)
- Extends: `@eslint/js`, `typescript-eslint`, `react-hooks`, `react-refresh`
- Key rules:
  - `@typescript-eslint/no-unused-vars`: error (except `^_` prefix)
  - `@typescript-eslint/no-explicit-any`: warn
  - `@typescript-eslint/no-floating-promises`: error
  - `react-hooks/exhaustive-deps`: warn
  - `no-console`: warn (allow `warn`/`error`)
- TypeScript strict mode: Project uses `tsconfig.app.json` with type checking

## Import Organization

**Backend Order:**
1. Standard library (e.g., `import os`, `import logging`, `from datetime import datetime`)
2. Third-party packages (e.g., `from flask import Flask`, `from pydantic import Field`)
3. Local modules (e.g., `from config import get_settings`, `from database import get_db`)

**Backend Patterns:**
- Absolute imports only (no relative imports observed)
- Module imports: `import <module>` for standard library, `from <module> import <names>` for specific symbols
- Group related imports together (e.g., all Flask imports on consecutive lines)
- No wildcard imports (`from x import *`)

**Frontend Order:**
1. React core (e.g., `import { useState, useEffect } from 'react'`)
2. Third-party packages (e.g., `import axios from 'axios'`, `from lucide-react import ...`)
3. Local utilities/types (e.g., `import type { Job } from '@/lib/types'`)
4. Local components (e.g., `import { StatusBadge } from '@/components/shared/StatusBadge'`)

**Frontend Path Aliases:**
- `@/` → `./src/` (configured in `vite.config.ts` and `tsconfig.json`)
- Always use `@/` prefix for local imports (e.g., `@/lib/types`, `@/hooks/useApi`)

**TypeScript Type Imports:**
- Use `import type` for type-only imports (e.g., `import type { HealthStatus } from '@/lib/types'`)
- Improves build performance and makes intent explicit

## Error Handling

**Backend Patterns:**
- Custom exception hierarchy: All errors inherit from `SublarrError` (base class in `error_handler.py`)
- Exception attributes: `code` (machine-readable), `http_status`, `context` (dict), `troubleshooting` (string)
- Specific error types: `TranslationError`, `OllamaConnectionError`, `DatabaseError`, `ProviderError`, etc.
- Flask error handlers: Registered via `register_error_handlers()` in `error_handler.py`
- Structured JSON responses: All errors return `{"error": {...}, "request_id": "..."}` format

**Backend Conventions:**
- Use `try/except` with specific exception types (never bare `except:`)
- Log errors before raising: `logger.error(f"message", exc_info=True)`
- Add troubleshooting hints to user-facing errors (see `OllamaConnectionError`)
- Database operations: Use `_db_lock` context manager for thread safety
- Provider operations: Wrapped in circuit breaker (see `circuit_breaker.py`)

**Frontend Patterns:**
- Error Boundary: `ErrorBoundary.tsx` component for React error catching
- API errors: Handled via axios interceptors in `client.ts`
- Async errors: TanStack Query handles promise rejections automatically
- User feedback: `toast()` function for error notifications

**Frontend Conventions:**
- TypeScript: All functions typed with return types (implicit or explicit)
- Async operations: Always use `async/await` (no raw promises)
- Optional chaining: Use `?.` for nullable access (e.g., `data?.services`)
- Nullish coalescing: Use `??` for defaults (e.g., `providers ?? []`)

## Logging

**Backend Framework:**
- Standard library: `logging` module
- Configuration: `logging.basicConfig()` in `server.py`
- Log format: `LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"`
- Log level: Configured via `SUBLARR_LOG_LEVEL` env var (default: INFO)

**Backend Patterns:**
- Module-level logger: `logger = logging.getLogger(__name__)`
- Structured JSON logging: `StructuredJSONFormatter` class for ELK/Loki integration
- WebSocket logging: `SocketIOLogHandler` emits logs to connected clients
- Request IDs: Attached via Flask `g.request_id` for tracing

**Backend When to Log:**
- DEBUG: Function entry/exit, detailed state
- INFO: Job start/completion, config changes
- WARNING: Degraded functionality, fallbacks
- ERROR: Operation failures, exceptions
- CRITICAL: System-level failures (rare)

**Frontend Logging:**
- Console: `console.warn()` and `console.error()` allowed by ESLint
- Production: No console.log() in production code (ESLint warns)
- Debugging: React DevTools for component inspection

## Comments

**Backend When to Comment:**
- Module docstrings: Describe purpose, dependencies, license (see `providers/base.py`)
- Function docstrings: Parameters, return values, exceptions (Google-style format)
- Complex logic: Inline comments for non-obvious algorithms (e.g., scoring in `providers/__init__.py`)
- TODOs: Use `# TODO:` format (searchable)

**Backend Docstring Pattern:**
```python
"""One-line summary.

Detailed description if needed. Can span multiple paragraphs.

Args:
    param1: Description
    param2: Description

Returns:
    Description of return value

Raises:
    ExceptionType: When this happens
"""
```

**Frontend When to Comment:**
- JSDoc for complex functions: Describe parameters and behavior
- Inline comments: For non-obvious logic or workarounds
- TODO comments: Use `// TODO:` format
- Minimal comments: Prefer self-documenting code with clear variable names

**Frontend JSDoc Pattern:**
```typescript
/**
 * Fetch subtitle jobs with pagination.
 * @param page - Page number (1-indexed)
 * @param perPage - Items per page
 * @returns Paginated job list
 */
```

## Function Design

**Backend Size:**
- Target: Functions under 50 lines (guideline, not enforced)
- Exception: Flask route handlers can be longer (see `server.py`)
- Extraction: Complex logic extracted to helper functions (prefix with `_`)

**Backend Parameters:**
- Type hints: Always use (e.g., `def translate_file(mkv_path: str, force: bool = False) -> dict:`)
- Defaults: Use Python defaults (not `None` placeholders unless semantic)
- Optional: Use `Optional[T]` for nullable types
- Keyword-only: Use `*` separator for clarity in complex functions

**Backend Return Values:**
- Dictionaries: For API responses (e.g., `{"success": True, "job_id": "..."}`)
- Dataclasses: For structured data (e.g., `VideoQuery`, `SubtitleResult`)
- None: For void operations (explicit `-> None` annotation)
- Exceptions: Raise errors instead of returning error codes

**Frontend Size:**
- Components: Keep under 200 lines (extract sub-components if larger)
- Hooks: Single responsibility (one data source per hook)
- Utilities: Pure functions, under 30 lines

**Frontend Parameters:**
- Props: Always typed with interface (e.g., `StatusBadgeProps`)
- Destructuring: Destructure props in function signature
- Defaults: Use TypeScript defaults in interface or parameter
- Children: Use `React.ReactNode` type for child elements

**Frontend Return Values:**
- Components: JSX.Element (implicit)
- Hooks: Explicit return type if complex (e.g., `UseQueryResult<Stats>`)
- Utilities: Always typed return value

## Module Design

**Backend Exports:**
- Public API: Functions/classes without `_` prefix
- Private helpers: Prefix with `_` (not imported by other modules)
- Constants: Exported if reusable (e.g., `SubtitleFormat.ASS`)
- Config: Use `get_settings()` singleton (never direct import of settings instance)

**Backend Module Pattern:**
```python
# Imports at top
import os
from typing import Optional

# Constants
DEFAULT_TIMEOUT = 30

# Public classes/functions
class MyClass:
    pass

def public_function():
    pass

# Private helpers
def _private_helper():
    pass
```

**Backend Barrel Files:**
- Not used (Python doesn't have barrel pattern)
- Providers: `providers/__init__.py` exports `ProviderManager`, not individual providers

**Frontend Exports:**
- Named exports preferred over default exports (e.g., `export function StatusBadge()`)
- Exception: Page components may use default export for lazy loading
- Components: Export component and its props interface
- Utilities: Export individual functions (no namespace objects)

**Frontend Barrel Files:**
- Minimal usage: `@/lib/types.ts` exports all interfaces
- Components: Direct imports (no `components/index.ts`)
- Hooks: Direct imports (no `hooks/index.ts`)

**Frontend Module Pattern:**
```typescript
// Imports
import { useState } from 'react'

// Types
interface MyComponentProps {
  value: string
}

// Component
export function MyComponent({ value }: MyComponentProps) {
  return <div>{value}</div>
}
```

## Configuration Management

**Backend Pattern:**
- Pydantic Settings: `Settings` class in `config.py`
- Environment variables: All prefixed with `SUBLARR_`
- Runtime overrides: Stored in `config_entries` database table
- Singleton: Access via `get_settings()` function
- Reload: `reload_settings()` for tests or runtime config changes

**Backend Cascading:**
1. `.env` file (loaded by `python-dotenv`)
2. Environment variables
3. Database overrides (`config_entries` table)
4. In-memory cache (`_settings_cache` global)

**Backend Access Pattern:**
```python
from config import get_settings

settings = get_settings()
value = settings.target_language
optional = getattr(settings, "optional_field", default_value)
```

**Frontend Configuration:**
- API config: Fetched via `/api/v1/config` endpoint
- Local storage: API key stored in localStorage (`sublarr_api_key`)
- Environment: Build-time variables via Vite (not used currently)
- TanStack Query: Config cached with React Query

## Threading and Concurrency

**Backend Patterns:**
- Database: `_db_lock = threading.Lock()` for SQLite thread safety
- Provider search: `ThreadPoolExecutor` for parallel provider queries
- Background jobs: Flask-SocketIO with `async_mode="threading"`
- Scheduler: Not implemented yet (wanted scan uses manual triggers)

**Backend Thread Safety:**
- All database operations: Use `with _db_lock:` context
- Config singleton: Thread-safe via module-level cache
- Provider circuits: Per-provider locks in `circuit_breaker.py`

**Frontend Concurrency:**
- React 19: Concurrent rendering enabled
- TanStack Query: Automatic request deduplication
- Async operations: All API calls async/await
- WebSocket: Single connection via `useWebSocket` hook

---

*Convention analysis: 2026-02-15*
