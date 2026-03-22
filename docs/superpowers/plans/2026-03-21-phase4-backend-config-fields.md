# Plan: Phase 4 — Backend Config Fields + Frontend Wiring (Steps 37–46)

**Goal:** Add 10 groups of new Pydantic fields to `backend/config.py` (Steps 37–46) and wire each group
to its corresponding frontend Settings page. No DB migration needed — fields auto-persist to
`config_entries` on first PATCH. Backend must be deployed before frontend sends new keys.

**Total tasks:** 11 (1 backend + 10 frontend groups)

---

## Patterns to Follow

**Backend (`config.py`):**
- All fields are typed Pydantic class attributes with explicit defaults.
- Comment block above each logical group (e.g. `# Interface Preferences`).
- New fields go immediately before `model_config = { ... }` at end of `Settings` class.
- After editing: `cd backend && ruff check . && ruff format --check .`

**Frontend (Settings pages):**
- `strVal(config, key, fallback)` / `boolVal(config, key, fallback)` / `numVal(config, key, fallback)` helpers already exist in each target file — reuse them.
- `inputStyle` const already defined in each target file — reuse it.
- Save pattern: `onChange={(e) => save({ key: value })}` with `useUpdateConfig()`.
- `<SettingsSection>` + `<FormGroup>` + native `<input>` / `<select>` / `<Toggle>` — no new component types.
- `<Toggle>` is imported from `@/components/shared/Toggle`.
- `data-testid` attributes required on every section wrapper div, FormGroup, and interactive element.
- Test file lives in `frontend/src/pages/Settings/__tests__/[PageName].test.tsx`.

---

## Task 1 — Add all 10 groups to `backend/config.py`

**Files:** `backend/config.py`

**Action:**
Insert the following block immediately before the `model_config = { ... }` line (currently at
the very end of the `Settings` class, after the Redis fields). Keep all existing fields unchanged.

```python
# Interface Preferences (Step 37)
interface_language: str = "en"
items_per_page: int = 25
default_library_view: str = "grid"  # "grid" | "list"
default_library_sort: str = "alpha"  # "alpha" | "date" | "score"
datetime_format: str = "relative"  # "relative" | "absolute"

# Subtitle Naming (Step 38)
subtitle_language_code_format: str = "iso_639_1"  # "iso_639_1" | "iso_639_2"
subtitle_suffix_separator: str = "dot"  # "dot" | "dash" | "underscore"
subtitle_hi_suffix: str = "hi"
subtitle_forced_suffix: str = "forced"

# Quiet Hours (Step 39)
quiet_hours_enabled: bool = False
quiet_hours_start: str = "23:00"
quiet_hours_end: str = "07:00"
quiet_hours_timezone: str = "UTC"

# Auto Backup (Step 40)
backup_auto_enabled: bool = False
backup_auto_interval_hours: int = 24
backup_auto_on_startup: bool = False
backup_notify_on_failure: bool = True

# Disk Monitoring (Step 41)
disk_warning_threshold_percent: int = 90
disk_warning_notify: bool = True

# Scan Ignore Patterns (Step 42)
scan_ignore_patterns: str = "[]"   # JSON array of glob patterns
scan_min_file_size_mb: float = 0.0
scan_ignore_languages: str = "[]"  # JSON array of ISO-639-1 codes

# Per-Language Score Thresholds (Step 43)
score_threshold_per_language: str = "{}"  # JSON object: {"de": 80, "fr": 70}

# Download Limits (Step 44)
max_concurrent_provider_searches: int = 3
max_subtitle_file_size_kb: int = 2048
download_delay_between_providers_ms: int = 0

# Translation Context (Step 45)
translation_use_episode_context: bool = False
translation_context_episodes: int = 1
translation_series_glossary_auto: bool = False

# Extended Security (Step 46)
session_timeout_minutes: int = 0       # 0 = no timeout
max_login_attempts: int = 20
lockout_duration_minutes: int = 60
allowed_ip_ranges: str = ""            # Comma-separated CIDR ranges; empty = allow all
```

**Verify:**
```bash
cd D:/Sublarr_Projekt/Sublarr/backend && ruff check . && ruff format --check .
```
Both commands must exit 0 with no violations.

**Done:** `backend/config.py` contains all 37 new fields, ruff passes clean.

**Commit:**
```
feat: add Phase 4 config fields to backend/config.py (37 new settings, steps 37–46)
```

---

## Task 2 — Step 37: Interface Preferences → `GeneralSettings.tsx`

**Files:**
- `frontend/src/pages/Settings/GeneralSettings.tsx`
- `frontend/src/pages/Settings/__tests__/GeneralSettings.test.tsx`

**Action:**

In `GeneralSettings.tsx`, add a new `<SettingsSection>` block **after** the existing Interface
section (after the `</div>` closing `data-testid="section-interface"`). Use the `Monitor` icon
from `lucide-react` (add to import). Title: "Interface Preferences". Description: "Pagination,
library layout, sorting, and date display defaults."

Add these constants near the top (with existing constants):
```typescript
const LANGUAGE_OPTIONS = [
  { value: 'en', label: 'English' },
  { value: 'de', label: 'Deutsch' },
] as const

const LIBRARY_VIEWS = ['grid', 'list'] as const
const LIBRARY_SORTS = [
  { value: 'alpha', label: 'Alphabetical' },
  { value: 'date', label: 'Date Added' },
  { value: 'score', label: 'Score' },
] as const
const DATETIME_FORMATS = [
  { value: 'relative', label: 'Relative (2 hours ago)' },
  { value: 'absolute', label: 'Absolute (2026-03-21 14:00)' },
] as const
```

Inside the new SettingsSection, add four FormGroups:
1. **Interface Language** — `<select>` bound to `interface_language`, options from `LANGUAGE_OPTIONS`, `data-testid="select-interface-language"`
2. **Items per Page** — `<input type="number">` bound to `items_per_page`, `min={10}` `max={200}`, `data-testid="input-items-per-page"`, `maxWidth: '120px'`
3. **Default Library View** — `<select>` bound to `default_library_view`, options `grid`/`list`, `data-testid="select-default-library-view"`
4. **Default Library Sort** — `<select>` bound to `default_library_sort`, options from `LIBRARY_SORTS`, `data-testid="select-default-library-sort"`
5. **Date/Time Format** — `<select>` bound to `datetime_format`, options from `DATETIME_FORMATS`, `data-testid="select-datetime-format"`

Wrap the new section in `<div data-testid="section-interface-preferences">`.

In the test file, add a describe block `"Interface Preferences section"` with tests:
- Renders the section heading "Interface Preferences"
- `select-interface-language` renders with value from config (default `'en'`)
- `input-items-per-page` renders with value from config (default `25`)
- `select-default-library-view` renders with value from config (default `'grid'`)
- `select-default-library-sort` renders with value from config (default `'alpha'`)
- `select-datetime-format` renders with value from config (default `'relative'`)
- Changing `select-interface-language` calls `updateConfig` with `{ interface_language: 'de' }`

Follow the existing test setup pattern in `GeneralSettings.test.tsx` (vi.mock for useConfig/useUpdateConfig).

**Verify:** `cd D:/Sublarr_Projekt/Sublarr/frontend && npm run test -- --run --reporter=verbose 2>&1 | grep -E "(PASS|FAIL|GeneralSettings)"`

**Done:** All GeneralSettings tests pass; the Interface Preferences section renders with all 5 controls.

**Commit:** `feat: add Interface Preferences settings to GeneralSettings (step 37)`

---

## Task 3 — Step 38: Subtitle Naming → `SubtitlesSettings.tsx`

**Files:**
- `frontend/src/pages/Settings/SubtitlesSettings.tsx`
- `frontend/src/pages/Settings/__tests__/SubtitlesSettings.test.tsx`

**Action:**

In `SubtitlesSettings.tsx`, add a new `<SettingsSection>` for "Subtitle Naming". Place it
after the existing Format & Tools section. Use the `Tag` icon from `lucide-react` (add to import).
Title: "Subtitle Naming". Description: "Language code format and suffix conventions for saved
subtitle files."

Add constants near top:
```typescript
const LANG_CODE_FORMATS = [
  { value: 'iso_639_1', label: 'ISO 639-1 (2-letter: de, en)' },
  { value: 'iso_639_2', label: 'ISO 639-2 (3-letter: deu, eng)' },
] as const
const SUFFIX_SEPARATORS = [
  { value: 'dot', label: 'Dot  (movie.de.ass)' },
  { value: 'dash', label: 'Dash  (movie-de.ass)' },
  { value: 'underscore', label: 'Underscore  (movie_de.ass)' },
] as const
```

Add four FormGroups inside the new section:
1. **Language Code Format** — `<select>` bound to `subtitle_language_code_format`, `data-testid="select-subtitle-language-code-format"`
2. **Suffix Separator** — `<select>` bound to `subtitle_suffix_separator`, `data-testid="select-subtitle-suffix-separator"`
3. **HI Subtitle Suffix** — `<input type="text">` bound to `subtitle_hi_suffix`, placeholder `"hi"`, `data-testid="input-subtitle-hi-suffix"`, `maxWidth: '120px'`
4. **Forced Subtitle Suffix** — `<input type="text">` bound to `subtitle_forced_suffix`, placeholder `"forced"`, `data-testid="input-subtitle-forced-suffix"`, `maxWidth: '120px'`

`strVal` helper is already present in the file — use it. Wrap in `<div data-testid="section-subtitle-naming">`.

In the test file, add a describe block `"Subtitle Naming section"` with tests:
- Renders heading "Subtitle Naming"
- `select-subtitle-language-code-format` defaults to `'iso_639_1'`
- `select-subtitle-suffix-separator` defaults to `'dot'`
- `input-subtitle-hi-suffix` defaults to `'hi'`
- `input-subtitle-forced-suffix` defaults to `'forced'`
- Changing separator calls `updateConfig` with `{ subtitle_suffix_separator: 'dash' }`

**Verify:** `cd D:/Sublarr_Projekt/Sublarr/frontend && npm run test -- --run --reporter=verbose 2>&1 | grep -E "(PASS|FAIL|SubtitlesSettings)"`

**Done:** All SubtitlesSettings tests pass; Subtitle Naming section renders with all 4 controls.

**Commit:** `feat: add Subtitle Naming settings to SubtitlesSettings (step 38)`

---

## Task 4 — Step 39: Quiet Hours → `NotificationsSettings.tsx`

**Files:**
- `frontend/src/pages/Settings/NotificationsSettings.tsx`
- `frontend/src/pages/Settings/__tests__/NotificationsSettings.test.tsx`

**Action:**

The Quiet Hours section in `NotificationsSettings.tsx` currently renders only a static placeholder
paragraph (lines 99–120). Replace the placeholder content with real controls wired to
`useConfig` / `useUpdateConfig`.

Add imports at the top:
```typescript
import { useConfig, useUpdateConfig } from '@/hooks/useApi'
import { Toggle } from '@/components/shared/Toggle'
import { FormGroup } from '@/components/settings/FormGroup'
```

Add helper functions (same pattern as other settings pages):
```typescript
function strVal(config: unknown, key: string, fallback = ''): string { ... }
function boolVal(config: unknown, key: string, fallback = false): boolean { ... }
```

In the component body, add:
```typescript
const { data: config, isLoading } = useConfig()
const { mutate: save, isPending } = useUpdateConfig()
```

Replace the placeholder paragraph in `data-testid="quiet-hours-summary"` / advanced prop with
real FormGroups:

**Main section body** (always visible):
- `<Toggle>` for `quiet_hours_enabled` — label "Enable Quiet Hours", `data-testid="toggle-quiet-hours-enabled"`

**Advanced prop content** (shown when section is expanded):
- **Start Time** — `<input type="time">` bound to `quiet_hours_start`, default `"23:00"`, `data-testid="input-quiet-hours-start"`
- **End Time** — `<input type="time">` bound to `quiet_hours_end`, default `"07:00"`, `data-testid="input-quiet-hours-end"`
- **Timezone** — `<input type="text">` bound to `quiet_hours_timezone`, default `"UTC"`, placeholder `"UTC"`, `data-testid="input-quiet-hours-timezone"`

Keep existing `data-testid="section-quiet-hours"` wrapper and `data-testid="quiet-hours-advanced-content"` on the advanced wrapper.

In the test file, add a describe block `"Quiet Hours section"` with tests:
- Renders heading "Quiet Hours"
- `toggle-quiet-hours-enabled` is rendered unchecked by default
- Toggling it calls `updateConfig` with `{ quiet_hours_enabled: true }`

**Verify:** `cd D:/Sublarr_Projekt/Sublarr/frontend && npm run test -- --run --reporter=verbose 2>&1 | grep -E "(PASS|FAIL|NotificationsSettings)"`

**Done:** All NotificationsSettings tests pass; Quiet Hours shows Toggle plus time/timezone controls in advanced panel.

**Commit:** `feat: wire Quiet Hours controls to config PATCH in NotificationsSettings (step 39)`

---

## Task 5 — Step 40: Auto Backup → `SystemSettings.tsx`

**Files:**
- `frontend/src/pages/Settings/SystemSettings.tsx`
- `frontend/src/pages/Settings/__tests__/SystemSettings.test.tsx`

**Action:**

In `SystemSettings.tsx`, the Backup & Restore section currently renders `<BackupTab>` (lazy) with
no config-wired controls. Add a new sub-block **above** the `<BackupTab>` lazy content inside the
Backup & Restore section. This sub-block is for automation settings, not manual backup actions.

Add imports:
```typescript
import { FormGroup } from '@/components/settings/FormGroup'
import { Toggle } from '@/components/shared/Toggle'
import { useConfig, useUpdateConfig } from '@/hooks/useApi'
```

Add helpers at module level (same pattern as other pages):
```typescript
function boolVal(config: unknown, key: string, fallback = false): boolean { ... }
function numVal(config: unknown, key: string, fallback = 0): number { ... }
```

Inside the component, add:
```typescript
const { data: config } = useConfig()
const { mutate: save, isPending } = useUpdateConfig()
```

Within the existing Backup & Restore `<SettingsSection>` (before the `<Suspense>` block for
BackupTab), add a `<div data-testid="backup-auto-controls">` containing four FormGroups:
1. **Auto Backup** — `<Toggle>` for `backup_auto_enabled`, `data-testid="toggle-backup-auto-enabled"`
2. **Backup Interval (hours)** — `<input type="number">` bound to `backup_auto_interval_hours`, `min={1}` `max={720}`, `data-testid="input-backup-auto-interval-hours"`, `maxWidth: '120px'`
3. **Backup on Startup** — `<Toggle>` for `backup_auto_on_startup`, `data-testid="toggle-backup-auto-on-startup"`
4. **Notify on Failure** — `<Toggle>` for `backup_notify_on_failure`, default `true`, `data-testid="toggle-backup-notify-on-failure"`

In the test file, add a describe block `"Auto Backup section"` with tests:
- `toggle-backup-auto-enabled` renders unchecked by default
- `input-backup-auto-interval-hours` renders with value `24`
- `toggle-backup-notify-on-failure` renders checked by default (default `true`)
- Toggling `backup_auto_enabled` calls `updateConfig` with `{ backup_auto_enabled: true }`

**Verify:** `cd D:/Sublarr_Projekt/Sublarr/frontend && npm run test -- --run --reporter=verbose 2>&1 | grep -E "(PASS|FAIL|SystemSettings)"`

**Done:** All SystemSettings tests pass; Auto Backup controls visible in Backup & Restore section.

**Commit:** `feat: add Auto Backup settings to SystemSettings (step 40)`

---

## Task 6 — Step 41: Disk Monitoring → `SystemSettings.tsx`

**Files:**
- `frontend/src/pages/Settings/SystemSettings.tsx`
- `frontend/src/pages/Settings/__tests__/SystemSettings.test.tsx`

**Action:**

This task builds on Task 5 (same file, now already has `useConfig`/`useUpdateConfig` and helpers).

Add a new `<SettingsSection>` for Disk Monitoring **after** the Backup & Restore section. Use
the `HardDrive` icon from `lucide-react` (add to import if not already present). Title: "Disk
Monitoring". Description: "Alert when disk usage exceeds a threshold."

Wrap in `<div data-testid="section-disk-monitoring">`.

Add two FormGroups inside:
1. **Warning Threshold (%)** — `<input type="number">` bound to `disk_warning_threshold_percent`, `min={50}` `max={99}`, `data-testid="input-disk-warning-threshold-percent"`, `maxWidth: '100px'`
2. **Notify on Warning** — `<Toggle>` for `disk_warning_notify`, `data-testid="toggle-disk-warning-notify"`

In the test file, extend the SystemSettings tests with a describe block `"Disk Monitoring section"`:
- Renders heading "Disk Monitoring"
- `input-disk-warning-threshold-percent` renders with value `90`
- `toggle-disk-warning-notify` renders checked by default
- Changing threshold calls `updateConfig` with `{ disk_warning_threshold_percent: 85 }`

**Verify:** `cd D:/Sublarr_Projekt/Sublarr/frontend && npm run test -- --run --reporter=verbose 2>&1 | grep -E "(PASS|FAIL|SystemSettings)"`

**Done:** All SystemSettings tests pass; Disk Monitoring section renders with both controls.

**Commit:** `feat: add Disk Monitoring settings to SystemSettings (step 41)`

---

## Task 7 — Step 42: Scan Ignore Patterns → `SubtitlesSettings.tsx`

**Files:**
- `frontend/src/pages/Settings/SubtitlesSettings.tsx`
- `frontend/src/pages/Settings/__tests__/SubtitlesSettings.test.tsx`

**Action:**

In `SubtitlesSettings.tsx`, add a new `<SettingsSection>` for "Scan Filters" **after** the
Subtitle Naming section (added in Task 3). Use the `Filter` icon from `lucide-react` (add to
import). Title: "Scan Filters". Description: "Exclude files and languages from subtitle scans."

Wrap in `<div data-testid="section-scan-filters">`.

Add three FormGroups:
1. **Ignore Patterns** — `<textarea>` bound to `scan_ignore_patterns`, `rows={3}`,
   placeholder `'["*.sample.*", "*.extras.*"]'`, hint "JSON array of glob patterns to skip
   during scan", `data-testid="textarea-scan-ignore-patterns"`. Style the textarea like
   inputStyle but `width: '100%'` and `resize: vertical`. Fire save on `onBlur` (not onChange)
   to avoid spamming the backend.
2. **Minimum File Size (MB)** — `<input type="number">` bound to `scan_min_file_size_mb`,
   `min={0}` `step={0.1}`, `data-testid="input-scan-min-file-size-mb"`, `maxWidth: '120px'`
3. **Ignore Languages** — `<textarea>` bound to `scan_ignore_languages`, `rows={2}`,
   placeholder `'["fr", "es"]'`, hint "JSON array of ISO-639-1 codes to exclude from scan",
   `data-testid="textarea-scan-ignore-languages"`. Also save on `onBlur`.

In the test file, add a describe block `"Scan Filters section"` with tests:
- Renders heading "Scan Filters"
- `textarea-scan-ignore-patterns` renders with default value `"[]"`
- `input-scan-min-file-size-mb` renders with value `0`
- `textarea-scan-ignore-languages` renders with default value `"[]"`
- Blurring `textarea-scan-ignore-patterns` calls `updateConfig` with `{ scan_ignore_patterns: '["*.sample.*"]' }`

**Verify:** `cd D:/Sublarr_Projekt/Sublarr/frontend && npm run test -- --run --reporter=verbose 2>&1 | grep -E "(PASS|FAIL|SubtitlesSettings)"`

**Done:** All SubtitlesSettings tests pass; Scan Filters section renders with all 3 controls.

**Commit:** `feat: add Scan Filters settings to SubtitlesSettings (step 42)`

---

## Task 8 — Step 43: Per-Language Score Thresholds → `SubtitlesSettings.tsx`

**Files:**
- `frontend/src/pages/Settings/SubtitlesSettings.tsx`
- `frontend/src/pages/Settings/__tests__/SubtitlesSettings.test.tsx`

**Action:**

In `SubtitlesSettings.tsx`, add a new `<SettingsSection>` for "Per-Language Score Thresholds"
**after** the Scan Filters section. Use the `Sliders` icon from `lucide-react` (add to import).
Title: "Per-Language Score Thresholds". Description: "Override the global minimum score for
specific languages."

Wrap in `<div data-testid="section-per-language-scores">`.

Add one FormGroup:
1. **Score Thresholds (JSON)** — `<textarea>` bound to `score_threshold_per_language`, `rows={4}`,
   placeholder `'{"de": 80, "fr": 70}'`, hint "JSON object mapping ISO-639-1 code to minimum
   score. Empty object uses global threshold for all languages.",
   `data-testid="textarea-score-threshold-per-language"`. Save on `onBlur`.

Below the textarea, add a small hint paragraph styled with `color: var(--text-muted)` and
`fontSize: '11px'`:
```
Example: {"de": 80, "fr": 70} — German subtitles require score ≥ 80, French ≥ 70.
Leave as {} to use the global threshold for all languages.
```

In the test file, add a describe block `"Per-Language Score Thresholds section"` with tests:
- Renders heading "Per-Language Score Thresholds"
- `textarea-score-threshold-per-language` renders with default value `"{}"`
- Blurring it calls `updateConfig` with `{ score_threshold_per_language: '{"de":80}' }`

**Verify:** `cd D:/Sublarr_Projekt/Sublarr/frontend && npm run test -- --run --reporter=verbose 2>&1 | grep -E "(PASS|FAIL|SubtitlesSettings)"`

**Done:** All SubtitlesSettings tests pass; Per-Language Score Thresholds section renders.

**Commit:** `feat: add Per-Language Score Thresholds settings to SubtitlesSettings (step 43)`

---

## Task 9 — Step 44: Download Limits → `ProvidersSettings.tsx`

**Files:**
- `frontend/src/pages/Settings/ProvidersSettings.tsx`
- `frontend/src/pages/Settings/__tests__/ProvidersSettings.test.tsx`

**Action:**

In `ProvidersSettings.tsx`, add a new `<SettingsSection>` for "Download Limits" **at the end**
of the page (after the Anti-Captcha section or as the last section). Use the `Download` icon
from `lucide-react` (add to import). Title: "Download Limits". Description: "Concurrency and
size limits for subtitle provider downloads."

The page already uses `useConfig` / `useUpdateConfig` and has `values` / `handleSave` / `handleFieldChange`.
Add a `numVal` helper if not present:
```typescript
function numVal(v: string | undefined, fallback: number): number {
  const n = Number(v)
  return isNaN(n) ? fallback : n
}
```

Wrap in `<div data-testid="section-download-limits">`.

Add three FormGroups using native `<input type="number">`:
1. **Concurrent Provider Searches** — bound to `max_concurrent_provider_searches`, `min={1}` `max={10}`, `data-testid="input-max-concurrent-provider-searches"`, `maxWidth: '100px'`. Save on `onChange` via `handleFieldChange('max_concurrent_provider_searches', String(Number(e.target.value)))`.
2. **Max Subtitle File Size (KB)** — bound to `max_subtitle_file_size_kb`, `min={100}` `max={10240}`, `data-testid="input-max-subtitle-file-size-kb"`, `maxWidth: '120px'`
3. **Delay Between Providers (ms)** — bound to `download_delay_between_providers_ms`, `min={0}` `max={5000}`, `data-testid="input-download-delay-between-providers-ms"`, `maxWidth: '120px'`

In the test file, add a describe block `"Download Limits section"` with tests:
- Renders heading "Download Limits"
- `input-max-concurrent-provider-searches` renders with value `3`
- `input-max-subtitle-file-size-kb` renders with value `2048`
- `input-download-delay-between-providers-ms` renders with value `0`
- Changing concurrent searches calls `updateConfig` / `handleFieldChange` with `max_concurrent_provider_searches: '5'`

**Verify:** `cd D:/Sublarr_Projekt/Sublarr/frontend && npm run test -- --run --reporter=verbose 2>&1 | grep -E "(PASS|FAIL|ProvidersSettings)"`

**Done:** All ProvidersSettings tests pass; Download Limits section renders with all 3 controls.

**Commit:** `feat: add Download Limits settings to ProvidersSettings (step 44)`

---

## Task 10 — Step 45: Translation Context → `TranslationTab.tsx`

**Files:**
- `frontend/src/pages/Settings/TranslationTab.tsx`
- (No dedicated test file exists for TranslationTab — add test coverage inside `TranslationSettings.test.tsx`)

**Action:**

`TranslationTab.tsx` is a large file with backend config cards. Locate the section that renders
global translation settings (near `useConfig` / `useUpdateConfig` usage). Add a new
`<SettingsSection>`-equivalent block (or a `<SettingsCard>` if that is the pattern in use in
this file) for "Episode Context".

Check the file for the existing pattern: if it uses `<SettingsCard>` + `<SettingRow>`, use those.
If it uses `<SettingsSection>` + `<FormGroup>`, use those. Do NOT mix patterns.

Add imports as needed (Toggle, SettingRow, or FormGroup depending on existing pattern).

Add a block with `data-testid="section-translation-context"` containing:
1. **Use Episode Context** — `<Toggle>` bound to `translation_use_episode_context`, label "Use
   Episode Context", hint "Include previous episode subtitle as context for translation",
   `data-testid="toggle-translation-use-episode-context"`
2. **Context Episodes** — `<input type="number">` bound to `translation_context_episodes`,
   `min={1}` `max={5}`, hint "Number of prior episodes to include as context",
   `data-testid="input-translation-context-episodes"`, `maxWidth: '80px'`. Only render this
   when `translation_use_episode_context` is `true`.
3. **Auto Series Glossary** — `<Toggle>` bound to `translation_series_glossary_auto`, label
   "Auto Series Glossary", hint "Automatically build a per-series glossary from translation
   history", `data-testid="toggle-translation-series-glossary-auto"`

Use `useConfig` / `useUpdateConfig` — both are already imported in this file.

In `TranslationSettings.test.tsx`, add a describe block `"Translation Context section"` with tests:
- `toggle-translation-use-episode-context` renders unchecked by default
- `toggle-translation-series-glossary-auto` renders unchecked by default
- When `translation_use_episode_context` is `true`, `input-translation-context-episodes` is visible
- Toggling use-episode-context calls `updateConfig` with `{ translation_use_episode_context: true }`

**Verify:** `cd D:/Sublarr_Projekt/Sublarr/frontend && npm run test -- --run --reporter=verbose 2>&1 | grep -E "(PASS|FAIL|TranslationSettings)"`

**Done:** All TranslationSettings tests pass; Translation Context block renders with conditional episode count input.

**Commit:** `feat: add Translation Context settings to TranslationTab (step 45)`

---

## Task 11 — Step 46: Extended Security → `SecurityTab.tsx` + `backend/auth.py`

**Files:**
- `frontend/src/pages/Settings/SecurityTab.tsx`
- `frontend/src/pages/Settings/__tests__/SystemSettings.test.tsx` (SecurityTab renders inside SystemSettings)
- `backend/auth.py`

**Action:**

**Part A — Frontend (`SecurityTab.tsx`):**

`SecurityTab.tsx` currently uses `<SettingsCard>` + `<SettingRow>` / `<Toggle>` pattern with
its own local `inputStyle`. The page uses `useMutation` and `useQuery` but NOT `useConfig` /
`useUpdateConfig`. Add them now:

```typescript
import { useConfig, useUpdateConfig } from '@/hooks/useApi'
import { FormGroup } from '@/components/settings/FormGroup'
```

Add in the component body:
```typescript
const { data: config } = useConfig()
const { mutate: saveConfig, isPending: savingConfig } = useUpdateConfig()
const save = (patch: Record<string, unknown>) => saveConfig(patch)
```

Add a `numVal` helper at module level:
```typescript
function numVal(config: unknown, key: string, fallback = 0): number {
  if (!config || typeof config !== 'object') return fallback
  const v = (config as Record<string, unknown>)[key]
  const n = Number(v)
  return isNaN(n) ? fallback : n
}
function strVal(config: unknown, key: string, fallback = ''): string {
  if (!config || typeof config !== 'object') return fallback
  const v = (config as Record<string, unknown>)[key]
  return v !== undefined && v !== null ? String(v) : fallback
}
```

Add a new `<SettingsCard title="Rate Limiting & Session" icon={Shield}>` (or use a div styled
consistently with existing cards) **after** the existing Change Password card. Use
`data-testid="section-extended-security"`.

Add four FormGroups inside:
1. **Session Timeout (minutes)** — `<input type="number">` bound to `session_timeout_minutes`,
   `min={0}`, hint "0 = sessions never expire", `data-testid="input-session-timeout-minutes"`,
   width `120px`
2. **Max Login Attempts** — `<input type="number">` bound to `max_login_attempts`, `min={1}` `max={100}`,
   `data-testid="input-max-login-attempts"`, width `120px`
3. **Lockout Duration (minutes)** — `<input type="number">` bound to `lockout_duration_minutes`,
   `min={1}` `max={1440}`, `data-testid="input-lockout-duration-minutes"`, width `120px`
4. **Allowed IP Ranges** — `<input type="text">` bound to `allowed_ip_ranges`,
   placeholder `"192.168.1.0/24, 10.0.0.0/8"`, hint "Comma-separated CIDR ranges. Empty = allow all.",
   `data-testid="input-allowed-ip-ranges"`, width `300px`

**Part B — Backend (`backend/auth.py`):**

Replace the two module-level constants at the top of `auth.py`:
```python
_FAIL_LIMIT = 20  # max failed attempts per window
_FAIL_WINDOW = 60  # seconds
```

With dynamic reads from settings inside `_is_rate_limited` and `_record_failure`. The constants
become fallback defaults only. Change `_is_rate_limited` to read the limit from settings:

```python
_FAIL_WINDOW = 60  # seconds — fixed sliding window

def _is_rate_limited(ip: str) -> bool:
    """Return True if ip has exceeded the failed-auth rate limit."""
    settings = get_settings()
    fail_limit = getattr(settings, "max_login_attempts", 20)
    now = time.monotonic()
    with _failed_lock:
        cutoff = now - _FAIL_WINDOW
        _failed_attempts[ip] = [t for t in _failed_attempts[ip] if t > cutoff]
        return len(_failed_attempts[ip]) >= fail_limit
```

Remove the `_FAIL_LIMIT = 20` module constant. Keep `_FAIL_WINDOW = 60` as-is (the lockout
duration in minutes applies to a different concept — session lockout — which is not implemented
in the current sliding window model; do not break the existing rate-limiter logic).

Note in a comment near `_FAIL_WINDOW`: `# lockout_duration_minutes from settings applies to
UI session lockout (future); this window is for API key brute-force protection.`

After editing backend: `cd D:/Sublarr_Projekt/Sublarr/backend && ruff check . && ruff format --check .`

**Tests:**

In `SystemSettings.test.tsx`, add a describe block `"Extended Security section (SecurityTab)"` with tests:
- `input-max-login-attempts` renders with value `20`
- `input-lockout-duration-minutes` renders with value `60`
- `input-session-timeout-minutes` renders with value `0`
- `input-allowed-ip-ranges` renders with empty string default
- Changing `max_login_attempts` calls `updateConfig` with `{ max_login_attempts: 10 }`

**Verify:**
```bash
cd D:/Sublarr_Projekt/Sublarr/frontend && npm run test -- --run --reporter=verbose 2>&1 | grep -E "(PASS|FAIL|SystemSettings)"
cd D:/Sublarr_Projekt/Sublarr/backend && ruff check . && ruff format --check .
```

**Done:** All SystemSettings tests pass; Extended Security card renders in SecurityTab with 4 controls.
Backend auth.py reads `max_login_attempts` from settings at runtime. Ruff passes.

**Commit:** `feat: add Extended Security settings to SecurityTab and wire max_login_attempts in auth.py (step 46)`

---

## Pre-PR Verification

Run the full suite before opening a PR:

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
cd D:/Sublarr_Projekt/Sublarr/frontend && npm run lint && npx tsc --noEmit && npm run test -- --run
```

All must pass before merge.

---

## Deployment Note

Backend (`config.py` + `auth.py`) must be built and deployed to CT 101 before the frontend
changes go live. The new Pydantic fields are backward-compatible (all have defaults). The frontend
changes only send new keys on user interaction, so they are safe after deployment.

Deploy order: 1. commit all → 2. Docker build → 3. push → 4. deploy CT 101 → 5. verify health.
