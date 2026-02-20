# Contributing to Sublarr

Thank you for your interest in contributing to Sublarr! This document provides guidelines and instructions for contributing to the project.

## Table of Contents

- [Getting Started](#getting-started)
- [Development Setup](#development-setup)
- [Code Style Guidelines](#code-style-guidelines)
- [Testing](#testing)
- [Pull Request Process](#pull-request-process)
- [Reporting Issues](#reporting-issues)
- [Adding New Features](#adding-new-features)
- [License](#license)

## Getting Started

Sublarr is a standalone subtitle manager and translator built with:
- Backend: Python 3.11, Flask, SQLite
- Frontend: React 18, TypeScript, Tailwind CSS
- Deployment: Docker

Before contributing, please:
1. Read the [ARCHITECTURE.md](ARCHITECTURE.md) to understand the system design
2. Check existing issues and pull requests to avoid duplicates
3. Join discussions in GitHub Issues for major changes

## Development Setup

### Prerequisites

**Required Software**
- Python 3.11 or higher
- Node.js 20 or higher
- npm or yarn
- Git
- SQLite 3
- ffmpeg (for subtitle processing)
- unrar-free (for archive extraction)

**Optional Tools**
- Docker and Docker Compose (for containerized development)
- Ollama (for local LLM testing)
- Sonarr/Radarr instances (for integration testing)

### Clone the Repository

```bash
git clone https://github.com/yourusername/sublarr.git
cd sublarr
```

### Backend Setup

1. **Create a virtual environment**
   ```bash
   cd backend
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```
   
   **Oder verwende das Setup-Script (empfohlen):**
   ```bash
   # Windows (PowerShell)
   npm run setup:ps1
   
   # Linux/Mac (Bash)
   ./scripts/setup-dev.sh
   ```

3. **Configure environment variables**
   ```bash
   cp ../.env.example .env
   # Edit .env with your local settings
   ```

   Minimum required settings for development:
   ```env
   SUBLARR_SOURCE_LANGUAGE=en
   SUBLARR_TARGET_LANGUAGE=de
   SUBLARR_OLLAMA_HOST=http://localhost:11434
   SUBLARR_OLLAMA_MODEL=llama3.1
   SUBLARR_LOG_LEVEL=DEBUG
   ```

4. **Initialize the database**
   ```bash
   python -c "from database import init_db; init_db()"
   ```

5. **Run the development server**
   ```bash
   python server.py
   ```
   Backend will be available at `http://localhost:5765`

### Frontend Setup

1. **Install dependencies**
   ```bash
   cd frontend
   npm install
   ```

2. **Run the development server**
   ```bash
   npm run dev
   ```
   Frontend will be available at `http://localhost:3000` with hot module reloading.

3. **The frontend development server proxies API requests to the backend**
   - Configured in `vite.config.ts`
   - No CORS issues during development

### Docker Setup (Alternative)

For testing the full production build locally:

```bash
# Build the image
docker build -t sublarr:dev .

# Run with docker-compose
docker-compose up -d

# View logs
docker-compose logs -f sublarr
```

## Code Style Guidelines

### Python (Backend)

**General Conventions**
- Follow PEP 8 style guide
- Use 4 spaces for indentation (no tabs)
- Maximum line length: 100 characters
- Use type hints for function signatures
- Write docstrings for all public functions and classes

**Naming Conventions**
- Variables and functions: `snake_case`
- Classes: `PascalCase`
- Constants: `UPPER_SNAKE_CASE`
- Private methods: `_leading_underscore`

**Example**
```python
from typing import Optional, List
from pydantic import BaseModel

class SubtitleResult(BaseModel):
    """Represents a subtitle search result from a provider."""

    provider: str
    language: str
    format: str
    score: int
    download_url: str

    def is_ass_format(self) -> bool:
        """Check if this result is in ASS format."""
        return self.format.lower() == "ass"


def search_subtitles(query: str, language: str) -> List[SubtitleResult]:
    """
    Search for subtitles across all enabled providers.

    Args:
        query: Search query (series/movie title)
        language: ISO 639-1 language code

    Returns:
        List of subtitle results sorted by score
    """
    # Implementation here
    pass
```

**Import Order**
1. Standard library imports
2. Third-party imports
3. Local application imports
4. Separate groups with blank lines

**Error Handling**
- Use specific exception types, not bare `except:`
- Log errors with appropriate context
- Raise custom exceptions for business logic errors

### TypeScript (Frontend)

**General Conventions**
- Use TypeScript strict mode
- Prefer interfaces over type aliases for object shapes
- Use const assertions for literal types
- No `any` type without explicit comment explaining why

**Naming Conventions**
- Variables and functions: `camelCase`
- React components: `PascalCase`
- Constants: `UPPER_SNAKE_CASE`
- Types and interfaces: `PascalCase`

**Example**
```typescript
interface SubtitleResult {
  provider: string;
  language: string;
  format: string;
  score: number;
  downloadUrl: string;
}

const SubtitleCard: React.FC<{ result: SubtitleResult }> = ({ result }) => {
  const isAssFormat = result.format.toLowerCase() === 'ass';

  return (
    <div className="subtitle-card">
      <span className={isAssFormat ? 'font-bold' : ''}>
        {result.provider} - {result.language}
      </span>
    </div>
  );
};

export default SubtitleCard;
```

**React Component Guidelines**
- Use functional components with hooks (no class components)
- Extract complex logic into custom hooks
- Prefer composition over prop drilling
- Use React.memo for expensive renders
- Keep components small and focused (< 200 lines)

**Import Order**
1. React and third-party imports
2. Local component imports
3. Hook imports
4. Utility imports
5. Type imports (use `import type`)

### CSS/Tailwind

**Conventions**
- Use Tailwind utility classes as primary styling method
- Extract repeated patterns into CSS components (not inline styles)
- Use semantic class names for custom CSS
- Follow mobile-first responsive design
- Use CSS variables for theme colors

**Example**
```tsx
// Good: Tailwind utilities
<div className="flex items-center justify-between p-4 bg-gray-100 rounded-lg">

// Good: Custom component class for repeated pattern
<div className="subtitle-card">

// Avoid: Inline styles
<div style={{ padding: '16px', backgroundColor: '#f0f0f0' }}>
```

### General Guidelines

**Code Quality**
- No trailing whitespace
- Files must end with a newline
- Use meaningful variable names (no single letters except loop counters)
- Keep functions short and focused (single responsibility)
- Comment complex logic, not obvious code

**Git Commit Messages**
- Use imperative mood: "Add feature" not "Added feature"
- First line: 50 characters or less, capitalized
- Blank line after first line if body follows
- Body: wrap at 72 characters, explain what and why (not how)

**Example**
```
feat: Add SubDL provider support

Implements SubDL provider with ZIP extraction and API key auth.
SubDL is a Subscene successor with 2000 daily download limit.

Closes #123
```

**Commit Prefixes**
- `feat:` New feature
- `fix:` Bug fix
- `docs:` Documentation only
- `style:` Formatting, no code change
- `refactor:` Code restructuring, no behavior change
- `test:` Adding or updating tests
- `chore:` Maintenance tasks, dependencies

## Testing

### Backend Tests

**Running Tests**
```bash
cd backend
pytest
pytest -v  # Verbose output
pytest tests/test_providers.py  # Specific file
```

**Writing Tests**
- Place tests in `backend/tests/` directory
- Name test files with `test_` prefix
- Use pytest fixtures for common setup
- Keep provider tests isolated (mock HTTP calls)

**Example Test**
```python
import pytest
from providers.opensubtitles import OpenSubtitlesProvider
from providers.base import VideoQuery

@pytest.fixture
def provider():
    return OpenSubtitlesProvider(api_key="test_key")

def test_search_returns_results(provider, mocker):
    # Mock HTTP call
    mock_response = {"data": [{"id": "123", "attributes": {...}}]}
    mocker.patch.object(provider.session, "get", return_value=mock_response)

    query = VideoQuery(
        series="Attack on Titan",
        season=1,
        episode=1,
        language="en"
    )
    results = provider.search(query)

    assert len(results) > 0
    assert results[0].provider == "opensubtitles"
```

**Test Coverage**
- **Backend**: Aim for 80%+ coverage (enforced in CI)
- **Frontend**: Aim for 70%+ coverage (enforced in CI)
- Mock external services (Ollama, Sonarr, providers)
- Test error handling and edge cases
- Don't test trivial getters/setters

**Coverage Reports:**
```bash
# Backend coverage
cd backend
pytest --cov=. --cov-report=html
# Open htmlcov/index.html in browser

# Frontend coverage
cd frontend
npm run test:coverage
# Open coverage/index.html in browser
```

### Frontend Tests

**Running Tests**
```bash
cd frontend
npm test
npm run test:coverage
```

**Writing Tests**
- Use React Testing Library for component tests
- Test user interactions, not implementation details
- Mock API calls with MSW (Mock Service Worker)

**Example Test**
```typescript
import { render, screen, fireEvent } from '@testing-library/react';
import SubtitleCard from './SubtitleCard';

test('renders subtitle information', () => {
  const result = {
    provider: 'OpenSubtitles',
    language: 'en',
    format: 'ass',
    score: 150,
    downloadUrl: 'http://example.com/sub.ass'
  };

  render(<SubtitleCard result={result} />);

  expect(screen.getByText(/OpenSubtitles/)).toBeInTheDocument();
  expect(screen.getByText(/en/)).toBeInTheDocument();
});
```

### Integration Tests

**Provider Testing**
- Test against real provider APIs (optional)
- Set `SUBLARR_TEST_PROVIDER_API=true` to enable
- Use separate API keys for testing
- Run manually before releases

### Manual Testing Checklist

Before submitting a PR with UI changes:
- [ ] Test in Chrome, Firefox, Safari
- [ ] Test mobile responsive layout
- [ ] Test dark mode (if applicable)
- [ ] Test loading and error states
- [ ] Test WebSocket disconnection/reconnection

## Pull Request Process

### Before Submitting

1. **Fork the repository** and create a branch from `master`
   ```bash
   git checkout -b feature/my-new-feature
   ```

2. **Make your changes** following the code style guidelines

3. **Test your changes** thoroughly
   - Run backend tests: `cd backend && pytest`
   - Run frontend tests: `cd frontend && npm test`
   - Test manually in the browser

4. **Update documentation** if needed
   - Update CHANGELOG.md with your changes
   - Add/update docstrings and comments
   - Update API.md for new endpoints

5. **Commit your changes** with clear messages
   ```bash
   git add .
   git commit -m "feat: Add new provider support"
   ```

### Submitting the PR

1. **Push to your fork**
   ```bash
   git push origin feature/my-new-feature
   ```

2. **Create a Pull Request** on GitHub
   - Use a clear, descriptive title
   - Fill out the PR template (if provided)
   - Link related issues with "Closes #123"

3. **PR Description Should Include**
   - What changes were made
   - Why these changes are needed
   - How to test the changes
   - Screenshots (for UI changes)
   - Breaking changes (if any)

### PR Review Process

1. **Automated Checks**: CI/CD runs tests automatically
2. **Code Review**: Maintainer reviews code and provides feedback
3. **Address Feedback**: Make requested changes, push to same branch
4. **Approval**: PR approved when ready to merge
5. **Merge**: Maintainer merges PR to master

**PR Guidelines**
- One feature/fix per PR (keep it focused)
- Keep PRs small (< 500 lines if possible)
- Respond to feedback within a week
- Rebase on master if conflicts arise
- Squash commits before merge (maintainer will do this)

## Reporting Issues

### Bug Reports

**Before Reporting**
- Search existing issues to avoid duplicates
- Test on the latest version
- Gather logs and error messages

**Issue Template**
```markdown
## Bug Description
Clear description of the bug

## Steps to Reproduce
1. Go to '...'
2. Click on '...'
3. See error

## Expected Behavior
What should happen

## Actual Behavior
What actually happens

## Environment
- Sublarr version:
- Docker or local:
- OS:
- Browser (if frontend issue):

## Logs
Paste relevant logs here
```

### Feature Requests

**Template**
```markdown
## Feature Description
What feature would you like to see?

## Use Case
Why is this feature needed? What problem does it solve?

## Proposed Solution
How would you implement this?

## Alternatives Considered
What other approaches did you think about?
```

## Adding New Features

### Adding a New Provider

See [PROVIDERS.md](PROVIDERS.md) for detailed instructions on adding subtitle providers.

**Quick Steps**
1. Create `providers/newprovider.py` extending `SubtitleProvider`
2. Implement `search()`, `download()`, `health_check()` methods
3. Add config settings to `config.py`
4. Register in `providers/__init__.py` PROVIDER_REGISTRY
5. Add to `.env.example` with `SUBLARR_` prefix
6. Write tests in `tests/test_providers.py`
7. Update PROVIDERS.md documentation

### Adding a New API Endpoint

**Steps**
1. Add route handler in `backend/server.py` (or new Blueprint)
2. Define Pydantic models for request/response validation
3. Update `frontend/src/api/client.ts` with TypeScript types
4. Add React Query hook in `frontend/src/hooks/useApi.ts`
5. Document endpoint in `docs/API.md`
6. Write tests for endpoint

**Example**
```python
# backend/server.py
from pydantic import BaseModel

class MyRequest(BaseModel):
    param: str

class MyResponse(BaseModel):
    result: str

@api_v1.route("/my-endpoint", methods=["POST"])
def my_endpoint():
    req = MyRequest(**request.json)
    # Process request
    return jsonify(MyResponse(result="success").dict())
```

```typescript
// frontend/src/api/client.ts
export const callMyEndpoint = async (param: string): Promise<string> => {
  const response = await apiClient.post('/my-endpoint', { param });
  return response.data.result;
};
```

### Adding Database Tables

**Steps**
1. Define schema in `backend/database.py` `init_db()`
2. Add version check and migration logic
3. Create model class and helper functions
4. Update relevant API endpoints
5. Add frontend UI if needed

**Migration Pattern**
```python
def init_db():
    # ... existing tables ...

    # Check for new table
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='my_new_table'")
    if not cursor.fetchone():
        cursor.execute("""
            CREATE TABLE my_new_table (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                ...
            )
        """)
        conn.commit()
```

## License

By contributing to Sublarr, you agree that your contributions will be licensed under the GNU General Public License v3.0 (GPL-3.0).

All submitted code must be compatible with GPL-3.0. If you include code from other projects:
- Ensure the original license is compatible with GPL-3.0
- Include proper attribution in comments
- Update ACKNOWLEDGMENTS.md if needed

## Questions?

- Open a GitHub Discussion for general questions
- Join the community chat (if available)
- Tag maintainers in issues for urgent matters

Thank you for contributing to Sublarr!
