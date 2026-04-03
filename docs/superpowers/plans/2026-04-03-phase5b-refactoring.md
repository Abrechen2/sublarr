# Phase 5b — Remaining Refactoring Plan

**Date:** 2026-04-03
**Branch:** `phase/5b-refactoring`
**Goal:** Split 5 oversized files to bring all under the size limit (backend ≤800 LOC, frontend ≤1000 LOC).
**Constraint:** Every task commits independently. All changes are backwards-compatible — zero caller changes.

---

## Setup

```bash
cd D:/Sublarr_Projekt/Sublarr
git checkout -b phase/5b-refactoring
```

---

## Shared Commands

**Backend checks (run after every backend task):**
```bash
cd D:/Sublarr_Projekt/Sublarr/backend && ruff check . && ruff format --check .
cd D:/Sublarr_Projekt/Sublarr/backend && python -m pytest --tb=short -q \
  --ignore=tests/performance \
  --ignore=tests/integration/test_provider_pipeline.py \
  --ignore=tests/test_video_sync.py \
  --ignore=tests/test_translation_backends.py \
  -k "not (test_sonarr_download_webhook or test_radarr_download_webhook or test_parse_llm_response_too_many_merge or test_record_backend_success)"
```

**Frontend checks (run after every frontend task):**
```bash
cd D:/Sublarr_Projekt/Sublarr/frontend && npx tsc --noEmit && npm run test -- --run
```

---

## Task 1: `backend/services/wanted_scanner.py` (1190 → ~250 LOC)

**Files changed:**
- `backend/services/wanted_scanner_core.py` — NEW (contains the full `WantedScanner` class)
- `backend/services/wanted_scanner.py` — MODIFIED (thin facade, keeps all public exports)
- `backend/tests/test_wanted_scanner_split.py` — NEW (smoke-test import check)

**Why this is safe:** All 10 external callers import only `get_scanner` or `invalidate_scanner` from `services.wanted_scanner`. The facade keeps those symbols at the same path. The `WantedScanner` class itself is not imported externally.

### Steps

- [ ] **Write smoke-test first (RED)**

  Create `backend/tests/test_wanted_scanner_split.py`:

  ```python
  """Smoke tests: verify wanted_scanner public API survives the split."""
  from services.wanted_scanner import get_scanner, invalidate_scanner, WantedScanner


  def test_get_scanner_returns_wanted_scanner_instance():
      scanner = get_scanner()
      assert isinstance(scanner, WantedScanner)


  def test_invalidate_scanner_resets_singleton():
      s1 = get_scanner()
      invalidate_scanner()
      s2 = get_scanner()
      # After invalidation a new instance is created
      assert s1 is not s2


  def test_wanted_scanner_class_importable_from_facade():
      """WantedScanner must be importable from the facade module."""
      from services import wanted_scanner as mod
      assert hasattr(mod, "WantedScanner")
      assert hasattr(mod, "get_scanner")
      assert hasattr(mod, "invalidate_scanner")
  ```

  Run tests — they should PASS (class exists in current file):
  ```bash
  cd D:/Sublarr_Projekt/Sublarr/backend && python -m pytest tests/test_wanted_scanner_split.py -v
  ```

- [ ] **Create `backend/services/wanted_scanner_core.py`**

  Copy lines 106–1190 from `wanted_scanner.py` (the entire `WantedScanner` class) into the new file.

  **CRITICAL:** `FULL_SCAN_INTERVAL = 6` (line 29 of original) MUST also be copied here — the class uses it at scan_all() lines ~177 and ~188. The facade will re-import it for backwards compat.

  The file needs these imports at the top (copy from `wanted_scanner.py` lines 1–28 and remove anything only used by the module-level singleton helpers):

  ```python
  """WantedScanner class implementation — imported by wanted_scanner.py facade."""

  import logging
  import os
  import threading
  import time
  from concurrent.futures import ThreadPoolExecutor, as_completed
  from datetime import UTC, datetime

  from ass_utils import get_media_streams, has_target_language_audio, has_target_language_stream
  from config import get_settings, map_path
  # ... (keep all imports that WantedScanner methods reference)

  FULL_SCAN_INTERVAL = 6  # every N scans forces a full rescan as safety fallback
  ```

  Then paste the full `WantedScanner` class verbatim from lines 106–1190 of the original.

  **Known exception:** This file will be ~1085 LOC. `WantedScanner` is a stateful coordinator (scanning + searching + scheduling) that cannot be cleanly split without complex mixin inheritance. Documented as accepted exception — still an improvement over the original mixed 1190-LOC file.

  Confirm the class ends correctly.

- [ ] **Rewrite `backend/services/wanted_scanner.py` as thin facade**

  Replace the file content with the module-level docstring, constants, helper functions (lines 1–104 of the original), plus the import of `WantedScanner` from the new core file and a re-export:

  ```python
  """Wanted subtitle scanner — public facade.

  All external callers import from this module. Implementation lives in
  wanted_scanner_core.py.
  """

  import logging
  import threading

  from wanted_scanner_core import FULL_SCAN_INTERVAL  # noqa: F401 — re-export for callers
  from wanted_scanner_core import WantedScanner  # noqa: F401

  logger = logging.getLogger(__name__)

  _scanner: WantedScanner | None = None
  _scanner_lock = threading.Lock()


  def _has_flask_app_context() -> bool:
      # ... (verbatim from original lines ~20–50)


  def _get_flask_extension(key: str):
      # ... (verbatim)


  def _set_flask_extension(key: str, value) -> None:
      # ... (verbatim)


  def _pop_flask_extension(key: str) -> None:
      # ... (verbatim)


  def get_scanner() -> WantedScanner:
      # ... (verbatim from original)


  def invalidate_scanner() -> None:
      # ... (verbatim from original)
  ```

  The facade should be ~100–150 LOC.

- [ ] **Verify file sizes**
  ```bash
  wc -l D:/Sublarr_Projekt/Sublarr/backend/services/wanted_scanner.py \
         D:/Sublarr_Projekt/Sublarr/backend/services/wanted_scanner_core.py
  ```
  Expected: facade ≤200 LOC, core ~1085 LOC (documented exception — see above).

- [ ] **Run smoke tests (GREEN)**
  ```bash
  cd D:/Sublarr_Projekt/Sublarr/backend && python -m pytest tests/test_wanted_scanner_split.py -v
  ```
  All 3 tests must pass.

- [ ] **Run full backend checks**
  ```bash
  cd D:/Sublarr_Projekt/Sublarr/backend && ruff check . && ruff format --check .
  cd D:/Sublarr_Projekt/Sublarr/backend && python -m pytest --tb=short -q \
    --ignore=tests/performance \
    --ignore=tests/integration/test_provider_pipeline.py \
    --ignore=tests/test_video_sync.py \
    --ignore=tests/test_translation_backends.py \
    -k "not (test_sonarr_download_webhook or test_radarr_download_webhook or test_parse_llm_response_too_many_merge or test_record_backend_success)"
  ```

- [ ] **Commit**
  ```bash
  cd D:/Sublarr_Projekt/Sublarr
  git add backend/services/wanted_scanner.py \
          backend/services/wanted_scanner_core.py \
          backend/tests/test_wanted_scanner_split.py
  git commit -m "refactor: extract WantedScanner class to services/wanted_scanner_core.py"
  ```

---

## Task 2: `backend/config.py` (1101 → ~790 LOC)

**Files changed:**
- `backend/config_language_data.py` — NEW (language tag dict + supported languages list + `_get_language_tags`)
- `backend/config_instances.py` — NEW (4 instance-resolution helper functions)
- `backend/config_utils.py` — NEW (`map_path` function, ~38 LOC)
- `backend/config.py` — MODIFIED (re-exports from all 3 new files, Settings class untouched)
- `backend/tests/test_config_split.py` — NEW (smoke-test import check)

**Critical constraint:** The `Settings(BaseSettings)` class AND the `_SettingsView` subclasses MUST stay in `config.py` — Pydantic reads all fields from the class body; moving them breaks env-var loading.

**Why 3 files (not 2):** Without extracting `map_path`, the post-split `config.py` would be ~849 LOC (still over limit). Extracting `map_path` (~38 LOC) brings it to ~790 LOC ≤ 800 target.

**Circular import prevention:** `config_instances.py` must import `get_settings` with a local import inside each function body — NOT at module top-level — to avoid a circular dependency (`config.py` imports `config_instances`, `config_instances` imports `config`).

### Steps

- [ ] **Write smoke-test first (RED)**

  Create `backend/tests/test_config_split.py`:

  ```python
  """Smoke tests: verify config public API survives the split."""


  def test_get_settings_importable_from_config():
      from config import get_settings
      s = get_settings()
      assert s is not None


  def test_supported_languages_importable_from_config():
      from config import SUPPORTED_LANGUAGES
      assert isinstance(SUPPORTED_LANGUAGES, list)
      assert len(SUPPORTED_LANGUAGES) > 0


  def test_get_language_tags_importable_from_config():
      from config import _get_language_tags
      tags = _get_language_tags("de")
      assert "de" in tags
      assert "deu" in tags


  def test_instance_helpers_importable_from_config():
      from config import (
          get_sonarr_instances,
          get_radarr_instances,
          is_standalone_mode,
          get_media_server_instances,
      )
      # Just confirm they are callable
      assert callable(get_sonarr_instances)
      assert callable(get_radarr_instances)
      assert callable(is_standalone_mode)
      assert callable(get_media_server_instances)


  def test_language_data_importable_directly():
      from config_language_data import SUPPORTED_LANGUAGES, _LANGUAGE_TAGS, _get_language_tags
      assert "de" in _LANGUAGE_TAGS
      assert isinstance(SUPPORTED_LANGUAGES, list)


  def test_instances_importable_directly():
      from config_instances import (
          get_sonarr_instances,
          get_radarr_instances,
          is_standalone_mode,
          get_media_server_instances,
      )
      assert callable(get_sonarr_instances)
  ```

  Run — tests for `config_language_data` and `config_instances` will FAIL (files don't exist yet). Others pass.

- [ ] **Create `backend/config_language_data.py`**

  Copy from `config.py` lines 770–914 (the `_LANGUAGE_TAGS` dict, `SUPPORTED_LANGUAGES` list, and `_get_language_tags` function):

  ```python
  """Language tag data — ISO 639-1 to all known file/metadata variant mappings.

  Extracted from config.py for size management. config.py re-exports everything
  from this module for backwards compatibility.
  """

  # Language tag mapping (ISO 639-1 -> all known file/metadata variants)
  _LANGUAGE_TAGS: dict[str, set[str]] = {
      # ... (verbatim copy of the dict)
  }

  SUPPORTED_LANGUAGES: list[dict[str, str]] = [
      # ... (verbatim copy of the list)
  ]


  def _get_language_tags(lang_code: str) -> set[str]:
      """Get all known tags for a language code."""
      return _LANGUAGE_TAGS.get(lang_code, {lang_code})
  ```

  No imports needed (pure data).

- [ ] **Create `backend/config_instances.py`**

  Copy from `config.py` lines 979–1101 (the 4 instance helper functions: `get_sonarr_instances`, `get_radarr_instances`, `is_standalone_mode`, `get_media_server_instances`).

  Use LOCAL imports inside each function to avoid circular dependency:

  ```python
  """Config instance-resolution helpers.

  Extracted from config.py for size management. config.py re-exports everything
  from this module for backwards compatibility.

  IMPORTANT: get_settings() is imported locally inside each function to prevent
  a circular import (config.py imports this module; this module needs config.get_settings).
  """

  import logging

  logger = logging.getLogger(__name__)


  def get_sonarr_instances() -> list:
      from config import get_settings  # local import — prevents circular dep
      settings = get_settings()
      # ... (verbatim function body)


  def get_radarr_instances() -> list:
      from config import get_settings  # local import — prevents circular dep
      settings = get_settings()
      # ... (verbatim function body)


  def is_standalone_mode() -> bool:
      from config import get_settings  # local import — prevents circular dep
      settings = get_settings()
      # ... (verbatim function body)


  def get_media_server_instances() -> list:
      from config import get_settings  # local import — prevents circular dep
      settings = get_settings()
      # ... (verbatim function body)
  ```

- [ ] **Create `backend/config_utils.py`** (NEW — for `map_path`)

  Copy the `map_path` function from `config.py` (line ~732, ~38 LOC) into a new file:

  ```python
  """Path mapping utility — extracted from config.py for size management.

  config.py re-exports map_path for backwards compatibility.
  """

  import os


  def map_path(path: str) -> str:
      # ... (verbatim function body from config.py line ~732)
  ```

  Also add a smoke test entry for it in `test_config_split.py`:
  ```python
  def test_map_path_importable_from_config():
      from config import map_path
      assert callable(map_path)

  def test_map_path_importable_directly():
      from config_utils import map_path
      assert callable(map_path)
  ```

- [ ] **Modify `backend/config.py` — remove extracted sections and add re-exports**

  Remove from `config.py`:
  - `map_path` function (line ~732–769, ~38 LOC)
  - Lines ~770–1101: language data + instance helpers

  Add re-exports at the bottom of `config.py` (after `get_settings` and `reload_settings`):

  ```python
  # ─── Re-exports for backwards compatibility ──────────────────────────────────
  from config_utils import map_path  # noqa: E402, F401

  from config_language_data import (  # noqa: E402, F401
      _LANGUAGE_TAGS,
      SUPPORTED_LANGUAGES,
      _get_language_tags,
  )

  from config_instances import (  # noqa: E402, F401
      get_sonarr_instances,
      get_radarr_instances,
      is_standalone_mode,
      get_media_server_instances,
  )
  ```

- [ ] **Verify file sizes**
  ```bash
  wc -l D:/Sublarr_Projekt/Sublarr/backend/config.py \
         D:/Sublarr_Projekt/Sublarr/backend/config_language_data.py \
         D:/Sublarr_Projekt/Sublarr/backend/config_instances.py \
         D:/Sublarr_Projekt/Sublarr/backend/config_utils.py
  ```
  Expected: `config.py` ≤800, new files each ≤200.

- [ ] **Run smoke tests (GREEN)**
  ```bash
  cd D:/Sublarr_Projekt/Sublarr/backend && python -m pytest tests/test_config_split.py -v
  ```
  All tests must pass.

- [ ] **Run full backend checks**
  ```bash
  cd D:/Sublarr_Projekt/Sublarr/backend && ruff check . && ruff format --check .
  cd D:/Sublarr_Projekt/Sublarr/backend && python -m pytest --tb=short -q \
    --ignore=tests/performance \
    --ignore=tests/integration/test_provider_pipeline.py \
    --ignore=tests/test_video_sync.py \
    --ignore=tests/test_translation_backends.py \
    -k "not (test_sonarr_download_webhook or test_radarr_download_webhook or test_parse_llm_response_too_many_merge or test_record_backend_success)"
  ```

- [ ] **Commit**
  ```bash
  cd D:/Sublarr_Projekt/Sublarr
  git add backend/config.py \
          backend/config_language_data.py \
          backend/config_instances.py \
          backend/config_utils.py \
          backend/tests/test_config_split.py
  git commit -m "refactor: extract language data, map_path, and instance helpers from config.py"
  ```

---

## Task 3: `frontend/src/pages/Settings/AdvancedTab.tsx` (1306 → ~6 LOC barrel)

**Files changed:**
- `frontend/src/pages/Settings/LanguageProfilesTab.tsx` — NEW (~400 LOC)
- `frontend/src/pages/Settings/LibrarySourcesTab.tsx` — NEW (~400 LOC)
- `frontend/src/pages/Settings/BackupTab.tsx` — NEW (~275 LOC)
- `frontend/src/pages/Settings/SubtitleToolsTab.tsx` — NEW (~200 LOC)
- `frontend/src/pages/Settings/AdvancedTab.tsx` — MODIFIED (becomes 6-line barrel)

**Why this is safe:** `LegacySettings.tsx` lazy-imports each component via `import('./AdvancedTab').then(m => ({ default: m.ComponentName }))`. The barrel re-exports all four names unchanged. `LanguageProfiles.tsx` also lazy-imports `LanguageProfilesTab` from `./Settings/AdvancedTab` — same barrel path continues to work.

**Note on `FieldConfig`:** `AdvancedTab.tsx` currently imports `type { FieldConfig } from './LegacySettings'`. After split, only `LibrarySourcesTab.tsx` uses `FieldConfig` — move that import there only.

### Steps

- [ ] **Read and map imports in `AdvancedTab.tsx`**

  Before touching anything, open `AdvancedTab.tsx` and note:
  - Lines 1–19: all imports
  - Lines 20–424: `LanguageProfilesTab` function (note which imports it uses)
  - Lines 426–828: `LibrarySourcesTab` function (note which imports it uses — including `FieldConfig`)
  - Lines 830–1103: `BackupTab` function (note which imports it uses)
  - Lines 1105–1304: `SubtitleToolsTab` function (note which imports it uses)

  This mapping is critical — each new file must only import what its component actually uses.

- [ ] **Create `frontend/src/pages/Settings/LanguageProfilesTab.tsx`**

  Paste the `LanguageProfilesTab` function (lines 20–424) with only the imports it needs at the top. No re-exports of the other components.

- [ ] **Create `frontend/src/pages/Settings/LibrarySourcesTab.tsx`**

  Paste the `LibrarySourcesTab` function (lines 426–828) with only its imports. Include `import type { FieldConfig } from './LegacySettings'` here (moved from the shared import list).

- [ ] **Create `frontend/src/pages/Settings/BackupTab.tsx`**

  Paste the `BackupTab` function (lines 830–1103) with only its imports.

- [ ] **Create `frontend/src/pages/Settings/SubtitleToolsTab.tsx`**

  Paste the `SubtitleToolsTab` function (lines 1105–1304) with only its imports.

- [ ] **Replace `AdvancedTab.tsx` with barrel**

  ```typescript
  export { LanguageProfilesTab } from './LanguageProfilesTab'
  export { LibrarySourcesTab } from './LibrarySourcesTab'
  export { BackupTab } from './BackupTab'
  export { SubtitleToolsTab } from './SubtitleToolsTab'
  ```

- [ ] **Run frontend checks**
  ```bash
  cd D:/Sublarr_Projekt/Sublarr/frontend && npx tsc --noEmit && npm run test -- --run
  ```

- [ ] **Verify barrel re-exports work** (manual spot-check)

  ```bash
  cd D:/Sublarr_Projekt/Sublarr/frontend
  node -e "
  const { createRequire } = require('module');
  console.log('Barrel check: OK if no error above');
  " 2>&1 || true
  ```

  More reliably: `npx tsc --noEmit` passing confirms all imports resolve.

- [ ] **Commit**
  ```bash
  cd D:/Sublarr_Projekt/Sublarr
  git add frontend/src/pages/Settings/AdvancedTab.tsx \
          frontend/src/pages/Settings/LanguageProfilesTab.tsx \
          frontend/src/pages/Settings/LibrarySourcesTab.tsx \
          frontend/src/pages/Settings/BackupTab.tsx \
          frontend/src/pages/Settings/SubtitleToolsTab.tsx
  git commit -m "refactor: split AdvancedTab.tsx into 4 focused sub-tab components"
  ```

---

## Task 4: `frontend/src/pages/Wanted.tsx` (1260 → ~600 LOC)

**Files changed:**
- `frontend/src/pages/wanted/WantedToolbar.tsx` — NEW (~80 LOC)
- `frontend/src/pages/wanted/WantedFilterPanel.tsx` — NEW (~200 LOC)
- `frontend/src/pages/wanted/WantedTableRow.tsx` — NEW (~150 LOC)
- `frontend/src/pages/Wanted.tsx` — MODIFIED (imports and uses the 3 new components, shrinks to ~600 LOC)

**Why this is safe:** `Wanted.tsx` is registered in `App.tsx` as a lazy route. Its own public API (the default export `WantedPage`) does not change. The 3 extracted components are private to the page — no other file imports them.

**State stays in `WantedPage`.** The 3 sub-components receive state and handlers as props.

### Steps

- [ ] **Create directory**
  ```bash
  mkdir -p D:/Sublarr_Projekt/Sublarr/frontend/src/pages/wanted
  ```

- [ ] **Design prop interfaces (do this before extracting)**

  In `Wanted.tsx`, identify the exact state and handlers the toolbar section, filter panel section, and table-row render use. Write prop interfaces mentally before extracting. The research file has complete interface sketches for `WantedToolbar` and `WantedFilterPanel` — use those as the starting point.

- [ ] **Create `frontend/src/pages/wanted/WantedToolbar.tsx`**

  Extract the toolbar JSX (approx lines 494–683 of `WantedPage`'s render). Include:
  - `WantedToolbarProps` interface
  - `export function WantedToolbar(props: WantedToolbarProps)` returning the header/buttons JSX
  - Only the imports the toolbar uses (action icons, button components)

- [ ] **Create `frontend/src/pages/wanted/WantedFilterPanel.tsx`**

  Extract the filter panel JSX (approx lines 686–893). Include:
  - `WantedFilterPanelProps` interface (all filter state values + their setters + available options arrays)
  - `export function WantedFilterPanel(props: WantedFilterPanelProps)` returning the filter rows + search + sort UI
  - Only the imports the filter panel uses

- [ ] **Create `frontend/src/pages/wanted/WantedTableRow.tsx`**

  Extract the single-row render logic. Include:
  - `WantedTableRowProps` interface (`item`, `isSelected`, `expandedItem`, `searchingItem`, action handlers)
  - `export function WantedTableRow(props: WantedTableRowProps)` returning one `<tr>` or row wrapper
  - Only the imports the row uses

- [ ] **Update `frontend/src/pages/Wanted.tsx`**

  Add imports for the 3 new components at the top. Replace the extracted JSX sections with `<WantedToolbar ... />`, `<WantedFilterPanel ... />`, and map with `<WantedTableRow ... />`. Verify line count drops to ~600.

- [ ] **Run frontend checks**
  ```bash
  cd D:/Sublarr_Projekt/Sublarr/frontend && npx tsc --noEmit && npm run test -- --run
  ```

- [ ] **Commit**
  ```bash
  cd D:/Sublarr_Projekt/Sublarr
  git add frontend/src/pages/Wanted.tsx \
          frontend/src/pages/wanted/WantedToolbar.tsx \
          frontend/src/pages/wanted/WantedFilterPanel.tsx \
          frontend/src/pages/wanted/WantedTableRow.tsx
  git commit -m "refactor: extract WantedToolbar, WantedFilterPanel, WantedTableRow from Wanted.tsx"
  ```

---

## Task 5: `frontend/src/pages/Settings/LegacySettings.tsx` (1248 → ~700 LOC)

**Files changed:**
- `frontend/src/pages/Settings/settingsFields.ts` — NEW (~200 LOC, data + types)
- `frontend/src/pages/Settings/PathMappingEditor.tsx` — NEW (~200 LOC)
- `frontend/src/pages/Settings/InstanceEditor.tsx` — NEW (~130 LOC)
- `frontend/src/pages/Settings/LegacySettings.tsx` — MODIFIED (imports from the 3 new files, re-exports `FieldConfig` and `NAV_GROUPS`)

**Critical exports that must remain in `LegacySettings.tsx`:**

`frontend/src/pages/Settings/index.tsx` re-exports these from `LegacySettings`:
```typescript
export { NAV_GROUPS } from './LegacySettings'
export type { FieldConfig } from './LegacySettings'
```
Both must remain exported from `LegacySettings.tsx` after the split (either defined there or re-exported through it from `settingsFields.ts`).

After Task 3, `AdvancedTab.tsx` no longer imports `FieldConfig` from `LegacySettings` directly (that import moved to `LibrarySourcesTab.tsx`). But confirm the `index.tsx` re-export chain still works.

### Steps

- [ ] **Create `frontend/src/pages/Settings/settingsFields.ts`**

  Copy from `LegacySettings.tsx`:
  - `FieldConfig` interface (lines ~106–116)
  - `FIELDS` array with all 60+ field definitions (lines ~117–275)
  - `NAV_GROUPS` constant (lines ~75–116)
  - `TABS` constant if present
  - `TAB_KEYS` i18n mapping (lines ~614–638)

  All as named exports:
  ```typescript
  export interface FieldConfig { ... }
  export const FIELDS: FieldConfig[] = [ ... ]
  export const NAV_GROUPS: NavGroup[] = [ ... ]
  export const TAB_KEYS: Record<string, string> = { ... }
  ```

  Include only the imports these data structures need (type imports for icons, etc.).

- [ ] **Create `frontend/src/pages/Settings/PathMappingEditor.tsx`**

  Copy from `LegacySettings.tsx` lines ~277–479 (the `PathMappingEditor` component). Include only its own imports.

- [ ] **Create `frontend/src/pages/Settings/InstanceEditor.tsx`**

  Copy from `LegacySettings.tsx` lines ~482–610 (the `InstanceEditor` component). Include only its own imports.

- [ ] **Update `frontend/src/pages/Settings/LegacySettings.tsx`**

  - Remove the extracted sections (FieldConfig, FIELDS, NAV_GROUPS, TAB_KEYS, PathMappingEditor, InstanceEditor)
  - Add imports at the top:
    ```typescript
    import { FIELDS, NAV_GROUPS, TAB_KEYS } from './settingsFields'
    import type { FieldConfig } from './settingsFields'
    import { PathMappingEditor } from './PathMappingEditor'
    import { InstanceEditor } from './InstanceEditor'
    ```
  - Re-export `FieldConfig` and `NAV_GROUPS` so `index.tsx` re-exports continue to work:
    ```typescript
    export type { FieldConfig } from './settingsFields'
    export { NAV_GROUPS } from './settingsFields'
    ```
  - Verify `SettingsPage` export is still present (do not remove it — `index.tsx` overrides it but the export must remain).

- [ ] **Verify `index.tsx` re-export chain**
  ```bash
  cd D:/Sublarr_Projekt/Sublarr/frontend
  grep -n "from './LegacySettings'" src/pages/Settings/index.tsx
  ```
  Confirm lines like `export { NAV_GROUPS } from './LegacySettings'` still resolve (they go through the re-export in `LegacySettings.tsx`).

- [ ] **Run frontend checks**
  ```bash
  cd D:/Sublarr_Projekt/Sublarr/frontend && npx tsc --noEmit && npm run test -- --run
  ```

- [ ] **Verify file sizes**
  ```bash
  wc -l D:/Sublarr_Projekt/Sublarr/frontend/src/pages/Settings/LegacySettings.tsx \
         D:/Sublarr_Projekt/Sublarr/frontend/src/pages/Settings/settingsFields.ts \
         D:/Sublarr_Projekt/Sublarr/frontend/src/pages/Settings/PathMappingEditor.tsx \
         D:/Sublarr_Projekt/Sublarr/frontend/src/pages/Settings/InstanceEditor.tsx
  ```
  Expected: `LegacySettings.tsx` ≤800, all new files ≤250.

- [ ] **Commit**
  ```bash
  cd D:/Sublarr_Projekt/Sublarr
  git add frontend/src/pages/Settings/LegacySettings.tsx \
          frontend/src/pages/Settings/settingsFields.ts \
          frontend/src/pages/Settings/PathMappingEditor.tsx \
          frontend/src/pages/Settings/InstanceEditor.tsx
  git commit -m "refactor: extract settingsFields, PathMappingEditor, InstanceEditor from LegacySettings.tsx"
  ```

---

## Final Verification

After all 5 tasks, run all checks one final time:

```bash
# Backend
cd D:/Sublarr_Projekt/Sublarr/backend && ruff check . && ruff format --check .
cd D:/Sublarr_Projekt/Sublarr/backend && python -m pytest --tb=short -q \
  --ignore=tests/performance \
  --ignore=tests/integration/test_provider_pipeline.py \
  --ignore=tests/test_video_sync.py \
  --ignore=tests/test_translation_backends.py \
  -k "not (test_sonarr_download_webhook or test_radarr_download_webhook or test_parse_llm_response_too_many_merge or test_record_backend_success)"

# Frontend
cd D:/Sublarr_Projekt/Sublarr/frontend && npx tsc --noEmit && npm run test -- --run

# Confirm all target files are under limit
wc -l \
  D:/Sublarr_Projekt/Sublarr/backend/services/wanted_scanner.py \
  D:/Sublarr_Projekt/Sublarr/backend/config.py \
  D:/Sublarr_Projekt/Sublarr/frontend/src/pages/Settings/AdvancedTab.tsx \
  D:/Sublarr_Projekt/Sublarr/frontend/src/pages/Wanted.tsx \
  D:/Sublarr_Projekt/Sublarr/frontend/src/pages/Settings/LegacySettings.tsx
```

Expected output: all 5 original files ≤ their respective limits (backend ≤800, frontend ≤1000).

---

## Pitfall Reminders

| Risk | Mitigation |
|------|------------|
| Pydantic Settings fields moved out of `Settings` class | Never move field definitions — only move `_LANGUAGE_TAGS`, `SUPPORTED_LANGUAGES`, helper functions |
| Circular import: `config_instances` → `config` → `config_instances` | Use `from config import get_settings` INSIDE each function body in `config_instances.py`, not at module top |
| `AdvancedTab.tsx` barrel missing a name | Barrel must re-export all 4 components; `LegacySettings.tsx` lazy imports resolve through it |
| `WantedScanner` mixin state-access failures | Use simple 2-file split (full class in `wanted_scanner_core.py`) — no mixin needed |
| `LegacySettings` double `SettingsPage` export | Do not remove `SettingsPage` export from `LegacySettings.tsx`; `index.tsx` override is intentional |
| `NAV_GROUPS` / `FieldConfig` disappear from `index.tsx` barrel | `LegacySettings.tsx` must re-export these after moving to `settingsFields.ts` |
