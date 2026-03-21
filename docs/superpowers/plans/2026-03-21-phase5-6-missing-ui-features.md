# Plan: Phase 5 & 6 — Missing UI for Existing Backend Features (Steps 47–66)

**Branch:** `feature/frontend-redesign`

**Scope:** 20 steps. Phase 5 wires backend routes that already exist to missing UI surfaces.
Phase 6 adds the remaining features (some need new backend routes, most need only frontend work).

**Execution rule:** One commit per step. Never touch files outside the step's file list.
Check `docs/PROTECTED.md` before every step.

---

## Codebase Conventions (apply everywhere)

### Component patterns (locked — use exactly)

```tsx
// Section wrapper
<SettingsSection title="..." description="..." icon={<Icon size={16} style={{ color: 'var(--accent)' }} />}>
  ...
</SettingsSection>

// Row with label + control
<SettingRow label="Label" description="hint text">
  <button className="btn-primary">Action</button>
</SettingRow>

// Toast
import { toast } from '@/components/shared/Toast'
toast('Success message')
toast('Error message', 'error')

// Confirm dialog
import { ConfirmDialog } from '@/components/shared/ConfirmDialog'
const [showConfirm, setShowConfirm] = useState(false)
<ConfirmDialog
  open={showConfirm}
  title="Are you sure?"
  description="This cannot be undone."
  onConfirm={() => { mutate(); setShowConfirm(false) }}
  onCancel={() => setShowConfirm(false)}
/>
```

### CSS — CSS variables only, never raw Tailwind colours
```tsx
style={{ color: 'var(--text-muted)' }}        // muted text
style={{ color: 'var(--accent)' }}              // accent
style={{ backgroundColor: 'var(--bg-surface)' }} // card background
style={{ border: '1px solid var(--border)' }}   // border
```

### New hooks: add to the correct domain file
- System/config hooks → `frontend/src/hooks/useSystemApi.ts`
- Translation hooks   → `frontend/src/hooks/useTranslationApi.ts`
- Integration/hooks   → `frontend/src/hooks/useIntegrationApi.ts`
- Provider hooks      → `frontend/src/hooks/useProvidersApi.ts`
- Wanted hooks        → `frontend/src/hooks/useWantedApi.ts`

### API client (`frontend/src/api/client.ts`)
Add new `async function` exports. Keep alphabetical order within logical groups.

### New Settings sub-route
To add `/settings/hooks`:
1. Create `frontend/src/pages/Settings/HooksPage.tsx`
2. In `frontend/src/pages/Settings/index.tsx` add:
   ```tsx
   <Route path="hooks" element={<HooksPage />} />
   ```

---

## Phase 5 — Missing UI for Existing Backend Routes

---

### Step 47 — Settings Export / Import UI

**Files:**
- `frontend/src/pages/Settings/SystemSettings.tsx` — add new 8th SettingsSection
- `frontend/src/pages/Settings/ConfigExportImportTab.tsx` — new sub-tab (create)

**Backend endpoints (already exist):**
- `GET  /api/v1/config/export` → returns JSON blob → trigger browser download
- `POST /api/v1/config/import` → body: `Record<string, unknown>` → `{ status, imported_keys: string[], skipped_secrets: string[] }`

**Hooks (already exist in `useSystemApi.ts`):**
- `useExportConfig()` — mutation
- `useImportConfig()` — mutation

**What to build in `ConfigExportImportTab.tsx`:**

```tsx
// Export row
<SettingRow label="Export settings" description="Download all config keys as JSON.">
  <button onClick={() => exportMut.mutate(undefined, {
    onSuccess: (data) => {
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a'); a.href = url; a.download = 'sublarr-config.json'; a.click()
      URL.revokeObjectURL(url)
    },
    onError: () => toast('Export failed', 'error'),
  })}>
    Export
  </button>
</SettingRow>

// Import row — file input + confirm dialog
// 1. <input type="file" accept=".json"> reads file → JSON.parse → setImportData
// 2. Show confirm dialog: "Import X keys? Secrets will be skipped."
// 3. On confirm: importMut.mutate(importData) → toast success with count
```

**Add to `SystemSettings.tsx`** — new 8th section after API Keys:
```tsx
import { Download } from 'lucide-react'
const ConfigExportImportTab = lazy(() =>
  import('./ConfigExportImportTab').then((m) => ({ default: m.ConfigExportImportTab })),
)
// ...
<div data-testid="section-config-export-import">
  <SettingsSection
    title={t('settings.system.configExportImport.title', 'Settings Export / Import')}
    description={t('settings.system.configExportImport.description', 'Export all settings as JSON or import from a backup file.')}
    icon={<Download size={16} style={{ color: 'var(--accent)' }} />}
  >
    <Suspense fallback={<SectionSkeleton />}>
      <ConfigExportImportTab />
    </Suspense>
  </SettingsSection>
</div>
```

**Test file:** `frontend/src/pages/Settings/__tests__/ConfigExportImportTab.test.tsx`

```tsx
// TDD — write these tests first (RED), then implement (GREEN)
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { vi } from 'vitest'

// Mock useExportConfig and useImportConfig
vi.mock('@/hooks/useApi', () => ({
  useExportConfig: () => ({ mutate: mockExport }),
  useImportConfig: () => ({ mutate: mockImport }),
}))

it('renders export button', () => {
  render(<ConfigExportImportTab />)
  expect(screen.getByRole('button', { name: /export/i })).toBeInTheDocument()
})

it('renders file input for import', () => {
  render(<ConfigExportImportTab />)
  expect(screen.getByTestId('import-file-input')).toBeInTheDocument()
})

it('shows confirm dialog before import', async () => {
  render(<ConfigExportImportTab />)
  // simulate file selection with valid JSON
  fireEvent.change(screen.getByTestId('import-file-input'), {
    target: { files: [new File(['{"key":"val"}'], 'config.json', { type: 'application/json' })] }
  })
  await waitFor(() => expect(screen.getByRole('dialog')).toBeInTheDocument())
})
```

**Verify:** `cd frontend && npm run test -- --run --reporter=verbose ConfigExportImportTab`

**Commit:** `feat: add settings export/import UI to SystemSettings`

---

### Step 48 — Translation Memory + Ollama Pull UI

**Files:**
- `frontend/src/pages/Settings/TranslationTab.tsx` — add `OllamaPullSection` component at bottom
- `frontend/src/hooks/useTranslationApi.ts` — add `useOllamaPullModel` hook
- `frontend/src/api/client.ts` — add `ollamaPullModel(modelName: string)` function

**Existing (already done — do NOT re-implement):**
- `TranslationMemorySection` component already exists at line ~935 of TranslationTab.tsx with stats panel, clear-cache button, and confirm dialog. Skip Step 48 memory work — it is complete.

**What is missing — Ollama Pull section only:**

Add to `frontend/src/api/client.ts`:
```ts
export async function ollamaPullModel(model: string): Promise<{ status: string; message?: string }> {
  const { data } = await api.post('/backends/ollama/pull', { model })
  return data
}
```

Add to `frontend/src/hooks/useTranslationApi.ts`:
```ts
export function useOllamaPullModel() {
  return useMutation({
    mutationFn: (model: string) => ollamaPullModel(model),
  })
}
```

Add `OllamaPullSection` component inside `TranslationTab.tsx` (near backend cards section):
```tsx
function OllamaPullSection() {
  const [modelName, setModelName] = useState('')
  const [pulling, setPulling] = useState(false)
  const pullMut = useOllamaPullModel()

  const handlePull = () => {
    if (!modelName.trim()) return
    setPulling(true)
    pullMut.mutate(modelName.trim(), {
      onSuccess: (r) => { toast(r.message ?? `Pulling ${modelName}…`); setPulling(false) },
      onError: () => { toast('Pull failed', 'error'); setPulling(false) },
    })
  }

  return (
    <SettingRow label="Pull Ollama model" description="Download or update a model from the Ollama registry.">
      <div className="flex gap-2 items-center">
        <input
          type="text"
          className="input-base"
          placeholder="e.g. gemma2:27b"
          value={modelName}
          onChange={(e) => setModelName(e.target.value)}
          data-testid="ollama-model-input"
        />
        <button
          className="btn-primary flex items-center gap-1"
          onClick={handlePull}
          disabled={pulling || !modelName.trim()}
          data-testid="ollama-pull-btn"
        >
          {pulling && <Loader2 size={14} className="animate-spin" />}
          Pull
        </button>
      </div>
    </SettingRow>
  )
}
```

Render `<OllamaPullSection />` inside the existing Backends SettingsSection in TranslationTab.

**Test file:** `frontend/src/pages/Settings/__tests__/TranslationTab.ollama.test.tsx`

```tsx
it('renders ollama pull input and button', () => {
  render(<OllamaPullSection />)
  expect(screen.getByTestId('ollama-model-input')).toBeInTheDocument()
  expect(screen.getByTestId('ollama-pull-btn')).toBeInTheDocument()
})

it('pull button disabled when input empty', () => {
  render(<OllamaPullSection />)
  expect(screen.getByTestId('ollama-pull-btn')).toBeDisabled()
})

it('calls mutate with model name on click', async () => {
  render(<OllamaPullSection />)
  fireEvent.change(screen.getByTestId('ollama-model-input'), { target: { value: 'gemma2:27b' } })
  fireEvent.click(screen.getByTestId('ollama-pull-btn'))
  expect(mockPull).toHaveBeenCalledWith('gemma2:27b', expect.any(Object))
})
```

**Verify:** `cd frontend && npm run test -- --run --reporter=verbose TranslationTab.ollama`

**Commit:** `feat: add Ollama model pull UI to TranslationSettings`

---

### Step 49 — Notification History Section

**Files:**
- `frontend/src/pages/Settings/NotificationsSettings.tsx` — add 3rd SettingsSection
- `frontend/src/pages/Settings/NotificationHistoryTab.tsx` — new sub-tab (create)

**Existing hooks (do NOT recreate):**
- `useNotificationHistory(page, eventType)` — in `useSystemApi.ts` line ~548
- `useResendNotification()` — in `useSystemApi.ts` line ~557

**Note:** `NotificationTemplatesTab.tsx` already renders notification history at the bottom of that tab. Check lines ~479+. If it is already complete there, this step becomes a stub redirect pointing at that tab. Read the file first before duplicating code.

**If history table is NOT yet in NotificationsSettings as its own dedicated section, build `NotificationHistoryTab.tsx`:**

```tsx
export function NotificationHistoryTab() {
  const [page, setPage] = useState(1)
  const [eventFilter, setEventFilter] = useState<string | undefined>(undefined)
  const { data, isLoading } = useNotificationHistory(page, eventFilter)
  const resendMut = useResendNotification()

  // Table columns: timestamp | event | channel | status | resend button
  // Pagination: show prev/next if data.total > data.per_page
  // Resend: toast on success/error
}
```

**Add to `NotificationsSettings.tsx`** — 3rd SettingsSection after Events & Hooks (Quiet Hours stays advanced):
```tsx
const NotificationHistoryTab = lazy(() =>
  import('./NotificationHistoryTab').then((m) => ({ default: m.NotificationHistoryTab })),
)
// section:
<div data-testid="section-notification-history">
  <SettingsSection
    title={t('settings.notifications.history.title', 'Notification History')}
    description={t('settings.notifications.history.description', 'Recent notifications sent, with resend capability.')}
    icon={<History size={16} style={{ color: 'var(--accent)' }} />}
  >
    <Suspense fallback={<SectionSkeleton />}>
      <NotificationHistoryTab />
    </Suspense>
  </SettingsSection>
</div>
```

**Test file:** `frontend/src/pages/Settings/__tests__/NotificationHistoryTab.test.tsx`

```tsx
it('renders table with notification rows', async () => {
  // mock useNotificationHistory to return { items: [{ id:1, timestamp:'...', event:'subtitle_found', channel:'discord', status:'sent' }], total:1, page:1, per_page:25 }
  render(<NotificationHistoryTab />)
  await waitFor(() => expect(screen.getByText('subtitle_found')).toBeInTheDocument())
})

it('renders resend button per row', () => {
  render(<NotificationHistoryTab />)
  expect(screen.getAllByRole('button', { name: /resend/i }).length).toBeGreaterThan(0)
})

it('shows empty state when no history', () => {
  // mock returns { items: [], total: 0, page: 1, per_page: 25 }
  render(<NotificationHistoryTab />)
  expect(screen.getByTestId('history-empty')).toBeInTheDocument()
})
```

**Verify:** `cd frontend && npm run test -- --run --reporter=verbose NotificationHistoryTab`

**Commit:** `feat: add notification history section to NotificationsSettings`

---

### Step 50 — Hook Manager Page

**Files:**
- `frontend/src/pages/Settings/HooksPage.tsx` — new page (create)
- `frontend/src/pages/Settings/index.tsx` — add route `/settings/hooks`

**Existing hooks in `useIntegrationApi.ts` (all exist — do NOT recreate):**
- `useHookConfigs()`, `useCreateHook()`, `useUpdateHook()`, `useDeleteHook()`, `useTestHook()`
- `useHookLogs(params?)`, `useClearHookLogs()`
- `useEventCatalog()`

**What to build:**

`HooksPage.tsx` structure:
```
SettingsDetailLayout title="Hooks"
  SettingsSection "Outgoing Hooks"    — list + new/edit/delete/test
  SettingsSection "Hook Logs"         — table + clear button (advanced collapsed)
```

Hook card (one per hook):
- Shows: name, event_type badge, url (truncated), enabled toggle
- Actions: Edit (pencil icon → opens modal), Delete (trash icon → confirm dialog), Test (flask icon → toast)

New/Edit modal fields:
- `name` — text input (required)
- `event_type` — `<select>` populated from `useEventCatalog()` data
- `url` — text input (required, URL)
- `secret` — password input (optional)
- `enabled` — Toggle component

Create: `POST /api/v1/hooks` body `{ name, event_type, url, secret?, enabled }`
Update: `PUT  /api/v1/hooks/:id`
Delete: `DELETE /api/v1/hooks/:id` (confirm dialog)
Test:   `POST /api/v1/hooks/:id/test` → toast result.message

Hook Logs table columns: timestamp | hook name | event | status | response_code
"Clear logs" → `DELETE /api/v1/hooks/logs` (confirm dialog)

**Add to `frontend/src/pages/Settings/index.tsx`:**
```tsx
import { lazy } from 'react'
const HooksPage = lazy(() =>
  import('./HooksPage').then((m) => ({ default: m.HooksPage })),
)
// Inside <Routes>:
<Route path="hooks" element={<HooksPage />} />
```

**Update `SettingsOverview.tsx`** — add Hooks card to the nav grid pointing to `/settings/hooks`.

**Test file:** `frontend/src/pages/Settings/__tests__/HooksPage.test.tsx`

```tsx
it('renders hooks list', async () => {
  // mock useHookConfigs returns [{ id:1, name:'Test Hook', event_type:'subtitle_found', url:'https://example.com', enabled:true }]
  render(<HooksPage />)
  await waitFor(() => expect(screen.getByText('Test Hook')).toBeInTheDocument())
})

it('opens new hook modal on "New Hook" button click', async () => {
  render(<HooksPage />)
  fireEvent.click(screen.getByRole('button', { name: /new hook/i }))
  await waitFor(() => expect(screen.getByRole('dialog')).toBeInTheDocument())
})

it('shows confirm dialog on delete', async () => {
  render(<HooksPage />)
  await waitFor(() => screen.getByText('Test Hook'))
  fireEvent.click(screen.getAllByRole('button', { name: /delete/i })[0])
  expect(screen.getByRole('dialog')).toBeInTheDocument()
})

it('renders hook logs section', async () => {
  render(<HooksPage />)
  expect(screen.getByTestId('section-hook-logs')).toBeInTheDocument()
})
```

**Verify:** `cd frontend && npm run test -- --run --reporter=verbose HooksPage`

**Commit:** `feat: add Hook Manager page with CRUD, test, and logs`

---

### Step 51 — Subtitle Editor Format Convert Tool

**Files:**
- `frontend/src/components/editor/SubtitleEditorModal.tsx` — add format convert dropdown + button to toolbar

**Existing (already done — do NOT re-add):**
- `splitLines` and `timingNormalize` are already wired in `qualityFixes` array at lines 171–173.

**What is missing — format convert only:**

The `convertFormat` API function exists in `client.ts` at line 1740.
There is no convert hook in hooks files yet. Add to `useTranslationApi.ts`:

```ts
export function useConvertSubtitleFormat() {
  return useMutation({
    mutationFn: ({ filePath, targetFormat }: { filePath: string; targetFormat: 'ass' | 'srt' | 'vtt' }) =>
      convertFormat({ file_path: filePath, target_format: targetFormat }),
  })
}
```

In `SubtitleEditorModal.tsx` — add after the quality-fix toolbar (in edit mode only):

```tsx
const [convertTarget, setConvertTarget] = useState<'ass' | 'srt' | 'vtt'>('srt')
const convertMut = useConvertSubtitleFormat()

// In JSX, after quality-fix toolbar buttons:
{mode === 'edit' && filePath && (
  <div className="flex items-center gap-1 border-l pl-2" style={{ borderColor: 'var(--border)' }}>
    <select
      value={convertTarget}
      onChange={(e) => setConvertTarget(e.target.value as 'ass' | 'srt' | 'vtt')}
      className="input-base text-xs py-0.5"
      data-testid="convert-format-select"
    >
      <option value="srt">SRT</option>
      <option value="ass">ASS</option>
      <option value="vtt">VTT</option>
    </select>
    <button
      className="btn-secondary text-xs py-0.5 px-2"
      onClick={() =>
        convertMut.mutate(
          { filePath, targetFormat: convertTarget },
          {
            onSuccess: () => {
              toast(`Converted to ${convertTarget.toUpperCase()}`)
              void queryClient.invalidateQueries({ queryKey: ['subtitle-content', filePath] })
            },
            onError: () => toast('Convert failed', 'error'),
          },
        )
      }
      data-testid="convert-format-btn"
    >
      Convert
    </button>
  </div>
)}
```

**Test file:** `frontend/src/components/editor/__tests__/SubtitleEditorModal.convert.test.tsx`

```tsx
it('renders format select and convert button in edit mode', () => {
  // render with mode='edit' and filePath set
  expect(screen.getByTestId('convert-format-select')).toBeInTheDocument()
  expect(screen.getByTestId('convert-format-btn')).toBeInTheDocument()
})

it('does not render convert UI in preview mode', () => {
  // render with mode='preview'
  expect(screen.queryByTestId('convert-format-select')).not.toBeInTheDocument()
})

it('calls convertMut with correct target format', async () => {
  render(...)
  fireEvent.change(screen.getByTestId('convert-format-select'), { target: { value: 'vtt' } })
  fireEvent.click(screen.getByTestId('convert-format-btn'))
  expect(mockConvert).toHaveBeenCalledWith({ filePath: '/test.ass', targetFormat: 'vtt' }, expect.any(Object))
})
```

**Verify:** `cd frontend && npm run test -- --run --reporter=verbose SubtitleEditorModal`

**Commit:** `feat: add format-convert tool to subtitle editor toolbar`

---

## Phase 6 — Remaining Features (Steps 52–66)

---

### Step 52 — Season Batch Search in SeriesDetail

**Backend:** `POST /api/v1/wanted/batch-search` already accepts `{ series_id: number }` (line 184 of wanted/search.py). No new backend code needed.

**Files:**
- `frontend/src/pages/SeriesDetail.tsx` — add "Search Season" button per season accordion
- `frontend/src/hooks/useWantedApi.ts` — add `useBatchSearchBySeason` hook if not already present

**Check first:** `grep -n "batch-search\|useBatchSearch\|batchSearch" frontend/src/pages/SeriesDetail.tsx` to see current state.

Add hook to `useWantedApi.ts`:
```ts
export function useWantedBatchSearch() {
  return useMutation({
    mutationFn: (params: { series_id?: number; item_ids?: number[] }) =>
      api.post('/wanted/batch-search', params).then(r => r.data),
  })
}
```

In `SeriesDetail.tsx` per-season accordion header add:
```tsx
<button
  className="btn-secondary text-xs"
  onClick={() => batchSearch.mutate({ series_id: seriesId })}
  data-testid={`search-season-${seasonNumber}`}
>
  Search Season {seasonNumber}
</button>
```

**Test:** Renders button per season; click calls mutate with correct series_id.

**Commit:** `feat: add season batch search button to SeriesDetail`

---

### Step 53 — Update Check Banner in Dashboard

**Backend:** `GET /api/v1/update` — already exists (health.py line 192). Returns `{ update_available: bool, latest_version: string, current_version: string, release_url: string }`.

**Existing hook:** `useUpdateInfo()` — already in `useSystemApi.ts` line 57.

**Files:**
- `frontend/src/pages/Dashboard.tsx` — add update banner

**Check first:** `grep -n "useUpdateInfo\|update.*banner\|UpdateBanner" frontend/src/pages/Dashboard.tsx`

If not present, add near the top of Dashboard JSX (before stats grid):
```tsx
const { data: updateInfo } = useUpdateInfo()

{updateInfo?.update_available && (
  <div
    className="flex items-center gap-3 rounded-lg px-4 py-3 text-sm"
    style={{ backgroundColor: 'var(--accent-muted)', border: '1px solid var(--accent)', color: 'var(--text)' }}
    data-testid="update-banner"
  >
    <Info size={16} style={{ color: 'var(--accent)' }} />
    <span>
      Update available: <strong>{updateInfo.latest_version}</strong>
    </span>
    <a
      href={updateInfo.release_url}
      target="_blank"
      rel="noopener noreferrer"
      className="ml-auto underline"
      style={{ color: 'var(--accent)' }}
    >
      View release
    </a>
  </div>
)}
```

**Test:**
```tsx
it('shows update banner when update_available is true', () => {
  // mock useUpdateInfo returns { update_available: true, latest_version: '0.32.0', release_url: 'https://...' }
  render(<Dashboard />)
  expect(screen.getByTestId('update-banner')).toBeInTheDocument()
  expect(screen.getByText(/0\.32\.0/)).toBeInTheDocument()
})

it('hides banner when no update', () => {
  // mock returns { update_available: false }
  render(<Dashboard />)
  expect(screen.queryByTestId('update-banner')).not.toBeInTheDocument()
})
```

**Commit:** `feat: add update check banner to Dashboard`

---

### Step 54 — Provider Rate Limit + Circuit Breaker Status

**Backend:** `GET /api/v1/providers/health` — exists (providers.py line 386). Returns per-provider health + circuit breaker state.

**Files:**
- `frontend/src/hooks/useProvidersApi.ts` — add `useProviderHealth` hook
- `frontend/src/api/client.ts` — add `getProviderHealth()` function
- `frontend/src/pages/Settings/ProvidersTab.tsx` — add health status indicators

**Add to client.ts:**
```ts
export async function getProviderHealth(): Promise<Record<string, { healthy: boolean; circuit_state: string; rate_limited: boolean; last_error?: string }>> {
  const { data } = await api.get('/providers/health')
  return data
}
```

**Add to useProvidersApi.ts:**
```ts
export function useProviderHealth() {
  return useQuery({
    queryKey: ['provider-health'],
    queryFn: getProviderHealth,
    refetchInterval: 30_000,
  })
}
```

**In ProvidersTab.tsx** — per provider card, below existing test-result display, add:
```tsx
const { data: healthData } = useProviderHealth()
const health = healthData?.[provider.name]

{health && (
  <div className="flex gap-2 text-xs mt-1" data-testid={`provider-health-${provider.name}`}>
    <span style={{ color: health.healthy ? 'var(--success)' : 'var(--error)' }}>
      {health.healthy ? 'Healthy' : 'Unhealthy'}
    </span>
    {health.circuit_state !== 'closed' && (
      <span style={{ color: 'var(--warning)' }}>Circuit: {health.circuit_state}</span>
    )}
    {health.rate_limited && (
      <span style={{ color: 'var(--warning)' }}>Rate limited</span>
    )}
  </div>
)}
```

**Test:** Renders health badge; shows "Rate limited" when `rate_limited: true`; shows circuit state when not "closed".

**Commit:** `feat: add provider rate limit and circuit breaker status to ProvidersSettings`

---

### Step 55 — ffprobe Cache Stats + Cleanup in SystemSettings

**Backend:** `GET /api/v1/cache/ffprobe/stats` and `POST /api/v1/cache/ffprobe/cleanup` — exist in system/logs.py lines 652–680.

**Files:**
- `frontend/src/hooks/useSystemApi.ts` — add `useFfprobeStats`, `useFfprobeCleanup`
- `frontend/src/api/client.ts` — add `getFfprobeStats`, `triggerFfprobeCleanup`
- `frontend/src/pages/Settings/SystemSettings.tsx` — add to existing Backup & Restore section OR create a new "Cache" SettingsSection

**Recommendation:** Create a new 9th SettingsSection "Cache Management" (before API Keys section is fine — keep API Keys last as it is advanced).

**Add to client.ts:**
```ts
export async function getFfprobeStats(): Promise<{ count: number; oldest?: string; newest?: string }> {
  const { data } = await api.get('/cache/ffprobe/stats')
  return data
}
export async function triggerFfprobeCleanup(): Promise<{ removed: number }> {
  const { data } = await api.post('/cache/ffprobe/cleanup')
  return data
}
```

**Add to useSystemApi.ts:**
```ts
export function useFfprobeStats() {
  return useQuery({ queryKey: ['ffprobe-stats'], queryFn: getFfprobeStats })
}
export function useFfprobeCleanup() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: triggerFfprobeCleanup,
    onSuccess: (r) => {
      toast(`Removed ${r.removed} stale ffprobe cache entries`)
      void qc.invalidateQueries({ queryKey: ['ffprobe-stats'] })
    },
    onError: () => toast('Cleanup failed', 'error'),
  })
}
```

**UI (new sub-tab `CacheTab.tsx`):**
```tsx
<SettingRow label="ffprobe cache" description={`${stats?.count ?? '…'} entries cached`}>
  <button onClick={() => cleanup.mutate()} data-testid="ffprobe-cleanup-btn">
    Clean up stale entries
  </button>
</SettingRow>
```

Add `<Database size={16} ... />` section icon in SystemSettings.

**Test:** Renders entry count; cleanup button calls mutate; toast shown on success.

**Commit:** `feat: add ffprobe cache stats and cleanup UI to SystemSettings`

---

### Step 56 — Batch Translate Button in Activity / Wanted Tab

**Backend:** `POST /api/v1/wanted/batch-translate` — exists (wanted/providers.py line 376).
Body: `{ item_ids: number[] }` or `{}` for all.

**Files:**
- `frontend/src/hooks/useWantedApi.ts` — add `useWantedBatchTranslate` if not present
- `frontend/src/pages/ActivityPage.tsx` (or `Wanted.tsx`) — add toolbar button

**Check first:** `grep -n "batch-translate\|batchTranslate\|useBatchTranslate" frontend/src/pages/ActivityPage.tsx frontend/src/pages/Wanted.tsx`

Note: `useBatchTranslate` already exists in `useTranslationApi.ts` line 363. Check if it calls `/wanted/batch-translate` or a different route.

**Add hook to `useWantedApi.ts`** (dedicated for wanted-item batch translate):
```ts
export function useWantedBatchTranslate() {
  return useMutation({
    mutationFn: (item_ids: number[]) =>
      api.post('/wanted/batch-translate', { item_ids }).then(r => r.data),
  })
}
```

**In Wanted tab toolbar** — add button alongside existing "Batch Search":
```tsx
<button
  className="btn-secondary text-sm"
  onClick={() => {
    const ids = selectedItems.map(i => i.id) // use existing selection state
    batchTranslate.mutate(ids, {
      onSuccess: () => toast('Batch translate started'),
      onError: () => toast('Failed to start batch translate', 'error'),
    })
  }}
  data-testid="batch-translate-btn"
>
  Batch Translate
</button>
```

**Test:** Button renders; click with selected items calls mutate with correct IDs.

**Commit:** `feat: add batch translate button to Wanted page`

---

### Step 57 — Wanted Cleanup + Refresh Buttons

**Backend:**
- `POST /api/v1/wanted/cleanup` — exists (wanted/providers.py line 192)
- `POST /api/v1/wanted/refresh` — exists (wanted/list.py line 180)

**Files:**
- `frontend/src/hooks/useWantedApi.ts` — add `useWantedCleanup`, `useWantedRefresh` if not present
- `frontend/src/pages/ActivityPage.tsx` (or Wanted tab) — add buttons

**Check first:** `grep -n "cleanup\|refresh\|useWantedCleanup\|useWantedRefresh" frontend/src/hooks/useWantedApi.ts`

**Add missing hooks:**
```ts
export function useWantedCleanup() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => api.post('/wanted/cleanup').then(r => r.data),
    onSuccess: (r) => {
      toast(`Cleaned up ${r.removed ?? 0} entries`)
      void qc.invalidateQueries({ queryKey: ['wanted'] })
    },
  })
}

export function useWantedRefresh() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => api.post('/wanted/refresh').then(r => r.data),
    onSuccess: () => {
      toast('Wanted list refreshed')
      void qc.invalidateQueries({ queryKey: ['wanted'] })
    },
  })
}
```

**In Wanted tab toolbar** — add two icon buttons:
```tsx
<button title="Refresh wanted list" data-testid="wanted-refresh-btn" onClick={() => refresh.mutate()}>
  <RefreshCw size={14} />
</button>
<button title="Clean up stale entries" data-testid="wanted-cleanup-btn" onClick={() => setShowCleanupConfirm(true)}>
  <Trash2 size={14} />
</button>
<ConfirmDialog open={showCleanupConfirm} title="Clean up wanted list?" ... />
```

**Test:** Both buttons render; cleanup shows confirm dialog; refresh calls mutate directly.

**Commit:** `feat: add cleanup and refresh buttons to Wanted page`

---

### Step 58 — Translation Backend Stats Cards

**Backend:** `GET /api/v1/backends/stats` — exists (translate/backends.py line 353).

**Existing hook:** `useBackendStats()` — already in `useTranslationApi.ts` line 260.

**Files:**
- `frontend/src/pages/Settings/TranslationTab.tsx` — confirm stats are rendered in BackendCard

**Check first:** `grep -n "useBackendStats\|backendStats\|successRate\|stats" frontend/src/pages/Settings/TranslationTab.tsx | head -20`

The `BackendCard` component already has stats logic (successRate at line 66) and renders stats in header. If the per-backend stats are already visible in the card UI, this step is complete.

If NOT rendered in card header, add to `BackendCard` header:
```tsx
{stats && (
  <div className="flex gap-3 text-xs" style={{ color: 'var(--text-muted)' }}>
    <span data-testid="backend-requests">{stats.total_requests} requests</span>
    {successRate !== null && (
      <span style={{ color: successRate >= 90 ? 'var(--success)' : 'var(--warning)' }}>
        {successRate}% success
      </span>
    )}
    {stats.avg_duration_ms && (
      <span>{Math.round(stats.avg_duration_ms)}ms avg</span>
    )}
  </div>
)}
```

**Test:** BackendCard renders stats row when stats prop provided; success rate colour changes at 90% threshold.

**Commit:** `feat: add translation backend stats display to TranslationSettings`

---

### Step 59 — Compat Check Button in IntegrationsTab

**Backend:** `POST /api/v1/compat-check` — exists (integrations.py line 68). Also `POST /api/v1/compat-check/single`.

**Existing hook:** `useCompatCheck()` — in `useIntegrationApi.ts` line 197.

**Files:**
- `frontend/src/pages/Settings/IntegrationsTab.tsx` — check if compat check UI exists

**Check first:** `grep -n "CompatCheck\|compatCheck\|compat-check\|useCompatCheck" frontend/src/pages/Settings/IntegrationsTab.tsx`

The `IntegrationsTab` already contains Bazarr mapping report and extended health sections. If compat check UI is missing, add a `CompatCheckSection` within the existing IntegrationsTab:

```tsx
function CompatCheckSection() {
  const compatCheck = useCompatCheck()
  const [results, setResults] = useState<CompatBatchResult | null>(null)

  return (
    <SettingRow label="Compatibility check" description="Test subtitle compatibility with Plex, Kodi, and other media servers.">
      <div className="space-y-2 w-full">
        <button
          className="btn-secondary"
          onClick={() => compatCheck.mutate(undefined, {
            onSuccess: (r) => setResults(r),
            onError: () => toast('Compat check failed', 'error'),
          })}
          data-testid="compat-check-btn"
        >
          {compatCheck.isPending ? <Loader2 size={14} className="animate-spin inline mr-1" /> : null}
          Run compatibility check
        </button>
        {results && (
          <div data-testid="compat-results" className="text-xs space-y-1" style={{ color: 'var(--text-muted)' }}>
            {/* render results.checks array */}
          </div>
        )}
      </div>
    </SettingRow>
  )
}
```

**Test:** Button renders; click calls useCompatCheck mutate; results display after success.

**Commit:** `feat: add compat check button to IntegrationsTab`

---

### Step 60 — Bazarr Import Wizard

**Backend:** `POST /api/v1/import/bazarr` — exists in api_keys.py line 712.

**Files:**
- `frontend/src/pages/Settings/MigrationTab.tsx` — already handles Bazarr migration (check current state first)

**Check first:** `grep -n "import.*bazarr\|bazarr.*import\|BazarrImport\|MigrationTab" frontend/src/pages/Settings/MigrationTab.tsx | head -20`

If MigrationTab already implements the Bazarr DB import wizard (it imports from api_keys endpoint), this step is complete. Verify by reading the component and confirming:
1. File upload input for Bazarr DB file
2. POST to `/api/v1/import/bazarr`
3. Progress/result display

If incomplete, add missing pieces. The IntegrationsTab already shows a link to "Settings > API Keys > Bazarr Migration" (line 219 of IntegrationsTab.tsx). Follow that existing navigation pattern — do not duplicate.

**If already done:** Document as complete.
**If missing import UI:** Add to MigrationTab.tsx a file-upload section for `bazarr.db` file → FormData POST → result toast.

**Test:** File input renders; upload triggers POST; success shows toast.

**Commit:** `feat: complete Bazarr import wizard in MigrationTab`

---

### Step 61 — DB Vacuum Button in SystemSettings

**Backend:** `POST /api/v1/database/vacuum` — exists (system/logs.py line 610).

**Files:**
- `frontend/src/hooks/useSystemApi.ts` — add `useDbVacuum` hook
- `frontend/src/api/client.ts` — add `triggerDbVacuum()` function
- `frontend/src/pages/Settings/SystemSettings.tsx` — add to existing "Migration" section or new "Database" section

**Add to client.ts:**
```ts
export async function triggerDbVacuum(): Promise<{ status: string; message: string; duration_ms?: number }> {
  const { data } = await api.post('/database/vacuum')
  return data
}
```

**Add to useSystemApi.ts:**
```ts
export function useDbVacuum() {
  return useMutation({
    mutationFn: triggerDbVacuum,
    onSuccess: (r) => toast(r.message ?? 'Database vacuumed'),
    onError: () => toast('Vacuum failed', 'error'),
  })
}
```

**In SystemSettings.tsx** — add to the existing Migration SettingsSection (or the new Cache section from step 55):
```tsx
<SettingRow label="Database vacuum" description="Reclaim unused space and defragment the SQLite database.">
  <button
    className="btn-secondary"
    onClick={() => setShowVacuumConfirm(true)}
    data-testid="db-vacuum-btn"
  >
    Run VACUUM
  </button>
  <ConfirmDialog
    open={showVacuumConfirm}
    title="Run database VACUUM?"
    description="This may take a moment on large databases. The app remains available."
    onConfirm={() => { vacuum.mutate(); setShowVacuumConfirm(false) }}
    onCancel={() => setShowVacuumConfirm(false)}
  />
</SettingRow>
```

**Test:** Button renders; click shows confirm dialog; confirm calls mutate; toast shown.

**Commit:** `feat: add database vacuum button to SystemSettings`

---

### Step 62 — Whisper Transcription in Episode Detail

**Backend:** `POST /api/v1/transcribe` — exists (whisper.py line 46).
Body: `{ file_path: string, language?: string, backend?: string }`.

**Files:**
- `frontend/src/pages/SeriesDetail.tsx` — find episode detail panel and add Transcribe button
- `frontend/src/hooks/useTranslationApi.ts` OR `useSystemApi.ts` — add `useTranscribeEpisode` hook

**Check first:** `grep -n "transcribe\|Transcribe\|whisper" frontend/src/pages/SeriesDetail.tsx | head -10`

Existing whisper hooks in `useTranslationApi.ts` lines 269+: `useWhisperQueue`, `useWhisperStats`.
Check if transcribe mutation hook exists: `grep -n "useTranscribe\|transcribe" frontend/src/hooks/useTranslationApi.ts`

**Add to useTranslationApi.ts:**
```ts
export function useTranscribeEpisode() {
  return useMutation({
    mutationFn: ({ filePath, language, backend }: { filePath: string; language?: string; backend?: string }) =>
      api.post('/transcribe', { file_path: filePath, language, backend }).then(r => r.data),
    onSuccess: () => toast('Transcription started'),
    onError: () => toast('Transcription failed', 'error'),
  })
}
```

**In SeriesDetail episode row / detail panel** — add Transcribe button:
```tsx
<button
  className="btn-secondary text-xs"
  title="Transcribe audio to subtitles via Whisper"
  onClick={() => transcribe.mutate({ filePath: episode.file_path })}
  data-testid={`transcribe-btn-${episode.id}`}
>
  Transcribe
</button>
```

**Test:** Transcribe button renders per episode; click calls mutate with correct file_path.

**Commit:** `feat: add Whisper transcription button to episode detail`

---

### Step 63 — OP/ED Detection in Episode Detail

**Backend:** `POST /api/v1/detect-opening-ending` — exists (tools/editing.py line 264).
Body: `{ file_path: string }`.

**Existing usage:** `detectOpeningEnding` is already imported in `SubtitleEditorModal.tsx` and used in quality-fixes toolbar. This backend function already works.

**Files:**
- `frontend/src/pages/SeriesDetail.tsx` — add OP/ED detect button to episode detail panel

**Check first:** `grep -n "detect.*opening\|detectOpening\|opEd\|op.ed" frontend/src/pages/SeriesDetail.tsx | head -5`

**Add hook to useTranslationApi.ts:**
```ts
export function useDetectOpeningEnding() {
  return useMutation({
    mutationFn: (filePath: string) => detectOpeningEnding(filePath),
    onSuccess: (r) => {
      if (r.detected?.length > 0) toast(`${r.detected.length} OP/ED segments detected`)
      else toast('No OP/ED segments detected')
    },
    onError: () => toast('Detection failed', 'error'),
  })
}
```

**In SeriesDetail episode row:**
```tsx
<button
  className="btn-secondary text-xs"
  title="Detect OP/ED segments in episode video"
  onClick={() => detectOpEd.mutate(episode.file_path)}
  data-testid={`detect-oped-btn-${episode.id}`}
>
  Detect OP/ED
</button>
```

**Test:** Button renders; click calls mutate with file_path; success toast shows count.

**Commit:** `feat: add OP/ED detection button to episode detail`

---

### Step 64 — AniDB Mapping Cache Viewer in SystemSettings

**Backend routes (anidb_mapping.py):**
- `POST /api/v1/anidb-mapping/refresh` — line 29
- `GET  /api/v1/anidb-mapping/status` — line 61

**Existing hooks in useIntegrationApi.ts:** `useAnidbMappingStatus()` line 228, `useRefreshAnidbMapping()` line 232.

**Files:**
- `frontend/src/pages/Settings/SystemSettings.tsx` — add AniDB section (or add to Integrations section)

**Check first:** `grep -rn "anidb\|AniDB\|useAnidb" frontend/src/pages/Settings/ | head -10`

**If not yet rendered**, add a new collapsible SettingsSection or expand IntegrationsTab:

```tsx
// In a new AnidbCacheSection component or inside IntegrationsTab:
function AnidbCacheSection() {
  const { data: status } = useAnidbMappingStatus()
  const refresh = useRefreshAnidbMapping()

  return (
    <SettingRow
      label="AniDB mapping cache"
      description={status ? `Last updated: ${status.last_updated ?? 'never'} · ${status.entry_count ?? 0} entries` : 'Loading…'}
    >
      <button
        className="btn-secondary"
        onClick={() => refresh.mutate(undefined, {
          onSuccess: () => toast('AniDB mapping refreshed'),
          onError: () => toast('Refresh failed', 'error'),
        })}
        data-testid="anidb-refresh-btn"
      >
        Refresh mapping
      </button>
    </SettingRow>
  )
}
```

**Test:** Status text renders; refresh button calls mutate; toast shown on success.

**Commit:** `feat: add AniDB mapping cache viewer to SystemSettings`

---

### Step 65 — Incoming Webhooks Config Page

**Backend (webhooks.py):** Incoming webhook *receivers* for Sonarr/Radarr/Jellyfin exist (lines 114, 231, 381). These are already active; they do not need configuration UI.

**Actual gap:** A page listing the configured webhook URLs so users can copy them into Sonarr/Radarr.

**Files:**
- `frontend/src/pages/Settings/WebhooksPage.tsx` — new page (create)
- `frontend/src/pages/Settings/index.tsx` — add route `/settings/webhooks`

**What to build** — read-only webhook URL viewer:
```tsx
export function WebhooksPage() {
  const baseUrl = window.location.origin  // or from config

  const webhooks = [
    { service: 'Sonarr', path: '/api/v1/webhook/sonarr', description: 'Paste into Sonarr → Connect → Webhook' },
    { service: 'Radarr', path: '/api/v1/webhook/radarr', description: 'Paste into Radarr → Connect → Webhook' },
    { service: 'Jellyfin', path: '/api/v1/webhook/jellyfin', description: 'Paste into Jellyfin → Webhooks plugin' },
  ]

  return (
    <SettingsDetailLayout title="Incoming Webhooks" subtitle="Copy these URLs into your media server webhook settings.">
      {webhooks.map(w => (
        <SettingsSection key={w.service} title={w.service} description={w.description} icon={<Webhook ... />}>
          <SettingRow label="Webhook URL">
            <div className="flex gap-2 items-center font-mono text-sm" style={{ color: 'var(--text-muted)' }}>
              <span data-testid={`webhook-url-${w.service.toLowerCase()}`}>{baseUrl}{w.path}</span>
              <button onClick={() => { navigator.clipboard.writeText(`${baseUrl}${w.path}`); toast('Copied!') }}>
                <Copy size={14} />
              </button>
            </div>
          </SettingRow>
        </SettingsSection>
      ))}
    </SettingsDetailLayout>
  )
}
```

**Add route in index.tsx:**
```tsx
<Route path="webhooks" element={<WebhooksPage />} />
```

**Test:**
```tsx
it('renders webhook URL for each service', () => {
  render(<WebhooksPage />)
  expect(screen.getByTestId('webhook-url-sonarr')).toHaveTextContent('/api/v1/webhook/sonarr')
  expect(screen.getByTestId('webhook-url-radarr')).toHaveTextContent('/api/v1/webhook/radarr')
  expect(screen.getByTestId('webhook-url-jellyfin')).toHaveTextContent('/api/v1/webhook/jellyfin')
})

it('copy button calls navigator.clipboard.writeText', async () => {
  Object.assign(navigator, { clipboard: { writeText: vi.fn().mockResolvedValue(undefined) } })
  render(<WebhooksPage />)
  fireEvent.click(screen.getAllByRole('button')[0])
  expect(navigator.clipboard.writeText).toHaveBeenCalled()
})
```

**Commit:** `feat: add incoming webhooks URL viewer page`

---

### Step 66 — Remux UI in SeriesDetail

**Backend (remux.py):**
- `POST /api/v1/library/episodes/:ep_id/tracks/:index/remove-from-container` — line 154, starts async remux job
- `GET  /api/v1/remux/jobs` — line 194, list all jobs
- `GET  /api/v1/remux/jobs/:job_id` — line 202, poll single job
- `GET  /api/v1/remux/backups` — line 212
- `POST /api/v1/remux/backups/cleanup` — line 219
- `POST /api/v1/remux/backups/restore` — line 249, body `{ backup_path: string }`

**Files:**
- `frontend/src/hooks/useLibraryApi.ts` — add remux hooks
- `frontend/src/api/client.ts` — add remux API functions
- `frontend/src/pages/SeriesDetail.tsx` — add remux track button per subtitle track in episode detail

**Check first:** `grep -n "remux\|Remux\|removeTrack\|remove.*track" frontend/src/pages/SeriesDetail.tsx | head -10`

**Add to client.ts:**
```ts
export async function removeTrackFromContainer(epId: number, trackIndex: number, subtitleTrackIndex?: number): Promise<{ job_id: string }> {
  const { data } = await api.post(`/library/episodes/${epId}/tracks/${trackIndex}/remove-from-container`, { subtitle_track_index: subtitleTrackIndex })
  return data
}

export async function getRemuxJob(jobId: string): Promise<{ job_id: string; status: string; progress?: number; error?: string }> {
  const { data } = await api.get(`/remux/jobs/${jobId}`)
  return data
}
```

**Add to useLibraryApi.ts:**
```ts
export function useRemoveTrackFromContainer() {
  return useMutation({
    mutationFn: ({ epId, trackIndex, subtitleTrackIndex }: { epId: number; trackIndex: number; subtitleTrackIndex?: number }) =>
      removeTrackFromContainer(epId, trackIndex, subtitleTrackIndex),
    onSuccess: (r) => toast(`Remux job started: ${r.job_id}`),
    onError: () => toast('Failed to start remux job', 'error'),
  })
}
```

**In SeriesDetail episode subtitle tracks list** — add per-track "Remove from container" button:
```tsx
<button
  className="btn-secondary text-xs"
  title="Remove this embedded subtitle track from the video file"
  onClick={() => setRemuxConfirmTrack(track)}
  data-testid={`remux-remove-track-${track.index}`}
>
  Remove track
</button>
<ConfirmDialog
  open={remuxConfirmTrack?.index === track.index}
  title="Remove embedded subtitle track?"
  description="This modifies the video file (backup created). Cannot be undone from Sublarr directly."
  onConfirm={() => {
    removeTrack.mutate({ epId: episode.id, trackIndex: track.index })
    setRemuxConfirmTrack(null)
  }}
  onCancel={() => setRemuxConfirmTrack(null)}
/>
```

**Test:**
```tsx
it('renders remove track button per subtitle track', () => {
  render(<SeriesDetail ... />)
  expect(screen.getByTestId('remux-remove-track-0')).toBeInTheDocument()
})

it('shows confirm dialog before remux', async () => {
  render(<SeriesDetail ... />)
  fireEvent.click(screen.getByTestId('remux-remove-track-0'))
  expect(screen.getByRole('dialog')).toBeInTheDocument()
})
```

**Commit:** `feat: add remux track removal UI to SeriesDetail`

---

## Pre-PR Checklist (run after ALL steps complete)

```bash
# Backend (no backend changes in most steps — but verify)
cd backend && ruff check . && ruff format --check .

# Frontend lint + typecheck
cd frontend && npm run lint && npx tsc --noEmit

# Full test suite
cd frontend && npm run test -- --run

# Verify no TypeScript errors introduced
cd frontend && npx tsc --noEmit 2>&1 | head -40
```

---

## Commit Message Reference

| Step | Message |
|------|---------|
| 47 | `feat: add settings export/import UI to SystemSettings` |
| 48 | `feat: add Ollama model pull UI to TranslationSettings` |
| 49 | `feat: add notification history section to NotificationsSettings` |
| 50 | `feat: add Hook Manager page with CRUD, test, and logs` |
| 51 | `feat: add format-convert tool to subtitle editor toolbar` |
| 52 | `feat: add season batch search button to SeriesDetail` |
| 53 | `feat: add update check banner to Dashboard` |
| 54 | `feat: add provider rate limit and circuit breaker status to ProvidersSettings` |
| 55 | `feat: add ffprobe cache stats and cleanup UI to SystemSettings` |
| 56 | `feat: add batch translate button to Wanted page` |
| 57 | `feat: add cleanup and refresh buttons to Wanted page` |
| 58 | `feat: add translation backend stats display to TranslationSettings` |
| 59 | `feat: add compat check button to IntegrationsTab` |
| 60 | `feat: complete Bazarr import wizard in MigrationTab` |
| 61 | `feat: add database vacuum button to SystemSettings` |
| 62 | `feat: add Whisper transcription button to episode detail` |
| 63 | `feat: add OP/ED detection button to episode detail` |
| 64 | `feat: add AniDB mapping cache viewer to SystemSettings` |
| 65 | `feat: add incoming webhooks URL viewer page` |
| 66 | `feat: add remux track removal UI to SeriesDetail` |

---

## Notes on Already-Complete Items

Before implementing each step, run the "Check first" grep command. Several items may already be partially or fully done:

- **Step 48 memory section** — `TranslationMemorySection` component is complete. Only Ollama Pull is missing.
- **Step 49** — `NotificationTemplatesTab.tsx` already renders history at bottom. Evaluate whether a dedicated section in `NotificationsSettings.tsx` adds value or is duplicative.
- **Step 51 split/timing** — already in `qualityFixes` array in SubtitleEditorModal. Only format convert is missing.
- **Step 58 backend stats** — `BackendCard` already computes `successRate`. Check if it is rendered.
- **Step 60 Bazarr import** — `MigrationTab.tsx` likely already has this; verify before building.

When a step is already done: write a one-line comment at the top of the relevant file confirming completion, skip the test, commit with `docs: confirm step N already implemented`.
