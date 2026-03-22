# Plan: Steps 15–18 — ProvidersSettings Missing Fields

**Date:** 2026-03-21
**Branch:** feature/frontend-redesign
**Spec:** `docs/superpowers/specs/2026-03-21-ui-improvement-plan-design.md` (Steps 15–18)
**Files touched:**
- `frontend/src/pages/Settings/ProvidersSettings.tsx`
- `frontend/src/pages/Settings/__tests__/ProvidersSettings.test.tsx`

---

## Context

`ProvidersSettings.tsx` has four existing sections:
1. **Installed Providers** — renders `<ProvidersTab>` (handles provider grid, priorities, credentials) but is missing 7 global config fields that live above or below the grid.
2. **Marketplace** — renders `<MarketplaceTab>` but is missing 3 config fields.
3. **Anti-Captcha** — has `anti_captcha_provider` + `anti_captcha_api_key` but uses raw `<div>/<select>/<input>` instead of `FormGroup`. Needs design alignment only.
4. **Cache Management** — already correct; do not touch.

The existing test file (`ProvidersSettings.test.tsx`) mocks `useConfig` to return:
```ts
{ anti_captcha_provider: '', anti_captcha_api_key: '' }
```
All new tests must extend this mock data with the new config keys.

### Pattern Reference (use exactly)

**Config helpers** (from `AutomationSettings.tsx`):
```ts
function strVal(config: unknown, key: string, fallback = ''): string {
  if (!config || typeof config !== 'object') return fallback
  const v = (config as Record<string, unknown>)[key]
  return v !== undefined && v !== null ? String(v) : fallback
}

function boolVal(config: unknown, key: string, fallback = false): boolean {
  if (!config || typeof config !== 'object') return fallback
  const v = (config as Record<string, unknown>)[key]
  if (v === undefined || v === null) return fallback
  return v === true || v === 'true' || v === 1
}
```

**Input style** (shared CSS object):
```ts
const inputStyle: React.CSSProperties = {
  background: 'var(--bg-elevated)',
  border: '1px solid var(--border)',
  color: 'var(--text-primary)',
  borderRadius: '6px',
  padding: '7px 12px',
  fontSize: '13px',
  fontFamily: 'var(--font-body)',
  width: '220px',
  outline: 'none',
}
```

**Toggle** — `<Toggle checked={boolVal(config, 'key')} onChange={(v) => save({ key: v })} />`
**Number input** — `type="number"` with `style={{ ...inputStyle, maxWidth: '120px' }}`, `onChange` casts to `Number(e.target.value)`.
**Password input** — `type="password"` with full `inputStyle` width.
**Text input** — `type="text"` with full `inputStyle` width.

**FormGroup** — `<FormGroup label="..." hint="..." htmlFor="..." data-testid="form-group-...">`

**Advanced prop on SettingsSection** — pass JSX as `advanced={<>...</>}` prop. SettingsSection renders a collapsible "Advanced" toggle that shows the content. The `advanced` prop is already supported; do not modify `SettingsSection.tsx`.

**Save pattern** — `const { mutate: updateConfig } = useUpdateConfig()` → `const save = (patch: Record<string, unknown>) => updateConfig(patch)`.

---

## PROTECTED: Do Not Touch

Per `docs/PROTECTED.md`:
- `SettingsSection.tsx`, `FormGroup.tsx`, `SettingsDetailLayout.tsx` — props API and CSS are frozen.
- The existing Cache Management section — already correct, leave as-is.
- The existing test structure (mocks, `renderPage()` helper, `beforeEach` clearing) — extend only, do not restructure.

---

## Task 1 — Step 15: Add 7 fields to Installed Providers section

### TDD: Write failing tests first

- [ ] Open `frontend/src/pages/Settings/__tests__/ProvidersSettings.test.tsx`

- [ ] Extend the `useConfig` mock data to include all new keys:
  ```ts
  useConfig: () => ({
    data: {
      anti_captcha_provider: '',
      anti_captcha_api_key: '',
      providers_hidden: '',
      dedup_on_download: false,
      provider_auto_prioritize: false,
      provider_rate_limit_enabled: false,
      provider_search_timeout: 30,
      provider_cache_ttl_minutes: 60,
      provider_auto_disable_cooldown_minutes: 30,
    },
    isLoading: false,
  }),
  ```

- [ ] Add a `describe('Step 15 — installed section fields', ...)` block with these tests:

  ```ts
  describe('Step 15 — installed section fields', () => {
    it('renders providers_hidden text input', () => {
      renderPage()
      expect(screen.getByTestId('input-providers-hidden')).toBeInTheDocument()
    })

    it('renders dedup_on_download toggle', () => {
      renderPage()
      expect(screen.getByTestId('toggle-dedup-on-download')).toBeInTheDocument()
    })

    it('renders provider_auto_prioritize toggle', () => {
      renderPage()
      expect(screen.getByTestId('toggle-provider-auto-prioritize')).toBeInTheDocument()
    })

    it('renders provider_rate_limit_enabled toggle', () => {
      renderPage()
      expect(screen.getByTestId('toggle-provider-rate-limit-enabled')).toBeInTheDocument()
    })

    it('renders provider_search_timeout number input', () => {
      renderPage()
      expect(screen.getByTestId('input-provider-search-timeout')).toBeInTheDocument()
    })

    it('renders provider_cache_ttl_minutes number input', () => {
      renderPage()
      expect(screen.getByTestId('input-provider-cache-ttl-minutes')).toBeInTheDocument()
    })

    it('renders provider_auto_disable_cooldown_minutes number input', () => {
      renderPage()
      expect(screen.getByTestId('input-provider-auto-disable-cooldown-minutes')).toBeInTheDocument()
    })

    it('calls updateConfig when providers_hidden changes', () => {
      renderPage()
      fireEvent.change(screen.getByTestId('input-providers-hidden'), {
        target: { value: 'opensubtitles' },
      })
      expect(mockUpdateConfig).toHaveBeenCalledWith({ providers_hidden: 'opensubtitles' })
    })

    it('calls updateConfig when dedup_on_download toggle is clicked', () => {
      renderPage()
      fireEvent.click(screen.getByTestId('toggle-dedup-on-download'))
      expect(mockUpdateConfig).toHaveBeenCalledWith({ dedup_on_download: true })
    })

    it('calls updateConfig when provider_search_timeout changes', () => {
      renderPage()
      fireEvent.change(screen.getByTestId('input-provider-search-timeout'), {
        target: { value: '45' },
      })
      expect(mockUpdateConfig).toHaveBeenCalledWith({ provider_search_timeout: 45 })
    })
  })
  ```

- [ ] Run tests — confirm they FAIL (RED):
  ```bash
  cd frontend && npm run test -- --run --reporter=verbose 2>&1 | grep -E "FAIL|PASS|✓|✗|×" | tail -30
  ```

### Implement the fields

- [ ] Open `frontend/src/pages/Settings/ProvidersSettings.tsx`

- [ ] Add imports at the top — add `FormGroup`, `Toggle`, and the helper functions. The file currently imports from `@/hooks/useApi`, `lucide-react`, etc. Add:
  ```ts
  import { FormGroup } from '@/components/settings/FormGroup'
  import { Toggle } from '@/components/shared/Toggle'
  ```

- [ ] Add the two helper functions and `inputStyle` constant after the imports, before the component:
  ```ts
  function strVal(config: unknown, key: string, fallback = ''): string {
    if (!config || typeof config !== 'object') return fallback
    const v = (config as Record<string, unknown>)[key]
    return v !== undefined && v !== null ? String(v) : fallback
  }

  function boolVal(config: unknown, key: string, fallback = false): boolean {
    if (!config || typeof config !== 'object') return fallback
    const v = (config as Record<string, unknown>)[key]
    if (v === undefined || v === null) return fallback
    return v === true || v === 'true' || v === 1
  }

  const inputStyle: React.CSSProperties = {
    background: 'var(--bg-elevated)',
    border: '1px solid var(--border)',
    color: 'var(--text-primary)',
    borderRadius: '6px',
    padding: '7px 12px',
    fontSize: '13px',
    fontFamily: 'var(--font-body)',
    width: '220px',
    outline: 'none',
  }
  ```

- [ ] In `ProvidersSettings`, change the data access from the existing `values` pattern to use `configData` directly with `strVal`/`boolVal`. Currently the component derives `values: Record<string, string>` and passes it down to `ProvidersTab` — keep that for `ProvidersTab` (it needs the string record). Add a `save` alias:
  ```ts
  const save = (patch: Record<string, unknown>) => updateConfig.mutate(patch)
  ```

- [ ] Locate the Installed Providers section. Currently it contains:
  ```tsx
  <div className="py-4" data-testid="providers-installed-content">
    <ProvidersTab values={values} onFieldChange={handleFieldChange} onSave={handleSave} />
  </div>
  ```
  Replace this with a structure that renders `ProvidersTab` first, then appends the 7 new `FormGroup` rows below it inside the same `providers-installed-content` div:

  ```tsx
  <div className="py-4 space-y-0" data-testid="providers-installed-content">
    <ProvidersTab
      values={values}
      onFieldChange={handleFieldChange}
      onSave={handleSave}
    />

    <div className="mt-6 space-y-0">
      <FormGroup
        label="Hidden Providers"
        hint="Comma-separated provider IDs to hide from the grid (e.g. opensubtitles,kitsunekko)."
        htmlFor="providers-hidden"
        data-testid="form-group-providers-hidden"
      >
        <input
          id="providers-hidden"
          type="text"
          data-testid="input-providers-hidden"
          style={inputStyle}
          value={strVal(configData, 'providers_hidden')}
          onChange={(e) => save({ providers_hidden: e.target.value })}
          placeholder="opensubtitles,kitsunekko"
        />
      </FormGroup>

      <FormGroup
        label="Deduplicate on Download"
        hint="Skip downloading a subtitle if an identical file is already present."
        data-testid="form-group-dedup-on-download"
      >
        <Toggle
          data-testid="toggle-dedup-on-download"
          checked={boolVal(configData, 'dedup_on_download')}
          onChange={(v) => save({ dedup_on_download: v })}
        />
      </FormGroup>

      <FormGroup
        label="Auto-Prioritize Providers"
        hint="Automatically sort providers by recent success rate."
        data-testid="form-group-provider-auto-prioritize"
      >
        <Toggle
          data-testid="toggle-provider-auto-prioritize"
          checked={boolVal(configData, 'provider_auto_prioritize')}
          onChange={(v) => save({ provider_auto_prioritize: v })}
        />
      </FormGroup>

      <FormGroup
        label="Rate Limiting"
        hint="Enforce per-provider request rate limits to avoid bans."
        data-testid="form-group-provider-rate-limit-enabled"
      >
        <Toggle
          data-testid="toggle-provider-rate-limit-enabled"
          checked={boolVal(configData, 'provider_rate_limit_enabled')}
          onChange={(v) => save({ provider_rate_limit_enabled: v })}
        />
      </FormGroup>

      <FormGroup
        label="Search Timeout (s)"
        hint="Seconds before a provider search request times out."
        htmlFor="provider-search-timeout"
        data-testid="form-group-provider-search-timeout"
      >
        <input
          id="provider-search-timeout"
          type="number"
          data-testid="input-provider-search-timeout"
          style={{ ...inputStyle, maxWidth: '120px' }}
          value={strVal(configData, 'provider_search_timeout', '30')}
          onChange={(e) => save({ provider_search_timeout: Number(e.target.value) })}
          min={1}
          placeholder="30"
        />
      </FormGroup>

      <FormGroup
        label="Cache TTL (minutes)"
        hint="How long to cache provider search results before expiring."
        htmlFor="provider-cache-ttl-minutes"
        data-testid="form-group-provider-cache-ttl-minutes"
      >
        <input
          id="provider-cache-ttl-minutes"
          type="number"
          data-testid="input-provider-cache-ttl-minutes"
          style={{ ...inputStyle, maxWidth: '120px' }}
          value={strVal(configData, 'provider_cache_ttl_minutes', '60')}
          onChange={(e) => save({ provider_cache_ttl_minutes: Number(e.target.value) })}
          min={0}
          placeholder="60"
        />
      </FormGroup>

      <FormGroup
        label="Auto-Disable Cooldown (min)"
        hint="Minutes a provider stays disabled after repeated failures."
        htmlFor="provider-auto-disable-cooldown-minutes"
        data-testid="form-group-provider-auto-disable-cooldown-minutes"
      >
        <input
          id="provider-auto-disable-cooldown-minutes"
          type="number"
          data-testid="input-provider-auto-disable-cooldown-minutes"
          style={{ ...inputStyle, maxWidth: '120px' }}
          value={strVal(configData, 'provider_auto_disable_cooldown_minutes', '30')}
          onChange={(e) =>
            save({ provider_auto_disable_cooldown_minutes: Number(e.target.value) })
          }
          min={0}
          placeholder="30"
        />
      </FormGroup>
    </div>
  </div>
  ```

  **Important:** `Toggle` does not have a `data-testid` prop in the component API (see `Toggle.tsx` — it only accepts `checked`, `onChange`, `disabled`). Instead, wrap the Toggle in a `<div data-testid="toggle-dedup-on-download">` for test targeting:
  ```tsx
  <div data-testid="toggle-dedup-on-download">
    <Toggle
      checked={boolVal(configData, 'dedup_on_download')}
      onChange={(v) => save({ dedup_on_download: v })}
    />
  </div>
  ```
  Apply the same wrapper pattern for all 4 toggle fields in this task (use the `data-testid` on the wrapping div, not on `<Toggle>`).

- [ ] Run tests — confirm they PASS (GREEN):
  ```bash
  cd frontend && npm run test -- --run --reporter=verbose 2>&1 | grep -E "FAIL|PASS|Step 15" | tail -20
  ```

- [ ] Run lint + type check:
  ```bash
  cd frontend && npm run lint && npx tsc --noEmit
  ```

- [ ] Commit:
  ```bash
  cd "D:/Sublarr_Projekt/Sublarr" && git add frontend/src/pages/Settings/ProvidersSettings.tsx frontend/src/pages/Settings/__tests__/ProvidersSettings.test.tsx && git commit -m "feat: add provider config fields to ProvidersSettings installed section"
  ```

---

## Task 2 — Step 16 + Step 17: Marketplace fields + Anti-Captcha design alignment

### TDD: Write failing tests first

- [ ] Open `frontend/src/pages/Settings/__tests__/ProvidersSettings.test.tsx`

- [ ] Extend the `useConfig` mock data further (add to the existing extended mock from Task 1):
  ```ts
  github_token: '',
  plugins_dir: '',
  plugin_hot_reload: false,
  ```

- [ ] Add a `describe('Step 16 — marketplace section fields', ...)` block:
  ```ts
  describe('Step 16 — marketplace section fields', () => {
    it('renders github_token password input', () => {
      renderPage()
      expect(screen.getByTestId('input-github-token')).toBeInTheDocument()
    })

    it('github_token is type="password"', () => {
      renderPage()
      expect(screen.getByTestId('input-github-token')).toHaveAttribute('type', 'password')
    })

    it('renders plugins_dir text input', () => {
      renderPage()
      expect(screen.getByTestId('input-plugins-dir')).toBeInTheDocument()
    })

    it('renders plugin_hot_reload toggle', () => {
      renderPage()
      expect(screen.getByTestId('toggle-plugin-hot-reload')).toBeInTheDocument()
    })

    it('calls updateConfig when github_token changes', () => {
      renderPage()
      fireEvent.change(screen.getByTestId('input-github-token'), {
        target: { value: 'ghp_abc123' },
      })
      expect(mockUpdateConfig).toHaveBeenCalledWith({ github_token: 'ghp_abc123' })
    })
  })
  ```

- [ ] Add a `describe('Step 17 — anti-captcha design alignment', ...)` block:
  ```ts
  describe('Step 17 — anti-captcha design alignment', () => {
    it('anti-captcha backend select is wrapped in a FormGroup', () => {
      renderPage()
      // FormGroup renders data-testid="form-group-anti-captcha-backend"
      expect(screen.getByTestId('form-group-anti-captcha-backend')).toBeInTheDocument()
    })
  })
  ```

- [ ] Run tests — confirm they FAIL (RED):
  ```bash
  cd frontend && npm run test -- --run --reporter=verbose 2>&1 | grep -E "FAIL|PASS|Step 16|Step 17" | tail -20
  ```

### Implement marketplace fields (Step 16)

- [ ] In `ProvidersSettings.tsx`, locate the Marketplace section. Currently it contains:
  ```tsx
  <div className="py-4" data-testid="providers-marketplace-content">
    <MarketplaceTab />
  </div>
  ```
  Replace with:
  ```tsx
  <div className="py-4 space-y-0" data-testid="providers-marketplace-content">
    <MarketplaceTab />

    <div className="mt-6 space-y-0">
      <FormGroup
        label="GitHub Token"
        hint="Personal access token for higher Marketplace API rate limits."
        htmlFor="github-token"
        data-testid="form-group-github-token"
      >
        <input
          id="github-token"
          type="password"
          data-testid="input-github-token"
          style={inputStyle}
          value={strVal(configData, 'github_token')}
          onChange={(e) => save({ github_token: e.target.value })}
          placeholder="ghp_..."
          autoComplete="off"
        />
      </FormGroup>

      <FormGroup
        label="Plugins Directory"
        hint="Path where plugin files are stored. Leave empty to use the default."
        htmlFor="plugins-dir"
        data-testid="form-group-plugins-dir"
      >
        <input
          id="plugins-dir"
          type="text"
          data-testid="input-plugins-dir"
          style={inputStyle}
          value={strVal(configData, 'plugins_dir')}
          onChange={(e) => save({ plugins_dir: e.target.value })}
          placeholder="/config/plugins"
        />
      </FormGroup>

      <FormGroup
        label="Hot Reload Plugins"
        hint="Automatically reload plugins when their files change on disk."
        data-testid="form-group-plugin-hot-reload"
      >
        <div data-testid="toggle-plugin-hot-reload">
          <Toggle
            checked={boolVal(configData, 'plugin_hot_reload')}
            onChange={(v) => save({ plugin_hot_reload: v })}
          />
        </div>
      </FormGroup>
    </div>
  </div>
  ```

### Implement Anti-Captcha design alignment (Step 17)

- [ ] In `ProvidersSettings.tsx`, locate the Anti-Captcha section. Currently it uses raw `<div className="grid grid-cols-[160px_1fr]...">` for layout. Replace the inner content with `FormGroup` pattern while keeping the same config keys and behavior:

  ```tsx
  <div className="py-4 space-y-0" data-testid="providers-anticaptcha-content">
    <FormGroup
      label="Backend"
      hint="Select the anti-captcha service provider."
      htmlFor="anti-captcha-backend"
      data-testid="form-group-anti-captcha-backend"
    >
      <select
        id="anti-captcha-backend"
        value={strVal(configData, 'anti_captcha_provider')}
        onChange={(e) => save({ anti_captcha_provider: e.target.value })}
        style={{
          ...inputStyle,
          width: '220px',
        }}
      >
        <option value="">{t('settings.providers.anticaptcha.disabled', 'Disabled')}</option>
        <option value="anticaptcha">Anti-Captcha.com</option>
        <option value="capmonster">CapMonster</option>
      </select>
    </FormGroup>

    {strVal(configData, 'anti_captcha_provider') && (
      <FormGroup
        label="API Key"
        hint="Your anti-captcha service API key."
        htmlFor="anti-captcha-api-key"
        data-testid="form-group-anti-captcha-api-key"
      >
        <input
          id="anti-captcha-api-key"
          type="password"
          data-testid="input-anti-captcha-api-key"
          style={inputStyle}
          value={strVal(configData, 'anti_captcha_api_key')}
          onChange={(e) => save({ anti_captcha_api_key: e.target.value })}
          placeholder={t('settings.providers.anticaptcha.api_key_placeholder', 'Your API key')}
          autoComplete="off"
        />
      </FormGroup>
    )}
  </div>
  ```

  **Existing test compatibility:** The existing test `'renders the backend select in the anti-captcha section'` finds the select via `screen.getByRole('combobox', { name: /Backend/i })`. The new `<select>` will have `id="anti-captcha-backend"` and `<FormGroup>` renders a `<label htmlFor="anti-captcha-backend">`, so `getByRole('combobox', { name: /Backend/i })` will still pass.

  The test `'calls updateConfig when anti-captcha backend changes'` checks `mockUpdateConfig` was called with `{ anti_captcha_provider: 'anticaptcha' }`. The new `onChange` calls `save({ anti_captcha_provider: e.target.value })` which calls `updateConfig(patch)` — matches.

  The test `'does not render API key field when captcha provider is empty'` checks `screen.queryByLabelText(/API Key/i)` returns null. With `strVal(configData, 'anti_captcha_provider')` returning `''` (falsy), the conditional block does not render. The `<FormGroup label="API Key">` renders a `<label>` — so `queryByLabelText` still works correctly.

- [ ] Run tests — confirm they PASS (GREEN):
  ```bash
  cd frontend && npm run test -- --run --reporter=verbose 2>&1 | grep -E "FAIL|PASS|Step 16|Step 17|anti-captcha" | tail -30
  ```

- [ ] Run lint + type check:
  ```bash
  cd frontend && npm run lint && npx tsc --noEmit
  ```

- [ ] Commit:
  ```bash
  cd "D:/Sublarr_Projekt/Sublarr" && git add frontend/src/pages/Settings/ProvidersSettings.tsx frontend/src/pages/Settings/__tests__/ProvidersSettings.test.tsx && git commit -m "feat: add marketplace github token and plugin fields to ProvidersSettings"
  ```

---

## Task 3 — Step 18: Advanced section (reranking, dynamic timeouts, circuit breaker)

### TDD: Write failing tests first

- [ ] Open `frontend/src/pages/Settings/__tests__/ProvidersSettings.test.tsx`

- [ ] Extend the `useConfig` mock data further:
  ```ts
  provider_reranking_enabled: false,
  provider_reranking_min_downloads: 10,
  provider_reranking_max_modifier: 0.3,
  provider_dynamic_timeout_enabled: false,
  provider_dynamic_timeout_min_samples: 5,
  provider_dynamic_timeout_multiplier: 1.5,
  provider_dynamic_timeout_buffer_secs: 2,
  provider_dynamic_timeout_min_secs: 5,
  provider_dynamic_timeout_max_secs: 60,
  circuit_breaker_failure_threshold: 5,
  circuit_breaker_cooldown_seconds: 300,
  ```

- [ ] Add a `describe('Step 18 — advanced section', ...)` block:
  ```ts
  describe('Step 18 — advanced section', () => {
    it('renders the advanced settings section', () => {
      renderPage()
      expect(screen.getByTestId('providers-advanced-section')).toBeInTheDocument()
    })

    it('advanced section has an Advanced toggle button', () => {
      renderPage()
      expect(screen.getByTestId('settings-section-advanced-toggle')).toBeInTheDocument()
    })

    it('advanced content is hidden by default (collapsed)', () => {
      renderPage()
      expect(screen.queryByTestId('settings-section-advanced-content')).not.toBeInTheDocument()
    })

    it('clicking Advanced toggle reveals the advanced content', () => {
      renderPage()
      fireEvent.click(screen.getByTestId('settings-section-advanced-toggle'))
      expect(screen.getByTestId('settings-section-advanced-content')).toBeInTheDocument()
    })

    it('advanced content contains provider_reranking_enabled toggle after expand', () => {
      renderPage()
      fireEvent.click(screen.getByTestId('settings-section-advanced-toggle'))
      expect(screen.getByTestId('toggle-provider-reranking-enabled')).toBeInTheDocument()
    })

    it('advanced content contains circuit_breaker_failure_threshold input after expand', () => {
      renderPage()
      fireEvent.click(screen.getByTestId('settings-section-advanced-toggle'))
      expect(
        screen.getByTestId('input-circuit-breaker-failure-threshold'),
      ).toBeInTheDocument()
    })

    it('calls updateConfig when provider_reranking_enabled is toggled', () => {
      renderPage()
      fireEvent.click(screen.getByTestId('settings-section-advanced-toggle'))
      fireEvent.click(screen.getByTestId('toggle-provider-reranking-enabled'))
      expect(mockUpdateConfig).toHaveBeenCalledWith({ provider_reranking_enabled: true })
    })

    it('calls updateConfig when circuit_breaker_cooldown_seconds changes', () => {
      renderPage()
      fireEvent.click(screen.getByTestId('settings-section-advanced-toggle'))
      fireEvent.change(screen.getByTestId('input-circuit-breaker-cooldown-seconds'), {
        target: { value: '600' },
      })
      expect(mockUpdateConfig).toHaveBeenCalledWith({ circuit_breaker_cooldown_seconds: 600 })
    })
  })
  ```

- [ ] Run tests — confirm they FAIL (RED):
  ```bash
  cd frontend && npm run test -- --run --reporter=verbose 2>&1 | grep -E "FAIL|PASS|Step 18" | tail -20
  ```

### Implement the Advanced section

- [ ] In `ProvidersSettings.tsx`, add a new import: `Settings2` icon from `lucide-react` (or use `Sliders` — pick whichever is already imported or use `Settings2`):
  ```ts
  import { Globe, Store, ShieldAlert, Trash2, Settings2 } from 'lucide-react'
  ```

- [ ] After the Cache Management `</SettingsSection>` block and before `</SettingsDetailLayout>`, insert the new Advanced section. Use `SettingsSection` with an `advanced` prop — the main `children` area is empty (or a brief description), and all 11 fields go into the `advanced` prop JSX:

  ```tsx
  {/* Advanced — Provider Engine */}
  <SettingsSection
    data-testid="providers-advanced-section"
    title={t('settings.providers.advanced.title', 'Provider Engine')}
    description={t(
      'settings.providers.advanced.description',
      'Fine-tune provider reranking, dynamic timeouts, and the circuit breaker.',
    )}
    icon={<Settings2 size={16} style={{ color: 'var(--accent)' }} />}
    advanced={
      <>
        {/* Reranking */}
        <FormGroup
          label="Provider Reranking"
          hint="Reorder provider results based on historical download success rates."
          data-testid="form-group-provider-reranking-enabled"
        >
          <div data-testid="toggle-provider-reranking-enabled">
            <Toggle
              checked={boolVal(configData, 'provider_reranking_enabled')}
              onChange={(v) => save({ provider_reranking_enabled: v })}
            />
          </div>
        </FormGroup>

        <FormGroup
          label="Reranking Min Downloads"
          hint="Minimum download count before a provider is eligible for reranking."
          htmlFor="provider-reranking-min-downloads"
          data-testid="form-group-provider-reranking-min-downloads"
        >
          <input
            id="provider-reranking-min-downloads"
            type="number"
            data-testid="input-provider-reranking-min-downloads"
            style={{ ...inputStyle, maxWidth: '120px' }}
            value={strVal(configData, 'provider_reranking_min_downloads', '10')}
            onChange={(e) =>
              save({ provider_reranking_min_downloads: Number(e.target.value) })
            }
            min={0}
            placeholder="10"
          />
        </FormGroup>

        <FormGroup
          label="Reranking Max Modifier"
          hint="Maximum score modifier applied by reranking (e.g. 0.3 = ±30%)."
          htmlFor="provider-reranking-max-modifier"
          data-testid="form-group-provider-reranking-max-modifier"
        >
          <input
            id="provider-reranking-max-modifier"
            type="number"
            data-testid="input-provider-reranking-max-modifier"
            style={{ ...inputStyle, maxWidth: '120px' }}
            value={strVal(configData, 'provider_reranking_max_modifier', '0.3')}
            onChange={(e) =>
              save({ provider_reranking_max_modifier: Number(e.target.value) })
            }
            min={0}
            step={0.05}
            placeholder="0.3"
          />
        </FormGroup>

        {/* Dynamic Timeouts */}
        <FormGroup
          label="Dynamic Timeouts"
          hint="Automatically adjust search timeouts based on provider response history."
          data-testid="form-group-provider-dynamic-timeout-enabled"
        >
          <div data-testid="toggle-provider-dynamic-timeout-enabled">
            <Toggle
              checked={boolVal(configData, 'provider_dynamic_timeout_enabled')}
              onChange={(v) => save({ provider_dynamic_timeout_enabled: v })}
            />
          </div>
        </FormGroup>

        <FormGroup
          label="Dynamic Timeout Min Samples"
          hint="Minimum number of response samples before dynamic adjustment kicks in."
          htmlFor="provider-dynamic-timeout-min-samples"
          data-testid="form-group-provider-dynamic-timeout-min-samples"
        >
          <input
            id="provider-dynamic-timeout-min-samples"
            type="number"
            data-testid="input-provider-dynamic-timeout-min-samples"
            style={{ ...inputStyle, maxWidth: '120px' }}
            value={strVal(configData, 'provider_dynamic_timeout_min_samples', '5')}
            onChange={(e) =>
              save({ provider_dynamic_timeout_min_samples: Number(e.target.value) })
            }
            min={1}
            placeholder="5"
          />
        </FormGroup>

        <FormGroup
          label="Dynamic Timeout Multiplier"
          hint="Multiply the measured average response time by this factor for the timeout."
          htmlFor="provider-dynamic-timeout-multiplier"
          data-testid="form-group-provider-dynamic-timeout-multiplier"
        >
          <input
            id="provider-dynamic-timeout-multiplier"
            type="number"
            data-testid="input-provider-dynamic-timeout-multiplier"
            style={{ ...inputStyle, maxWidth: '120px' }}
            value={strVal(configData, 'provider_dynamic_timeout_multiplier', '1.5')}
            onChange={(e) =>
              save({ provider_dynamic_timeout_multiplier: Number(e.target.value) })
            }
            min={1}
            step={0.1}
            placeholder="1.5"
          />
        </FormGroup>

        <FormGroup
          label="Dynamic Timeout Buffer (s)"
          hint="Fixed seconds added on top of the calculated dynamic timeout."
          htmlFor="provider-dynamic-timeout-buffer-secs"
          data-testid="form-group-provider-dynamic-timeout-buffer-secs"
        >
          <input
            id="provider-dynamic-timeout-buffer-secs"
            type="number"
            data-testid="input-provider-dynamic-timeout-buffer-secs"
            style={{ ...inputStyle, maxWidth: '120px' }}
            value={strVal(configData, 'provider_dynamic_timeout_buffer_secs', '2')}
            onChange={(e) =>
              save({ provider_dynamic_timeout_buffer_secs: Number(e.target.value) })
            }
            min={0}
            placeholder="2"
          />
        </FormGroup>

        <FormGroup
          label="Dynamic Timeout Min (s)"
          hint="Minimum timeout regardless of dynamic calculation."
          htmlFor="provider-dynamic-timeout-min-secs"
          data-testid="form-group-provider-dynamic-timeout-min-secs"
        >
          <input
            id="provider-dynamic-timeout-min-secs"
            type="number"
            data-testid="input-provider-dynamic-timeout-min-secs"
            style={{ ...inputStyle, maxWidth: '120px' }}
            value={strVal(configData, 'provider_dynamic_timeout_min_secs', '5')}
            onChange={(e) =>
              save({ provider_dynamic_timeout_min_secs: Number(e.target.value) })
            }
            min={1}
            placeholder="5"
          />
        </FormGroup>

        <FormGroup
          label="Dynamic Timeout Max (s)"
          hint="Maximum timeout cap even if dynamic calculation exceeds it."
          htmlFor="provider-dynamic-timeout-max-secs"
          data-testid="form-group-provider-dynamic-timeout-max-secs"
        >
          <input
            id="provider-dynamic-timeout-max-secs"
            type="number"
            data-testid="input-provider-dynamic-timeout-max-secs"
            style={{ ...inputStyle, maxWidth: '120px' }}
            value={strVal(configData, 'provider_dynamic_timeout_max_secs', '60')}
            onChange={(e) =>
              save({ provider_dynamic_timeout_max_secs: Number(e.target.value) })
            }
            min={1}
            placeholder="60"
          />
        </FormGroup>

        {/* Circuit Breaker */}
        <FormGroup
          label="Circuit Breaker Threshold"
          hint="Number of consecutive failures before a provider is temporarily disabled."
          htmlFor="circuit-breaker-failure-threshold"
          data-testid="form-group-circuit-breaker-failure-threshold"
        >
          <input
            id="circuit-breaker-failure-threshold"
            type="number"
            data-testid="input-circuit-breaker-failure-threshold"
            style={{ ...inputStyle, maxWidth: '120px' }}
            value={strVal(configData, 'circuit_breaker_failure_threshold', '5')}
            onChange={(e) =>
              save({ circuit_breaker_failure_threshold: Number(e.target.value) })
            }
            min={1}
            placeholder="5"
          />
        </FormGroup>

        <FormGroup
          label="Circuit Breaker Cooldown (s)"
          hint="Seconds a provider stays in OPEN state before being retried."
          htmlFor="circuit-breaker-cooldown-seconds"
          data-testid="form-group-circuit-breaker-cooldown-seconds"
        >
          <input
            id="circuit-breaker-cooldown-seconds"
            type="number"
            data-testid="input-circuit-breaker-cooldown-seconds"
            style={{ ...inputStyle, maxWidth: '120px' }}
            value={strVal(configData, 'circuit_breaker_cooldown_seconds', '300')}
            onChange={(e) =>
              save({ circuit_breaker_cooldown_seconds: Number(e.target.value) })
            }
            min={10}
            placeholder="300"
          />
        </FormGroup>
      </>
    }
  >
    {/* No primary content — all fields are in the collapsible advanced area */}
    <span />
  </SettingsSection>
  ```

  **Note on `data-testid` on `SettingsSection`:** Looking at `SettingsSection.tsx`, it spreads no extra props — the `data-testid` on `<SettingsSection data-testid="providers-advanced-section">` is NOT forwarded automatically. Instead, pass it as a known prop if it is not in the interface, or use a wrapping div. Since existing sections already use `data-testid` on `SettingsSection` and the existing tests find `providers-installed-section` etc. via `screen.getByTestId`, check whether the current `SettingsSection` does forward unknown props.

  Looking at the `SettingsSection.tsx` source: the outer `<div>` only receives `className` and the explicit `style`. The `data-testid` is NOT spread. However, the existing test `'renders all four sections'` passes using `providers-installed-content` etc., which are on the inner content divs — NOT on the `<SettingsSection>` wrapper. The pattern used throughout is `data-testid` on the content div inside `SettingsSection`, not on `SettingsSection` itself.

  Therefore: the `data-testid="providers-advanced-section"` should go on a wrapping `<div>` around the `<SettingsSection>`, not on `<SettingsSection>` itself:
  ```tsx
  <div data-testid="providers-advanced-section">
    <SettingsSection
      title={...}
      description={...}
      icon={...}
      advanced={...}
    >
      <span />
    </SettingsSection>
  </div>
  ```
  This matches the test expectation `screen.getByTestId('providers-advanced-section')`.

- [ ] Run all tests — confirm GREEN:
  ```bash
  cd frontend && npm run test -- --run --reporter=verbose 2>&1 | tail -40
  ```

- [ ] Run lint + type check:
  ```bash
  cd frontend && npm run lint && npx tsc --noEmit
  ```

- [ ] Commit:
  ```bash
  cd "D:/Sublarr_Projekt/Sublarr" && git add frontend/src/pages/Settings/ProvidersSettings.tsx frontend/src/pages/Settings/__tests__/ProvidersSettings.test.tsx && git commit -m "feat: add provider reranking, dynamic timeouts and circuit breaker advanced section"
  ```

---

## Final Verification

- [ ] All 3 commits exist on `feature/frontend-redesign`:
  ```bash
  git log --oneline -5
  ```
  Expected:
  ```
  <hash> feat: add provider reranking, dynamic timeouts and circuit breaker advanced section
  <hash> feat: add marketplace github token and plugin fields to ProvidersSettings
  <hash> feat: add provider config fields to ProvidersSettings installed section
  ```

- [ ] Full test suite passes:
  ```bash
  cd frontend && npm run test -- --run 2>&1 | tail -10
  ```

- [ ] TypeScript compiles clean:
  ```bash
  cd frontend && npx tsc --noEmit
  ```

- [ ] Lint clean:
  ```bash
  cd frontend && npm run lint
  ```

---

## Key Decisions

| Decision | Rationale |
|----------|-----------|
| Config helpers (`strVal`, `boolVal`) added to `ProvidersSettings.tsx` | Component previously used a `values: Record<string, string>` string-coercion pattern. The helpers are the standard pattern from `AutomationSettings.tsx` and work with the typed config object. |
| `<div data-testid="toggle-X">` wrapper around `Toggle` | `Toggle.tsx` does not accept `data-testid`. Wrapper div is the idiomatic solution without modifying the protected Toggle component. |
| `<div data-testid="providers-advanced-section">` wrapper around `SettingsSection` | `SettingsSection` does not forward arbitrary props to its outer div. Wrapper div is the correct approach, consistent with how all other section content is addressed in existing tests. |
| 7 new fields appended below `<ProvidersTab>` inside `providers-installed-content` | `ProvidersTab` manages its own internal state and must remain intact. New global config fields are separate concerns added after the grid. |
| Anti-Captcha switches from raw grid to `FormGroup` | Design alignment (Step 17). Existing tests that use `getByRole('combobox', { name: /Backend/i })` and `queryByLabelText(/API Key/i)` remain valid because `FormGroup` renders a `<label>` with `htmlFor`. |
| `<span />` as `children` for the Advanced section | `SettingsSection` requires `children: React.ReactNode`. A minimal `<span />` satisfies the type contract without rendering visible content — all real content is in `advanced` prop. |
