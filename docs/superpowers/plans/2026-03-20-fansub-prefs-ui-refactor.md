# Fansub Preferences UI Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move global release-group fields from the Wanted tab to the Scoring tab in Settings, and replace the prominent `SeriesFansubPrefsPanel` card in SeriesDetail with a compact toolbar button that opens a modal dialog.

**Architecture:** Two independent frontend-only changes. No backend, no migrations, no API changes. Task 1 removes the hardcoded card from the Wanted tab and adds it manually to `ScoringTab` in `EventsTab.tsx` (the Scoring tab does NOT use SETTING_DEFS — it renders a fully custom component). Task 2 replaces the full-card panel with a button+modal following the `SeriesProcessingOverride` pattern already present on the same page.

**Tech Stack:** React 19, TypeScript, React Query, CSS variables (design tokens), Vite

---

## File Map

| Action | File | What changes |
|--------|------|--------------|
| Modify | `frontend/src/pages/Settings/index.tsx` | Remove hardcoded release_group card from Wanted tab; remove 3 fields from SETTING_DEFS |
| Modify | `frontend/src/pages/Settings/EventsTab.tsx` | Add release_group card manually inside `ScoringTab` |
| Create | `frontend/src/components/series/FansubOverrideModal.tsx` | New modal: form + save/reset |
| Modify | `frontend/src/pages/SeriesDetail.tsx` | Add Fansub toolbar button + modal; remove panel block + import |
| Delete | `frontend/src/components/series/SeriesFansubPrefsPanel.tsx` | Removed — logic migrated into modal |

---

## Task 1: Move Release Group Fields to Scoring Tab

**Goal:** The 3 global release-group settings (`release_group_prefer`, `release_group_exclude`, `release_group_prefer_bonus`) belong conceptually with scoring parameters, not with automation settings in the Wanted tab.

**Important:** The Scoring tab renders via `<ScoringTab />` (a fully custom component from `EventsTab.tsx`) — it does NOT consume SETTING_DEFS fields. The Wanted tab also hardcodes its own card blocks and does not use `tabFields`. Therefore the only correct approach is:
1. Remove the hardcoded card from the Wanted tab's render block in `Settings/index.tsx`
2. Remove the 3 fields from SETTING_DEFS (they are now dead)
3. Add the card manually inside `ScoringTab` in `EventsTab.tsx`

**Files:**
- Modify: `frontend/src/pages/Settings/index.tsx`
- Modify: `frontend/src/pages/Settings/EventsTab.tsx`

### Steps

- [ ] **Step 1.1: Remove the Release Group card from the Wanted tab render block**

  In `frontend/src/pages/Settings/index.tsx`, find the Wanted tab's hardcoded render block (around lines 1241–1245). It will look like a `<SettingsCard>` or similar component rendering the 3 `release_group_*` fields. Delete the entire card block.

  ```bash
  grep -n "release_group" frontend/src/pages/Settings/index.tsx
  ```

  Delete the card element that contains all three `release_group_prefer`, `release_group_exclude`, `release_group_prefer_bonus` field renders.

- [ ] **Step 1.2: Remove the 3 field definitions from SETTING_DEFS**

  In the same file, find and delete the 3 objects in SETTING_DEFS:
  ```typescript
  { key: 'release_group_prefer', ..., tab: 'Wanted', ... },
  { key: 'release_group_exclude', ..., tab: 'Wanted', ... },
  { key: 'release_group_prefer_bonus', ..., tab: 'Wanted', ..., advanced: true },
  ```

- [ ] **Step 1.3: Add the card to ScoringTab in EventsTab.tsx**

  In `frontend/src/pages/Settings/EventsTab.tsx`, inside the `ScoringTab` function, add a new card section **before** the scoring weights tables. Match the exact JSX pattern (component names, className, styling) already used by the other cards in `ScoringTab`.

  ```bash
  grep -n "SettingsCard\|settings-card\|CardTitle\|className" frontend/src/pages/Settings/EventsTab.tsx | head -20
  ```

  Use whatever card/field components are already used in `ScoringTab`. The three fields to add:
  - **Preferred Release Groups** — `release_group_prefer`, type text, placeholder `SubsPlease,Erai-raws`, description: `Komma-getrennte Release-Gruppen die bevorzugt werden (Score-Bonus). Leer = deaktiviert.`
  - **Blocked Release Groups** — `release_group_exclude`, type text, placeholder `HorribleSubs,CoalGirls`, description: `Komma-getrennte Release-Gruppen die aus Suchergebnissen ausgeschlossen werden.`
  - **Prefer Bonus (score pts)** — `release_group_prefer_bonus`, type number, placeholder `20`, description: `Score-Bonus für Ergebnisse die einer bevorzugten Gruppe entsprechen.`

- [ ] **Step 1.4: Verify in dev server**

  Start dev server (`npm run dev`). Navigate to Settings → Wanted tab — the "Release Group Filter" card must be gone. Navigate to Scoring tab — the 3 fields must appear there.

- [ ] **Step 1.5: Run frontend checks**

  ```bash
  cd frontend && npm run lint && npx tsc --noEmit
  ```
  Expected: no errors.

- [ ] **Step 1.6: Commit**

  ```bash
  git add frontend/src/pages/Settings/index.tsx frontend/src/pages/Settings/EventsTab.tsx
  git commit -m "refactor: move release group fields from Wanted tab to Scoring tab"
  ```

---

## Task 2: Replace SeriesFansubPrefsPanel with Toolbar Button + Modal

**Goal:** The full-card panel on every series detail page is too prominent. Replace with a compact "Fansub" button in the existing actions toolbar. The button shows an active visual indicator when per-series rules are configured. Clicking opens a modal dialog.

**Pattern reference:** `frontend/src/components/series/SeriesProcessingOverride.tsx`

**Files:**
- Create: `frontend/src/components/series/FansubOverrideModal.tsx`
- Modify: `frontend/src/pages/SeriesDetail.tsx`
- Delete: `frontend/src/components/series/SeriesFansubPrefsPanel.tsx`

### Steps

- [ ] **Step 2.1: Create `FansubOverrideModal.tsx`**

  Create `frontend/src/components/series/FansubOverrideModal.tsx`:

  ```tsx
  import { useEffect, useState } from 'react'
  import {
    useSeriesFansubPrefs,
    useSetSeriesFansubPrefs,
    useDeleteSeriesFansubPrefs,
  } from '../../hooks/useApi'

  interface Props {
    seriesId: number
    open: boolean
    onClose: () => void
  }

  export function FansubOverrideModal({ seriesId, open, onClose }: Props) {
    const { data: prefs, isLoading } = useSeriesFansubPrefs(seriesId)
    const setPrefs = useSetSeriesFansubPrefs(seriesId)
    const deletePrefs = useDeleteSeriesFansubPrefs(seriesId)

    const [preferred, setPreferred] = useState('')
    const [excluded, setExcluded] = useState('')
    const [bonus, setBonus] = useState(20)

    // Sync local state from prefs whenever the modal opens or prefs change.
    // `open` is included so re-opening with already-cached prefs still resets fields.
    useEffect(() => {
      if (prefs) {
        setPreferred(prefs.preferred_groups.join(', '))
        setExcluded(prefs.excluded_groups.join(', '))
        setBonus(prefs.bonus)
      }
    }, [prefs, open])

    if (!open) return null

    const parseGroups = (s: string) =>
      s.split(',').map((g) => g.trim()).filter(Boolean)

    const handleSave = () => {
      setPrefs.mutate(
        { preferred_groups: parseGroups(preferred), excluded_groups: parseGroups(excluded), bonus },
        { onSuccess: onClose },
      )
    }

    const handleReset = () => {
      deletePrefs.mutate(undefined, { onSuccess: onClose })
    }

    const hasOverride =
      (prefs?.preferred_groups.length ?? 0) > 0 ||
      (prefs?.excluded_groups.length ?? 0) > 0

    return (
      <>
        {/* Backdrop */}
        <div
          onClick={onClose}
          style={{
            position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)', zIndex: 1000,
          }}
        />
        {/* Dialog */}
        <div
          role="dialog"
          aria-modal="true"
          aria-label="Fansub Preferences"
          style={{
            position: 'fixed', top: '50%', left: '50%',
            transform: 'translate(-50%, -50%)',
            background: 'var(--bg-card)', border: '1px solid var(--border)',
            borderRadius: 8, padding: 20, zIndex: 1001, width: 400, maxWidth: '90vw',
          }}
          onKeyDown={(e) => e.key === 'Escape' && onClose()}
        >
          <h3 style={{ margin: '0 0 16px', fontSize: 14, fontWeight: 600 }}>
            Fansub Preferences
          </h3>

          {isLoading ? (
            <p style={{ color: 'var(--text-muted)', fontSize: 12 }}>Loading…</p>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              <label style={{ fontSize: 12 }}>
                <span style={{ color: 'var(--text-muted)', display: 'block', marginBottom: 4 }}>
                  Preferred Groups (comma-separated)
                </span>
                <input
                  type="text"
                  value={preferred}
                  onChange={(e) => setPreferred(e.target.value)}
                  placeholder="SubsPlease, Erai-raws"
                  style={{
                    width: '100%', boxSizing: 'border-box',
                    background: 'var(--bg-input)', border: '1px solid var(--border)',
                    borderRadius: 4, padding: '6px 8px', color: 'var(--text)', fontSize: 12,
                  }}
                />
              </label>

              <label style={{ fontSize: 12 }}>
                <span style={{ color: 'var(--text-muted)', display: 'block', marginBottom: 4 }}>
                  Excluded Groups (comma-separated)
                </span>
                <input
                  type="text"
                  value={excluded}
                  onChange={(e) => setExcluded(e.target.value)}
                  placeholder="HorribleSubs, CoalGirls"
                  style={{
                    width: '100%', boxSizing: 'border-box',
                    background: 'var(--bg-input)', border: '1px solid var(--border)',
                    borderRadius: 4, padding: '6px 8px', color: 'var(--text)', fontSize: 12,
                  }}
                />
              </label>

              <label style={{ fontSize: 12 }}>
                <span style={{ color: 'var(--text-muted)', display: 'block', marginBottom: 4 }}>
                  Bonus Points (score)
                </span>
                <input
                  type="number"
                  value={bonus}
                  min={0}
                  max={999}
                  onChange={(e) => setBonus(parseInt(e.target.value, 10) || 0)}
                  style={{
                    width: 80,
                    background: 'var(--bg-input)', border: '1px solid var(--border)',
                    borderRadius: 4, padding: '6px 8px', color: 'var(--text)', fontSize: 12,
                  }}
                />
              </label>

              <div style={{ display: 'flex', gap: 8, marginTop: 4 }}>
                <button
                  onClick={handleSave}
                  disabled={setPrefs.isPending}
                  style={{
                    background: 'var(--accent)', color: '#fff',
                    border: 'none', borderRadius: 4, padding: '6px 14px',
                    fontSize: 12, cursor: 'pointer', fontWeight: 600,
                  }}
                >
                  {setPrefs.isPending ? 'Saving…' : 'Save'}
                </button>
                {hasOverride && (
                  <button
                    onClick={handleReset}
                    disabled={deletePrefs.isPending}
                    style={{
                      background: 'transparent', color: 'var(--text-muted)',
                      border: '1px solid var(--border)', borderRadius: 4,
                      padding: '6px 14px', fontSize: 12, cursor: 'pointer',
                    }}
                  >
                    {deletePrefs.isPending ? '…' : 'Reset to Global'}
                  </button>
                )}
                <button
                  onClick={onClose}
                  style={{
                    marginLeft: 'auto', background: 'transparent',
                    color: 'var(--text-muted)', border: 'none',
                    fontSize: 12, cursor: 'pointer',
                  }}
                >
                  Cancel
                </button>
              </div>
            </div>
          )}
        </div>
      </>
    )
  }
  ```

- [ ] **Step 2.2: Add button + modal to SeriesDetail**

  In `frontend/src/pages/SeriesDetail.tsx`:

  **a) Add imports at the top:**
  ```tsx
  import { FansubOverrideModal } from '@/components/series/FansubOverrideModal'
  import { useSeriesFansubPrefs } from '@/hooks/useApi'
  ```

  **b) Add state + derived value near other state declarations in the component:**
  ```tsx
  const [fansubOpen, setFansubOpen] = useState(false)
  ```

  **c) Add the query — but only call it when `seriesId` is not null. Find the pattern used for other series-scoped queries in this component (they use `enabled: seriesId != null`). Add:**
  ```tsx
  const { data: fansubPrefs } = useSeriesFansubPrefs(seriesId ?? -1)
  // Note: the query should only fire when seriesId is known.
  // useSeriesFansubPrefs wraps useQuery — check if it supports an `enabled` option,
  // or pass seriesId ?? -1 and accept that a request for id=-1 will 404 harmlessly.
  // If the hook does not support enabled, guard the derived value instead:
  const hasFansubOverride = seriesId !== null && (
    (fansubPrefs?.preferred_groups.length ?? 0) > 0 ||
    (fansubPrefs?.excluded_groups.length ?? 0) > 0
  )
  ```

  **d) In the toolbar (near the "Bereinigen" button, around line 1793), add the Fansub button:**
  ```tsx
  {seriesId !== null && (
    <button
      onClick={() => setFansubOpen(true)}
      title="Fansub Preferences"
      style={{
        background: 'transparent',
        border: `1px solid ${hasFansubOverride ? 'var(--accent)' : 'var(--border)'}`,
        color: hasFansubOverride ? 'var(--accent)' : 'var(--text-muted)',
        borderRadius: 4, padding: '4px 10px', fontSize: 12, cursor: 'pointer',
        fontWeight: hasFansubOverride ? 600 : 400,
      }}
    >
      Fansub
    </button>
  )}
  ```

  **e) Add modal at the bottom of the JSX (before closing fragment):**
  ```tsx
  {seriesId !== null && (
    <FansubOverrideModal
      seriesId={seriesId}
      open={fansubOpen}
      onClose={() => setFansubOpen(false)}
    />
  )}
  ```

- [ ] **Step 2.3: Remove the old panel from SeriesDetail**

  Delete two things in `frontend/src/pages/SeriesDetail.tsx`:

  **1. The import line (around line 30):**
  ```tsx
  import { SeriesFansubPrefsPanel } from '@/components/series/SeriesFansubPrefsPanel'
  ```

  **2. The JSX block (around lines 1868–1879):**
  ```tsx
  {/* Fansub Preferences Panel */}
  {seriesId !== null && (
    <div
      className="rounded-lg overflow-hidden"
      style={{ border: '1px solid var(--border)', padding: '16px' }}
    >
      <h3 style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-muted)', marginBottom: 8, marginTop: 0 }}>
        Fansub Preferences
      </h3>
      <SeriesFansubPrefsPanel seriesId={seriesId} />
    </div>
  )}
  ```

- [ ] **Step 2.4: Delete the old panel file**

  ```bash
  git rm frontend/src/components/series/SeriesFansubPrefsPanel.tsx
  ```

- [ ] **Step 2.5: Run frontend checks**

  ```bash
  cd frontend && npm run lint && npx tsc --noEmit
  ```
  Expected: no errors. The removed import must not appear in tsc output. Fix any remaining references before continuing.

- [ ] **Step 2.6: Manual smoke-test**

  Start dev server (`npm run dev`). Open a series detail page.
  - Confirm the "Fansub Preferences" card is gone from the page body.
  - Confirm a "Fansub" button appears in the toolbar.
  - Button is grey/inactive when no prefs are set.
  - Click → modal opens.
  - Set a preferred group → Save → modal closes → button turns accent-colored.
  - Re-open → values are still set (not blank).
  - Click "Reset to Global" → button returns to grey.
  - Press Escape or click backdrop → modal closes without saving.

- [ ] **Step 2.7: Commit**

  ```bash
  git add frontend/src/components/series/FansubOverrideModal.tsx
  git add frontend/src/pages/SeriesDetail.tsx
  git rm frontend/src/components/series/SeriesFansubPrefsPanel.tsx
  git commit -m "refactor: replace SeriesFansubPrefsPanel with toolbar button + modal"
  ```

---

## Final Checks

- [ ] **Run full frontend pre-PR check**

  ```bash
  cd frontend && npm run lint && npx tsc --noEmit && npm run test -- --run
  ```
  Expected: all pass.

- [ ] **Push branch and open PR — do NOT merge without green CI**

  ```bash
  git push origin <branch>
  gh pr create --title "refactor: fansub prefs UI — scoring tab + toolbar modal" --base master
  # Then check CI:
  gh pr checks <pr-number>
  # Wait for all checks to be green before merging.
  ```

---

## What is NOT in scope

- Backend changes (no migration, no new routes)
- Standalone series support (tracked separately in design spec)
- Automatic pipeline gap (`process_wanted_item` not applying Layer 2 rules)
- Any changes to scoring logic or provider integration
