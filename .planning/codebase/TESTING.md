# Testing Patterns

**Analysis Date:** 2026-02-15

## Test Framework

**Backend Runner:**
- Framework: pytest 8.3.4
- Config: `backend/pytest.ini`
- Plugins: `pytest-cov` (coverage), `pytest-mock` (mocking), `pytest-benchmark` (performance)

**Backend Assertion Library:**
- Built-in: Python `assert` statements
- No additional assertion library (pytest's assert rewriting is sufficient)

**Backend Run Commands:**
```bash
cd backend && python -m pytest              # Run all tests
python -m pytest -v                         # Verbose output
python -m pytest -k test_server             # Run specific test
python -m pytest tests/integration/         # Run integration tests only
python -m pytest --cov=. --cov-report=html  # Generate HTML coverage report
```

**Frontend Runner:**
- Framework: vitest 4.0.18
- Config: `frontend/vitest.config.ts`
- Environment: jsdom (browser simulation)
- Plugins: `@vitest/coverage-v8` (coverage)

**Frontend Assertion Library:**
- Built-in: Vitest `expect` (compatible with Jest)
- Testing Library: `@testing-library/jest-dom` matchers (e.g., `.toBeInTheDocument()`)
- React Testing: `@testing-library/react` (render, screen, cleanup)

**Frontend Run Commands:**
```bash
cd frontend && npm test                 # Run all tests in watch mode
npm run test:coverage                   # Generate coverage report
npm run test:ui                         # Open Vitest UI
npm run test:e2e                        # Run Playwright e2e tests
npm run test:e2e:ui                     # Playwright UI mode
```

## Test File Organization

**Backend Location:**
- Pattern: Co-located in `backend/tests/` (separate from source)
- Unit tests: `backend/tests/test_<module>.py`
- Integration tests: `backend/tests/integration/test_<feature>.py`
- Performance tests: `backend/tests/performance/test_<feature>.py`
- Fixtures: `backend/tests/fixtures/<name>.py`

**Backend Naming:**
- Test files: `test_*.py` (e.g., `test_server.py`, `test_database.py`)
- Test functions: `test_<behavior>` (e.g., `test_health_endpoint`, `test_create_job`)
- Test classes: `Test<Feature>` (e.g., `TestCaseA`, `TestCaseB`) — optional grouping
- Fixtures: Descriptive names (e.g., `temp_db`, `client`, `mock_ollama`)

**Backend Structure:**
```
backend/tests/
├── __init__.py
├── conftest.py                     # Shared fixtures
├── test_server.py                  # Flask API tests
├── test_database.py                # Database operations
├── test_config.py                  # Configuration tests
├── test_auth.py                    # Authentication tests
├── test_ass_utils.py               # ASS utility tests
├── fixtures/
│   ├── __init__.py
│   ├── provider_responses.py       # Mock provider data
│   └── test_data.py                # Sample subtitle files
├── integration/
│   ├── __init__.py
│   ├── test_api_endpoints.py       # Full API flow tests
│   ├── test_translator_pipeline.py # Translation pipeline tests
│   ├── test_provider_pipeline.py   # Provider search tests
│   ├── test_database_operations.py # Database integration tests
│   └── test_webhooks.py            # Webhook handling tests
└── performance/
    ├── __init__.py
    └── test_api_performance.py     # Load/benchmark tests
```

**Frontend Location:**
- Pattern: Co-located in `frontend/src/test/` (separate from components)
- Unit tests: `frontend/src/test/<ComponentName>.test.tsx`
- E2E tests: `frontend/e2e/<feature>.spec.ts`
- Setup: `frontend/src/test/setup.ts`

**Frontend Naming:**
- Test files: `<ComponentName>.test.tsx` or `<module>.test.ts`
- E2E files: `<feature>.spec.ts`
- Test suites: `describe('<ComponentName>', () => {})`
- Test cases: `it('behavior description', () => {})`

**Frontend Structure:**
```
frontend/
├── src/test/
│   ├── setup.ts                   # Vitest global setup
│   ├── StatusBadge.test.tsx       # Component tests
│   ├── ProgressBar.test.tsx       # Component tests
│   ├── api.test.ts                # API client tests
│   └── utils.test.ts              # Utility function tests
└── e2e/
    ├── onboarding.spec.ts         # E2E test: first-run flow
    ├── settings.spec.ts           # E2E test: settings page
    ├── wanted.spec.ts             # E2E test: wanted items
    └── language-profiles.spec.ts  # E2E test: profiles management
```

## Test Structure

**Backend Suite Organization:**
```python
# backend/tests/test_database.py
import pytest
from database import create_job, get_job

@pytest.fixture
def temp_db():
    """Create temporary test database."""
    # Setup code
    yield db_path
    # Teardown code

def test_create_job(temp_db):
    """Test job creation returns valid ID."""
    job = create_job("/test/path.mkv", force=False)
    assert job["id"] is not None
    assert job["status"] == "queued"

def test_get_job(temp_db):
    """Test job retrieval by ID."""
    job = create_job("/test/path.mkv")
    retrieved = get_job(job["id"])
    assert retrieved is not None
    assert retrieved["id"] == job["id"]
```

**Backend Patterns:**
- One fixture per resource (database, temp directory, mock client)
- Fixtures in `conftest.py` for shared setup (e.g., `temp_db`, `client`)
- Fixtures in test files for test-specific setup (e.g., `mkv_path`)
- Factory fixtures: Return functions for parameterized creation (e.g., `create_test_subtitle(fmt="ass")`)
- Yield fixtures: Use `yield` for setup/teardown pattern

**Frontend Suite Organization:**
```typescript
// frontend/src/test/StatusBadge.test.tsx
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { StatusBadge } from '@/components/shared/StatusBadge'

describe('StatusBadge', () => {
  it('renders status text', () => {
    render(<StatusBadge status="completed" />)
    expect(screen.getByText('completed')).toBeInTheDocument()
  })

  it('applies custom className', () => {
    const { container } = render(<StatusBadge status="completed" className="custom-class" />)
    expect(container.firstChild).toHaveClass('custom-class')
  })
})
```

**Frontend Patterns:**
- `describe()` for component grouping
- `it()` for individual test cases (readable sentence format)
- `render()` from Testing Library for component mounting
- `screen` queries for DOM access (not container queries)
- `expect()` with jest-dom matchers for assertions
- `cleanup()` automatic via `setup.ts` (`afterEach`)

## Mocking

**Backend Framework:**
- pytest-mock: `pytest-mock==3.14.0` (provides `mocker` fixture)
- unittest.mock: Standard library `MagicMock`, `patch`, `Mock`

**Backend Patterns:**

**Monkeypatching (conftest.py pattern):**
```python
@pytest.fixture
def mock_ollama(monkeypatch):
    """Mock Ollama client."""
    from unittest.mock import MagicMock

    mock_client = MagicMock()
    mock_client.return_value = ["translated line 1", "translated line 2"]

    monkeypatch.setattr("ollama_client.translate_all", mock_client)
    return mock_client
```

**Context manager patching (integration tests):**
```python
from unittest.mock import patch, MagicMock

def test_translation_pipeline(mkv_path):
    with patch("translator.get_settings", return_value=mock_settings), \
         patch("translator.run_ffprobe", return_value=None), \
         patch("translator.translate_all", return_value=["Übersetzt"]):
        result = translate_file(mkv_path)
        assert result["success"] is True
```

**Backend What to Mock:**
- External services: Ollama API, Sonarr/Radarr APIs, provider APIs
- Filesystem operations: `os.path.exists`, `shutil.copy`, `Path.write_text` (when testing logic, not I/O)
- Network requests: `requests.get`, `requests.post` via mock responses
- Database: Use `temp_db` fixture with real SQLite (not mocked — fast enough)
- Settings: Mock via `get_settings()` return value

**Backend What NOT to Mock:**
- Business logic: Test actual implementation
- Database operations: Use temporary SQLite database (real DB, isolated)
- Pure functions: Test directly (no external dependencies)
- Dataclasses: Instantiate real objects (lightweight)

**Frontend Framework:**
- Vitest: Built-in mocking via `vi.fn()`, `vi.mock()`, `vi.spyOn()`
- Testing Library: `@testing-library/user-event` for user interactions
- React Query: Use `QueryClientProvider` wrapper in tests

**Frontend Patterns:**

**Component with mocked API:**
```typescript
import { vi, describe, it, expect } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

vi.mock('@/api/client', () => ({
  getHealth: vi.fn().mockResolvedValue({ status: 'healthy' })
}))

describe('Dashboard', () => {
  it('displays health status', async () => {
    const queryClient = new QueryClient()
    render(
      <QueryClientProvider client={queryClient}>
        <Dashboard />
      </QueryClientProvider>
    )
    await waitFor(() => {
      expect(screen.getByText('healthy')).toBeInTheDocument()
    })
  })
})
```

**Frontend What to Mock:**
- API calls: Mock `@/api/client` functions
- WebSocket: Mock `socket.io-client` connection
- Browser APIs: LocalStorage, window.location
- External libraries: Lucide icons can use real imports (lightweight)

**Frontend What NOT to Mock:**
- React core: Never mock useState, useEffect, etc.
- Testing Library utilities: Use real render, screen, etc.
- Utility functions: Test actual implementations
- Simple components: Use real child components (unless slow)

## Fixtures and Factories

**Backend Test Data (conftest.py):**

**Temporary database:**
```python
@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    os.environ["SUBLARR_DB_PATH"] = db_path
    os.environ["SUBLARR_API_KEY"] = ""  # Disable auth

    reload_settings()
    init_db()

    yield db_path

    if os.path.exists(db_path):
        os.unlink(db_path)
```

**Flask test client:**
```python
@pytest.fixture
def client(temp_db):
    """Create a test client for Flask app."""
    app.config["TESTING"] = True

    with app.test_client() as client:
        yield client
```

**Factory fixture for subtitles:**
```python
@pytest.fixture
def create_test_subtitle(temp_dir):
    """Factory to create test subtitle files."""
    def _create(fmt="ass", lang="en", lines=None):
        if lines is None:
            lines = ["Hello World", "How are you"]

        # Generate ASS or SRT content
        path = f"{temp_dir}/test.{lang}.{fmt}"
        Path(path).write_text(content, encoding="utf-8")
        return path

    return _create
```

**Backend Location:**
- Shared fixtures: `backend/tests/conftest.py` (170 lines)
- Test data: `backend/tests/fixtures/test_data.py` (144 lines)
- Provider responses: `backend/tests/fixtures/provider_responses.py` (141 lines)

**Frontend Test Data:**

**Setup file (setup.ts):**
```typescript
import { expect, afterEach } from 'vitest'
import { cleanup } from '@testing-library/react'
import '@testing-library/jest-dom'

afterEach(() => {
  cleanup()
})
```

**Query client wrapper (custom utility):**
```typescript
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

export function createTestQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  })
}

export function wrapper(children: React.ReactNode) {
  return (
    <QueryClientProvider client={createTestQueryClient()}>
      {children}
    </QueryClientProvider>
  )
}
```

**Frontend Location:**
- Setup: `frontend/src/test/setup.ts`
- Test utilities: Inline in test files (no shared file yet)

## Coverage

**Backend Requirements:**
- Target: 80% minimum (enforced via `--cov-fail-under=80` in pytest.ini)
- Current: Not measured in analysis (CI/CD enforces)

**Backend View Coverage:**
```bash
cd backend
python -m pytest --cov=. --cov-report=html
# Open htmlcov/index.html in browser
```

**Backend Configuration (pytest.ini):**
```ini
[pytest]
addopts =
    --cov=.
    --cov-report=term-missing
    --cov-report=html
    --cov-report=xml
    --cov-fail-under=80

[coverage:run]
source = .
omit =
    */tests/*
    */test_*.py
    */__pycache__/*
    */venv/*
    */env/*
    */site-packages/*

[coverage:report]
exclude_lines =
    pragma: no cover
    def __repr__
    raise AssertionError
    raise NotImplementedError
    if __name__ == .__main__.:
    if TYPE_CHECKING:
    @abstractmethod
```

**Frontend Requirements:**
- Target: 70% minimum (all metrics: lines, functions, branches, statements)
- Provider: v8 (native V8 coverage)

**Frontend View Coverage:**
```bash
cd frontend
npm run test:coverage
# Open coverage/index.html in browser
```

**Frontend Configuration (vitest.config.ts):**
```typescript
coverage: {
  provider: 'v8',
  reporter: ['text', 'json', 'html', 'lcov'],
  reportsDirectory: './coverage',
  exclude: [
    'node_modules/',
    'dist/',
    'coverage/',
    '**/*.d.ts',
    '**/*.config.*',
    '**/test/**',
    '**/tests/**',
    '**/*.test.*',
    '**/*.spec.*',
    '**/setup.ts',
  ],
  include: ['src/**/*.{ts,tsx}'],
  thresholds: {
    lines: 70,
    functions: 70,
    branches: 70,
    statements: 70,
  },
}
```

## Test Types

**Backend Unit Tests:**
- Scope: Single module, isolated functions
- Dependencies: Mocked (Ollama, providers, external APIs)
- Database: Real SQLite (temp file, isolated)
- Examples: `test_config.py`, `test_auth.py`, `test_ass_utils.py`

**Backend Unit Test Pattern:**
```python
def test_get_output_path():
    """Test output path generation for translated subtitle."""
    from translator import get_output_path

    result = get_output_path("/media/anime/episode.mkv", fmt="ass")
    assert result.endswith(".de.ass")
```

**Backend Integration Tests:**
- Scope: Multiple modules, full request lifecycle
- Dependencies: Mocked external services, real database
- Flask: Test client (`app.test_client()`)
- Examples: `test_api_endpoints.py`, `test_translator_pipeline.py`, `test_provider_pipeline.py`

**Backend Integration Test Pattern:**
```python
def test_translate_endpoint_success(client, mock_ollama, mock_provider_manager):
    """Test full translation via API endpoint."""
    response = client.post("/api/v1/translate", json={
        "file_path": "/media/test.mkv",
        "force": False
    })
    assert response.status_code == 200
    data = response.get_json()
    assert "job_id" in data
```

**Backend Performance Tests:**
- Scope: Load testing, benchmarking
- Framework: `pytest-benchmark` for microbenchmarks, `locust` for load tests
- File: `tests/performance/test_api_performance.py`
- CI: Not run by default (manual or nightly)

**Backend E2E Tests:**
- Not implemented yet
- Future: Docker-based tests with real Ollama, Sonarr, Radarr instances

**Frontend Unit Tests:**
- Scope: Single component, isolated utilities
- Rendering: `@testing-library/react` with jsdom
- Examples: `StatusBadge.test.tsx`, `ProgressBar.test.tsx`, `utils.test.ts`

**Frontend Unit Test Pattern:**
```typescript
describe('formatDuration', () => {
  it('formats seconds correctly', () => {
    expect(formatDuration(125)).toBe('2m 5s')
  })

  it('handles hours', () => {
    expect(formatDuration(3665)).toBe('1h 1m 5s')
  })
})
```

**Frontend Integration Tests:**
- Scope: Component + API hooks + state management
- Mocking: API client mocked, React Query real
- Pattern: Render component with QueryClientProvider
- Examples: Would be in `src/test/<Page>.test.tsx` (not fully implemented yet)

**Frontend E2E Tests:**
- Framework: Playwright (`@playwright/test`)
- Scope: Full user workflows in real browser
- Files: `frontend/e2e/*.spec.ts`
- Examples: `onboarding.spec.ts`, `settings.spec.ts`, `wanted.spec.ts`, `language-profiles.spec.ts`

**Frontend E2E Test Pattern:**
```typescript
import { test, expect } from '@playwright/test'

test('user can complete onboarding', async ({ page }) => {
  await page.goto('http://localhost:5173')
  await page.fill('input[name="ollama_url"]', 'http://localhost:11434')
  await page.click('button[type="submit"]')
  await expect(page.locator('.dashboard')).toBeVisible()
})
```

## Common Patterns

**Backend Async Testing:**
```python
# Not needed — Flask tests are synchronous
# For future async code:
import pytest

@pytest.mark.asyncio
async def test_async_function():
    result = await some_async_function()
    assert result is not None
```

**Backend Error Testing:**
```python
def test_translate_missing_file(client):
    """Test error response for missing file."""
    response = client.post("/api/v1/translate", json={
        "file_path": "/nonexistent/file.mkv"
    })
    assert response.status_code == 404
    data = response.get_json()
    assert "error" in data
    assert data["error"]["code"] == "FILE_404"
```

**Backend Parametrized Tests:**
```python
@pytest.mark.parametrize("status,expected", [
    ("queued", 200),
    ("running", 200),
    ("completed", 200),
])
def test_job_status_values(client, status, expected):
    """Test different job status values."""
    # Create job with status
    response = client.get(f"/api/v1/jobs?status={status}")
    assert response.status_code == expected
```

**Frontend Async Testing:**
```typescript
import { waitFor } from '@testing-library/react'

it('loads data asynchronously', async () => {
  render(<Dashboard />)

  await waitFor(() => {
    expect(screen.getByText('Dashboard')).toBeInTheDocument()
  })
})
```

**Frontend User Interaction Testing:**
```typescript
import userEvent from '@testing-library/user-event'

it('handles button click', async () => {
  const user = userEvent.setup()
  render(<MyComponent />)

  await user.click(screen.getByRole('button', { name: 'Submit' }))

  expect(screen.getByText('Success')).toBeInTheDocument()
})
```

**Frontend Error Testing:**
```typescript
it('displays error message on API failure', async () => {
  vi.mocked(getHealth).mockRejectedValue(new Error('Network error'))

  render(<Dashboard />)

  await waitFor(() => {
    expect(screen.getByText(/error/i)).toBeInTheDocument()
  })
})
```

## CI/CD Integration

**Backend CI:**
- Pre-commit: `pre-commit>=3.8.0` for linting and formatting
- Test command: `cd backend && python -m pytest`
- Coverage upload: XML report for coverage services
- Security: `bandit[toml]` for security scanning
- Dependencies: `pip-audit>=2.7.0` for vulnerability scanning
- License check: `liccheck>=0.9.0` for license compliance

**Frontend CI:**
- Lint: `npm run lint` (ESLint)
- Format check: `npm run format:check` (Prettier)
- Test: `npm test` (Vitest)
- Coverage: `npm run test:coverage` with thresholds enforced
- E2E: `npm run test:e2e` (Playwright)
- Dead code: `npm run dead-code` (ts-prune)
- Lighthouse: `npm run lhci` (optional, performance audit)

**Continuous Integration:**
- Not explicitly configured in codebase (no `.github/workflows` found)
- Docker: `Dockerfile` builds both backend and frontend
- Multi-stage build: Tests run during Docker build

---

*Testing analysis: 2026-02-15*
