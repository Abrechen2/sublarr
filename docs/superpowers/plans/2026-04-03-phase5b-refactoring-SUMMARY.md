---
phase: 5b
plan: refactoring
subsystem: backend-services, frontend-settings, frontend-wanted
tags: [refactoring, file-split, backwards-compatible]
dependency_graph:
  requires: []
  provides: [wanted_scanner_core, config_utils, config_language_data, config_instances, settingsFields, PathMappingEditor, InstanceEditor, WantedToolbar, WantedFilterPanel, WantedTableRow]
  affects: [wanted_scanner, config, LegacySettings, Wanted, AdvancedTab]
tech_stack:
  added: []
  patterns: [barrel-re-export, local-import-circular-prevention, prop-drilling-to-sub-components]
key_files:
  created:
    - backend/services/wanted_scanner_core.py
    - backend/config_utils.py
    - backend/config_language_data.py
    - backend/config_instances.py
    - backend/tests/test_wanted_scanner_split.py
    - backend/tests/test_config_split.py
    - frontend/src/pages/Settings/AdvancedTab sub-components (LanguageProfilesTab, LibrarySourcesTab, BackupTab, SubtitleToolsTab)
    - frontend/src/pages/Settings/settingsFields.ts
    - frontend/src/pages/Settings/PathMappingEditor.tsx
    - frontend/src/pages/Settings/InstanceEditor.tsx
    - frontend/src/pages/wanted/WantedToolbar.tsx
    - frontend/src/pages/wanted/WantedFilterPanel.tsx
    - frontend/src/pages/wanted/WantedTableRow.tsx
  modified:
    - backend/services/wanted_scanner.py (thin facade, 88 LOC)
    - backend/config.py (805 LOC, down from 1101)
    - frontend/src/pages/Settings/AdvancedTab.tsx (4-line barrel)
    - frontend/src/pages/Settings/LegacySettings.tsx (682 LOC, down from 1248)
    - frontend/src/pages/Wanted.tsx (640 LOC, down from 1497)
decisions:
  - "wanted_scanner_core.py accepted at ~1120 LOC (plan target was 1085) — no further split warranted"
  - "config.py at 805 LOC (5 over target) — re-export block unavoidable; accepted as minor deviation"
  - "Circular imports in config_instances.py and config_utils.py solved via local imports inside function bodies"
  - "Package import pattern: services/ modules must use from services.module import, not bare imports"
metrics:
  duration: "~90 minutes (across two sessions)"
  completed: "2026-04-03"
  tasks_completed: 5/5
  commits: 6
---

# Phase 5b Plan: File Splitting Refactoring Summary

**One-liner:** Backwards-compatible split of 5 oversized files (1101–1497 LOC) into 15 focused modules using barrel re-export pattern, reducing all primary files to under 1000 LOC.

## Objective

Split oversized backend and frontend files to bring them within project size limits (backend ≤800 LOC, frontend ≤1000 LOC) while maintaining 100% backwards compatibility for all callers.

## Tasks Completed

| Task | Description | Before LOC | After LOC | Commit |
|------|-------------|-----------|-----------|--------|
| 1 | wanted_scanner.py → facade + core | 1085 | 88 (facade) + 1120 (core) | ab18541 |
| 2 | config.py → 3 helper modules | 1101 | 805 + 46 + 151 + 144 | abf59bf |
| 3 | AdvancedTab.tsx → 4 sub-tab components | ~800 | 4 (barrel) + 4 new files | 99bdd63 |
| 4 | Wanted.tsx → 3 sub-components | 1497 | 640 + 110 + 240 + 320 | f7f3124 |
| 5 | LegacySettings.tsx → 3 helper files | 1248 | 682 + 241 + 207 + 130 | 34e65e1 |

## Commits

| Hash | Message |
|------|---------|
| ab18541 | refactor: extract WantedScanner class to services/wanted_scanner_core.py |
| abf59bf | refactor: extract language data, map_path, and instance helpers from config.py |
| 99bdd63 | refactor: split AdvancedTab.tsx into 4 focused sub-tab components |
| f7f3124 | refactor: extract WantedToolbar, WantedFilterPanel, WantedTableRow from Wanted.tsx |
| 34e65e1 | refactor: split LegacySettings.tsx into settingsFields, PathMappingEditor, InstanceEditor |
| b5cacfb | fix: remove unused FilterCondition import from Wanted.tsx and Loader2 from WantedToolbar |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Package-relative import in wanted_scanner.py**
- **Found during:** Task 1
- **Issue:** Facade used `from wanted_scanner_core import ...` (bare import). Since `wanted_scanner.py` is inside the `services/` package, Python resolves bare imports relative to sys.path, not the current package — causing `ModuleNotFoundError`.
- **Fix:** Changed to `from services.wanted_scanner_core import FULL_SCAN_INTERVAL, WantedScanner`
- **Files modified:** `backend/services/wanted_scanner.py`
- **Commit:** ab18541

**2. [Rule 1 - Bug] Ruff I001 import ordering**
- **Found during:** Task 1 post-check
- **Issue:** ruff reported unsorted import blocks in wanted_scanner.py and test_wanted_scanner_split.py
- **Fix:** `ruff check . --fix && ruff format .`
- **Files modified:** `backend/services/wanted_scanner.py`, `backend/tests/test_wanted_scanner_split.py`
- **Commit:** ab18541

**3. [Rule 1 - Bug] Unused import FilterCondition in Wanted.tsx**
- **Found during:** Task 4 lint check
- **Issue:** `FilterCondition` was imported in Wanted.tsx but only used in WantedFilterPanel (which was extracted). ESLint error.
- **Fix:** Removed `FilterCondition` from import in Wanted.tsx
- **Files modified:** `frontend/src/pages/Wanted.tsx`
- **Commit:** b5cacfb

**4. [Rule 1 - Bug] Unused import Loader2 in WantedToolbar.tsx**
- **Found during:** Task 4 lint check
- **Issue:** `Loader2` was in the import list but not referenced in WantedToolbar JSX. ESLint error.
- **Fix:** Removed from import
- **Files modified:** `frontend/src/pages/wanted/WantedToolbar.tsx`
- **Commit:** b5cacfb

### Plan-level Notes

- **config.py at 805 LOC** (5 over the 800 target): The re-export block added lines beyond the plan's ~790 estimate. Accepted — removing the re-exports would break callers.
- **wanted_scanner_core.py at 1120 LOC** (vs. plan's 1085 target): Slight overage; accepted per plan's explicit allowance of this as an exception.

## Backwards Compatibility

All public APIs maintained:

**Backend:**
- `from services.wanted_scanner import WantedScanner, get_scanner, invalidate_scanner` — unchanged
- `from services.wanted_scanner import FULL_SCAN_INTERVAL` — re-exported from facade
- `from config import get_settings, map_path, SUPPORTED_LANGUAGES, _LANGUAGE_TAGS, get_sonarr_instances, get_radarr_instances, is_standalone_mode, get_media_server_instances` — all re-exported

**Frontend:**
- `AdvancedTab.tsx` re-exports `LanguageProfilesTab`, `LibrarySourcesTab`, `BackupTab`, `SubtitleToolsTab`
- `LegacySettings.tsx` re-exports `FieldConfig` (type), `NAV_GROUPS`, `TABS`
- `Wanted.tsx` keeps `formatRetryCountdown`, `FailureReasonRow`, `SCOPE`, `WANTED_FILTERS`

## Verification Results

- Backend ruff check: passed (0 violations)
- Backend new split smoke tests: 11/11 passed
- Frontend TypeScript: 0 errors
- Frontend ESLint: 0 errors (8 pre-existing warnings, unchanged)
- Frontend Vitest: 806/806 tests passed

## Self-Check: PASSED

Created files verified to exist:
- backend/services/wanted_scanner_core.py: FOUND
- backend/config_utils.py: FOUND
- backend/config_language_data.py: FOUND
- backend/config_instances.py: FOUND
- frontend/src/pages/Settings/settingsFields.ts: FOUND
- frontend/src/pages/Settings/PathMappingEditor.tsx: FOUND
- frontend/src/pages/Settings/InstanceEditor.tsx: FOUND
- frontend/src/pages/wanted/WantedToolbar.tsx: FOUND
- frontend/src/pages/wanted/WantedFilterPanel.tsx: FOUND
- frontend/src/pages/wanted/WantedTableRow.tsx: FOUND

All 6 task commits verified on branch phase/5b-refactoring.
