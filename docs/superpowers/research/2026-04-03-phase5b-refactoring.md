# Phase 5b: Oversized File Refactoring — Research

**Researched:** 2026-04-03
**Domain:** Python service splitting, React component extraction, backwards-compatible refactoring
**Confidence:** HIGH

---

## Summary

Five files exceed the 800-line project limit by a factor of 1.4–1.6x. All five have clear, well-marked internal section boundaries already (comment banners, distinct export functions, logical groupings). None require logic changes — only physical reorganization.

The codebase already provides two reference patterns for splitting: the `routes/wanted/` and `routes/system/` packages (Python), and the `TranslationTab.tsx` / `EventsTab.tsx` / `AdvancedTab.tsx` multi-export pattern (TypeScript). Both confirm the project's preferred split strategy: keep exports identical, move code to focused sibling files.

**Primary recommendation:** Split each file along its already-existing internal section boundaries. Maintain all public exports unchanged. No logic modifications permitted.

---

## File 1: `backend/services/wanted_scanner.py` (1190 LOC)

### Logical Sections

| Lines | Section | Responsibility |
|-------|---------|----------------|
| 1–104 | Module-level helpers | `get_scanner()`, `invalidate_scanner()`, Flask extension helpers (`_has_flask_app_context`, `_get_flask_extension`, etc.) |
| 106–897 | `WantedScanner` class | Scan logic (`scan_all`, `scan_series`, `scan_movie`, `_scan_sonarr`, `_scan_radarr`, `_scan_standalone`, `_cleanup`, `_batch_probe`, `_maybe_auto_extract`, `_scan_sonarr_series`, `_scan_radarr_movie`) |
| 902–1094 | `WantedScanner.search_all` + `cancel_search` | Provider search engine: backoff filtering, embedded extraction, parallel ThreadPoolExecutor dispatch |
| 1100–1191 | `WantedScanner` scheduler methods | `start_scheduler`, `stop_scheduler`, `_schedule_next_scan`, `_run_scan_with_context`, `_run_search_with_context`, `_scheduled_scan`, `_schedule_next_search`, `_scheduled_search` |

### Natural Split Points

Three focused modules fit within the limit:

**`wanted_scanner_scan.py`** (~500 LOC) — `WantedScanner` class with all scan methods. This is the core. `scan_all`, `force_full_scan`, `scan_series`, `scan_movie`, `_scan_sonarr`, `_scan_radarr`, `_scan_standalone`, `_cleanup`, `_batch_probe`, `_maybe_auto_extract`, `_scan_sonarr_series`, `_scan_radarr_movie`. State attributes stay here because they are all scan-state.

**`wanted_scanner_search.py`** (~200 LOC) — `search_all` and `cancel_search` logic. These can either live as standalone functions that accept a scanner instance, or as a mixin. Given the class is a singleton, the cleanest approach is to keep them on `WantedScanner` but extract to a mixin file that `wanted_scanner_scan.py` inherits from.

**`wanted_scanner.py`** (~100 LOC, kept as public entrypoint) — Module-level singleton helpers (`get_scanner`, `invalidate_scanner`, Flask extension helpers), scheduler methods, the `WantedScanner` class definition line (importing from the split files). All external callers import from `wanted_scanner` — this file must remain and re-export everything.

### Safer Alternative: 2-Module Split

Given the search and scheduler methods are tightly coupled to `WantedScanner`'s state (`_search_lock`, `_cancel_event`, `_socketio`, `_app`), the safest split that avoids mixin complexity is:

- **`wanted_scanner_core.py`** (~900 LOC): Full `WantedScanner` class with all scan + search + scheduler methods. Reduces `wanted_scanner.py` to ~250 LOC (module helpers only, `class WantedScanner(WantedScannerCore): pass` re-export).
- **`wanted_scanner.py`** (~250 LOC): Singleton factory + Flask extension helpers + imports from core.

This gives ~900 and ~250 LOC — both under 1000. If 3-way is needed: extract the search logic (lines 902–1094) into a `_WantedSearchMixin` in `wanted_scanner_search.py`.

### External Callers (must not break)

All callers import exactly:
- `from services.wanted_scanner import get_scanner` — 8 call sites
- `from services.wanted_scanner import invalidate_scanner` — 2 call sites

No caller imports `WantedScanner` directly. The singleton facade pattern means `wanted_scanner.py` can contain just the factory functions and import the class from a sibling.

### Safest Split Strategy

1. Create `backend/services/wanted_scanner_core.py` with the full `WantedScanner` class (lines 106–1191 of the current file).
2. Rewrite `wanted_scanner.py` to: keep all module-level docstring and `FULL_SCAN_INTERVAL` constant, keep `get_scanner`/`invalidate_scanner` and Flask helpers, do `from services.wanted_scanner_core import WantedScanner` at the top.
3. All external imports (`from services.wanted_scanner import get_scanner`) continue to work unchanged.

### Existing Pattern Reference

`backend/routes/wanted/` splits into `__init__.py`, `list.py`, `search.py`, `extract.py`, `providers.py` — all route methods are in separate files, the `__init__.py` registers them.

---

## File 2: `backend/config.py` (1101 LOC)

### Logical Sections

| Lines | Section | Responsibility |
|-------|---------|----------------|
| 1–17 | Imports | `hashlib`, `logging`, `os`, `threading`, Pydantic |
| 18–517 | `Settings` class | All 100+ setting fields + `get_database_url()`, `get_prompt_template()`, `get_target_patterns()`, `get_translation_config_hash()`, `get_safe_config()`, grouped `@property` views |
| 519–729 | `_SettingsView` + 5 view classes | `GeneralSettings`, `TranslationSettings`, `ProviderSettings`, `MediaServerSettings`, `ScanningSettings` |
| 732–767 | `map_path()` | Path mapping logic |
| 770–914 | `_LANGUAGE_TAGS` dict + `SUPPORTED_LANGUAGES` list | 60+ language entries |
| 912–976 | `get_settings()`, `reload_settings()` | Singleton + DB-override reload |
| 979–1101 | `get_sonarr_instances()`, `get_radarr_instances()`, `is_standalone_mode()`, `get_media_server_instances()` | Instance resolution helpers |

### What NOT to Split

`Settings` class and `_SettingsView` subclasses **must stay together** in `config.py` because:
- Every backend file imports `from config import get_settings` — dozens of callers
- `Settings` is a Pydantic `BaseSettings` with `model_config` — splitting it would require maintaining a single Pydantic class or creating cross-file inheritance
- The view classes are small and tightly coupled to `Settings` fields

The "validation logic extraction" task means pulling out:
1. `_LANGUAGE_TAGS` + `SUPPORTED_LANGUAGES` + `_get_language_tags()` → `config_language_data.py`
2. Instance helper functions (lines 979–1101) → `config_instances.py`
3. `map_path()` may stay in `config.py` since it calls `get_settings()` and is used by `wanted_scanner` directly

### Proposed Split

**`config.py`** (~750 LOC, reduced from 1101):
- All imports
- `Settings` class (all fields + methods)
- `_SettingsView` + all 5 view classes
- `map_path()`
- `get_settings()`, `reload_settings()`
- Import `SUPPORTED_LANGUAGES`, `_LANGUAGE_TAGS`, `_get_language_tags` from sibling for backwards compat

**`config_language_data.py`** (~180 LOC):
- `_LANGUAGE_TAGS` dict
- `SUPPORTED_LANGUAGES` list
- `_get_language_tags()` helper function

**`config_instances.py`** (~130 LOC):
- `get_sonarr_instances()`
- `get_radarr_instances()`
- `is_standalone_mode()`
- `get_media_server_instances()`

### External Callers

Currently callers import from `config` module:
- `from config import get_settings` — ~40 call sites. Must stay in `config.py`.
- `from config import get_sonarr_instances` — only in `wanted_scanner.py` (deferred import inside method), `app.py`, `sonarr_client.py`
- `from config import get_radarr_instances` — similar pattern
- `from config import is_standalone_mode` — `app.py`, `wanted_scanner.py`
- `from config import get_media_server_instances` — `mediaserver/__init__.py`
- `from config import map_path` — `wanted_scanner.py`, `translator.py`
- `from config import SUPPORTED_LANGUAGES` — used in frontend API response; `routes/config.py` exports it
- `from config import _get_language_tags` — Settings internal methods only (prefixed `_`, private)

**Backwards compatibility strategy:** `config.py` must re-export everything from the new sibling files:
```python
from config_language_data import _LANGUAGE_TAGS, SUPPORTED_LANGUAGES, _get_language_tags
from config_instances import get_sonarr_instances, get_radarr_instances, is_standalone_mode, get_media_server_instances
```
This ensures zero changes to any caller.

---

## File 3: `frontend/src/pages/Settings/AdvancedTab.tsx` (1306 LOC)

### Logical Sections

| Lines | Section | Exported As |
|-------|---------|-------------|
| 1–19 | Imports | — |
| 20–424 | `LanguageProfilesTab` component | `export function LanguageProfilesTab()` |
| 426–828 | `LibrarySourcesTab` component | `export function LibrarySourcesTab(...)` |
| 830–1103 | `BackupTab` component | `export function BackupTab()` |
| 1105–1304 | `SubtitleToolsTab` component | `export function SubtitleToolsTab()` |

### Each Section is Already Independent

Each of the four exported functions has entirely different:
- State (no shared `useState`)
- API hooks (no shared mutations)
- Imports (the file imports a superset of all four)

The components share no logic. `AdvancedTab.tsx` is just a bundling file.

### Split Strategy

Create four new files, each containing exactly one exported component:

| New File | Content | Approx LOC |
|----------|---------|------------|
| `LanguageProfilesTab.tsx` | `LanguageProfilesTab` | ~400 |
| `LibrarySourcesTab.tsx` | `LibrarySourcesTab` | ~400 |
| `BackupTab.tsx` | `BackupTab` | ~275 |
| `SubtitleToolsTab.tsx` | `SubtitleToolsTab` | ~200 |

**`AdvancedTab.tsx` becomes a re-export barrel** (6 lines):
```typescript
export { LanguageProfilesTab } from './LanguageProfilesTab'
export { LibrarySourcesTab } from './LibrarySourcesTab'
export { BackupTab } from './BackupTab'
export { SubtitleToolsTab } from './SubtitleToolsTab'
```

### External Callers (all lazy-import via barrel)

- `LegacySettings.tsx` lazy-imports all four: `import('./AdvancedTab').then(m => ({ default: m.LanguageProfilesTab }))` etc. — these continue to work since the barrel re-exports.
- `frontend/src/pages/LanguageProfiles.tsx` lazy-imports `LanguageProfilesTab` from `./Settings/AdvancedTab` — continues to work.
- `AdvancedTab.tsx` imports `type { FieldConfig } from './LegacySettings'` — move this import to `LibrarySourcesTab.tsx` only (it's the only consumer that uses `FieldConfig`).

### Shared Imports to Assign

Each new file gets its own imports. The current shared import list splits naturally:
- `useLanguageProfiles`, `useCreateProfile`, etc. → `LanguageProfilesTab.tsx`
- `useWatchedFolders`, `useSaveWatchedFolder`, `useTriggerStandaloneScan`, `useStandaloneStatus` → `LibrarySourcesTab.tsx`
- `useFullBackups`, `useCreateFullBackup`, `useRestoreFullBackup`, `useConfig`, `useUpdateConfig` → `BackupTab.tsx`
- `useSubtitleTool`, `usePreviewSubtitle` → `SubtitleToolsTab.tsx`
- Icons are split per file — only import what each component uses.

---

## File 4: `frontend/src/pages/Wanted.tsx` (1260 LOC)

### Logical Sections

| Lines | Section | Purpose |
|-------|---------|---------|
| 1–31 | Imports | All hooks, components, types |
| 32–74 | `formatRetryCountdown`, `FailureReasonRow` | Utility function + small display component (already exported) |
| 76–80 | `deriveSubtitlePath` | Utility function (private) |
| 82–113 | Constants: `STATUS_FILTERS`, `TYPE_FILTERS`, `SUBTITLE_TYPE_FILTERS`, `WANTED_FILTERS`, `SORT_FIELDS` | Filter/sort config |
| 114–148 | `SummaryCard`, `ScoreBadge` | Small pure display components (private) |
| 150–263 | `SearchResultsRow` | Provider search results inline table (private) |
| 265–1260 | `WantedPage` | Main page component |
| (within WantedPage) 494–683 | Toolbar section | Header, scan/search/cleanup/translate buttons |
| (within WantedPage) 686–893 | Filter panel | Status/type/subtitle type/language/upgrade filter rows + search + sort |
| (within WantedPage) 895–1197 | Table + row rendering | Table, row map with inline action buttons |
| (within WantedPage) 1199–1259 | Modals | BatchActionBar, SubtitleEditorModal, InteractiveSearchModal, CleanupConfirmDialog |

### Extraction Strategy

The Wanted page is one large `WantedPage` function that cannot be trivially split without prop-drilling. The following subcomponents can be extracted:

**`WantedToolbar.tsx`** (~80 LOC):
```typescript
interface WantedToolbarProps {
  onRefresh: () => void
  onBatchSearch: () => void
  onBatchProbe: () => void
  onCleanup: () => void
  onBatchTranslate: () => void
  isRefreshing: boolean
  isScanning: boolean
  isBatchRunning: boolean
  isProbeRunning: boolean
  translationEnabled: boolean
  summary: { scan_running?: boolean } | undefined
}
export function WantedToolbar(props: WantedToolbarProps) { ... }
```

**`WantedFilterPanel.tsx`** (~200 LOC):
- Status/type/subtitle-type/language/upgrade filter buttons
- Search text input + sort dropdown + sort direction button
- FilterBar + FilterPresetMenu
- Props: all filter state values + setters + available options
- Note: `handleFiltersChange` callback must be lifted or passed as prop

**`WantedTableRow.tsx`** (~150 LOC):
- A single wanted item row with all action buttons
- Props: `item`, `isSelected`, `expandedItem`, `searchingItem`, handlers

The constants (`STATUS_FILTERS`, `SORT_FIELDS`, etc.) and small utilities (`formatRetryCountdown`, `FailureReasonRow`, `SummaryCard`, `ScoreBadge`, `SearchResultsRow`) → `wanted-utils.ts` or `WantedComponents.tsx`.

### Remaining `WantedPage` After Extraction (~600 LOC)

After extracting toolbar (~80 LOC), filter panel (~200 LOC), and row component (~150 LOC), `WantedPage` itself drops to ~600 LOC — under the 800 limit. All state stays in `WantedPage`.

### What NOT to Extract

The batch progress banners (probe, extract, batch) are simple conditional renders inline with local state — not worth extracting.

The `SummaryCard` grid (4 cards, ~20 LOC) stays inline.

### External Callers

`formatRetryCountdown` and `FailureReasonRow` are already exported. Nothing outside `Wanted.tsx` uses `WantedPage`'s internals. The page is registered in `App.tsx` as a lazy route. No risky surface.

---

## File 5: `frontend/src/pages/Settings/LegacySettings.tsx` (1248 LOC)

### Current Architecture

`LegacySettings.tsx` contains:
1. Lazy imports for 20+ tab components (lines 23–50)
2. `TabSkeleton` component (lines 54–65)
3. `NAV_GROUPS` + `TABS` constants (lines 67–116)
4. `FieldConfig` interface + `FIELDS` array with 60+ field definitions (lines 106–275)
5. `PathMappingEditor` component (lines 277–479)
6. `InstanceEditor` component (lines 482–610)
7. `TAB_KEYS` i18n mapping (lines 614–638)
8. `SettingsPage` wrapper + `SettingsPageInner` main component (lines 640–1248)

### Key Discovery: `index.tsx` Already Supersedes `LegacySettings.tsx`

`frontend/src/pages/Settings/index.tsx` is the **actual settings router** used by `App.tsx`. It uses React Router `<Routes>` to dispatch `/settings/*` sub-routes to dedicated page components (`GeneralSettings`, `ConnectionsSettings`, etc.). `SettingsPage` exported from `LegacySettings.tsx` is **still exported from `index.tsx`** but there is a naming collision — **both files export `SettingsPage`**. The one in `index.tsx` wins since it's the barrel.

`LegacySettings.tsx` is **still used for sub-tabs** that haven't been migrated to dedicated route pages. The sub-tab `SettingsPage` inside `LegacySettings.tsx` renders the full sidebar + tab system as a fallback. Most tabs now have dedicated pages but several still render inside `LegacySettings.SettingsPageInner`.

### Tab Migration Status

Tabs that have dedicated `/settings/*` route pages (do NOT render in LegacySettings):
- `GeneralSettings` → `/settings/general`
- `ConnectionsSettings` → `/settings/connections`
- `SubtitlesSettings` → `/settings/subtitles`
- `ProvidersSettings` → `/settings/providers`
- `AutomationSettings` → `/settings/automation`
- `TranslationSettings` → `/settings/translation`
- `NotificationsSettings` → `/settings/notifications`
- `SystemSettings` → `/settings/system`

Tabs that STILL render inside `LegacySettings.SettingsPageInner` (line 998–1239):
- `ApiKeysTab`, `ProvidersTab`, `LanguageProfilesTab`, `PromptPresetsTab`, `TranslationBackendsTab`, `MediaServersTab`, `LibrarySourcesTab`, `WhisperTab`, `EventsHooksTab`, `ScoringTab`, `BackupTab`, `SubtitleToolsTab`, `CleanupTab`, `IntegrationsTab`, `MigrationTab`, `NotificationTemplatesTab`, `SecurityTab`, `ProtokollTab`
- Plus inline renders for: Translation tab (with SettingsCards), General tab (SettingsCards), Sonarr/Radarr tabs (SettingsCards), Automation tab (SettingsCards), Wanted tab (SettingsCards)

### Does Tab-Based URL Routing Break Existing Links?

The existing `/settings/*` routes in `App.tsx` already exist and are live. Adding more sub-routes (e.g., `/settings/providers/api-keys`) would NOT break the existing deep links from `settingsRegistry.ts`. Any remaining tabs in `LegacySettings.SettingsPageInner` that do not have URL routes are accessed only by clicking the sidebar — they have no deep-linkable URL currently.

Tests in `__tests__/` confirm no test directly imports `LegacySettings.tsx` — all tests import from their specific dedicated page files (`AutomationSettings.test.tsx` imports `AutomationSettings`, etc.).

### Split Strategy for LegacySettings.tsx

The safest reduction is to extract the two large private components and the `FIELDS` data:

**Option A: Extract FIELDS + inline render helpers (safest, -300 LOC)**
- `settingsFields.ts` — `FIELDS` array (lines 117–275, ~160 LOC) + `FieldConfig` interface, `NAV_GROUPS`, `TABS`, `TAB_KEYS`
- `PathMappingEditor.tsx` — `PathMappingEditor` component (~200 LOC)
- `InstanceEditor.tsx` — `InstanceEditor` component (~130 LOC)
- `LegacySettings.tsx` drops to ~700 LOC

**Option B: Extract FIELDS data + split remaining inline tab renders into dedicated files**
- Extract `FIELDS` to `settingsFields.ts`
- `SonarrSettings.tsx` — Sonarr/Radarr tab content (~80 LOC)
- `AutomationTabContent.tsx` — Automation settings cards (~80 LOC)
- This brings `LegacySettings.tsx` to ~700 LOC with all sub-component extractions

**Recommendation: Option A**. It extracts the data (where bugs hide) and the two reusable components (PathMapping, InstanceEditor appear in multiple tabs). Option B risks regression in the complex `SettingsPageInner` conditional render chain.

### Exports That Must Stay in `LegacySettings.tsx`

`index.tsx` re-exports from `LegacySettings.tsx`:
```typescript
export { NAV_GROUPS } from './LegacySettings'
export type { FieldConfig } from './LegacySettings'
```
These must remain exported from `LegacySettings.tsx` (or be re-exported through it).

`AdvancedTab.tsx` imports:
```typescript
import type { FieldConfig } from './LegacySettings'
```
After split, `FieldConfig` moves to `settingsFields.ts`, but `LegacySettings.tsx` must re-export it.

---

## Architecture Patterns

### Python: Package-Based Splitting

Existing pattern: `routes/wanted/` contains `__init__.py`, `list.py`, `search.py`, `extract.py`, `providers.py`. Each file exports route handler functions. `__init__.py` registers all blueprints.

For services: keep a thin `wanted_scanner.py` as facade, extract class to `wanted_scanner_core.py`. No package directory needed since there's only one class.

For config: keep `config.py` as facade with re-exports, extract data constants and helper functions to siblings.

### TypeScript: Barrel Re-Export Pattern

Existing pattern: `AdvancedTab.tsx` itself lazy-imports from `TranslationTab.tsx`, `EventsTab.tsx`, etc. Each of those files exports multiple named components. The consumer always imports via the barrel name, not the internal file.

```typescript
// Before: everything in AdvancedTab.tsx
export function LanguageProfilesTab() { ... } // 400 lines
export function BackupTab() { ... } // 275 lines

// After: barrel re-exports
export { LanguageProfilesTab } from './LanguageProfilesTab'
export { BackupTab } from './BackupTab'
```

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Checking all callers of a module | Manual grep | See caller list in this doc | Already researched |
| Pydantic model splitting | Multiple BaseSettings classes | Re-export from facade `config.py` | Pydantic Settings singleton must be a single class |
| React lazy import paths | Rewriting all import strings | Keep barrel file, lazy imports resolve through it | Zero caller changes |

---

## Common Pitfalls

### Pitfall 1: Breaking Pydantic Settings
**What goes wrong:** Moving fields out of `Settings(BaseSettings)` class into a separate file causes Pydantic to fail to load env vars for those fields.
**Why it happens:** Pydantic reads all fields from the class body at import time. Subclassing or composing splits the env-loading contract.
**How to avoid:** Keep ALL Pydantic field definitions in a single `Settings(BaseSettings)` class in `config.py`. Only move non-Pydantic data (`_LANGUAGE_TAGS`, helper functions) to sibling files.

### Pitfall 2: Circular Import in config_instances.py
**What goes wrong:** `config_instances.py` imports `get_settings()`, but `config.py` imports from `config_instances.py`. Python circular import error.
**Why it happens:** `get_settings()` returns a `Settings` instance, and `config_instances.py` functions call `get_settings()`.
**How to avoid:** `config.py` imports from `config_language_data.py` (no circular dep). `config_instances.py` imports `get_settings` from `config.py` (one-way). `config.py` then re-exports `get_sonarr_instances` etc. by importing `config_instances.py` AFTER defining `get_settings`. Standard Python allows this as long as the circular import is not at module parse time. Alternatively, do a local import inside each helper function: `def get_sonarr_instances(): from config import get_settings; s = get_settings()...`.

### Pitfall 3: LegacySettings Double SettingsPage Export
**What goes wrong:** Both `LegacySettings.tsx` and `index.tsx` export `SettingsPage`. The one in `index.tsx` is the live one. If someone imports `SettingsPage` from `LegacySettings` directly, they get the old tab-based UI.
**How to avoid:** Do not rename or remove `SettingsPage` from `LegacySettings.tsx`. The `index.tsx` override is intentional.

### Pitfall 4: AdvancedTab Barrel Breaks Lazy Import Path
**What goes wrong:** `LegacySettings.tsx` line 37: `import('./AdvancedTab').then(m => ({ default: m.LanguageProfilesTab }))`. If the barrel doesn't re-export `LanguageProfilesTab`, the lazy import will get `undefined`.
**How to avoid:** The barrel `AdvancedTab.tsx` must re-export all four components. Test each lazy import after split.

### Pitfall 5: WantedScanner Mixin State Access
**What goes wrong:** If `search_all` is extracted to a mixin or separate file, it references `self._searching`, `self._cancel_event`, `self._search_lock`, `self._socketio`. If the mixin is instantiated separately, these don't exist.
**How to avoid:** Use the simpler 2-file split: move the full `WantedScanner` class to `wanted_scanner_core.py`, keep only singleton helpers in `wanted_scanner.py`. No mixin needed.

---

## Code Examples

### Python Facade Pattern (wanted_scanner.py after split)
```python
# Source: routes/wanted/__init__.py pattern
"""Wanted subtitle scanner — public facade.

All external callers import from this module. Implementation lives in
wanted_scanner_core.py.
"""
from services.wanted_scanner_core import WantedScanner  # noqa: F401

FULL_SCAN_INTERVAL = 6  # Keep constant here for external tests

_scanner = None
_scanner_lock = threading.Lock()

def get_scanner() -> WantedScanner:
    ...  # unchanged singleton logic

def invalidate_scanner() -> None:
    ...  # unchanged
```

### TypeScript Barrel Pattern (AdvancedTab.tsx after split)
```typescript
// Source: existing pattern in Settings directory
// All lazy-import consumers continue to work unchanged
export { LanguageProfilesTab } from './LanguageProfilesTab'
export { LibrarySourcesTab } from './LibrarySourcesTab'
export { BackupTab } from './BackupTab'
export { SubtitleToolsTab } from './SubtitleToolsTab'
```

### Python Re-Export in config.py (backwards compat)
```python
# At bottom of config.py after defining get_settings():
from config_language_data import _LANGUAGE_TAGS, SUPPORTED_LANGUAGES, _get_language_tags  # noqa: F401, E402
from config_instances import (  # noqa: F401, E402
    get_sonarr_instances,
    get_radarr_instances,
    is_standalone_mode,
    get_media_server_instances,
)
```

---

## State of the Art

| Old Approach | Current Approach | Impact |
|--------------|------------------|--------|
| Monolithic service file | Thin facade + extracted class file | All callers unchanged |
| Monolithic tab component file | Barrel re-export + dedicated tab files | All lazy-imports unchanged |
| Inline config data + helpers | Separate data module re-exported from config | Keeps Pydantic class intact |

---

## Open Questions

1. **`SettingsPageInner` in LegacySettings.tsx — is it still used?**
   - What we know: `index.tsx` is the actual route handler. `LegacySettings.SettingsPage` is exported but `index.tsx` overrides it via its own `SettingsPage` export.
   - What's unclear: Whether any remaining tab (`ApiKeysTab`, `Whisper`, etc.) has no dedicated settings route, meaning `SettingsPageInner` is still the render path for those tabs.
   - Recommendation: Before splitting, verify by navigating to e.g. `/settings/api-keys` — if it 404s or redirects, the old `SettingsPageInner` is still active for those tabs. This is **critical before any LegacySettings split**.

2. **`FIELDS` array usage in new dedicated settings pages**
   - What we know: `FIELDS` is used inside `SettingsPageInner.renderField()` and passed to `LibrarySourcesTab`. The new `AutomationSettings.tsx`, `ConnectionsSettings.tsx`, etc. likely have their OWN field definitions.
   - What's unclear: Whether `FIELDS` is duplicated or still imported from `LegacySettings` in the new pages.
   - Recommendation: Check each new settings page file for `FIELDS` imports before splitting.

---

## Sources

### Primary (HIGH confidence)
- Direct file reads of all five target files (confirmed line-by-line)
- `grep` analysis of all external callers for `wanted_scanner.py` (8 + 2 imports)
- `grep` analysis of all external callers for `config.py` helper functions
- `grep` analysis of all importers of `LegacySettings.tsx` and `AdvancedTab.tsx`
- `frontend/src/pages/Settings/index.tsx` — confirmed it is the active router
- `frontend/src/App.tsx` — confirmed routing structure

### Secondary (MEDIUM confidence)
- Existing codebase split patterns: `routes/wanted/`, `routes/system/`, `TranslationTab.tsx`
- Test file listing confirming no tests import `LegacySettings.tsx` directly

---

## Metadata

**Confidence breakdown:**
- File structures and line ranges: HIGH — directly read
- External caller lists: HIGH — grep-verified
- Circular import risk in config split: MEDIUM — inferred from Python import rules, not runtime-tested
- LegacySettings "still active" question: LOW — requires runtime navigation test to confirm

**Research date:** 2026-04-03
**Valid until:** 2026-05-03 (stable codebase, no external libraries involved)
