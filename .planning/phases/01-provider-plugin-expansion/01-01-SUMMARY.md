---
phase: 01-provider-plugin-expansion
plan: 01
subsystem: providers
tags: [plugin-system, importlib, provider-registry, config-fields, flask-blueprint]

# Dependency graph
requires:
  - phase: 00-architecture-refactoring
    provides: "Modular app factory, route blueprints, db package"
provides:
  - "SubtitleProvider ABC with declarative config_fields, rate_limit, timeout, max_retries, is_plugin"
  - "PluginManager for plugin discovery, validation, and registration"
  - "Plugin manifest validation (name, search/download methods, SubtitleProvider subclass check)"
  - "Namespaced plugin config storage in config_entries table"
  - "Plugin management API endpoints (/api/v1/plugins)"
  - "Built-in providers with declarative class attributes replacing hardcoded switch/case"
affects: [01-02, 01-03, 01-04, 01-05, 01-06, frontend-settings]

# Tech tracking
tech-stack:
  added: [beautifulsoup4, lxml, watchdog, guessit]
  patterns: [plugin-discovery-via-importlib, declarative-config-fields, namespaced-db-config]

key-files:
  created:
    - backend/providers/plugins/__init__.py
    - backend/providers/plugins/loader.py
    - backend/providers/plugins/manifest.py
    - backend/db/plugins.py
    - backend/routes/plugins.py
  modified:
    - backend/providers/base.py
    - backend/providers/__init__.py
    - backend/providers/animetosho.py
    - backend/providers/jimaku.py
    - backend/providers/opensubtitles.py
    - backend/providers/subdl.py
    - backend/config.py
    - backend/routes/__init__.py
    - backend/app.py
    - backend/requirements.txt

key-decisions:
  - "Plugin config stored in existing config_entries table with plugin.<name>.<key> namespacing -- no new DB table needed"
  - "Built-in providers always win name collisions -- plugins with duplicate names are rejected"
  - "Safe import = exception catching only (no sandboxing), same trust model as Bazarr"
  - "Config field keys on built-in providers match Pydantic Settings field names (e.g. jimaku_api_key) and are stripped to short params (e.g. api_key) for constructor compatibility"

patterns-established:
  - "Declarative config_fields: providers declare their config as a list of dicts on the class"
  - "Class-level rate_limit/timeout/max_retries: operational params declared on the provider class, read by ProviderManager"
  - "Plugin module naming: sublarr_plugin_{filename} in sys.modules"
  - "Plugin registration: PluginManager sets cls.is_plugin=True, then assigns directly to _PROVIDER_CLASSES"

# Metrics
duration: 8min
completed: 2026-02-15
---

# Phase 01 Plan 01: Plugin Infrastructure Summary

**Plugin-based provider architecture with importlib discovery, declarative config_fields, namespaced DB storage, and REST API management endpoints**

## Performance

- **Duration:** 8 min
- **Started:** 2026-02-15T12:18:13Z
- **Completed:** 2026-02-15T12:26:55Z
- **Tasks:** 3
- **Files modified:** 15 (5 created, 10 modified)

## Accomplishments

- Extended SubtitleProvider ABC with 5 new class attributes (config_fields, rate_limit, timeout, max_retries, is_plugin) enabling declarative provider configuration
- Refactored ProviderManager to read config from class attributes instead of hardcoded switch/case blocks and static dicts
- Created complete plugin discovery system: PluginManager + importlib loader + manifest validator
- Added plugin config CRUD with namespaced config_entries storage (plugin.<name>.<key>)
- Created /api/v1/plugins REST endpoints for listing, reloading, and configuring plugins
- All 4 built-in providers updated with declarative attributes matching existing Settings keys

## Task Commits

Each task was committed atomically:

1. **Task 1: Extend SubtitleProvider ABC and refactor ProviderManager** - `194ff69` (feat)
2. **Task 2: Update 4 built-in providers with declarative attributes** - `a1bf99a` (feat)
3. **Task 3: Create plugin system, manifest validation, DB config, API endpoints** - `4ca2bc7` (feat)

## Files Created/Modified

- `backend/providers/base.py` - Added config_fields, rate_limit, timeout, max_retries, is_plugin class attributes to SubtitleProvider ABC
- `backend/providers/__init__.py` - Refactored _get_provider_config(), _get_provider_config_fields(), added _get_rate_limit/timeout/retries helpers, collision check, _load_plugins()
- `backend/providers/animetosho.py` - Added declarative config_fields=[], rate_limit=(50,30), timeout=20, max_retries=2
- `backend/providers/jimaku.py` - Added 1 config field (jimaku_api_key), rate_limit=(100,60), timeout=30
- `backend/providers/opensubtitles.py` - Added 3 config fields, rate_limit=(40,10), timeout=15, max_retries=3
- `backend/providers/subdl.py` - Added 1 config field (subdl_api_key), rate_limit=(30,10), timeout=15
- `backend/providers/plugins/__init__.py` - PluginManager class with discover/reload/get_plugin_info, module-level singleton
- `backend/providers/plugins/loader.py` - importlib-based module loader with safe import (exception catching)
- `backend/providers/plugins/manifest.py` - PluginManifest dataclass + validate_plugin + extract_manifest
- `backend/db/plugins.py` - Plugin config CRUD (get/set/get_all/delete) with namespaced config_entries keys
- `backend/routes/plugins.py` - Blueprint with GET /plugins, POST /plugins/reload, GET/PUT /plugins/<name>/config
- `backend/routes/__init__.py` - Added plugins_bp to blueprint registration list
- `backend/app.py` - Added plugin system initialization in create_app()
- `backend/config.py` - Added plugins_dir setting (default: /config/plugins)
- `backend/requirements.txt` - Added beautifulsoup4, lxml, watchdog, guessit

## Decisions Made

- Plugin config stored in existing config_entries table with `plugin.<name>.<key>` namespacing rather than a new table -- simpler, no schema migration needed
- Built-in providers always win on name collision -- collision check in register_provider() logs warning and skips duplicate
- Config field keys use full Pydantic Settings names (e.g. `opensubtitles_api_key`) on the class, but ProviderManager strips the provider-name prefix when building constructor kwargs (e.g. `api_key`)
- Plugin module names use `sublarr_plugin_` prefix in sys.modules to avoid namespace collisions

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required. The plugin system creates its plugins directory automatically on startup.

## Next Phase Readiness

- Plugin infrastructure complete and ready for Plans 04-06 (new provider implementations)
- Built-in providers already have declarative attributes, so Plans 02-03 (refactoring existing providers) can build on this foundation
- /api/v1/plugins endpoints are registered and return empty plugin list when no external plugins are installed
- All 24 existing unit tests pass (integration test failures are pre-existing, documented in STATE.md)

## Self-Check: PASSED

- All 12 key files verified present
- All 3 task commits verified (194ff69, a1bf99a, 4ca2bc7)
- 24/24 unit tests passing
- App creates without errors (create_app(testing=True))
- /api/v1/providers returns 200 with existing providers
- /api/v1/plugins returns 200 with empty plugins list

---
*Phase: 01-provider-plugin-expansion*
*Completed: 2026-02-15*
