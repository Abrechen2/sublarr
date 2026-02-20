# Phase 9: OpenAPI + Release Preparation - Research

**Researched:** 2026-02-16
**Domain:** API documentation (OpenAPI/Swagger), backend performance optimization, frontend performance, health monitoring, release engineering
**Confidence:** HIGH (core libraries verified via official docs and PyPI; patterns verified from codebase analysis)

## Summary

Phase 9 combines two milestone areas: M21 (OpenAPI + Performance) with 6 requirements and M22 (Release + Community) with 5 requirements. The codebase has 120+ API endpoints across 15 Flask Blueprints, all under `/api/v1/`. The prior decision to use **apispec** (not Flask-smorest or APIFlask) is sound -- it avoids route rewrites since it works with YAML docstrings parsed from existing view functions. The key challenge is Blueprint support: apispec-webframeworks does not natively iterate Blueprint views, so a helper function must iterate `app.view_functions` within an app context and call `spec.path(view=fn)` for each.

The wanted scanner currently rescans ALL series/episodes on every run -- there is no incremental mechanism. Each file also invokes `ffprobe` inline. The provider search is already parallel (ThreadPoolExecutor) and uses connection pooling (urllib3 Retry + HTTPAdapter), but wanted search processes items sequentially with `time.sleep(0.5)` between items. The health/detailed endpoint exists but lacks translation backend and media server subsystem detail. Frontend performance is dominated by the 4703-line Settings.tsx monolith and the absence of route-level code splitting.

**Primary recommendation:** Split this into 4-5 plans: (1) OpenAPI spec + Swagger UI, (2) backend performance (incremental scan + parallel search), (3) health endpoint + task scheduler page, (4) frontend performance, (5) release preparation (docs, CHANGELOG, tag, Docker, Unraid).

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| apispec | 6.9.0 | OpenAPI 3.0 spec generation from view docstrings | Prior decision; avoids route rewrites, works with existing Flask views |
| apispec-webframeworks | 1.3.0+ | Flask plugin for apispec (spec.path from views) | Official Flask integration for apispec |
| flask-swagger-ui | 5.21.0 | Serve Swagger UI as a Flask Blueprint at /api/docs | Simple Blueprint registration, no config complexity |
| @tanstack/react-virtual | 3.13.x | Virtual scrolling for long lists (Wanted, Library) | Headless, works with existing TanStack Query, ~12kb |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pyyaml | (already installed) | YAML spec output for apispec | Already a transitive dep of Flask |
| React.lazy + Suspense | built-in React 19 | Route-level code splitting | Split all page components for lazy loading |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| apispec | flasgger | Flasgger is heavier, injects its own UI, harder to control spec output |
| apispec | APIFlask | Would require rewriting all route decorators -- unacceptable at this stage |
| flask-swagger-ui | custom static serve | flask-swagger-ui is a 1-line Blueprint registration, no reason to DIY |
| @tanstack/react-virtual | react-virtuoso | react-virtuoso is larger (~40kb) and more opinionated; TanStack Virtual is headless and consistent with existing TanStack Query |

**Installation:**
```bash
# Backend
pip install apispec>=6.9.0 apispec-webframeworks>=1.3.0 flask-swagger-ui>=5.21.0

# Frontend
cd frontend && npm install @tanstack/react-virtual
```

## Architecture Patterns

### Recommended Project Structure
```
backend/
├── openapi.py           # APISpec instance, helper to register all views
├── routes/
│   ├── __init__.py      # register_blueprints() -- exists, add spec registration
│   ├── system.py        # /health/detailed enhanced, /api/docs spec endpoint
│   └── [all others]     # Add YAML docstrings to existing view functions
└── ...

frontend/
├── src/
│   ├── App.tsx          # React.lazy() imports for all page components
│   ├── pages/
│   │   ├── Settings/    # Split into sub-modules (SettingsGeneral, SettingsProviders, etc.)
│   │   └── ...
│   └── ...
```

### Pattern 1: apispec with YAML Docstrings (No Marshmallow)
**What:** Add OpenAPI YAML documentation as docstring blocks in existing view functions, separated by `---`. apispec parses these automatically.
**When to use:** For all 120+ endpoints. No Marshmallow schemas are needed since the project uses plain dicts/jsonify.

**Example:**
```python
# Source: https://apispec.readthedocs.io/en/latest/using_plugins.html
@bp.route("/health", methods=["GET"])
def health():
    """Health check endpoint.
    ---
    get:
      tags:
        - System
      summary: Basic health check
      description: Returns overall system health status. No authentication required.
      responses:
        200:
          description: System is healthy
          content:
            application/json:
              schema:
                type: object
                properties:
                  status:
                    type: string
                    enum: [healthy, unhealthy]
                  version:
                    type: string
                  services:
                    type: object
        503:
          description: System is unhealthy
    """
    # existing implementation unchanged
```

### Pattern 2: Centralized Spec Registration (Blueprint Workaround)
**What:** Since apispec-webframeworks does not natively iterate Blueprint views, create a helper that walks `app.view_functions` after all blueprints are registered.
**When to use:** Once, in `openapi.py`, called during `create_app()`.

**Example:**
```python
# backend/openapi.py
from apispec import APISpec
from apispec_webframeworks.flask import FlaskPlugin

spec = APISpec(
    title="Sublarr API",
    version="0.9.0-beta",
    openapi_version="3.0.3",
    info={
        "description": "Standalone Subtitle Manager & Translator for Anime/Media",
        "license": {"name": "GPL-3.0", "url": "https://www.gnu.org/licenses/gpl-3.0.html"},
    },
    plugins=[FlaskPlugin()],
)

def register_all_paths(app):
    """Register all Flask view functions with apispec.

    Must be called within app context AFTER all blueprints are registered.
    Only registers views with YAML docstring blocks (containing '---').
    """
    with app.test_request_context():
        for name, view_fn in app.view_functions.items():
            if name == "static":
                continue
            docstring = getattr(view_fn, "__doc__", "") or ""
            if "---" in docstring:
                try:
                    spec.path(view=view_fn)
                except Exception:
                    pass  # Skip views that fail to parse
```

### Pattern 3: Route-Level Code Splitting with React.lazy
**What:** Wrap all page imports in React.lazy() with Suspense fallback. Vite automatically creates separate chunks for each lazy import.
**When to use:** For all page components in App.tsx.

**Example:**
```typescript
import { lazy, Suspense } from 'react'

const Dashboard = lazy(() => import('@/pages/Dashboard'))
const SettingsPage = lazy(() => import('@/pages/Settings'))
const WantedPage = lazy(() => import('@/pages/Wanted'))
// ... all other pages

function AnimatedRoutes() {
  return (
    <Suspense fallback={<PageSkeleton />}>
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/settings" element={<SettingsPage />} />
        {/* ... */}
      </Routes>
    </Suspense>
  )
}
```

### Pattern 4: Incremental Wanted Scan via Timestamp Tracking
**What:** Store last_scanned_at timestamp per series/movie. On scan, only query Sonarr/Radarr for items modified since last scan. Fall back to full scan on first run or manual trigger.
**When to use:** In WantedScanner.scan_all() to avoid rescanning unchanged items.

**Example:**
```python
# In wanted_scanner.py
def scan_all(self, incremental=True) -> dict:
    """Run a wanted scan. If incremental=True, only scan items changed since last scan."""
    if incremental and self._last_scan_at:
        # Sonarr/Radarr APIs support ?since= parameter (ISO timestamp)
        series_list = sonarr.get_series(since=self._last_scan_at)
    else:
        series_list = sonarr.get_series()
    # ... rest of scan logic
```

### Pattern 5: Parallel Wanted Search with ThreadPoolExecutor
**What:** Replace sequential item processing in search_all() with parallel execution using bounded concurrency.
**When to use:** In WantedScanner.search_all() to process multiple items simultaneously.

**Example:**
```python
from concurrent.futures import ThreadPoolExecutor, as_completed

max_workers = min(4, len(eligible))  # Limit concurrency
with ThreadPoolExecutor(max_workers=max_workers) as executor:
    futures = {executor.submit(process_wanted_item, item["id"]): item for item in eligible}
    for future in as_completed(futures):
        item = futures[future]
        result = future.result()
        # update counters, emit progress
```

### Anti-Patterns to Avoid
- **Don't use marshmallow just for OpenAPI:** The codebase uses plain dicts everywhere. Adding marshmallow schemas would be massive scope creep with no benefit -- YAML docstrings achieve the same result.
- **Don't auto-generate spec from code:** The spec should be authored by hand in docstrings. Auto-generation from return types would miss most detail since the codebase uses untyped dicts.
- **Don't split Settings.tsx into 50 files:** Split into 5-7 logical tab components (General, Providers, Translation, Whisper, MediaServers, Events, Advanced). Each tab is already visually separated in the UI.
- **Don't parallelize ffprobe calls without limit:** ffprobe spawns subprocess per call. Unbounded parallelism would fork-bomb the system. Use a bounded pool (4-8 workers).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| OpenAPI spec generation | Manual JSON/YAML spec file | apispec + YAML docstrings | 120+ endpoints, manual spec would be unmaintainable |
| Swagger UI serving | Custom HTML/JS static files | flask-swagger-ui Blueprint | One-line registration, auto-updates with pip |
| Virtual scrolling | Custom DOM recycling | @tanstack/react-virtual | Handles variable heights, resize observers, scroll math |
| Code splitting | Manual dynamic imports per component | React.lazy + Vite auto-chunking | Vite handles chunk naming, preloading, and caching |
| CHANGELOG generation | Manual editing from git log | Conventional Commits + manual curation | Sublarr already has CHANGELOG.md format; enhance, don't replace |

**Key insight:** The OpenAPI documentation is the most labor-intensive part of this phase (120+ endpoints). Using apispec with docstrings means each endpoint gets documented incrementally without changing any route logic.

## Common Pitfalls

### Pitfall 1: Blueprint Path Resolution with apispec
**What goes wrong:** `spec.path(view=fn)` fails for Blueprint views because the URL rule isn't found without proper app context.
**Why it happens:** apispec-webframeworks iterates `app.url_map` to find the rule matching the view function, but it needs an active app context.
**How to avoid:** Always call `register_all_paths(app)` inside `with app.test_request_context():` and AFTER `register_blueprints(app)` has been called.
**Warning signs:** Empty spec.to_dict()["paths"] or KeyError on view registration.

### Pitfall 2: YAML Docstring Indentation
**What goes wrong:** apispec silently produces an empty or malformed spec path entry.
**Why it happens:** YAML in docstrings is indentation-sensitive. Python docstrings auto-strip leading whitespace inconsistently.
**How to avoid:** Always start the YAML block after `---` with consistent indentation (2 or 4 spaces). Use `textwrap.dedent` awareness. Test spec output for each blueprint after adding docstrings.
**Warning signs:** Spec paths with empty operations or missing responses.

### Pitfall 3: Incremental Scan Missing Items
**What goes wrong:** Newly downloaded episodes are missed because Sonarr doesn't update the series `updated` timestamp when an episode file is added.
**Why it happens:** The Sonarr API `since` filter may not catch all changes. File additions don't always update the series-level timestamp.
**How to avoid:** Use a combination of: (a) Sonarr's episode file events, (b) series-level modified timestamp, and (c) periodic full scan fallback (e.g., every 6th scan is full). Store last full scan time separately.
**Warning signs:** Growing count of "missing" items that never appear in wanted list.

### Pitfall 4: Settings.tsx Split Breaking State
**What goes wrong:** After splitting Settings.tsx into tab components, shared state (unsaved changes, form values) breaks across tab navigation.
**Why it happens:** Each tab component has its own state. Navigating between tabs unmounts/remounts components, losing form state.
**How to avoid:** Lift shared state to a SettingsContext or use a form library that persists state across tab changes. Keep the parent Settings.tsx as the state owner; tabs receive props.
**Warning signs:** Unsaved changes lost on tab switch, "save" button state incorrect.

### Pitfall 5: Version String Inconsistency
**What goes wrong:** Health endpoint says "0.1.0", CHANGELOG says "1.0.0-beta", roadmap says "0.9.0-beta".
**Why it happens:** Version strings are hardcoded in 3 places: `app.py:268`, `routes/system.py:83`, `routes/system.py:330`.
**How to avoid:** Create a single `__version__` string in a `version.py` module. Import it everywhere. Set it to "0.9.0-beta" for this release.
**Warning signs:** `/health` and `/api/docs` showing different versions.

### Pitfall 6: Swagger UI CSP (Content Security Policy) Issues
**What goes wrong:** Swagger UI loads but shows blank page or broken CSS/JS.
**Why it happens:** If the app sets Content-Security-Policy headers, Swagger UI's inline scripts/styles get blocked.
**How to avoid:** flask-swagger-ui serves from its own Blueprint. Ensure no CSP middleware blocks the `/api/docs/dist/` path. Test Swagger UI in the Docker container, not just dev mode.
**Warning signs:** Browser console shows CSP violation errors on /api/docs.

## Code Examples

### Swagger UI Blueprint Registration
```python
# In app.py create_app(), after register_blueprints(app):
from flask_swagger_ui import get_swaggerui_blueprint

SWAGGER_URL = "/api/docs"
API_URL = "/api/v1/openapi.json"

swaggerui_blueprint = get_swaggerui_blueprint(
    SWAGGER_URL,
    API_URL,
    config={"app_name": "Sublarr API", "layout": "BaseLayout"},
)
app.register_blueprint(swaggerui_blueprint)
```

### OpenAPI JSON Endpoint
```python
# In routes/system.py
@bp.route("/openapi.json", methods=["GET"])
def openapi_spec():
    """Serve the OpenAPI 3.0 specification as JSON."""
    from openapi import spec
    return jsonify(spec.to_dict())
```

### Enhanced /health/detailed with Translation Backends and Media Servers
```python
# Additional subsystem checks for /health/detailed
# Translation backends
try:
    from translation import get_translation_manager
    tm = get_translation_manager()
    backends_health = {}
    for name in tm.list_backends():
        backend = tm.get_backend(name)
        if backend:
            healthy, msg = backend.health_check()
            backends_health[name] = {"healthy": healthy, "message": msg}
    subsystems["translation_backends"] = {
        "healthy": any(b["healthy"] for b in backends_health.values()) if backends_health else True,
        "backends": backends_health,
    }
except Exception as exc:
    subsystems["translation_backends"] = {"healthy": False, "message": str(exc)}

# Media servers (already partially implemented -- extend with individual checks)
try:
    from mediaserver import get_media_server_manager
    ms_mgr = get_media_server_manager()
    ms_checks = ms_mgr.health_check_all()
    subsystems["media_servers"] = {
        "healthy": all(c["healthy"] for c in ms_checks) if ms_checks else True,
        "instances": ms_checks,
    }
except Exception as exc:
    subsystems["media_servers"] = {"healthy": False, "message": str(exc)}

# Whisper backends
try:
    from whisper import get_whisper_manager
    wm = get_whisper_manager()
    whisper_health = {}
    for name in wm.list_backends():
        backend = wm.get_backend(name)
        if backend:
            healthy, msg = backend.health_check()
            whisper_health[name] = {"healthy": healthy, "message": msg}
    subsystems["whisper_backends"] = {
        "healthy": any(b["healthy"] for b in whisper_health.values()) if whisper_health else True,
        "backends": whisper_health,
    }
except Exception as exc:
    subsystems["whisper_backends"] = {"healthy": False, "message": str(exc)}
```

### Version Module Pattern
```python
# backend/version.py
__version__ = "0.9.0-beta"

# Usage everywhere:
from version import __version__
```

### Task Scheduler Dashboard Data Endpoint
```python
@bp.route("/tasks", methods=["GET"])
def get_tasks():
    """Get status of all background tasks/schedulers.
    ---
    get:
      tags:
        - System
      summary: List background tasks and their status
      responses:
        200:
          description: Task list with next run times
    """
    from wanted_scanner import get_scanner
    from database_backup import get_backup_scheduler_status

    scanner = get_scanner()
    tasks = [
        {
            "name": "wanted_scan",
            "display_name": "Wanted Scan",
            "running": scanner.is_scanning,
            "last_run": scanner.last_scan_at,
            "interval_hours": settings.wanted_scan_interval_hours,
        },
        {
            "name": "wanted_search",
            "display_name": "Wanted Search",
            "running": scanner.is_searching,
            "last_run": scanner.last_search_at,
            "interval_hours": settings.wanted_search_interval_hours,
        },
        # ... backup scheduler, standalone watcher
    ]
    return jsonify({"tasks": tasks})
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Flask-RESTPlus/Flask-RESTX | apispec + flask-swagger-ui | 2023+ | apispec is lighter, no route decorator changes required |
| Webpack code splitting | Vite automatic chunk splitting | 2023+ | Vite handles it with zero config via dynamic imports |
| react-window/react-virtualized | @tanstack/react-virtual | 2023+ | Headless, smaller, framework-aligned with TanStack ecosystem |
| Manual CHANGELOG | Keep a Changelog format | established | Sublarr already uses this format |
| Semantic versioning 1.0.0-beta | 0.9.0-beta (pre-release) | per roadmap | v1.0.0 reserved for final release after community testing |

**Deprecated/outdated:**
- flask-apispec: Abandoned (last update 2021), relies on webargs for parsing
- swagger-ui-py: Dead project, use flask-swagger-ui instead
- react-window: Still works but @tanstack/react-virtual is the modern replacement

## Open Questions

1. **Sonarr/Radarr incremental API support**
   - What we know: Sonarr v3 API supports `/api/v3/series?includeAllSeries=false` but the `since` parameter behavior for detecting changed episodes is undocumented.
   - What's unclear: Whether the Sonarr API reliably surfaces episode-level changes via series-level queries.
   - Recommendation: Implement timestamp-based filtering for `scan_all()` with a fallback to full scan every N cycles. Track the `updated` field from Sonarr series metadata. Verify empirically during testing.

2. **OpenAPI spec coverage depth**
   - What we know: 120+ endpoints need documentation. Full request/response schema documentation for all is substantial effort.
   - What's unclear: How much schema detail is needed for community launch vs. post-launch iteration.
   - Recommendation: Document all endpoints with summary, parameters, and response status codes. Add detailed request/response schemas for the top 20 most-used endpoints (translate, wanted, providers, config, health). Mark remaining as "schema TBD" for post-launch.

3. **Community Provider Repository setup (RELS-04)**
   - What we know: The plugin system supports loading providers from a plugins directory. A community repo would be a GitHub repository with contributed provider plugins.
   - What's unclear: Whether this means a separate GitHub repo, a branch, or a directory with CI.
   - Recommendation: Create a `sublarr-community-providers` GitHub repo with a README, contributing guide, and template. Minimal -- just the structure, not populated plugins.

4. **Migration Guide scope (RELS-01)**
   - What we know: The roadmap says "Migration Guide v1.0.0-beta -> v0.9.0-beta". This implies documenting what changed between the first beta and this release.
   - What's unclear: The version numbering went backwards (1.0.0-beta was tagged in CHANGELOG, now targeting 0.9.0-beta). This needs explanation.
   - Recommendation: Write the migration guide as "Upgrading from v1.0.0-beta to v0.9.0-beta" explaining: (a) version renumber rationale, (b) new features requiring config changes, (c) breaking API changes if any, (d) Docker image update steps.

## Phase-Specific Findings

### Endpoint Count by Blueprint (for OpenAPI scoping)
| Blueprint | Endpoints | Priority |
|-----------|-----------|----------|
| system | 20 | HIGH (health, stats, backup, logs) |
| translate | 14 | HIGH (core feature) |
| wanted | 11 | HIGH (core feature) |
| hooks | 17 | MEDIUM (events, scoring) |
| standalone | 12 | MEDIUM |
| profiles | 12 | MEDIUM (language profiles, glossary, presets) |
| providers | 7 | HIGH (core feature) |
| library | 7 | HIGH |
| tools | 4 | LOW |
| config | 7 | HIGH |
| whisper | 10 | MEDIUM |
| mediaservers | 5 | MEDIUM |
| plugins | 4 | MEDIUM |
| webhooks | 2 | LOW |
| blacklist | 7 | LOW |

### Frontend Page Sizes (for code-splitting priority)
| Page | Lines | Split Priority |
|------|-------|---------------|
| Settings.tsx | 4703 | CRITICAL -- must split into tab components |
| SeriesDetail.tsx | 1129 | HIGH |
| Wanted.tsx | 854 | HIGH |
| Onboarding.tsx | 643 | MEDIUM |
| Library.tsx | 485 | MEDIUM |
| Dashboard.tsx | 437 | MEDIUM |
| All others | <320 each | LOW (still lazy-load for routing) |

### Existing Infrastructure to Leverage
- **CI/CD:** GitHub Actions already configured for tests, Docker build, security scan
- **Docker build:** Multi-arch (amd64/arm64) with GHCR publishing on tags
- **Unraid template:** `unraid/sublarr.xml` exists, needs update for new features
- **CHANGELOG.md:** Exists with Keep a Changelog format, covers v1.0.0-beta
- **docs/:** API.md, ARCHITECTURE.md, CONTRIBUTING.md, PROVIDERS.md, TROUBLESHOOTING.md already exist
- **Version strings:** Hardcoded "0.1.0" in 3 places -- must be centralized

### Health Endpoint Gap Analysis
Current `/health/detailed` checks:
- [x] Database (integrity + stats)
- [x] Ollama (legacy direct check)
- [x] Providers (circuit breaker state)
- [x] Disk usage (/config, /media)
- [x] Memory (RSS/VMS)

Missing from `/health/detailed`:
- [ ] Translation backends (5 backends: ollama, deepl, libretranslate, openai_compat, google)
- [ ] Media servers (individual instance health -- partially done, needs enhancement)
- [ ] Whisper backends (faster_whisper, subgen)
- [ ] Sonarr/Radarr connectivity (separate from provider health)
- [ ] Standalone watcher status
- [ ] Scheduler status (scan/search timers running)

## Sources

### Primary (HIGH confidence)
- [apispec docs v6.9.0](https://apispec.readthedocs.io/en/latest/) - Plugin usage, Flask integration, YAML docstring parsing
- [flask-swagger-ui v5.21.0 on PyPI](https://pypi.org/project/flask-swagger-ui/) - Blueprint registration, configuration
- [@tanstack/react-virtual on npm](https://www.npmjs.com/package/react-virtuoso) - Virtual scrolling API, headless approach
- Codebase analysis: `backend/routes/*.py` (120+ endpoints), `backend/wanted_scanner.py` (scan logic), `backend/providers/__init__.py` (parallel search)
- Codebase analysis: `frontend/src/pages/Settings.tsx` (4703 lines), `frontend/src/App.tsx` (routing)

### Secondary (MEDIUM confidence)
- [apispec-webframeworks Flask Blueprint workaround](https://github.com/marshmallow-code/apispec-webframeworks/issues/11) - Blueprint support limitations and `app.view_functions` iteration pattern
- [Vite code splitting with React.lazy](https://codeparrot.ai/blogs/advanced-guide-to-using-vite-with-react-in-2025) - Route-level lazy loading best practices
- [TanStack Virtual docs](https://tanstack.com/virtual/latest/docs/introduction) - Virtualizer hook API

### Tertiary (LOW confidence)
- Sonarr v3 API incremental query behavior -- undocumented, needs empirical validation

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - apispec, flask-swagger-ui, @tanstack/react-virtual all verified via official docs/PyPI
- Architecture: HIGH - Patterns verified against existing codebase structure
- Pitfalls: HIGH - Blueprint issues documented in apispec-webframeworks issue tracker; Settings.tsx size confirmed
- Performance patterns: MEDIUM - Incremental scan feasibility depends on Sonarr API behavior (needs validation)
- Release preparation: HIGH - CI/CD, Docker, Unraid template all exist and are well-understood

**Research date:** 2026-02-16
**Valid until:** 2026-03-16 (30 days -- stable libraries, no fast-moving dependencies)
