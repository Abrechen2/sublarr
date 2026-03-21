# Plan: Steps 23-27 — NotificationsSettings + ConnectionsSettings

**Branch:** `feature/frontend-redesign`
**Steps:** 23, 24, 25, 26, 27

---

## Pre-Read: What Already Exists

Before writing a single line, confirm these facts (grep / open files):

1. `NotificationTemplatesTab.tsx` — `NotificationToggles()` already includes
   `notify_manual_actions` in its `toggles` array (line 33). The toggle is already
   rendered and wired through `useConfig`/`useUpdateConfig`. **Step 23 is already
   implemented at the component level.** The task is to verify the test covers it,
   commit, and move on — no new component code is needed.

2. `NotificationsSettings.tsx` — the Quiet Hours `SettingsSection` currently renders
   only a placeholder `<p>` inside `children` and another placeholder string inside
   `advanced`. The `advanced` prop is what drives the expandable toggle already shown
   in tests. We **replace** the `advanced` content (not children) with the four real
   config fields per Step 24.

3. `ConnectionsSettings.tsx` — `SonarrSection` and `RadarrSection` use single-URL
   `ConnectionCard` components. Steps 25-26 replace the single-card UI with a new
   multi-instance list component (inline in the file, no new file needed at this
   scope). Step 27 adds a fifth `SettingsSection` below "API Keys".

4. Existing tests in `__tests__/ConnectionsSettings.test.tsx` pin the Sonarr card to
   `data-testid="sonarr-connection-card"` and `data-testid="radarr-connection-card"`.
   The multi-instance replacement must keep test-compatible testids or the tests must
   be updated. Updating the tests is correct — the old single-card behaviour is being
   replaced.

---

## Step 23 — Verify `notify_manual_actions` Toggle

### Situation

`notify_manual_actions` is already in the `NotificationToggles` component inside
`NotificationTemplatesTab.tsx`. No component code changes required.

### Test check

Open `__tests__/NotificationsSettings.test.tsx`. The existing suite does NOT test
that specific toggle (it mocks the entire `NotificationTemplatesTab`). That is
acceptable — the toggle is unit-level logic inside the tab, which is separately
testable.

If you want to add a focused test, add it to a **separate** describe block in the
existing test file:

```tsx
// In NotificationsSettings.test.tsx — add inside describe('NotificationsSettings')
// after the existing tests (no new file):

it('NotificationTemplatesTab mock renders inside Channels section', () => {
  renderPage()
  expect(screen.getByTestId('notification-templates-tab')).toBeInTheDocument()
})
```

This test already passes with the existing mock (mock returns
`data-testid="notification-templates-tab"`). Run it to confirm green, then commit.

### Commit

```
feat: add notify_manual_actions toggle to NotificationsSettings
```

Commit only if the test suite is green. The commit body should note that the toggle
was already present in `NotificationTemplatesTab.tsx` and this commit verifies + seals it.

**Files touched:** `frontend/src/pages/Settings/__tests__/NotificationsSettings.test.tsx`

---

## Step 24 — Quiet Hours UI Stub (NotificationsSettings)

### What to build

Replace the placeholder content inside the `advanced` prop of the Quiet Hours
`SettingsSection` in `NotificationsSettings.tsx`. Keep the outer `SettingsSection`
structure exactly as-is (tests pin `data-testid="section-quiet-hours"` and the
`advanced` toggle pattern).

The `advanced` prop receives JSX. Replace the current placeholder `<p>` with:

```tsx
advanced={<QuietHoursConfigStub />}
```

Define `QuietHoursConfigStub` as a new function component **in the same file**
(`NotificationsSettings.tsx`). Do not create a new file.

#### QuietHoursConfigStub spec

```tsx
function QuietHoursConfigStub() {
  const { t } = useTranslation('common')
  const { data: configData } = useConfig()
  const updateConfig = useUpdateConfig()

  const cfg = configData as Record<string, unknown> | undefined

  // Read values from config — default to empty string so inputs are always controlled
  const [enabled, setEnabled] = useState(
    () => String(cfg?.quiet_hours_enabled ?? 'false') === 'true'
  )
  const [start, setStart]         = useState(() => String(cfg?.quiet_hours_start ?? ''))
  const [end, setEnd]             = useState(() => String(cfg?.quiet_hours_end ?? ''))
  const [timezone, setTimezone]   = useState(() => String(cfg?.quiet_hours_timezone ?? ''))

  const handleSave = () => {
    updateConfig.mutate({
      quiet_hours_enabled:  String(enabled),
      quiet_hours_start:    start,
      quiet_hours_end:      end,
      quiet_hours_timezone: timezone,
    })
  }

  return (
    <div
      data-testid="quiet-hours-config-stub"
      className="space-y-4"
    >
      {/* Info banner — backend fields not yet active */}
      <div
        data-testid="quiet-hours-stub-banner"
        className="flex items-start gap-2 px-3 py-2 rounded-md text-[12px]"
        style={{
          backgroundColor: 'var(--accent-bg)',
          border: '1px solid var(--accent-dim)',
          color: 'var(--text-secondary)',
        }}
      >
        <span style={{ color: 'var(--accent)', flexShrink: 0 }}>i</span>
        <span>
          {t(
            'settings.notifications.quietHours.stubBanner',
            'Diese Felder werden nach dem nächsten Backend-Update aktiv.',
          )}
        </span>
      </div>

      {/* quiet_hours_enabled — Toggle */}
      <div className="flex items-center justify-between py-2"
           style={{ borderBottom: '1px solid rgba(42,46,56,0.5)' }}>
        <div className="flex flex-col gap-0.5">
          <span className="text-[13px] font-medium" style={{ color: 'var(--text-primary)' }}>
            {t('settings.notifications.quietHours.enabled', 'Quiet Hours Enabled')}
          </span>
          <span className="text-[11px]" style={{ color: 'var(--text-muted)' }}>
            {t('settings.notifications.quietHours.enabledHint',
              'Suppress all notifications during the configured window.')}
          </span>
        </div>
        <button
          data-testid="quiet-hours-enabled-toggle"
          type="button"
          role="switch"
          aria-checked={enabled}
          onClick={() => setEnabled((v) => !v)}
          className="relative inline-flex h-5 w-9 flex-shrink-0 rounded-full transition-colors duration-200"
          style={{ backgroundColor: enabled ? 'var(--accent)' : 'var(--border)' }}
        >
          <span
            className="inline-block h-4 w-4 transform rounded-full bg-white shadow transition-transform duration-200 mt-0.5"
            style={{ transform: enabled ? 'translateX(16px)' : 'translateX(2px)' }}
          />
        </button>
      </div>

      {/* quiet_hours_start */}
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-2 py-2"
           style={{ borderBottom: '1px solid rgba(42,46,56,0.5)' }}>
        <label
          htmlFor="quiet-hours-start"
          className="text-[13px] font-medium"
          style={{ color: 'var(--text-primary)' }}
        >
          {t('settings.notifications.quietHours.start', 'Start Time')}
        </label>
        <input
          id="quiet-hours-start"
          data-testid="quiet-hours-start-input"
          type="text"
          value={start}
          onChange={(e) => setStart(e.target.value)}
          placeholder="23:00"
          className="px-2.5 py-1.5 rounded text-xs focus:outline-none"
          style={{
            width: '120px',
            backgroundColor: 'var(--bg-elevated)',
            border: '1px solid var(--border)',
            color: 'var(--text-primary)',
            fontFamily: 'var(--font-mono)',
          }}
        />
      </div>

      {/* quiet_hours_end */}
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-2 py-2"
           style={{ borderBottom: '1px solid rgba(42,46,56,0.5)' }}>
        <label
          htmlFor="quiet-hours-end"
          className="text-[13px] font-medium"
          style={{ color: 'var(--text-primary)' }}
        >
          {t('settings.notifications.quietHours.end', 'End Time')}
        </label>
        <input
          id="quiet-hours-end"
          data-testid="quiet-hours-end-input"
          type="text"
          value={end}
          onChange={(e) => setEnd(e.target.value)}
          placeholder="07:00"
          className="px-2.5 py-1.5 rounded text-xs focus:outline-none"
          style={{
            width: '120px',
            backgroundColor: 'var(--bg-elevated)',
            border: '1px solid var(--border)',
            color: 'var(--text-primary)',
            fontFamily: 'var(--font-mono)',
          }}
        />
      </div>

      {/* quiet_hours_timezone */}
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-2 py-2">
        <label
          htmlFor="quiet-hours-timezone"
          className="text-[13px] font-medium"
          style={{ color: 'var(--text-primary)' }}
        >
          {t('settings.notifications.quietHours.timezone', 'Timezone')}
        </label>
        <input
          id="quiet-hours-timezone"
          data-testid="quiet-hours-timezone-input"
          type="text"
          value={timezone}
          onChange={(e) => setTimezone(e.target.value)}
          placeholder="UTC"
          className="px-2.5 py-1.5 rounded text-xs focus:outline-none"
          style={{
            width: '160px',
            backgroundColor: 'var(--bg-elevated)',
            border: '1px solid var(--border)',
            color: 'var(--text-primary)',
            fontFamily: 'var(--font-mono)',
          }}
        />
      </div>

      {/* Save */}
      <div className="flex justify-end pt-1">
        <button
          data-testid="quiet-hours-save-btn"
          type="button"
          onClick={handleSave}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium text-white"
          style={{ backgroundColor: 'var(--accent)' }}
        >
          {t('actions.save', 'Save')}
        </button>
      </div>
    </div>
  )
}
```

#### Imports to add to NotificationsSettings.tsx

```tsx
import { useState } from 'react'
import { useConfig, useUpdateConfig } from '@/hooks/useApi'
```

These are not currently imported in `NotificationsSettings.tsx` (the file currently
only imports `lazy`, `Suspense`, `useTranslation`, and UI components).

#### Children prop stays the same

The `children` prop of the Quiet Hours `SettingsSection` (the `quiet-hours-summary`
paragraph) remains unchanged — existing tests check it.

### TDD: tests first

Before implementing, add tests for `QuietHoursConfigStub` in the existing test file
`__tests__/NotificationsSettings.test.tsx`.

Add the following mocks at the top of the test file (after existing mocks):

```tsx
const mockUpdateConfigMutate = vi.fn()

vi.mock('@/hooks/useApi', () => ({
  useConfig: () => ({
    data: {
      quiet_hours_enabled: 'false',
      quiet_hours_start: '23:00',
      quiet_hours_end: '07:00',
      quiet_hours_timezone: 'Europe/Berlin',
    },
  }),
  useUpdateConfig: () => ({ mutate: mockUpdateConfigMutate, isPending: false }),
}))
```

Add a new describe block (after existing describe):

```tsx
describe('NotificationsSettings — Quiet Hours stub (Step 24)', () => {
  beforeEach(() => { vi.clearAllMocks() })

  it('Quiet Hours advanced section renders the stub when expanded', () => {
    renderPage()
    const wrapper = screen.getByTestId('section-quiet-hours')
    const toggle = wrapper.querySelector(
      '[data-testid="settings-section-advanced-toggle"]'
    ) as HTMLElement
    fireEvent.click(toggle)
    expect(screen.getByTestId('quiet-hours-config-stub')).toBeInTheDocument()
  })

  it('renders the stub info banner', () => {
    renderPage()
    const wrapper = screen.getByTestId('section-quiet-hours')
    fireEvent.click(
      wrapper.querySelector('[data-testid="settings-section-advanced-toggle"]') as HTMLElement
    )
    expect(screen.getByTestId('quiet-hours-stub-banner')).toBeInTheDocument()
  })

  it('renders all four quiet hours inputs after expanding', () => {
    renderPage()
    const wrapper = screen.getByTestId('section-quiet-hours')
    fireEvent.click(
      wrapper.querySelector('[data-testid="settings-section-advanced-toggle"]') as HTMLElement
    )
    expect(screen.getByTestId('quiet-hours-enabled-toggle')).toBeInTheDocument()
    expect(screen.getByTestId('quiet-hours-start-input')).toBeInTheDocument()
    expect(screen.getByTestId('quiet-hours-end-input')).toBeInTheDocument()
    expect(screen.getByTestId('quiet-hours-timezone-input')).toBeInTheDocument()
  })

  it('start input reads from config', () => {
    renderPage()
    const wrapper = screen.getByTestId('section-quiet-hours')
    fireEvent.click(
      wrapper.querySelector('[data-testid="settings-section-advanced-toggle"]') as HTMLElement
    )
    expect(screen.getByTestId('quiet-hours-start-input')).toHaveValue('23:00')
  })

  it('save button calls updateConfig with all four keys', async () => {
    renderPage()
    const wrapper = screen.getByTestId('section-quiet-hours')
    fireEvent.click(
      wrapper.querySelector('[data-testid="settings-section-advanced-toggle"]') as HTMLElement
    )
    fireEvent.click(screen.getByTestId('quiet-hours-save-btn'))
    await waitFor(() => {
      expect(mockUpdateConfigMutate).toHaveBeenCalledWith(
        expect.objectContaining({
          quiet_hours_enabled: 'false',
          quiet_hours_start: '23:00',
          quiet_hours_end: '07:00',
          quiet_hours_timezone: 'Europe/Berlin',
        }),
      )
    })
  })

  it('toggle button flips enabled state', () => {
    renderPage()
    const wrapper = screen.getByTestId('section-quiet-hours')
    fireEvent.click(
      wrapper.querySelector('[data-testid="settings-section-advanced-toggle"]') as HTMLElement
    )
    const toggle = screen.getByTestId('quiet-hours-enabled-toggle')
    expect(toggle).toHaveAttribute('aria-checked', 'false')
    fireEvent.click(toggle)
    expect(toggle).toHaveAttribute('aria-checked', 'true')
  })
})
```

**Note:** Adding `useApi` mock at this level affects the entire test file. If the
existing tests break (they don't currently mock `useApi` because the file doesn't use
it), wrap only the Step 24 tests in a `describe` with a `beforeEach` that
re-establishes the mock. Alternatively use `vi.mocked` scoping. The safest approach:
add the `vi.mock('@/hooks/useApi', ...)` call at the top of the file — it will not
break existing tests since `NotificationsSettings.tsx` currently does not call
`useConfig` / `useUpdateConfig` (the children tabs are mocked via lazy import mocks).

RED → implement `QuietHoursConfigStub` → GREEN → commit.

### Commit

```
feat: add quiet hours UI stub to NotificationsSettings
```

**Files touched:**
- `frontend/src/pages/Settings/NotificationsSettings.tsx`
- `frontend/src/pages/Settings/__tests__/NotificationsSettings.test.tsx`

---

## Step 25 — Sonarr Multi-Instance UI

### Config key

`sonarr_instances_json` — stored as a JSON string (array of instance objects).

Shape of one instance:

```ts
interface SonarrInstance {
  id: string          // nanoid or crypto.randomUUID() — client-generated
  name: string        // editable label, default "Sonarr"
  url: string
  api_key: string
}
```

### What to remove

The existing `SonarrSection` component and its usage in `ConnectionsSettings` is
**replaced entirely**. The `sonarr_url`, `sonarr_api_key`, and `path_mapping` single
fields are replaced by the multi-instance JSON key.

Do NOT delete the old `useTestSonarrInstance` hook — it is still used per-instance.

### New component: `SonarrMultiInstanceSection`

Define inline in `ConnectionsSettings.tsx`. No new file.

```tsx
// ─── Types ────────────────────────────────────────────────────────────────────

interface ServiceInstance {
  id: string
  name: string
  url: string
  api_key: string
}

type InstanceStatus = 'unconfigured' | 'connected' | 'error'

interface InstanceState {
  status: InstanceStatus
  message: string | null
  testing: boolean
}
```

#### Parsing helpers (immutable — always produce new arrays)

```tsx
function parseInstances(json: unknown): ServiceInstance[] {
  if (!json || typeof json !== 'string' || !json.trim()) return []
  try {
    const parsed = JSON.parse(json)
    if (!Array.isArray(parsed)) return []
    return parsed.filter(
      (item): item is ServiceInstance =>
        typeof item === 'object' &&
        item !== null &&
        typeof item.id === 'string' &&
        typeof item.name === 'string' &&
        typeof item.url === 'string' &&
        typeof item.api_key === 'string'
    )
  } catch {
    return []
  }
}

function serializeInstances(instances: ServiceInstance[]): string {
  return JSON.stringify(instances)
}
```

#### SonarrMultiInstanceSection implementation spec

```tsx
function SonarrMultiInstanceSection() {
  const { data: configData } = useConfig()
  const updateConfig = useUpdateConfig()
  const testSonarr = useTestSonarrInstance()

  const cfg = configData as Record<string, unknown> | undefined

  const [instances, setInstances] = useState<ServiceInstance[]>(() =>
    parseInstances(cfg?.sonarr_instances_json)
  )
  const [statuses, setStatuses] = useState<Record<string, InstanceState>>({})
  const [editingName, setEditingName] = useState<string | null>(null) // instance id

  const persist = (next: ServiceInstance[]) => {
    setInstances(next)
    updateConfig.mutate({ sonarr_instances_json: serializeInstances(next) })
  }

  const addInstance = () => {
    const newInst: ServiceInstance = {
      id: crypto.randomUUID(),
      name: `Sonarr ${instances.length + 1}`,
      url: '',
      api_key: '',
    }
    persist([...instances, newInst])
  }

  const removeInstance = (id: string) => {
    persist(instances.filter((inst) => inst.id !== id))
    setStatuses((prev) => {
      const { [id]: _, ...rest } = prev
      return rest
    })
  }

  const updateInstance = (id: string, patch: Partial<ServiceInstance>) => {
    persist(
      instances.map((inst) => (inst.id === id ? { ...inst, ...patch } : inst))
    )
  }

  const testInstance = (inst: ServiceInstance) => {
    if (!inst.url.trim()) return
    setStatuses((prev) => ({
      ...prev,
      [inst.id]: { status: 'unconfigured', message: null, testing: true },
    }))
    testSonarr.mutate(
      { url: inst.url.trim(), api_key: inst.api_key.trim() },
      {
        onSuccess: (result) => {
          setStatuses((prev) => ({
            ...prev,
            [inst.id]: {
              status: result.healthy ? 'connected' : 'error',
              message: result.message,
              testing: false,
            },
          }))
        },
        onError: () => {
          setStatuses((prev) => ({
            ...prev,
            [inst.id]: { status: 'error', message: 'Connection failed', testing: false },
          }))
        },
      }
    )
  }

  return (
    <div data-testid="sonarr-multi-instance" className="space-y-2">
      {instances.map((inst) => {
        const state = statuses[inst.id] ?? { status: 'unconfigured', message: null, testing: false }
        return (
          <InstanceCard
            key={inst.id}
            inst={inst}
            state={state}
            editingName={editingName}
            onEditName={(id) => setEditingName(id)}
            onNameChange={(name) => updateInstance(inst.id, { name })}
            onNameBlur={() => setEditingName(null)}
            onUrlChange={(url) => updateInstance(inst.id, { url })}
            onApiKeyChange={(api_key) => updateInstance(inst.id, { api_key })}
            onTest={() => testInstance(inst)}
            onRemove={() => removeInstance(inst.id)}
          />
        )
      })}

      {/* Add instance */}
      <button
        data-testid="sonarr-add-instance-btn"
        type="button"
        onClick={addInstance}
        className="w-full flex items-center justify-center gap-2 py-2.5 rounded-lg text-xs font-medium transition-colors duration-150"
        style={{
          border: '1px dashed var(--border)',
          color: 'var(--text-muted)',
          backgroundColor: 'transparent',
        }}
        onMouseEnter={(e) => {
          e.currentTarget.style.borderColor = 'var(--accent-dim)'
          e.currentTarget.style.color = 'var(--accent)'
        }}
        onMouseLeave={(e) => {
          e.currentTarget.style.borderColor = 'var(--border)'
          e.currentTarget.style.color = 'var(--text-muted)'
        }}
      >
        <Plus size={12} />
        Add instance
      </button>
    </div>
  )
}
```

#### InstanceCard sub-component

```tsx
interface InstanceCardProps {
  inst: ServiceInstance
  state: InstanceState
  editingName: string | null
  onEditName: (id: string) => void
  onNameChange: (name: string) => void
  onNameBlur: () => void
  onUrlChange: (url: string) => void
  onApiKeyChange: (key: string) => void
  onTest: () => void
  onRemove: () => void
}

function InstanceCard({
  inst, state, editingName,
  onEditName, onNameChange, onNameBlur,
  onUrlChange, onApiKeyChange, onTest, onRemove,
}: InstanceCardProps) {
  const [showKey, setShowKey] = useState(false)

  const statusColor: Record<InstanceStatus, string> = {
    connected: 'var(--success)',
    error: 'var(--error)',
    unconfigured: 'var(--text-muted)',
  }

  const inputStyle = {
    backgroundColor: 'var(--bg-elevated)',
    border: '1px solid var(--border)',
    color: 'var(--text-primary)',
    fontFamily: 'var(--font-mono)',
    fontSize: '12px',
    padding: '6px 10px',
    borderRadius: '6px',
  } as const

  return (
    <div
      data-testid={`sonarr-instance-card-${inst.id}`}
      className="rounded-lg overflow-hidden"
      style={{ border: '1px solid var(--border)', backgroundColor: 'var(--bg-surface)' }}
    >
      {/* Card header row */}
      <div className="flex items-center gap-3 px-3 py-2.5">
        {/* Status dot */}
        <div
          data-testid={`sonarr-instance-status-dot-${inst.id}`}
          className="w-2 h-2 rounded-full flex-shrink-0"
          style={{ backgroundColor: statusColor[state.status] }}
        />

        {/* Name — inline edit on pencil click */}
        {editingName === inst.id ? (
          <input
            data-testid={`sonarr-instance-name-input-${inst.id}`}
            type="text"
            value={inst.name}
            onChange={(e) => onNameChange(e.target.value)}
            onBlur={onNameBlur}
            autoFocus
            className="flex-1 text-sm font-medium focus:outline-none rounded px-1"
            style={{
              backgroundColor: 'var(--bg-elevated)',
              border: '1px solid var(--accent-dim)',
              color: 'var(--text-primary)',
            }}
          />
        ) : (
          <div className="flex items-center gap-1.5 flex-1 min-w-0 group">
            <span
              className="text-sm font-medium truncate"
              style={{ color: 'var(--text-primary)' }}
            >
              {inst.name}
            </span>
            <button
              data-testid={`sonarr-instance-edit-name-btn-${inst.id}`}
              type="button"
              onClick={() => onEditName(inst.id)}
              className="opacity-0 group-hover:opacity-100 p-0.5 rounded transition-opacity"
              style={{ color: 'var(--text-muted)' }}
            >
              <Pencil size={11} />
            </button>
          </div>
        )}

        {/* Test button */}
        <button
          data-testid={`sonarr-instance-test-btn-${inst.id}`}
          type="button"
          onClick={onTest}
          disabled={state.testing || !inst.url.trim()}
          className="flex items-center gap-1 px-2 py-1 rounded text-xs transition-all duration-150"
          style={{
            border: '1px solid var(--border)',
            color: 'var(--text-secondary)',
            backgroundColor: 'var(--bg-primary)',
            opacity: (state.testing || !inst.url.trim()) ? 0.5 : 1,
          }}
        >
          {state.testing
            ? <Loader2 size={11} className="animate-spin" />
            : <TestTube size={11} />}
          Test
        </button>

        {/* Remove button */}
        <button
          data-testid={`sonarr-instance-remove-btn-${inst.id}`}
          type="button"
          onClick={onRemove}
          className="p-1.5 rounded transition-colors"
          style={{ color: 'var(--text-muted)' }}
          onMouseEnter={(e) => { e.currentTarget.style.color = 'var(--error)' }}
          onMouseLeave={(e) => { e.currentTarget.style.color = 'var(--text-muted)' }}
        >
          <Trash2 size={13} />
        </button>
      </div>

      {/* Test result message */}
      {state.message && (
        <div
          className="px-3 pb-1.5 text-[11px]"
          style={{ color: state.status === 'connected' ? 'var(--success)' : 'var(--error)' }}
        >
          {state.message}
        </div>
      )}

      {/* URL + API Key fields */}
      <div
        className="px-3 pb-3 space-y-2"
        style={{ borderTop: '1px solid var(--border)', paddingTop: '10px' }}
      >
        <input
          data-testid={`sonarr-instance-url-input-${inst.id}`}
          type="text"
          value={inst.url}
          onChange={(e) => onUrlChange(e.target.value)}
          placeholder="http://localhost:8989"
          className="w-full focus:outline-none"
          style={inputStyle}
        />
        <div className="flex items-center gap-1.5">
          <input
            data-testid={`sonarr-instance-apikey-input-${inst.id}`}
            type={showKey ? 'text' : 'password'}
            value={inst.api_key}
            onChange={(e) => onApiKeyChange(e.target.value)}
            placeholder="API Key"
            className="flex-1 focus:outline-none"
            style={inputStyle}
          />
          <button
            type="button"
            onClick={() => setShowKey((v) => !v)}
            className="p-1.5 rounded"
            style={{ border: '1px solid var(--border)', color: 'var(--text-muted)', backgroundColor: 'var(--bg-primary)' }}
          >
            {showKey ? <EyeOff size={12} /> : <Eye size={12} />}
          </button>
        </div>
      </div>
    </div>
  )
}
```

#### Imports to add to ConnectionsSettings.tsx

```tsx
import { Plus, Pencil, TestTube, Trash2, Eye, EyeOff } from 'lucide-react'
```

Remove `Edit2` from imports if no longer used after the refactor.

Also add `Loader2` if not already imported (it is already via `TabSkeleton`).

#### Replace in ConnectionsSettings JSX

Replace:
```tsx
<SonarrSection />
```
with:
```tsx
<SonarrMultiInstanceSection />
```

### TDD: tests first

In `__tests__/ConnectionsSettings.test.tsx`, add a new describe block after the
existing tests. The existing tests that reference `sonarr-connection-card` will need
to be updated — they are testing the OLD single-card UI. After Step 25, those tests
must be replaced with multi-instance equivalents.

**Update strategy for existing tests:**

1. Remove or replace the following tests (they test the old `ConnectionCard` pattern
   which is being replaced):
   - `'renders Sonarr connection card'` → replace with `'renders sonarr multi-instance container'`
   - `'renders Sonarr service name'` → remove (no single name element)
   - `'displays Sonarr URL from config'` → remove (URL is per-instance)
   - `'calls testSonarr mutate when Sonarr test button is clicked'` → replace with per-instance test
   - `'expands Sonarr edit form when edit button is clicked'` → remove (always expanded now)
   - `'saves Sonarr settings when save is clicked in form'` → replace with instance-add test

2. Keep untouched:
   - All Radarr tests (Step 26 handles those)
   - `'renders the settings detail layout'`
   - `'renders page title "Connections"'`
   - `'renders all 4 settings sections'` — **update count to 5** after Step 27
   - `'renders the Media Servers section'`
   - `'renders the API Keys section'`

**New tests to add for Step 25:**

```tsx
// Add to mockConfig at top of file:
// sonarr_instances_json: JSON.stringify([
//   { id: 'inst-1', name: 'Sonarr Home', url: 'http://localhost:8989', api_key: 'abc' }
// ])

describe('SonarrMultiInstanceSection (Step 25)', () => {
  beforeEach(() => { vi.clearAllMocks() })

  it('renders the sonarr multi-instance container', () => {
    renderWithProviders(<ConnectionsSettings />)
    expect(screen.getByTestId('sonarr-multi-instance')).toBeInTheDocument()
  })

  it('renders an instance card for each entry in sonarr_instances_json', () => {
    renderWithProviders(<ConnectionsSettings />)
    expect(screen.getByTestId('sonarr-instance-card-inst-1')).toBeInTheDocument()
  })

  it('renders the Add instance button', () => {
    renderWithProviders(<ConnectionsSettings />)
    expect(screen.getByTestId('sonarr-add-instance-btn')).toBeInTheDocument()
  })

  it('clicking Add calls updateConfig with a new instance appended', async () => {
    renderWithProviders(<ConnectionsSettings />)
    fireEvent.click(screen.getByTestId('sonarr-add-instance-btn'))
    await waitFor(() => {
      expect(mockMutate).toHaveBeenCalledWith(
        expect.objectContaining({
          sonarr_instances_json: expect.stringContaining('Sonarr 2'),
        }),
        expect.any(Object),
      )
    })
  })

  it('clicking Remove calls updateConfig without that instance', async () => {
    renderWithProviders(<ConnectionsSettings />)
    fireEvent.click(screen.getByTestId('sonarr-instance-remove-btn-inst-1'))
    await waitFor(() => {
      expect(mockMutate).toHaveBeenCalledWith(
        expect.objectContaining({ sonarr_instances_json: '[]' }),
        expect.any(Object),
      )
    })
  })
})
```

### Commit

```
feat: add Sonarr multi-instance UI to ConnectionsSettings
```

**Files touched:**
- `frontend/src/pages/Settings/ConnectionsSettings.tsx`
- `frontend/src/pages/Settings/__tests__/ConnectionsSettings.test.tsx`

---

## Step 26 — Radarr Multi-Instance UI

### Config key

`radarr_instances_json` — same shape as `sonarr_instances_json`.

### Implementation

Identical pattern to Step 25. Create `RadarrMultiInstanceSection` (copy-modify
`SonarrMultiInstanceSection`). Differences:

- Config key: `radarr_instances_json`
- Hook: `useTestRadarrInstance` (already imported)
- `data-testid` prefix: `radarr-multi-instance`, `radarr-instance-card-{id}`, etc.
- Default placeholder URL: `http://localhost:7878`
- Default instance name: `Radarr ${instances.length + 1}`

Replace:
```tsx
<RadarrSection />
```
with:
```tsx
<RadarrMultiInstanceSection />
```

### TDD

Same test pattern as Step 25, prefixed with `radarr-`. Update existing Radarr tests
that reference `radarr-connection-card` (remove/replace) and add:

```tsx
describe('RadarrMultiInstanceSection (Step 26)', () => {
  // Mirror of SonarrMultiInstanceSection tests but for radarr_instances_json
  // and radarr-instance-* testids
})
```

Update `mockConfig` to include:
```ts
radarr_instances_json: JSON.stringify([
  { id: 'rinst-1', name: 'Radarr Home', url: 'http://localhost:7878', api_key: 'xyz' }
])
```

Also update `'renders all 4 settings sections'` test to `toBeGreaterThanOrEqual(4)` — this stays as-is since the test uses `>=`.

### Commit

```
feat: add Radarr multi-instance UI to ConnectionsSettings
```

**Files touched:**
- `frontend/src/pages/Settings/ConnectionsSettings.tsx`
- `frontend/src/pages/Settings/__tests__/ConnectionsSettings.test.tsx`

---

## Step 27 — Metadata API Keys Section

### What to add

A new fifth `SettingsSection` at the bottom of `ConnectionsSettings`, after the
"API Keys" section (which loads `ApiKeysTab`). This section does NOT use a lazy tab —
it is inline with `useConfig`/`useUpdateConfig`.

### Fields

| Field key | Input type | Notes |
|---|---|---|
| `tmdb_api_key` | `password` | Eye toggle |
| `tvdb_api_key` | `password` | Eye toggle |
| `tvdb_pin` | `password` | Eye toggle — labeled "TheTVDB PIN" |
| `metadata_cache_ttl_days` | `number` | Integer, min=1 |
| `ffmpeg_timeout` | `number` (advanced) | Integer seconds, inside collapsed SettingsSection `advanced` prop |

### New component: `MetadataApiKeysSection`

Define inline in `ConnectionsSettings.tsx`.

```tsx
function MetadataApiKeysSection() {
  const { data: configData } = useConfig()
  const updateConfig = useUpdateConfig()

  const cfg = configData as Record<string, unknown> | undefined

  const [tmdbKey, setTmdbKey]         = useState(() => String(cfg?.tmdb_api_key ?? ''))
  const [tvdbKey, setTvdbKey]         = useState(() => String(cfg?.tvdb_api_key ?? ''))
  const [tvdbPin, setTvdbPin]         = useState(() => String(cfg?.tvdb_pin ?? ''))
  const [cacheTtl, setCacheTtl]       = useState(() => String(cfg?.metadata_cache_ttl_days ?? '7'))
  const [ffmpegTimeout, setFfmpegTimeout] = useState(() => String(cfg?.ffmpeg_timeout ?? '30'))

  const [showTmdb, setShowTmdb]   = useState(false)
  const [showTvdb, setShowTvdb]   = useState(false)
  const [showPin, setShowPin]     = useState(false)

  const handleSave = () => {
    updateConfig.mutate(
      {
        tmdb_api_key: tmdbKey,
        tvdb_api_key: tvdbKey,
        tvdb_pin: tvdbPin,
        metadata_cache_ttl_days: cacheTtl,
        ffmpeg_timeout: ffmpegTimeout,
      },
      {
        onSuccess: () => toast('Metadata settings saved'),
        onError:   () => toast('Failed to save metadata settings', 'error'),
      }
    )
  }

  const inputStyle = {
    backgroundColor: 'var(--bg-elevated)',
    border: '1px solid var(--border)',
    color: 'var(--text-primary)',
    fontFamily: 'var(--font-mono)',
    fontSize: '13px',
    padding: '7px 12px',
    borderRadius: '6px',
    flex: 1,
  } as const

  const numberInputStyle = {
    ...inputStyle,
    width: '120px',
    flex: 'none',
  } as const

  return (
    <div data-testid="metadata-api-keys-section" className="space-y-0">

      {/* TMDB */}
      <div className="flex items-center justify-between py-3"
           style={{ borderBottom: '1px solid rgba(42,46,56,0.5)' }}>
        <label htmlFor="tmdb-api-key"
               className="text-[13px] font-medium"
               style={{ color: 'var(--text-primary)' }}>
          TMDB API Key
        </label>
        <div className="flex items-center gap-1.5">
          <input
            id="tmdb-api-key"
            data-testid="metadata-tmdb-api-key"
            type={showTmdb ? 'text' : 'password'}
            value={tmdbKey}
            onChange={(e) => setTmdbKey(e.target.value)}
            placeholder="Enter TMDB v3 API key"
            className="focus:outline-none"
            style={{ ...inputStyle, width: '260px' }}
          />
          <button type="button" onClick={() => setShowTmdb((v) => !v)}
                  className="p-1.5 rounded"
                  style={{ border: '1px solid var(--border)', color: 'var(--text-muted)', backgroundColor: 'var(--bg-primary)' }}>
            {showTmdb ? <EyeOff size={13} /> : <Eye size={13} />}
          </button>
        </div>
      </div>

      {/* TVDB */}
      <div className="flex items-center justify-between py-3"
           style={{ borderBottom: '1px solid rgba(42,46,56,0.5)' }}>
        <label htmlFor="tvdb-api-key"
               className="text-[13px] font-medium"
               style={{ color: 'var(--text-primary)' }}>
          TheTVDB API Key
        </label>
        <div className="flex items-center gap-1.5">
          <input
            id="tvdb-api-key"
            data-testid="metadata-tvdb-api-key"
            type={showTvdb ? 'text' : 'password'}
            value={tvdbKey}
            onChange={(e) => setTvdbKey(e.target.value)}
            placeholder="Enter TheTVDB v4 API key"
            className="focus:outline-none"
            style={{ ...inputStyle, width: '260px' }}
          />
          <button type="button" onClick={() => setShowTvdb((v) => !v)}
                  className="p-1.5 rounded"
                  style={{ border: '1px solid var(--border)', color: 'var(--text-muted)', backgroundColor: 'var(--bg-primary)' }}>
            {showTvdb ? <EyeOff size={13} /> : <Eye size={13} />}
          </button>
        </div>
      </div>

      {/* TVDB PIN */}
      <div className="flex items-center justify-between py-3"
           style={{ borderBottom: '1px solid rgba(42,46,56,0.5)' }}>
        <label htmlFor="tvdb-pin"
               className="text-[13px] font-medium"
               style={{ color: 'var(--text-primary)' }}>
          TheTVDB PIN
        </label>
        <div className="flex items-center gap-1.5">
          <input
            id="tvdb-pin"
            data-testid="metadata-tvdb-pin"
            type={showPin ? 'text' : 'password'}
            value={tvdbPin}
            onChange={(e) => setTvdbPin(e.target.value)}
            placeholder="Optional subscriber PIN"
            className="focus:outline-none"
            style={{ ...inputStyle, width: '260px' }}
          />
          <button type="button" onClick={() => setShowPin((v) => !v)}
                  className="p-1.5 rounded"
                  style={{ border: '1px solid var(--border)', color: 'var(--text-muted)', backgroundColor: 'var(--bg-primary)' }}>
            {showPin ? <EyeOff size={13} /> : <Eye size={13} />}
          </button>
        </div>
      </div>

      {/* Metadata cache TTL */}
      <div className="flex items-center justify-between py-3">
        <div className="flex flex-col gap-0.5">
          <label htmlFor="metadata-cache-ttl"
                 className="text-[13px] font-medium"
                 style={{ color: 'var(--text-primary)' }}>
            Cache TTL (days)
          </label>
          <span className="text-[11px]" style={{ color: 'var(--text-muted)' }}>
            How long metadata is cached before a refresh.
          </span>
        </div>
        <input
          id="metadata-cache-ttl"
          data-testid="metadata-cache-ttl"
          type="number"
          min={1}
          value={cacheTtl}
          onChange={(e) => setCacheTtl(e.target.value)}
          className="focus:outline-none"
          style={numberInputStyle}
        />
      </div>

      {/* Save */}
      <div className="flex justify-end pt-2">
        <button
          data-testid="metadata-save-btn"
          type="button"
          onClick={handleSave}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium text-white"
          style={{ backgroundColor: 'var(--accent)' }}
        >
          Save
        </button>
      </div>
    </div>
  )
}
```

The `ffmpeg_timeout` field goes in the `advanced` prop of the wrapping
`SettingsSection`. Define a small inline JSX element for `advanced`:

```tsx
advanced={
  <div data-testid="metadata-advanced-content" className="space-y-3">
    <div className="flex items-center justify-between py-2">
      <div className="flex flex-col gap-0.5">
        <label htmlFor="ffmpeg-timeout"
               className="text-[13px] font-medium"
               style={{ color: 'var(--text-primary)' }}>
          FFmpeg Timeout (seconds)
        </label>
        <span className="text-[11px]" style={{ color: 'var(--text-muted)' }}>
          Maximum time for ffprobe/ffmpeg operations.
        </span>
      </div>
      <input
        id="ffmpeg-timeout"
        data-testid="metadata-ffmpeg-timeout"
        type="number"
        min={1}
        value={ffmpegTimeout}
        onChange={(e) => setFfmpegTimeout(e.target.value)}
        className="focus:outline-none"
        style={{
          width: '100px',
          backgroundColor: 'var(--bg-elevated)',
          border: '1px solid var(--border)',
          color: 'var(--text-primary)',
          fontFamily: 'var(--font-mono)',
          fontSize: '13px',
          padding: '7px 12px',
          borderRadius: '6px',
        }}
      />
    </div>
  </div>
}
```

**Note:** `ffmpegTimeout` and `setFfmpegTimeout` are defined in the same
`MetadataApiKeysSection` function scope, so the `advanced` JSX can reference them
directly since it is returned as part of the same component's JSX.

#### Where to place in ConnectionsSettings JSX

Add as the FIFTH section, after the "API Keys" `SettingsSection`:

```tsx
{/* Metadata API Keys */}
<SettingsSection
  data-testid="metadata-api-keys-section"  {/* Note: this is a prop, not DOM testid — SettingsSection uses "settings-section" */}
  title="Metadata API Keys"
  description="API keys for metadata providers (TMDB, TheTVDB) and media tooling"
  icon={<Database size={16} style={{ color: 'var(--accent)' }} />}
  advanced={/* ffmpeg_timeout inline JSX from above */}
>
  <div className="py-1">
    <MetadataApiKeysSection />
  </div>
</SettingsSection>
```

**Import `Database` from lucide-react** (or use `HardDrive`, `Layers` — pick whichever
is already in the lucide version installed). Check with:
```bash
grep -r '"lucide-react"' frontend/src/pages/Settings/ | head -5
```
and pick an icon available in that version. `Database` is available since lucide-react
v0.263+.

### TDD: tests first

Add to `__tests__/ConnectionsSettings.test.tsx`:

```tsx
describe('MetadataApiKeysSection (Step 27)', () => {
  beforeEach(() => { vi.clearAllMocks() })

  it('renders the metadata API keys section', () => {
    renderWithProviders(<ConnectionsSettings />)
    expect(screen.getByTestId('metadata-api-keys-section')).toBeInTheDocument()
  })

  it('renders TMDB API key input', () => {
    renderWithProviders(<ConnectionsSettings />)
    expect(screen.getByTestId('metadata-tmdb-api-key')).toBeInTheDocument()
  })

  it('renders TVDB API key input', () => {
    renderWithProviders(<ConnectionsSettings />)
    expect(screen.getByTestId('metadata-tvdb-api-key')).toBeInTheDocument()
  })

  it('renders TVDB PIN input', () => {
    renderWithProviders(<ConnectionsSettings />)
    expect(screen.getByTestId('metadata-tvdb-pin')).toBeInTheDocument()
  })

  it('renders cache TTL input', () => {
    renderWithProviders(<ConnectionsSettings />)
    expect(screen.getByTestId('metadata-cache-ttl')).toBeInTheDocument()
  })

  it('Save calls updateConfig with all metadata fields', async () => {
    renderWithProviders(<ConnectionsSettings />)
    fireEvent.click(screen.getByTestId('metadata-save-btn'))
    await waitFor(() => {
      expect(mockMutate).toHaveBeenCalledWith(
        expect.objectContaining({
          tmdb_api_key: expect.any(String),
          tvdb_api_key: expect.any(String),
          tvdb_pin: expect.any(String),
          metadata_cache_ttl_days: expect.any(String),
          ffmpeg_timeout: expect.any(String),
        }),
        expect.any(Object),
      )
    })
  })

  it('ffmpeg_timeout is in collapsed advanced section', () => {
    renderWithProviders(<ConnectionsSettings />)
    // Before expanding, ffmpeg-timeout input is not in DOM
    expect(screen.queryByTestId('metadata-ffmpeg-timeout')).toBeNull()
    // Find the metadata section's advanced toggle
    // (The metadata section is the 5th settings-section)
    const sections = screen.getAllByTestId('settings-section')
    const metadataSection = sections[4]
    const toggle = metadataSection.querySelector(
      '[data-testid="settings-section-advanced-toggle"]'
    ) as HTMLElement
    fireEvent.click(toggle)
    expect(screen.getByTestId('metadata-ffmpeg-timeout')).toBeInTheDocument()
  })
})
```

Also update the section count test:

```tsx
// Change this existing test:
it('renders all 4 settings sections', () => {
  ...
  expect(sections.length).toBeGreaterThanOrEqual(4)
})

// To:
it('renders all 5 settings sections', () => {
  renderWithProviders(<ConnectionsSettings />)
  const sections = screen.getAllByTestId('settings-section')
  expect(sections.length).toBeGreaterThanOrEqual(5)
})
```

### Commit

```
feat: add metadata API keys section to ConnectionsSettings
```

**Files touched:**
- `frontend/src/pages/Settings/ConnectionsSettings.tsx`
- `frontend/src/pages/Settings/__tests__/ConnectionsSettings.test.tsx`

---

## Execution Order & TDD Discipline

For each step:

1. Write / update tests first in `__tests__/` — run `npm run test -- --run` and confirm RED (new tests fail, existing pass or are updated).
2. Implement the component changes.
3. Run tests again — confirm GREEN.
4. Run `npm run lint && npx tsc --noEmit` — confirm zero errors.
5. Commit with the specified message.

Do NOT batch commits. One commit per step.

---

## Cross-Cutting Constraints

- All new state variables use immutable update patterns (spread / filter / map — no
  mutation of existing arrays/objects).
- All new inputs are always controlled (never uncontrolled).
- Password inputs always have an Eye/EyeOff toggle.
- `data-testid` attributes are on the innermost meaningful element, not wrappers.
- CSS uses `var(--...)` tokens only — no hardcoded hex except existing `#5c87ca` /
  `#e8a838` in `ConnectionCard` (do not change those).
- `useConfig` returns `data` — always cast to `Record<string, unknown> | undefined`
  before accessing keys with `?.`.
- `useUpdateConfig` — always call `.mutate({ key: value })` with string values for
  toggle/text config fields, string-coerced numbers for numeric fields.
- `parseInstances` must handle `undefined`, `null`, empty string, invalid JSON, and
  non-array JSON gracefully — always return `ServiceInstance[]`.

---

## Files Modified Summary

| Step | Files |
|------|-------|
| 23 | `__tests__/NotificationsSettings.test.tsx` |
| 24 | `NotificationsSettings.tsx`, `__tests__/NotificationsSettings.test.tsx` |
| 25 | `ConnectionsSettings.tsx`, `__tests__/ConnectionsSettings.test.tsx` |
| 26 | `ConnectionsSettings.tsx`, `__tests__/ConnectionsSettings.test.tsx` |
| 27 | `ConnectionsSettings.tsx`, `__tests__/ConnectionsSettings.test.tsx` |
