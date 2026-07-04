# Translation Backend Selector Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give users a UI to choose which translation backend is used — a global default that language profiles inherit, with an optional single fallback backend.

**Architecture:** A global default lives in two `config_entries` keys; each language profile's existing `translation_backend` column is either empty (inherit the global default) or an explicit override. `_resolve_backend_for_context` reads the profile first, falls back to the global default, then to `ollama`. Two UI entry points (global control on the Backends page, per-profile override in the profile editor) share one `BackendSelect` dropdown component. No DB migration, no new backend endpoint — the profile API and config API already round-trip everything.

**Tech Stack:** Python 3.11 / Flask / SQLAlchemy (backend); React 19 + TypeScript + Vite + Vitest + React Testing Library (frontend); react-i18next (DE primary + EN mirror).

## Global Constraints

- Backend: ruff `line-length=100`, `target-version=py311`. Run `ruff check .` + `ruff format --check .` over the whole `backend/` dir before commit.
- Backend config reads: use `getattr(self.settings, "field", default)` style / `db.config.get_config_entry` — never assume a config key exists.
- Frontend: new static styling uses Tailwind utility classes mapped to design tokens (`bg-surface`, `text-primary`, `text-muted`, `border-border`, `rounded`, `p-2`…). Inline `style={{ }}` only for runtime-computed values. When editing legacy files that use inline `var(--…)` styles, new elements should still prefer Tailwind; do not mass-migrate the surrounding file.
- i18n: every new user-facing string is added to BOTH `frontend/src/i18n/locales/de/settings.json` (primary) and `frontend/src/i18n/locales/en/settings.json` (mirror) in the same change.
- No new `SUBLARR_` env fields (UI-first policy). The global default lives in `config_entries`, not env.
- Commit after every task (Conventional Commits: `feat:` / `test:` / `docs:`).
- Pre-existing helpers: `db.config.get_config_entry(key) -> str | None` (returns None if unset). Frontend hooks exist: `useBackends()`, `useConfig()`, `useUpdateConfig()`, `useLanguageProfiles()`, `useUpdateProfile()` (all re-exported from `@/hooks/useApi`).

---

## File Structure

- `backend/translator/_helpers.py` — MODIFY `_resolve_backend_for_context` (the single resolution path). One clear responsibility: turn (context, target-lang) into (primary, chain).
- `backend/tests/test_translator_helpers.py` — MODIFY `TestResolveBackendForContext` — add inheritance + chain-build cases.
- `frontend/src/components/settings/BackendSelect.tsx` — CREATE — one reusable backend dropdown (list, inherit/none options, unconfigured marker).
- `frontend/src/components/settings/__tests__/BackendSelect.test.tsx` — CREATE.
- `frontend/src/pages/Settings/translation/DefaultBackendSection.tsx` — CREATE — the global default control (primary + fallback), self-contained; mounted by `TranslationBackendsTab`.
- `frontend/src/pages/Settings/translation/__tests__/DefaultBackendSection.test.tsx` — CREATE.
- `frontend/src/pages/Settings/translation/TranslationBackendsTab.tsx` — MODIFY — mount `<DefaultBackendSection />`.
- `frontend/src/pages/Settings/LanguageProfilesTab.tsx` — MODIFY — add backend + fallback fields to the form + save payload.
- `frontend/src/i18n/locales/{de,en}/settings.json` — MODIFY — new keys.

---

## Task 1: Backend resolver — global-default inheritance + single fallback

**Files:**
- Modify: `backend/translator/_helpers.py` (`_resolve_backend_for_context`, currently ~line 194)
- Test: `backend/tests/test_translator_helpers.py` (`TestResolveBackendForContext`)

**Interfaces:**
- Consumes: `db.config.get_config_entry(key: str) -> str | None`; profile dict with keys `translation_backend` (str, may be `""`/`None`) and `fallback_chain` (list[str]).
- Produces: `_resolve_backend_for_context(arr_context, target_language) -> tuple[str, list[str]]` — `(primary_backend, chain)` where `chain == [primary]` or `[primary, fallback]`. Empty/inherit profile → global default config → `"ollama"`.

- [ ] **Step 1: Write failing tests** — append to `class TestResolveBackendForContext` in `backend/tests/test_translator_helpers.py`:

```python
    @patch("db.config.get_config_entry")
    @patch("db.profiles.get_default_profile")
    def test_empty_profile_inherits_global_default(self, mock_default, mock_cfg):
        from translator._helpers import _resolve_backend_for_context

        mock_default.return_value = {"translation_backend": "", "fallback_chain": []}
        cfg = {"translation_default_backend": "deepl", "translation_default_fallback": "ollama"}
        mock_cfg.side_effect = lambda k: cfg.get(k)

        backend, chain = _resolve_backend_for_context(None, "de")
        assert backend == "deepl"
        assert chain == ["deepl", "ollama"]

    @patch("db.config.get_config_entry")
    @patch("db.profiles.get_default_profile")
    def test_empty_profile_and_empty_global_falls_back_to_ollama(self, mock_default, mock_cfg):
        from translator._helpers import _resolve_backend_for_context

        mock_default.return_value = {"translation_backend": "", "fallback_chain": []}
        mock_cfg.side_effect = lambda k: None  # nothing configured

        backend, chain = _resolve_backend_for_context(None, "de")
        assert backend == "ollama"
        assert chain == ["ollama"]

    @patch("db.config.get_config_entry")
    @patch("db.profiles.get_default_profile")
    def test_profile_override_wins_over_global(self, mock_default, mock_cfg):
        from translator._helpers import _resolve_backend_for_context

        mock_default.return_value = {"translation_backend": "deepl", "fallback_chain": ["deepl", "ollama"]}
        mock_cfg.side_effect = lambda k: "chatgpt"  # global default must be ignored

        backend, chain = _resolve_backend_for_context(None, "de")
        assert backend == "deepl"
        assert chain == ["deepl", "ollama"]

    @patch("db.config.get_config_entry")
    @patch("db.profiles.get_default_profile")
    def test_global_fallback_equal_to_primary_is_dropped(self, mock_default, mock_cfg):
        from translator._helpers import _resolve_backend_for_context

        mock_default.return_value = {"translation_backend": "", "fallback_chain": []}
        cfg = {"translation_default_backend": "ollama", "translation_default_fallback": "ollama"}
        mock_cfg.side_effect = lambda k: cfg.get(k)

        backend, chain = _resolve_backend_for_context(None, "de")
        assert backend == "ollama"
        assert chain == ["ollama"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_translator_helpers.py::TestResolveBackendForContext -q`
Expected: the 4 new tests FAIL (current code coerces empty→"ollama" and never reads config).

- [ ] **Step 3: Rewrite `_resolve_backend_for_context`**

Replace the body from `backend = profile.get(...)` to `return (backend, chain)` with:

```python
    # Guard against EMPTY values, not just missing keys. An empty
    # translation_backend means "inherit the global default" (config_entries
    # translation_default_backend / translation_default_fallback). This turns
    # the empty-profile state from a bug into a first-class feature.
    prof_backend = profile.get("translation_backend")
    if prof_backend:
        primary = prof_backend
        prof_chain = [b for b in (profile.get("fallback_chain") or []) if b]
        fallback = next((b for b in prof_chain if b != primary), None)
    else:
        from db.config import get_config_entry

        primary = get_config_entry("translation_default_backend") or "ollama"
        fallback = get_config_entry("translation_default_fallback") or None
        if fallback == primary:
            fallback = None

    chain = [primary] + ([fallback] if fallback else [])
    return (primary, chain)
```

- [ ] **Step 4: Run tests to verify they pass** (new + existing)

Run: `cd backend && python -m pytest tests/test_translator_helpers.py -q`
Expected: PASS (including the pre-existing `test_empty_profile_values_coerce_to_ollama` — it uses `get_default_profile` returning empty and no config mock, so `get_config_entry` returns None in the test DB → primary "ollama", chain ["ollama"] — still green).

- [ ] **Step 5: Lint + commit**

```bash
cd backend && ruff check translator/_helpers.py tests/test_translator_helpers.py && ruff format translator/_helpers.py tests/test_translator_helpers.py
git add backend/translator/_helpers.py backend/tests/test_translator_helpers.py
git commit -m "feat(translation): resolver inherits global-default backend + single fallback"
```

---

## Task 2: `BackendSelect` shared dropdown component

**Files:**
- Create: `frontend/src/components/settings/BackendSelect.tsx`
- Test: `frontend/src/components/settings/__tests__/BackendSelect.test.tsx`

**Interfaces:**
- Consumes: `TranslationBackendInfo` from `@/lib/types` (has `name: string`, `display_name: string`, `configured: boolean`).
- Produces:
  ```ts
  interface BackendSelectProps {
    value: string                        // backend name, or "" for inherit/none
    onChange: (name: string) => void
    backends: TranslationBackendInfo[]
    inheritLabel?: string                // if set, adds a value="" option with this label (profile primary)
    noneLabel?: string                   // if set, adds a value="" option with this label (fallback selects)
    'data-testid'?: string
  }
  export function BackendSelect(props: BackendSelectProps): JSX.Element
  ```
  Renders each backend as `<option value={name}>{display_name}{configured || name==='ollama' ? '' : ' (nicht konfiguriert)'}</option>`. `inheritLabel` and `noneLabel` are mutually exclusive callers; when either is set the first option has `value=""`.

- [ ] **Step 1: Write the failing test** — `frontend/src/components/settings/__tests__/BackendSelect.test.tsx`:

```tsx
import { render, screen, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import { BackendSelect } from '../BackendSelect'

const backends = [
  { name: 'ollama', display_name: 'Ollama (Local LLM)', configured: false, supports_glossary: true, supports_batch: true, max_batch_size: 25, config_fields: [] },
  { name: 'deepl', display_name: 'DeepL', configured: true, supports_glossary: true, supports_batch: true, max_batch_size: 50, config_fields: [] },
  { name: 'claude', display_name: 'Anthropic Claude', configured: false, supports_glossary: true, supports_batch: true, max_batch_size: 50, config_fields: [] },
] as any

describe('BackendSelect', () => {
  it('marks unconfigured backends except ollama', () => {
    render(<BackendSelect value="deepl" onChange={() => {}} backends={backends} />)
    expect(screen.getByRole('option', { name: 'DeepL' })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: /Anthropic Claude \(nicht konfiguriert\)/ })).toBeInTheDocument()
    // ollama is local-only, never flagged
    expect(screen.getByRole('option', { name: 'Ollama (Local LLM)' })).toBeInTheDocument()
  })

  it('adds an inherit option and emits its value', () => {
    const onChange = vi.fn()
    render(<BackendSelect value="" onChange={onChange} backends={backends} inheritLabel="Standardvorgabe verwenden" data-testid="sel" />)
    expect(screen.getByRole('option', { name: 'Standardvorgabe verwenden' })).toBeInTheDocument()
    fireEvent.change(screen.getByTestId('sel'), { target: { value: 'deepl' } })
    expect(onChange).toHaveBeenCalledWith('deepl')
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/components/settings/__tests__/BackendSelect.test.tsx`
Expected: FAIL — cannot resolve `../BackendSelect`.

- [ ] **Step 3: Implement `BackendSelect.tsx`**

```tsx
import type { TranslationBackendInfo } from '@/lib/types'

interface BackendSelectProps {
  value: string
  onChange: (name: string) => void
  backends: TranslationBackendInfo[]
  inheritLabel?: string
  noneLabel?: string
  'data-testid'?: string
}

export function BackendSelect({ value, onChange, backends, inheritLabel, noneLabel, ...rest }: BackendSelectProps) {
  const emptyLabel = inheritLabel ?? noneLabel
  return (
    <select
      data-testid={rest['data-testid']}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className="w-full px-2.5 py-1.5 rounded text-xs bg-surface border border-border text-primary"
    >
      {emptyLabel !== undefined && <option value="">{emptyLabel}</option>}
      {backends.map((b) => (
        <option key={b.name} value={b.name}>
          {b.display_name}
          {b.configured || b.name === 'ollama' ? '' : ' (nicht konfiguriert)'}
        </option>
      ))}
    </select>
  )
}
```

> Note: the "(nicht konfiguriert)" text is intentionally inline here because `<option>` cannot render child elements or per-option i18n components; the caller localizes surrounding labels. If i18n of this suffix is required, pass it as a prop `unconfiguredSuffix` — deferred (YAGNI) until a second locale needs it in an option.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npx vitest run src/components/settings/__tests__/BackendSelect.test.tsx`
Expected: PASS.

- [ ] **Step 5: Typecheck + commit**

```bash
cd frontend && npx tsc --noEmit
git add frontend/src/components/settings/BackendSelect.tsx frontend/src/components/settings/__tests__/BackendSelect.test.tsx
git commit -m "feat(translation-ui): add shared BackendSelect dropdown"
```

---

## Task 3: Global default control on the Backends page

**Files:**
- Create: `frontend/src/pages/Settings/translation/DefaultBackendSection.tsx`
- Test: `frontend/src/pages/Settings/translation/__tests__/DefaultBackendSection.test.tsx`
- Modify: `frontend/src/pages/Settings/translation/TranslationBackendsTab.tsx` (mount the section)
- Modify: `frontend/src/i18n/locales/de/settings.json`, `frontend/src/i18n/locales/en/settings.json`

**Interfaces:**
- Consumes: `useBackends()` → `{ data: TranslationBackendInfo[] | undefined }`; `useConfig()` → `{ data: Record<string,string> | undefined }`; `useUpdateConfig()` → `{ mutate(obj: Record<string,string>) }`; `BackendSelect` from Task 2.
- Produces: `<DefaultBackendSection />` — reads `translation_default_backend` / `translation_default_fallback` from config, writes them via `useUpdateConfig().mutate` on change.

- [ ] **Step 1: Add i18n keys** — under the existing `translation_backends` object in BOTH locale files.

`de/settings.json`:
```json
"default_backend_title": "Standard-Übersetzungs-Backend",
"default_backend_help": "Wird für Übersetzungen genutzt, sofern ein Sprachprofil nichts anderes vorgibt.",
"default_backend_primary": "Primär",
"default_backend_fallback": "Fallback (optional)",
"default_backend_none": "— kein Fallback —",
"default_backend_unconfigured_warn": "Dieses Backend hat noch keinen API-Key — Übersetzung würde fehlschlagen. Weiter unten konfigurieren."
```
`en/settings.json`:
```json
"default_backend_title": "Default translation backend",
"default_backend_help": "Used for translations unless a language profile overrides it.",
"default_backend_primary": "Primary",
"default_backend_fallback": "Fallback (optional)",
"default_backend_none": "— no fallback —",
"default_backend_unconfigured_warn": "This backend has no API key yet — translation would fail. Configure it below."
```

- [ ] **Step 2: Write the failing test** — `__tests__/DefaultBackendSection.test.tsx`:

```tsx
import { render, screen, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'

const mutate = vi.fn()
vi.mock('@/hooks/useApi', () => ({
  useBackends: () => ({ data: [
    { name: 'ollama', display_name: 'Ollama (Local LLM)', configured: false },
    { name: 'deepl', display_name: 'DeepL', configured: true },
  ] }),
  useConfig: () => ({ data: { translation_default_backend: 'ollama', translation_default_fallback: '' } }),
  useUpdateConfig: () => ({ mutate }),
}))
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k: string) => k }) }))

import { DefaultBackendSection } from '../DefaultBackendSection'

describe('DefaultBackendSection', () => {
  it('saves the primary backend on change', () => {
    render(<DefaultBackendSection />)
    fireEvent.change(screen.getByTestId('default-backend-primary'), { target: { value: 'deepl' } })
    expect(mutate).toHaveBeenCalledWith({ translation_default_backend: 'deepl' })
  })
  it('saves the fallback on change', () => {
    render(<DefaultBackendSection />)
    fireEvent.change(screen.getByTestId('default-backend-fallback'), { target: { value: 'ollama' } })
    expect(mutate).toHaveBeenCalledWith({ translation_default_fallback: 'ollama' })
  })
})
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/pages/Settings/translation/__tests__/DefaultBackendSection.test.tsx`
Expected: FAIL — cannot resolve `../DefaultBackendSection`.

- [ ] **Step 4: Implement `DefaultBackendSection.tsx`**

```tsx
import { useTranslation } from 'react-i18next'
import { SettingRow } from '@/components/shared/SettingRow'
import { useBackends, useConfig, useUpdateConfig } from '@/hooks/useApi'
import { BackendSelect } from '@/components/settings/BackendSelect'

export function DefaultBackendSection() {
  const { t } = useTranslation('settings')
  const { data: backends } = useBackends()
  const { data: config } = useConfig()
  const updateConfig = useUpdateConfig()

  const primary = config?.translation_default_backend ?? 'ollama'
  const fallback = config?.translation_default_fallback ?? ''
  const list = backends ?? []

  const primaryUnconfigured =
    primary !== 'ollama' && !list.find((b) => b.name === primary)?.configured

  return (
    <div className="rounded-lg p-4 space-y-3 bg-surface border border-border">
      <h2 className="text-sm font-semibold text-primary">{t('translation_backends.default_backend_title')}</h2>
      <p className="text-xs text-muted">{t('translation_backends.default_backend_help')}</p>

      <SettingRow label={t('translation_backends.default_backend_primary')}>
        <BackendSelect
          data-testid="default-backend-primary"
          value={primary}
          backends={list}
          onChange={(name) => updateConfig.mutate({ translation_default_backend: name })}
        />
      </SettingRow>

      {primaryUnconfigured && (
        <p className="text-xs text-warning">{t('translation_backends.default_backend_unconfigured_warn')}</p>
      )}

      <SettingRow label={t('translation_backends.default_backend_fallback')}>
        <BackendSelect
          data-testid="default-backend-fallback"
          value={fallback}
          backends={list}
          noneLabel={t('translation_backends.default_backend_none')}
          onChange={(name) => updateConfig.mutate({ translation_default_fallback: name })}
        />
      </SettingRow>
    </div>
  )
}
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd frontend && npx vitest run src/pages/Settings/translation/__tests__/DefaultBackendSection.test.tsx`
Expected: PASS.

- [ ] **Step 6: Mount it in `TranslationBackendsTab.tsx`**

Add the import near the other page imports:
```tsx
import { DefaultBackendSection } from '@/pages/Settings/translation/DefaultBackendSection'
```
Render `<DefaultBackendSection />` immediately before the backends list header (the `flex items-center justify-between` block that holds `backends_available` + `add_from_template`, ~line 337). Place it as the first child of that section's container.

- [ ] **Step 7: Typecheck + lint + commit**

```bash
cd frontend && npx tsc --noEmit && npx eslint src/pages/Settings/translation/DefaultBackendSection.tsx src/components/settings/BackendSelect.tsx
git add frontend/src/pages/Settings/translation/DefaultBackendSection.tsx frontend/src/pages/Settings/translation/__tests__/DefaultBackendSection.test.tsx frontend/src/pages/Settings/translation/TranslationBackendsTab.tsx frontend/src/i18n/locales/de/settings.json frontend/src/i18n/locales/en/settings.json
git commit -m "feat(translation-ui): global default backend + fallback control"
```

---

## Task 4: Per-profile backend override in the profile editor

**Files:**
- Modify: `frontend/src/pages/Settings/LanguageProfilesTab.tsx` (form state, edit prefill, save payload, two new fields)
- Modify: `frontend/src/i18n/locales/de/settings.json`, `frontend/src/i18n/locales/en/settings.json`
- Test: extend `frontend/src/pages/__tests__/LanguageProfiles.test.tsx` (existing profiles test)

**Interfaces:**
- Consumes: `useBackends()`, `BackendSelect`, existing `LanguageProfile` type (already has `translation_backend?: string` and `fallback_chain?: string[]` via the profiles API `to_dict`).
- Produces: the profile save payload now includes `translation_backend: string` (`""` = inherit) and `fallback_chain: string[]` (`[]` when inheriting, `[primary]` or `[primary, fallback]` when overriding).

- [ ] **Step 1: Add i18n keys** — under `language_profiles` in BOTH locale files.

`de`:
```json
"translation_backend_label": "Übersetzungs-Backend",
"translation_backend_inherit": "Standardvorgabe verwenden",
"translation_backend_fallback": "Fallback (optional)",
"translation_backend_none": "— kein Fallback —",
"translation_backend_help": "Leer = globaler Standard. Sonst nutzt dieses Profil das gewählte Backend (Fallback nur bei Fehlschlag)."
```
`en`:
```json
"translation_backend_label": "Translation backend",
"translation_backend_inherit": "Use global default",
"translation_backend_fallback": "Fallback (optional)",
"translation_backend_none": "— no fallback —",
"translation_backend_help": "Empty = global default. Otherwise this profile uses the chosen backend (fallback only on failure)."
```

- [ ] **Step 2: Write the failing test** — add to `LanguageProfiles.test.tsx`. It asserts that saving an edited profile with an override sends `translation_backend` + `fallback_chain` in the payload. Match the file's existing mocking style for `useUpdateProfile`; the assertion core:

```tsx
// after selecting primary=deepl and fallback=ollama in the edit form and clicking save:
expect(updateMutate).toHaveBeenCalledWith(
  expect.objectContaining({
    data: expect.objectContaining({
      translation_backend: 'deepl',
      fallback_chain: ['deepl', 'ollama'],
    }),
  }),
  expect.anything(),
)
```

(If the existing test file has no edit-save test to extend, add one modelled on the file's create/save tests: render `<LanguageProfilesTab />` with a mocked profile list containing one profile, click its edit button, change the two selects via their `data-testid`s `profile-backend` / `profile-fallback`, click save, assert the payload.)

- [ ] **Step 3: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/pages/__tests__/LanguageProfiles.test.tsx`
Expected: FAIL — payload lacks `translation_backend`/`fallback_chain`.

- [ ] **Step 4: Implement the form changes in `LanguageProfilesTab.tsx`**

4a. Add to the `form` state initializer (and both `resetForm` / add-button resets) two fields:
```tsx
translation_backend: '' as string,
fallback_backend: '' as string,
```
4b. In `startEdit`, prefill from the profile:
```tsx
translation_backend: p.translation_backend && p.translation_backend !== '' ? p.translation_backend : '',
fallback_backend: (p.fallback_chain ?? []).filter((b) => b && b !== p.translation_backend)[0] ?? '',
```
4c. Add `const { data: backends } = useBackends()` near the other hooks, and import `BackendSelect` + `useBackends`.
4d. In `handleSave`, build the chain and extend the payload:
```tsx
const primary = form.translation_backend  // '' means inherit
const fallback = primary ? form.fallback_backend : ''
const fallback_chain = primary
  ? (fallback && fallback !== primary ? [primary, fallback] : [primary])
  : []
const payload = {
  name: form.name,
  target_languages: targetLangs,
  target_language_names: targetNames,
  forced_preference: form.forced_preference,
  forced_scoring: form.forced_scoring,
  hi_preference: form.hi_preference,
  cutoff_language: form.cutoff_language,
  translation_backend: primary,
  fallback_chain,
}
```
4e. Add two form fields inside the `grid` (after the Cutoff Language block), using Tailwind + `BackendSelect`:
```tsx
<div className="space-y-1">
  <label className="text-xs font-medium text-secondary">{t('language_profiles.translation_backend_label')}</label>
  <BackendSelect
    data-testid="profile-backend"
    value={form.translation_backend}
    backends={backends ?? []}
    inheritLabel={t('language_profiles.translation_backend_inherit')}
    onChange={(name) => setForm((f) => ({ ...f, translation_backend: name, fallback_backend: name ? f.fallback_backend : '' }))}
  />
  <p className="text-[11px] text-muted">{t('language_profiles.translation_backend_help')}</p>
</div>
{form.translation_backend && (
  <div className="space-y-1">
    <label className="text-xs font-medium text-secondary">{t('language_profiles.translation_backend_fallback')}</label>
    <BackendSelect
      data-testid="profile-fallback"
      value={form.fallback_backend}
      backends={backends ?? []}
      noneLabel={t('language_profiles.translation_backend_none')}
      onChange={(name) => setForm((f) => ({ ...f, fallback_backend: name }))}
    />
  </div>
)}
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd frontend && npx vitest run src/pages/__tests__/LanguageProfiles.test.tsx`
Expected: PASS.

- [ ] **Step 6: Typecheck + lint + commit**

```bash
cd frontend && npx tsc --noEmit && npx eslint src/pages/Settings/LanguageProfilesTab.tsx
git add frontend/src/pages/Settings/LanguageProfilesTab.tsx frontend/src/pages/__tests__/LanguageProfiles.test.tsx frontend/src/i18n/locales/de/settings.json frontend/src/i18n/locales/en/settings.json
git commit -m "feat(translation-ui): per-profile backend override + fallback"
```

---

## Task 5: End-to-end verification (no new code)

**Files:** none — verification only.

- [ ] **Step 1: Full targeted test run**

```bash
cd backend && python -m pytest tests/test_translator_helpers.py tests/test_translation_backends.py -q
cd frontend && npx vitest run src/components/settings/__tests__/BackendSelect.test.tsx src/pages/Settings/translation/__tests__/DefaultBackendSection.test.tsx src/pages/__tests__/LanguageProfiles.test.tsx && npx tsc --noEmit && npm run lint
```
Expected: all green, 0 TS errors, lint 0 errors (inline-style warnings tolerated).

- [ ] **Step 2: Manual smoke (after deploy or local dev)**

  1. Settings → Translation → Backends & Glossary: set **Default backend = DeepL**, **Fallback = Ollama**. Reload → values persist.
  2. Settings → Subtitles → Languages & Profiles → edit "Standard": leave backend = "Use global default" → save. Confirm the profile row still translates via DeepL (global default) by triggering one translation and checking the produced `.de.srt` came from DeepL (fast) vs Ollama (slow).
  3. Edit "Standard" again → set backend = Ollama (override) → save → translation now uses Ollama.
  4. Pick an unconfigured backend (e.g. Claude) in the global primary → the "no API key" warning shows; saving still works.

- [ ] **Step 3: Update docs + changelog**

Add a `### Added` line to the `[1.4.0]` section of `CHANGELOG.md`:
```markdown
- **Translation backend is now selectable in the UI** — a global default backend
  (with an optional fallback) on Settings → Translation → Backends & Glossary,
  plus a per-profile override on Languages & Profiles. Profiles inherit the global
  default unless overridden. Previously the backend was a DB-only field with no UI.
```

```bash
git add CHANGELOG.md
git commit -m "docs(changelog): note UI translation-backend selector under 1.4.0"
```

---

## Self-Review

**Spec coverage:** inheritance model → Task 1; no-migration global default → Tasks 1/3 (config_entries); resolution algorithm → Task 1; global UI → Task 3; per-profile UI → Task 4; shared `BackendSelect` → Task 2; unconfigured warning → Tasks 2 (marker) + 3 (warn line); primary+1 fallback → Tasks 3/4 payload shape; testing → each task + Task 5; i18n DE+EN → Tasks 3/4; profile-API round-trip (open check #1) → RESOLVED (repo `allowed` set already includes both fields); backends-list hook (open check #2) → RESOLVED (`useBackends()`); Pydantic-vs-config-entries (open check #3) → RESOLVED (read via `get_config_entry` in resolver, no `config_settings` churn).

**Placeholder scan:** none — every code step shows real code; the one deferred item (`unconfiguredSuffix` prop) is explicitly YAGNI, not a gap.

**Type consistency:** `BackendSelect` props (`value`/`onChange`/`backends`/`inheritLabel`/`noneLabel`) are used identically in Tasks 3 and 4. Config keys `translation_default_backend` / `translation_default_fallback` match between Task 1 (resolver reads) and Task 3 (UI writes). Payload keys `translation_backend` / `fallback_chain` match the backend `allowed` set and `to_dict` output.
