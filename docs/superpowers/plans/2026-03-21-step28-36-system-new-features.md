# Plan: Steps 28–36 — SystemSettings Sections + Phase 3 New Features

**Scope:** Complete the remaining SystemSettings sub-sections (Steps 28–31) and implement all Phase 3 new features (Steps 32–36).

**Branch:** `feature/frontend-redesign`

**Commits:** One commit per step (9 total — see commit messages at the end).

---

## Protected Areas — Read Before Touching Anything

Per `docs/PROTECTED.md`:
- `SettingsSection`, `FormGroup`, `SettingsDetailLayout`, `SettingsCard` — APIs and visual structure are locked.
- CSS Custom Properties in `index.css` — never touch.
- `SystemSettings.tsx` sections 1–7 already rendered — never remove or restructure them.

New sections (Steps 28–31) are **additions** to existing SettingsSections, not replacements.

---

## Codebase Patterns (use exactly)

### Settings field — text input
```tsx
<SettingRow label="Label" description="hint">
  <input
    type="text"
    value={values['field_key'] ?? ''}
    onChange={(e) => onFieldChange('field_key', e.target.value)}
    className="w-full px-3 py-2 rounded-md text-sm"
    style={{
      backgroundColor: 'var(--bg-primary)',
      border: '1px solid var(--border)',
      color: 'var(--text-primary)',
      fontFamily: 'var(--font-mono)',
      fontSize: '13px',
    }}
  />
</SettingRow>
```

### Settings field — number input
Same as text input but `type="number"` and no `fontFamily: mono`.

### Settings field — toggle
```tsx
<SettingRow label="Label" description="hint">
  <Toggle
    checked={values['field_key'] === 'true'}
    onChange={(v) => onFieldChange('field_key', String(v))}
  />
</SettingRow>
```

### Config persistence
All config fields persist via `useConfig()` + `useUpdateConfig()` from `@/hooks/useApi` (re-exported from `useSystemApi.ts`). Keys map directly to backend config keys (stored as strings).

### New SettingsSection in SystemSettings.tsx
```tsx
import { SomeIcon } from 'lucide-react'
// Add lazy import at top of file
const SomeTab = lazy(() =>
  import('./SomeTab').then((m) => ({ default: m.SomeTab })),
)
// Add section in JSX:
<div data-testid="section-some">
  <SettingsSection
    title={t('settings.system.some.title', 'Some Title')}
    description={t('settings.system.some.description', 'Description.')}
    icon={<SomeIcon size={16} style={{ color: 'var(--accent)' }} />}
  >
    <div data-testid="some-content">
      <Suspense fallback={<SectionSkeleton />}>
        <SomeTab />
      </Suspense>
    </div>
  </SettingsSection>
</div>
```

### Hook / API pattern
New hooks go in `useSystemApi.ts`. New API functions go in `api/client.ts`. Always use `useMutation` for mutations and `useQuery` for reads.

### Test pattern
See `frontend/src/pages/Settings/__tests__/SystemSettings.test.tsx` for the mock pattern. Every new sub-tab component is lazy-mocked. New sections need `data-testid` assertions.

---

## Step 28 — SystemSettings › Backup Retention Fields

**Goal:** Add four config fields to the existing Backup & Restore section.

**Files to create/modify:**
- `frontend/src/pages/Settings/AdvancedTab.tsx` — add fields to `BackupTab` component
- `frontend/src/pages/Settings/__tests__/SystemSettings.test.tsx` — update section count if needed

**What already exists:**
- `BackupTab` is exported from `AdvancedTab.tsx` and rendered inside the "Backup & Restore" `SettingsSection` in `SystemSettings.tsx`
- `BackupTab` already uses `useConfig()` + `useUpdateConfig()` for field persistence
- `useFullBackups`, `useCreateFullBackup`, `useRestoreFullBackup` already exist in `useSystemApi.ts`

**Implementation:**

In `BackupTab` (inside `AdvancedTab.tsx`), after the existing backup controls, add a subsection titled "Retention Policy" with these four `SettingRow` entries:

| Config key | Label | Type | Description |
|---|---|---|---|
| `backup_dir` | Backup Directory | text (mono) | Absolute path for backup storage |
| `backup_retention_daily` | Daily Backups | number | Number of daily backups to keep |
| `backup_retention_weekly` | Weekly Backups | number | Number of weekly backups to keep |
| `backup_retention_monthly` | Monthly Backups | number | Number of monthly backups to keep |

Persistence: use the existing `useConfig()` read and `useUpdateConfig()` mutation pattern already used in `BackupTab`. Each field saves on blur (not on change) to avoid spamming the API. Pattern: local state initialized from config, `onBlur` calls `updateConfig.mutate({ field_key: String(localValue) })`.

**Tests:**
- Add a test to `SystemSettings.test.tsx` asserting `data-testid="backup-restore-content"` is present (it already is — verify test still passes).
- Add unit test for the retention fields in a new `__tests__/BackupRetentionFields.test.tsx` (or inline in an existing AdvancedTab test if one exists). Test: renders 4 inputs with correct labels, values from mocked config.

**Verification:**
```bash
cd frontend && npm run test -- --run
```
Retention inputs render. Blur on each field triggers `updateConfig` with correct key.

**Commit:** `feat: add backup retention fields to SystemSettings`

---

## Step 29 — SystemSettings › AniDB Section (new)

**Goal:** New SettingsSection "AniDB" with four config fields.

**Files to create/modify:**
- `frontend/src/pages/Settings/AnidbTab.tsx` — NEW file, exports `AnidbTab`
- `frontend/src/pages/Settings/SystemSettings.tsx` — add lazy import + new section
- `frontend/src/pages/Settings/__tests__/SystemSettings.test.tsx` — add mock + section assertion

**AnidbTab implementation:**

```tsx
// frontend/src/pages/Settings/AnidbTab.tsx
import { useState, useEffect } from 'react'
import { useConfig, useUpdateConfig } from '@/hooks/useApi'
import { SettingRow } from '@/components/shared/SettingRow'
import { Toggle } from '@/components/shared/Toggle'
import { toast } from '@/components/shared/Toast'

export function AnidbTab() {
  const { data: config } = useConfig()
  const updateConfig = useUpdateConfig()
  // derive values from config (all stored as strings)
  // local state per numeric field for blur-save pattern
  // ...
}
```

Fields:

| Config key | Label | Type | Description |
|---|---|---|---|
| `anidb_enabled` | Enable AniDB | toggle | Use AniDB for metadata lookups |
| `anidb_cache_ttl_days` | Cache TTL (days) | number | Days to cache AniDB responses |
| `anidb_custom_field_name` | Custom Field Name | text | Custom metadata field name for AniDB ID |
| `anidb_fallback_to_mapping` | Fallback to Mapping | toggle | Use AniDB-to-Sonarr mapping when direct lookup fails |

Toggle fields: save immediately on change via `updateConfig.mutate({ anidb_enabled: String(v) })` with success/error toast.

Number/text fields: blur-save pattern.

**SystemSettings.tsx additions:**
```tsx
// Add lazy import (after existing lazy imports):
const AnidbTab = lazy(() =>
  import('./AnidbTab').then((m) => ({ default: m.AnidbTab })),
)

// Add icon import: Database (already imported? check — if not, add it)
// Better: use 'Tv2' or keep 'Database' from lucide-react

// Add new section after "API Keys" section:
<div data-testid="section-anidb">
  <SettingsSection
    title={t('settings.system.anidb.title', 'AniDB')}
    description={t(
      'settings.system.anidb.description',
      'AniDB integration for anime metadata and mapping.',
    )}
    icon={<Database size={16} style={{ color: 'var(--accent)' }} />}
  >
    <div data-testid="anidb-content">
      <Suspense fallback={<SectionSkeleton />}>
        <AnidbTab />
      </Suspense>
    </div>
  </SettingsSection>
</div>
```

Note: `Database` is already imported in `SystemSettings.tsx` (used by the Migration section). Pick a different icon to avoid semantic confusion — use `Tv2` from lucide-react (anime/TV context) or `Globe2`. Use `Tv2`.

**Tests:**
- Mock `../AnidbTab` in `SystemSettings.test.tsx`
- Assert `data-testid="section-anidb"` is present
- Add `AnidbTab.test.tsx`: renders all 4 fields, toggle calls updateConfig

**Commit:** `feat: add AniDB section to SystemSettings`

---

## Step 30 — SystemSettings › Remux Section (new)

**Goal:** New SettingsSection "Remux" with four config fields.

**Files to create/modify:**
- `frontend/src/pages/Settings/RemuxTab.tsx` — NEW file, exports `RemuxTab`
- `frontend/src/pages/Settings/SystemSettings.tsx` — lazy import + section
- `frontend/src/pages/Settings/__tests__/SystemSettings.test.tsx` — mock + assertion

**Fields:**

| Config key | Label | Type | Description |
|---|---|---|---|
| `remux_trash_dir` | Trash Directory | text (mono) | Path for remux trash/originals |
| `remux_backup_retention_days` | Backup Retention (days) | number | Days to keep remux backups |
| `remux_use_reflink` | Use Reflink | toggle | Use CoW reflink copies instead of full copies |
| `remux_arr_pause_enabled` | Pause Arr on Remux | toggle | Pause Sonarr/Radarr during remux operations |

Same blur-save / toggle-save pattern as Step 29.

**SystemSettings.tsx section:**
```tsx
const RemuxTab = lazy(() =>
  import('./RemuxTab').then((m) => ({ default: m.RemuxTab })),
)

<div data-testid="section-remux">
  <SettingsSection
    title={t('settings.system.remux.title', 'Remux')}
    description={t(
      'settings.system.remux.description',
      'Settings for remux operations and backup retention.',
    )}
    icon={<HardDrive size={16} style={{ color: 'var(--accent)' }} />}
  >
    <div data-testid="remux-content">
      <Suspense fallback={<SectionSkeleton />}>
        <RemuxTab />
      </Suspense>
    </div>
  </SettingsSection>
</div>
```

Add `HardDrive` to lucide-react imports in `SystemSettings.tsx`.

**Tests:** Same pattern as Step 29 — mock, assert section testid, unit test for fields.

**Commit:** `feat: add Remux section to SystemSettings`

---

## Step 31 — SystemSettings › Standalone Section (new)

**Goal:** New SettingsSection "Standalone Mode" with three config fields.

**Files to create/modify:**
- `frontend/src/pages/Settings/StandaloneSettingsTab.tsx` — NEW file, exports `StandaloneSettingsTab`
- `frontend/src/pages/Settings/SystemSettings.tsx` — lazy import + section
- `frontend/src/pages/Settings/__tests__/SystemSettings.test.tsx` — mock + assertion

**Fields:**

| Config key | Label | Type | Description |
|---|---|---|---|
| `standalone_scan_interval_hours` | Scan Interval (hours) | number | How often the standalone watcher rescans |
| `standalone_debounce_seconds` | Debounce (seconds) | number | Seconds to wait after a file event before processing |
| `standalone_skip_extras` | Skip Extras | toggle | Skip extras/specials during standalone scan |

**SystemSettings.tsx section:**
```tsx
const StandaloneSettingsTab = lazy(() =>
  import('./StandaloneSettingsTab').then((m) => ({ default: m.StandaloneSettingsTab })),
)

// Icon: FolderOpen is used in AdvancedTab internally. Use 'MonitorPlay' or 'ScanLine'.
// Use 'ScanLine' from lucide-react.

<div data-testid="section-standalone">
  <SettingsSection
    title={t('settings.system.standalone.title', 'Standalone Mode')}
    description={t(
      'settings.system.standalone.description',
      'Configure the standalone file watcher and scan behaviour.',
    )}
    icon={<ScanLine size={16} style={{ color: 'var(--accent)' }} />}
  >
    <div data-testid="standalone-content">
      <Suspense fallback={<SectionSkeleton />}>
        <StandaloneSettingsTab />
      </Suspense>
    </div>
  </SettingsSection>
</div>
```

**Tests:** Same pattern — mock, assert section testid, unit test for 3 fields.

**Commit:** `feat: add Standalone section to SystemSettings`

---

## Step 32 — Re-scan Series + NFO Export Button

**Goal:** Wire existing "Re-scan Series" button in `SeriesHero`, implement the backend route, and add an "NFO Export" button.

### Backend — `backend/routes/standalone.py`

Add a new route **after the existing `refresh_series_metadata` route**:

```python
@bp.route("/series/<int:series_id>/scan", methods=["POST"])
def scan_series(series_id):
    """Trigger a re-scan of a single standalone series.
    ---
    tags: [standalone]
    parameters:
      - in: path
        name: series_id
        required: true
        schema: { type: integer }
    responses:
      200: { description: "Scan started" }
      404: { description: "Series not found" }
      500: { description: "Scan failed" }
    """
    from ..db.repositories.standalone_repo import StandaloneRepository
    repo = StandaloneRepository(db.session)
    series = repo.get_series(series_id)
    if not series:
        return jsonify({"error": "Series not found"}), 404
    try:
        manager = current_app.extensions.get("standalone_manager")
        if manager:
            manager.scan_series(series_id)
        else:
            # Fallback: re-trigger wanted refresh for this series
            from ..services.wanted_service import WantedService
            WantedService(db.session).refresh_for_series(series_id)
        return jsonify({"message": "Scan started", "series_id": series_id})
    except Exception as e:
        logger.error("Failed to scan series %d: %s", series_id, e)
        return jsonify({"error": str(e)}), 500
```

Check what `StandaloneManager` exposes. If `scan_series` method does not exist on the manager, fall back to calling `refresh_wanted` logic. Use `current_app.extensions.get("standalone_manager")` pattern already used elsewhere in `standalone.py`. If that pattern differs (check top of file), mirror exactly.

The route is on the `standalone` blueprint which is registered at `/api/v1/standalone`. So the full path is `POST /api/v1/standalone/series/{id}/scan`.

### Frontend — `api/client.ts`

Add:
```ts
export async function rescanSeries(seriesId: number): Promise<{ message: string; series_id: number }> {
  const { data } = await api.post(`/standalone/series/${seriesId}/scan`)
  return data
}
```

### Frontend — `hooks/useLibraryApi.ts`

Add hook:
```ts
export function useRescanSeries() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (seriesId: number) => rescanSeries(seriesId),
    onSuccess: (_data, seriesId) => {
      void qc.invalidateQueries({ queryKey: ['series', seriesId] })
      void qc.invalidateQueries({ queryKey: ['library'] })
    },
  })
}
```

### Frontend — `SeriesDetail.tsx`

The existing `onRescan` prop is passed to `SeriesHero`. Find where `onRescan` is defined (currently shows a "coming soon" toast — search for `toast.*coming soon` or `onRescan`).

Replace the stub with:
```tsx
const rescanSeries = useRescanSeries()
const [isRescanning, setIsRescanning] = useState(false)

const handleRescan = () => {
  if (!seriesId) return
  setIsRescanning(true)
  rescanSeries.mutate(seriesId, {
    onSuccess: () => {
      toast('Re-scan started', 'success')
      setIsRescanning(false)
    },
    onError: () => {
      toast('Re-scan failed', 'error')
      setIsRescanning(false)
    },
  })
}
```

Pass `isRescanning` into `SeriesHero` as `isRescanning` prop (add to `SeriesHeroProps`).

### Frontend — `SeriesHero.tsx`

1. Add `isRescanning: boolean` to `SeriesHeroProps`.
2. Show `<Loader2 size={13} className="animate-spin" />` instead of `<RefreshCw size={13} />` when `isRescanning` is true. Disable button while rescanning.
3. Add NFO Export button:

```tsx
<button
  onClick={onNfoExport}
  style={{
    display: 'inline-flex',
    alignItems: 'center',
    gap: '6px',
    padding: '7px 14px',
    borderRadius: '6px',
    fontSize: '13px',
    fontWeight: 500,
    backgroundColor: 'var(--bg-elevated)',
    color: 'var(--text-secondary)',
    border: '1px solid var(--border)',
    cursor: 'pointer',
  }}
>
  <FileText size={13} />
  NFO Export
</button>
```

Add `onNfoExport: () => void` to `SeriesHeroProps`.

### Frontend — `SeriesDetail.tsx` — NFO Export handler

Check `api/client.ts` for the existing NFO export API function (search `export-nfo` — `getSeriesSubtitleExportUrl` exists; there may also be a POST endpoint). The NFO export route is `POST /api/v1/subtitles/export-nfo`. Check `client.ts` for an existing function; if found, use it. If not:

```ts
export async function exportSeriesNfo(seriesId: number): Promise<Blob> {
  const { data } = await api.post('/subtitles/export-nfo', { series_id: seriesId }, { responseType: 'blob' })
  return data
}
```

Handler in `SeriesDetail.tsx`:
```tsx
const handleNfoExport = async () => {
  if (!seriesId) return
  try {
    const blob = await exportSeriesNfo(seriesId)
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `series-${seriesId}-nfo.zip`
    a.click()
    URL.revokeObjectURL(url)
    toast('NFO exported', 'success')
  } catch {
    toast('NFO export failed', 'error')
  }
}
```

Pass `onNfoExport={handleNfoExport}` to `<SeriesHero>`.

**Backend tests:**
Add `backend/tests/test_standalone_scan.py`:
```python
def test_scan_series_not_found(client):
    resp = client.post('/api/v1/standalone/series/99999/scan')
    assert resp.status_code == 404

def test_scan_series_ok(client, mocker):
    mocker.patch('..routes.standalone.StandaloneRepository.get_series', return_value=MockSeries())
    mocker.patch('flask.current_app.extensions.get', return_value=None)
    # ... assert 200
```

**Frontend tests:**
- `SeriesHero.test.tsx` (create if missing): assert NFO Export button renders, Re-scan shows spinner when `isRescanning=true`.

**Verification:**
```bash
cd backend && python -m pytest backend/tests/test_standalone_scan.py -v
cd frontend && npm run test -- --run
```

**Commit:** `feat: wire re-scan and NFO export buttons, implement scan backend route`

---

## Step 33 — Glossary CRUD (Global Glossary in TranslationSettings)

**Goal:** The `GlobalGlossaryPanel` in `TranslationSettings.tsx` (rendered via lazy import from `TranslationTab.tsx`) already has Add/Edit/Delete functionality fully wired (see `TranslationTab.tsx:1228+`). The series-level `GlossaryPanel` (`components/series/GlossaryPanel.tsx`) also already has full CRUD.

**Audit result:** Both panels already implement:
- Add entry (showAdd state → inline form → `useCreateGlossaryEntry`)
- Edit per row (`startEdit` → form pre-filled → `useUpdateGlossaryEntry`)
- Delete per row (confirm → `useDeleteGlossaryEntry`)
- Export TSV (`useExportGlossaryTsv`)

**What is missing:** The `GlobalGlossaryPanel` in `TranslationTab.tsx` (line 1228) — check if it has Edit and Delete buttons per row. Read lines 1280–1450 to verify.

**Action:** Read `TranslationTab.tsx` from line 1280 to 1500. If Edit/Delete/Export are already fully implemented, this step is complete (just verify). If missing, add them following the pattern from `GlossaryPanel.tsx` exactly.

**Specifically to check:**
1. Does `GlobalGlossaryPanel` have Edit button per row? (Look for `startEdit` or `Edit2` icon in its entry rows)
2. Does `GlobalGlossaryPanel` have Delete button per row? (Look for `Trash2`)
3. Does `GlobalGlossaryPanel` have Export button? (Look for `Download` or `exportTsv`)

**If missing any of the three, add them.** The hooks are already imported at the top of `TranslationTab.tsx`:
```ts
useCreateGlossaryEntry, useUpdateGlossaryEntry, useDeleteGlossaryEntry
```

The export hook `useExportGlossaryTsv` — check if imported. If not, add the import.

**Files to modify (only if gaps found):**
- `frontend/src/pages/Settings/TranslationTab.tsx` — add missing CRUD operations to `GlobalGlossaryPanel`
- `frontend/src/pages/Settings/__tests__/TranslationSettings.test.tsx` — add assertions for new buttons

**Tests:** Assert that the Add button, Edit buttons per row, Delete buttons per row, and Export button are present in `GlobalGlossaryPanel` render.

**Commit:** `feat: add CRUD and export to GlossaryPanel`

---

## Step 34 — Backup Management UI

**Goal:** Add a "Create backup now" button, a backup list table with download/restore per-row actions to the Backup & Restore section in SystemSettings.

**What already exists:**
- `useFullBackups()`, `useCreateFullBackup()`, `useRestoreFullBackup()` in `useSystemApi.ts`
- `downloadFullBackupUrl` in `api/client.ts`
- `BackupTab` exported from `AdvancedTab.tsx`

The backup management UI may already exist in `BackupTab` (check `AdvancedTab.tsx` around lines 580–800). Read that section to determine what is and is not yet present.

**Read:** `frontend/src/pages/Settings/AdvancedTab.tsx` offset 580, limit 120.

**If backup list/create/restore are already present:** Step is complete — verify tests pass.

**If missing:** Add to `BackupTab` inside `AdvancedTab.tsx`.

**UI to add inside `BackupTab`:**

```tsx
// "Create Backup" action bar
<div className="flex items-center justify-between pt-4" style={{ borderTop: '1px solid var(--border)' }}>
  <div>
    <h3 className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>Backups</h3>
    <p className="text-xs mt-0.5" style={{ color: 'var(--text-muted)' }}>Full application backups including database and config.</p>
  </div>
  <button
    onClick={handleCreateBackup}
    disabled={createBackup.isPending}
    style={{ /* accent button style */ }}
  >
    {createBackup.isPending ? <Loader2 size={13} className="animate-spin" /> : <Archive size={13} />}
    Create Backup Now
  </button>
</div>

// Backup list table
{backups && backups.length > 0 && (
  <table className="w-full text-xs" style={{ borderCollapse: 'collapse' }}>
    <thead>
      <tr style={{ borderBottom: '1px solid var(--border)' }}>
        <th className="text-left py-1.5 px-2" style={{ color: 'var(--text-muted)' }}>Filename</th>
        <th className="text-left py-1.5 px-2" style={{ color: 'var(--text-muted)' }}>Size</th>
        <th className="text-left py-1.5 px-2" style={{ color: 'var(--text-muted)' }}>Created</th>
        <th className="py-1.5 px-2" />
      </tr>
    </thead>
    <tbody>
      {backups.map((b: FullBackupInfo) => (
        <tr key={b.filename} style={{ borderBottom: '1px solid var(--border)' }}>
          <td className="py-1.5 px-2 font-mono" style={{ color: 'var(--text-primary)' }}>{b.filename}</td>
          <td className="py-1.5 px-2" style={{ color: 'var(--text-secondary)' }}>{b.size_human}</td>
          <td className="py-1.5 px-2" style={{ color: 'var(--text-secondary)' }}>{new Date(b.created_at).toLocaleString()}</td>
          <td className="py-1.5 px-2">
            <div className="flex items-center gap-1 justify-end">
              <a
                href={downloadFullBackupUrl(b.filename)}
                download
                className="p-1.5 rounded"
                style={{ border: '1px solid var(--border)', color: 'var(--text-secondary)' }}
                title="Download"
              >
                <Download size={11} />
              </a>
              <button
                onClick={() => handleRestore(b.filename)}
                disabled={restoreBackup.isPending}
                className="p-1.5 rounded"
                style={{ border: '1px solid var(--border)', color: 'var(--warning)' }}
                title="Restore"
              >
                <RotateCcw size={11} />
              </button>
            </div>
          </td>
        </tr>
      ))}
    </tbody>
  </table>
)}
```

Restore: show `window.confirm('Restore this backup? This will overwrite current data.')` before calling `restoreBackup.mutate(filename, { onSuccess: () => toast('Restore complete — restart may be required', 'success'), onError: () => toast('Restore failed', 'error') })`.

**Hooks used:**
```tsx
const { data: backupsData } = useFullBackups()
const createBackup = useCreateFullBackup()
const restoreBackup = useRestoreFullBackup()
const backups = backupsData?.backups ?? []
```

**Tests:** Unit test for `BackupTab` (or `AdvancedTab` tests if they exist): mock `useFullBackups`, `useCreateFullBackup`, `useRestoreFullBackup`. Assert "Create Backup Now" button renders, backup list renders with download link and restore button per row.

**Commit:** `feat: add backup management UI to SystemSettings`

---

## Step 35 — Language Profiles Page

**Goal:** Dedicated `/settings/language-profiles` page for CRUD management of language profiles.

**What already exists:**
- `LanguageProfilesTab` is exported from `AdvancedTab.tsx` — full CRUD implementation already present (lines 21–230+). This is the authoritative implementation; do NOT duplicate it.
- Hooks: `useLanguageProfiles`, `useCreateProfile`, `useUpdateProfile`, `useDeleteProfile` in `useSystemApi.ts`.

**Action:**

Create `frontend/src/pages/LanguageProfiles.tsx`:

```tsx
/**
 * LanguageProfiles — Standalone page for Language Profile management.
 * Wraps the existing LanguageProfilesTab in a SettingsDetailLayout.
 */
import { Suspense, lazy } from 'react'
import { SettingsDetailLayout } from '@/components/settings/SettingsDetailLayout'
import { FormSkeleton } from '@/components/shared/PageSkeleton'

const LanguageProfilesTab = lazy(() =>
  import('./Settings/AdvancedTab').then((m) => ({ default: m.LanguageProfilesTab })),
)

export function LanguageProfilesPage() {
  return (
    <SettingsDetailLayout
      title="Language Profiles"
      subtitle="Configure language profiles for subtitle search and translation."
    >
      <Suspense fallback={<FormSkeleton />}>
        <LanguageProfilesTab />
      </Suspense>
    </SettingsDetailLayout>
  )
}
```

**App.tsx — add route:**

Add lazy import:
```tsx
const LanguageProfilesPage = lazy(() =>
  import('@/pages/LanguageProfiles').then((m) => ({ default: m.LanguageProfilesPage })),
)
```

Add route inside `<AuthGuard>` routes, under settings routes:
```tsx
<Route
  path="/settings/language-profiles"
  element={
    <ErrorBoundary>
      <Suspense fallback={<FormSkeleton />}>
        <LanguageProfilesPage />
      </Suspense>
    </ErrorBoundary>
  }
/>
```

**SettingsOverview.tsx — optional:** If there is a settings navigation list, consider adding a link to `/settings/language-profiles`. Check `SettingsOverview.tsx` for the nav items list pattern. Do NOT touch any protected area — only add a new nav entry if the pattern is a simple array push.

**Tests:**
- `frontend/src/pages/__tests__/LanguageProfiles.test.tsx` (new): renders `SettingsDetailLayout` with correct title, renders `LanguageProfilesTab` (mocked).
- Assert the route renders by checking it renders via `MemoryRouter` with path `/settings/language-profiles`.

**Verification:**
```bash
cd frontend && npm run lint && npm run test -- --run
```

**Commit:** `feat: add Language Profiles management page`

---

## Step 36 — MovieDetailPage

**Goal:** New `/movies/{id}` page analogous to `SeriesDetail.tsx` but for movies (no seasons, subtitles listed directly).

**What already exists:**
- `backend/routes/standalone.py` has `GET /standalone/movies`, `GET /standalone/movies/{id}/poster`, `DELETE /standalone/movies/{id}`
- `api/client.ts` — check for existing movie API functions. Search for `movie` in client.ts.
- Library page likely shows movies — check how they are navigated to.

**Read first:** `frontend/src/api/client.ts` around movie functions (search `movie` in client.ts using grep before implementing).

**Files to create:**
- `frontend/src/pages/MovieDetail.tsx`
- `frontend/src/hooks/useLibraryApi.ts` — add `useMovieDetail` hook if not present
- `frontend/src/api/client.ts` — add `getMovieDetail` if not present
- `frontend/src/App.tsx` — add route `/movies/:id`

**MovieDetail.tsx structure:**

```tsx
/**
 * MovieDetailPage — Detail view for a standalone movie.
 * Shows poster, metadata, and subtitle list. No season/episode hierarchy.
 */
import { useParams, useNavigate } from 'react-router-dom'
import { useMovieDetail } from '@/hooks/useApi'
import { Breadcrumb } from '@/components/shared/Breadcrumb'
import { Loader2, FileVideo } from 'lucide-react'

export function MovieDetailPage() {
  const { id } = useParams<{ id: string }>()
  const movieId = id && !isNaN(Number(id)) ? Number(id) : null
  const { data: movie, isLoading, error } = useMovieDetail(movieId)
  const navigate = useNavigate()

  if (isLoading) { /* spinner */ }
  if (error || !movie) { /* error state with back button */ }

  return (
    <div>
      <Breadcrumb items={[
        { label: 'Library', to: '/library' },
        { label: movie.title },
      ]} />
      {/* Hero — same visual pattern as SeriesHero but no season stats */}
      <MovieHero movie={movie} />
      {/* Subtitle list — flat list, no season grouping */}
      <SubtitleList movieId={movieId} />
    </div>
  )
}
```

**MovieHero** (inline component in `MovieDetail.tsx`): follow `SeriesHero.tsx` visual pattern exactly (fanart background, poster, title/year, stat boxes, action buttons). Stat boxes for movies: "Subtitles" count, "Missing" count. Buttons: "Search Missing", "Re-scan".

**SubtitleList** (inline component): flat table of subtitles from `GET /api/v1/standalone/movies/{id}` response (or a dedicated subtitles endpoint). Check the movie detail response shape. If it includes a `subtitle_files` or `subtitles` array, render them. If not, use `listSeriesSubtitles` analog for movies (check if `listMovieSubtitles` or similar exists in `client.ts`).

**Backend data shape:** The `GET /standalone/movies/{id}` route returns the movie object — check `standalone.py` for the route handler to understand the response shape. Read `standalone.py` starting at line 453 (the movies section).

**API/hook additions in `client.ts`:**
```ts
export async function getMovieDetail(movieId: number): Promise<MovieDetail> {
  const { data } = await api.get(`/standalone/movies/${movieId}`)
  return data
}
```

**Hook in `useLibraryApi.ts`:**
```ts
export function useMovieDetail(movieId: number | null) {
  return useQuery({
    queryKey: ['movie', movieId],
    queryFn: () => movieId != null ? getMovieDetail(movieId) : Promise.resolve(null),
    enabled: movieId != null,
  })
}
```

**Type in `lib/types.ts`:** Add `MovieDetail` type mirroring the backend response. Check if it already exists — search `MovieDetail` in `lib/types.ts`.

**App.tsx route:**
```tsx
const MovieDetailPage = lazy(() =>
  import('@/pages/MovieDetail').then((m) => ({ default: m.MovieDetailPage })),
)

// In routes:
<Route
  path="/movies/:id"
  element={<Suspense fallback={<PageSkeleton />}><MovieDetailPage /></Suspense>}
/>
```

**Tests:**
- `frontend/src/pages/__tests__/MovieDetail.test.tsx` (new):
  - Loading state renders spinner
  - Error state renders error message
  - Loaded state renders movie title, poster placeholder, subtitle list
  - Uses mocked `useMovieDetail`

**Verification:**
```bash
cd frontend && npm run lint && npx tsc --noEmit && npm run test -- --run
```

**Commit:** `feat: add MovieDetailPage`

---

## Pre-PR Verification Checklist

Run in this order after all 9 commits:

```bash
# 1. Backend lint + tests
cd D:/Sublarr_Projekt/Sublarr/backend
ruff check . && ruff format --check .
python -m pytest --tb=short -q \
  --ignore=tests/performance \
  --ignore=tests/integration/test_provider_pipeline.py \
  --ignore=tests/test_video_sync.py \
  --ignore=tests/test_translation_backends.py \
  -k "not (test_sonarr_download_webhook or test_radarr_download_webhook or test_parse_llm_response_too_many_merge or test_record_backend_success)"

# 2. Frontend lint + types + tests
cd D:/Sublarr_Projekt/Sublarr/frontend
npm run lint && npx tsc --noEmit && npm run test -- --run
```

All must pass before PR creation.

---

## Commit Sequence (exact messages)

1. `feat: add backup retention fields to SystemSettings`
2. `feat: add AniDB section to SystemSettings`
3. `feat: add Remux section to SystemSettings`
4. `feat: add Standalone section to SystemSettings`
5. `feat: wire re-scan and NFO export buttons, implement scan backend route`
6. `feat: add CRUD and export to GlossaryPanel`
7. `feat: add backup management UI to SystemSettings`
8. `feat: add Language Profiles management page`
9. `feat: add MovieDetailPage`

---

## Key Cross-References

| What | Where |
|------|-------|
| Config read/write hooks | `frontend/src/hooks/useSystemApi.ts` (useConfig, useUpdateConfig) |
| Backup hooks | `frontend/src/hooks/useSystemApi.ts` (useFullBackups, useCreateFullBackup, useRestoreFullBackup) |
| Library hooks | `frontend/src/hooks/useLibraryApi.ts` |
| All hooks barrel | `frontend/src/hooks/useApi.ts` |
| API client | `frontend/src/api/client.ts` |
| SettingsSection pattern | `frontend/src/components/settings/SettingsSection.tsx` (DO NOT MODIFY) |
| SeriesHero props | `frontend/src/components/series/SeriesHero.tsx` |
| SeriesDetail wiring | `frontend/src/pages/SeriesDetail.tsx` |
| GlobalGlossaryPanel | `frontend/src/pages/Settings/TranslationTab.tsx` (line 1228) |
| LanguageProfilesTab | `frontend/src/pages/Settings/AdvancedTab.tsx` (line 21) |
| BackupTab | `frontend/src/pages/Settings/AdvancedTab.tsx` (exported) |
| Standalone routes | `backend/routes/standalone.py` |
| SystemSettings test | `frontend/src/pages/Settings/__tests__/SystemSettings.test.tsx` |
| Protected areas | `docs/PROTECTED.md` |
