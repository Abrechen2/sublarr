---
phase: 01-provider-plugin-expansion
plan: 03
subsystem: providers
tags: [watchdog, hot-reload, plugin-template, file-watcher, developer-docs]

# Dependency graph
requires:
  - phase: 01-provider-plugin-expansion
    plan: 01
    provides: "PluginManager, plugin discovery, manifest validation, plugin API endpoints"
provides:
  - "Watchdog-based file watcher for plugin hot-reload with debounce"
  - "plugin_hot_reload config setting (default: false)"
  - "Graceful degradation when watchdog not installed"
  - "Annotated plugin template (my_provider.py) with full SubtitleProvider implementation"
  - "Plugin developer guide (README.md) covering API contract, scoring, config, error handling"
affects: [01-04, 01-05, 01-06, plugin-developers]

# Tech tracking
tech-stack:
  added: [watchdog]
  patterns: [debounced-file-watcher, graceful-import-fallback, plugin-template]

key-files:
  created:
    - backend/providers/plugins/watcher.py
    - backend/providers/plugins/template/my_provider.py
    - backend/providers/plugins/template/README.md
  modified:
    - backend/config.py
    - backend/app.py

key-decisions:
  - "Watcher uses 2-second debounce via threading.Timer to coalesce rapid file events"
  - "Hot-reload is opt-in (plugin_hot_reload=false by default) to avoid unnecessary filesystem watching in production"
  - "Watchdog is optional -- ImportError caught gracefully, hot-reload simply disabled if not installed"
  - "Watcher is non-recursive (only watches plugins dir root, not subdirectories)"

patterns-established:
  - "Optional dependency pattern: try/except ImportError in app.py for optional features"
  - "Plugin template pattern: working example with comprehensive docstrings as developer reference"

# Metrics
duration: 8min
completed: 2026-02-15
---

# Phase 01 Plan 03: Hot-Reload & Plugin Template Summary

**Watchdog file watcher with debounced plugin reload, plus annotated developer template with 436-line developer guide**

## Performance

- **Duration:** 8 min
- **Started:** 2026-02-15T12:29:57Z
- **Completed:** 2026-02-15T12:38:40Z
- **Tasks:** 2
- **Files modified:** 5 (3 created, 2 modified)

## Accomplishments

- Created watchdog-based file watcher (PluginFileWatcher) with 2-second debounce for plugin hot-reload
- Added plugin_hot_reload config setting and wired optional watcher startup in create_app() with graceful ImportError fallback
- Created fully annotated plugin template (my_provider.py) covering all SubtitleProvider methods, config_fields, scoring, and error handling
- Created comprehensive plugin developer guide (README.md, 436 lines) covering API contract, VideoQuery/SubtitleResult references, scoring weights, rate limiting, common patterns (ZIP/XZ/RAR), Docker mounting, and testing workflow

## Task Commits

Each task was committed atomically:

1. **Task 1: Implement watchdog-based file watcher and wire hot-reload** - `fa0c607` (feat)
2. **Task 2: Create plugin developer template and documentation** - template files committed in prior session as part of `db62010`

## Files Created/Modified

- `backend/providers/plugins/watcher.py` - PluginFileWatcher with debounced reload, start/stop lifecycle functions
- `backend/providers/plugins/template/my_provider.py` - Annotated plugin template with all SubtitleProvider methods and config_fields
- `backend/providers/plugins/template/README.md` - 436-line plugin developer guide covering full development workflow
- `backend/config.py` - Added plugin_hot_reload setting (default: false)
- `backend/app.py` - Conditional watcher startup after plugin discovery with ImportError fallback

## Decisions Made

- Watcher uses threading.Timer for 2-second debounce (cancels previous timer on rapid events)
- Hot-reload is opt-in (default false) to avoid unnecessary filesystem watching in production deployments
- Watchdog is an optional dependency -- if not installed, hot-reload is simply unavailable (no crash)
- Watcher monitors non-recursively (root of plugins dir only)
- Template includes commented-out example code showing real API call patterns rather than abstract instructions

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

- Template files (my_provider.py, README.md) were already committed in a prior execution session (commit db62010). Content matched plan requirements, so no additional commit was needed for Task 2.

## User Setup Required

None - hot-reload is disabled by default. Enable with `SUBLARR_PLUGIN_HOT_RELOAD=true` environment variable.

## Next Phase Readiness

- Hot-reload mechanism complete for plugin development workflow
- Template and documentation ready for third-party plugin developers
- Plans 04-06 (new provider implementations) can use the template as a reference
- POST /plugins/reload and file watcher both trigger invalidate_manager() ensuring new plugins are immediately searchable
- All 24 unit tests passing

## Self-Check: PASSED

- All 3 key files verified present (watcher.py, my_provider.py, README.md)
- Task 1 commit verified (fa0c607)
- Task 2 artifacts verified in commit db62010
- 24/24 unit tests passing
- Watcher module imports successfully
- Template parses as valid Python
- README.md is 436 lines (substantive content)

---
*Phase: 01-provider-plugin-expansion*
*Completed: 2026-02-15*
