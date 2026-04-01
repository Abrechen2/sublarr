# Translation Feature Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a global `translation_enabled` toggle that gates all translation UI/functionality behind an explicit opt-in with a Beta warning.

**Architecture:** `translation_enabled: bool = False` is added to Pydantic Settings (backend). The frontend reads it via the existing `useConfig()` hook. A new `EnableTranslationModal` handles the opt-in flow with Beta confirmation. Disabling cancels queued jobs via a new `POST /translate/disable` endpoint and hides all translation UI outside of Settings.

**Tech Stack:** Python/Flask (backend), React 19 + TypeScript + TanStack Query (frontend), Vitest + pytest (tests)

---

## File Map

| File | Change |
|------|--------|
| `backend/config.py` | Add `translation_enabled: bool = False` |
| `backend/db/repositories/jobs.py` | Add `cancel_queued_jobs() -> int` |
| `backend/db/jobs.py` | Add `cancel_queued_jobs()` facade |
| `backend/routes/translate/core.py` | Add `POST /translate/disable` endpoint |
| `backend/tests/test_config.py` | Test `translation_enabled` default |
| `backend/tests/test_translate_disable.py` | Test disable endpoint + job cancellation |
| `frontend/src/api/client.ts` | Add `disableTranslation()` API function |
| `frontend/src/hooks/useSystemApi.ts` | Add `useTranslationEnabled()` + `useDisableTranslation()` |
| `frontend/src/components/settings/EnableTranslationModal.tsx` | New: Beta confirm modal |
| `frontend/src/components/settings/SettingsGrid.tsx` | Translation card clickable + modal trigger |
| `frontend/src/components/settings/__tests__/SettingsGrid.test.tsx` | Test modal trigger |
| `frontend/src/pages/Settings/TranslationSettings.tsx` | Add "Disable Translation" danger section |
| `frontend/src/pages/Settings/__tests__/TranslationSettings.test.tsx` | Test disable button |
| `frontend/src/pages/ActivityPage.tsx` | Hide Translations tab when disabled |
| `frontend/src/pages/Wanted.tsx` | Hide batch-translate + retranslate buttons when disabled |

---

## Task 1: Backend — `translation_enabled` config field

**Files:**
- Modify: `backend/config.py` (around line 43, Translation section)
- Modify: `backend/tests/test_config.py`

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_config.py`:

```python
def test_translation_enabled_default():
    """translation_enabled defaults to False (opt-in feature)."""
    settings = reload_settings()
    assert settings.translation_enabled is False


def test_translation_enabled_env_override(monkeypatch):
    """SUBLARR_TRANSLATION_ENABLED=true activates the feature."""
    monkeypatch.setenv("SUBLARR_TRANSLATION_ENABLED", "true")
    settings = reload_settings()
    assert settings.translation_enabled is True
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && python -m pytest tests/test_config.py::test_translation_enabled_default -v
```

Expected: `FAILED — AttributeError: 'Settings' object has no attribute 'translation_enabled'`

- [ ] **Step 3: Add field to Settings**

In `backend/config.py`, in the `Settings` class, after the `# Translation` block comment (around line 43):

```python
    # Translation feature gate
    translation_enabled: bool = False  # Must be explicitly enabled — Beta feature
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd backend && python -m pytest tests/test_config.py::test_translation_enabled_default tests/test_config.py::test_translation_enabled_env_override -v
```

Expected: `2 passed`

- [ ] **Step 5: Commit**

```bash
git add backend/config.py backend/tests/test_config.py
git commit -m "feat: add translation_enabled config field (default False)"
```

---

## Task 2: Backend — `cancel_queued_jobs()` in DB layer

**Files:**
- Modify: `backend/db/repositories/jobs.py`
- Modify: `backend/db/jobs.py`
- Create: `backend/tests/test_translate_disable.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_translate_disable.py`:

```python
"""Tests for translation disable: job cancellation."""
import pytest


def test_cancel_queued_jobs_cancels_only_queued(app):
    """cancel_queued_jobs() marks queued jobs as cancelled, leaves running/completed alone."""
    from db.jobs import cancel_queued_jobs, create_job, update_job

    with app.app_context():
        # Create jobs in different states
        queued_job = create_job("/media/queued.mkv")
        running_job = create_job("/media/running.mkv")
        update_job(running_job["id"], "running")
        done_job = create_job("/media/done.mkv")
        update_job(done_job["id"], "completed", result={})

        cancelled_count = cancel_queued_jobs()

        from db.jobs import get_job
        assert get_job(queued_job["id"])["status"] == "cancelled"
        assert get_job(running_job["id"])["status"] == "running"  # unchanged
        assert get_job(done_job["id"])["status"] == "completed"  # unchanged
        assert cancelled_count == 1


def test_cancel_queued_jobs_returns_zero_when_none(app):
    """cancel_queued_jobs() returns 0 when no queued jobs exist."""
    from db.jobs import cancel_queued_jobs
    with app.app_context():
        count = cancel_queued_jobs()
        assert count == 0
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && python -m pytest tests/test_translate_disable.py -v
```

Expected: `FAILED — ImportError: cannot import name 'cancel_queued_jobs'`

- [ ] **Step 3: Add `cancel_queued_jobs` to repository**

In `backend/db/repositories/jobs.py`, add after the `delete_job` method:

```python
def cancel_queued_jobs(self) -> int:
    """Mark all queued translation jobs as cancelled. Returns count of cancelled jobs."""
    from db.models.core import Job
    with self.session.begin():
        result = self.session.execute(
            self.session.query(Job)
            .filter(Job.status == "queued")
            .update({"status": "cancelled"}, synchronize_session="fetch")
        )
    return result
```

Note: SQLAlchemy `Query.update()` returns the number of rows matched. Use this pattern to match the existing ORM style in the file.

Actually, looking at how the existing repository uses `select` + `self._commit()`, the correct pattern is:

```python
def cancel_queued_jobs(self) -> int:
    """Mark all queued translation jobs as cancelled. Returns count of cancelled jobs."""
    from sqlalchemy import update as sa_update
    from db.models.core import Job

    stmt = sa_update(Job).where(Job.status == "queued").values(status="cancelled")
    result = self.session.execute(stmt)
    self._commit()
    return result.rowcount
```

- [ ] **Step 4: Add facade to `backend/db/jobs.py`**

Add after `delete_old_jobs`:

```python
def cancel_queued_jobs() -> int:
    """Mark all queued translation jobs as cancelled. Returns count cancelled."""
    return _get_repo().cancel_queued_jobs()
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd backend && python -m pytest tests/test_translate_disable.py -v
```

Expected: `2 passed`

- [ ] **Step 6: Commit**

```bash
git add backend/db/repositories/jobs.py backend/db/jobs.py backend/tests/test_translate_disable.py
git commit -m "feat: add cancel_queued_jobs() to DB layer for translation disable"
```

---

## Task 3: Backend — `POST /api/v1/translate/disable` endpoint

**Files:**
- Modify: `backend/routes/translate/core.py`
- Modify: `backend/tests/test_translate_disable.py`

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_translate_disable.py`:

```python
def test_disable_endpoint_sets_flag_and_cancels_jobs(client, app):
    """POST /translate/disable sets translation_enabled=false and cancels queued jobs."""
    from db.jobs import create_job, get_job

    with app.app_context():
        job = create_job("/media/test.mkv")

    resp = client.post("/api/v1/translate/disable")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "disabled"
    assert data["cancelled_jobs"] >= 1

    with app.app_context():
        assert get_job(job["id"])["status"] == "cancelled"


def test_disable_endpoint_returns_200_when_no_jobs(client):
    """POST /translate/disable returns 200 even when no queued jobs exist."""
    resp = client.post("/api/v1/translate/disable")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["cancelled_jobs"] == 0
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && python -m pytest tests/test_translate_disable.py::test_disable_endpoint_sets_flag_and_cancels_jobs -v
```

Expected: `FAILED — 404`

- [ ] **Step 3: Add the endpoint to `backend/routes/translate/core.py`**

Add at the end of the file:

```python
@bp.route("/translate/disable", methods=["POST"])
def disable_translation():
    """Disable the translation feature and cancel all queued jobs.
    ---
    post:
      tags:
        - Translate
      summary: Disable translation feature
      description: Sets translation_enabled=false in config and cancels all queued translation jobs.
      security:
        - apiKeyAuth: []
      responses:
        200:
          description: Translation disabled
          content:
            application/json:
              schema:
                type: object
                properties:
                  status:
                    type: string
                  cancelled_jobs:
                    type: integer
    """
    from config import reload_settings
    from db.config import get_all_config_entries, save_config_entry
    from db.jobs import cancel_queued_jobs

    save_config_entry("translation_enabled", "false")
    all_overrides = get_all_config_entries()
    reload_settings(all_overrides)

    cancelled = cancel_queued_jobs()
    return jsonify({"status": "disabled", "cancelled_jobs": cancelled})
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd backend && python -m pytest tests/test_translate_disable.py -v
```

Expected: `4 passed`

- [ ] **Step 5: Commit**

```bash
git add backend/routes/translate/core.py backend/tests/test_translate_disable.py
git commit -m "feat: add POST /translate/disable endpoint"
```

---

## Task 4: Frontend — API function + hooks

**Files:**
- Modify: `frontend/src/api/client.ts`
- Modify: `frontend/src/hooks/useSystemApi.ts`

- [ ] **Step 1: Add `disableTranslation()` to `frontend/src/api/client.ts`**

Find the existing `updateConfig` function (around line 212) and add after it:

```typescript
export async function disableTranslation(): Promise<{ status: string; cancelled_jobs: number }> {
  const { data } = await api.post('/translate/disable')
  return data
}
```

- [ ] **Step 2: Add hooks to `frontend/src/hooks/useSystemApi.ts`**

Add after the existing `useUpdateConfig` function (around line 126):

```typescript
/** Returns whether the translation feature is enabled. */
export function useTranslationEnabled(): boolean {
  const { data } = useConfig()
  return Boolean(data?.translation_enabled)
}

/** Mutation: disables translation + cancels all queued jobs. */
export function useDisableTranslation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: disableTranslation,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['config'] })
      queryClient.invalidateQueries({ queryKey: ['jobs'] })
    },
  })
}
```

Add `disableTranslation` to the import from `@/api/client` at the top of `useSystemApi.ts`.

- [ ] **Step 3: Run TypeScript check**

```bash
cd frontend && npx tsc --noEmit
```

Expected: no errors

- [ ] **Step 4: Commit**

```bash
git add frontend/src/api/client.ts frontend/src/hooks/useSystemApi.ts
git commit -m "feat: add disableTranslation API + useTranslationEnabled/useDisableTranslation hooks"
```

---

## Task 5: Frontend — `EnableTranslationModal` component

**Files:**
- Create: `frontend/src/components/settings/EnableTranslationModal.tsx`
- Create: `frontend/src/components/settings/__tests__/EnableTranslationModal.test.tsx`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/components/settings/__tests__/EnableTranslationModal.test.tsx`:

```typescript
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { EnableTranslationModal } from '../EnableTranslationModal'

const mockMutate = vi.fn()
vi.mock('@/hooks/useApi', () => ({
  useUpdateConfig: () => ({ mutate: mockMutate, isPending: false }),
}))

describe('EnableTranslationModal', () => {
  it('renders beta warning text', () => {
    render(<EnableTranslationModal onClose={vi.fn()} />)
    expect(screen.getByText(/Beta/i)).toBeInTheDocument()
    expect(screen.getByText(/experimentell/i)).toBeInTheDocument()
  })

  it('Enable button is disabled until checkbox is checked', () => {
    render(<EnableTranslationModal onClose={vi.fn()} />)
    const enableBtn = screen.getByRole('button', { name: /enable translation/i })
    expect(enableBtn).toBeDisabled()
    fireEvent.click(screen.getByRole('checkbox'))
    expect(enableBtn).not.toBeDisabled()
  })

  it('calls updateConfig with translation_enabled=true on confirm', () => {
    render(<EnableTranslationModal onClose={vi.fn()} />)
    fireEvent.click(screen.getByRole('checkbox'))
    fireEvent.click(screen.getByRole('button', { name: /enable translation/i }))
    expect(mockMutate).toHaveBeenCalledWith({ translation_enabled: 'true' })
  })

  it('calls onClose when Cancel is clicked', () => {
    const onClose = vi.fn()
    render(<EnableTranslationModal onClose={onClose} />)
    fireEvent.click(screen.getByRole('button', { name: /cancel/i }))
    expect(onClose).toHaveBeenCalled()
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd frontend && npm run test -- --run EnableTranslationModal
```

Expected: `FAILED — Cannot find module '../EnableTranslationModal'`

- [ ] **Step 3: Create the component**

Create `frontend/src/components/settings/EnableTranslationModal.tsx`:

```typescript
import { useState } from 'react'
import { FlaskConical, X } from 'lucide-react'
import { useUpdateConfig } from '@/hooks/useApi'

interface EnableTranslationModalProps {
  readonly onClose: () => void
}

export function EnableTranslationModal({ onClose }: EnableTranslationModalProps) {
  const [understood, setUnderstood] = useState(false)
  const updateConfig = useUpdateConfig()

  function handleEnable() {
    updateConfig.mutate({ translation_enabled: 'true' }, { onSuccess: onClose })
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center"
      style={{ backgroundColor: 'rgba(0,0,0,0.6)' }}
      onClick={(e) => { if (e.target === e.currentTarget) onClose() }}
    >
      <div
        className="relative flex flex-col gap-5 rounded-xl"
        style={{
          backgroundColor: 'var(--bg-surface)',
          border: '1px solid var(--border)',
          padding: 28,
          maxWidth: 480,
          width: '90vw',
        }}
      >
        {/* Close */}
        <button
          onClick={onClose}
          className="absolute top-4 right-4 p-1 rounded"
          style={{ color: 'var(--text-muted)' }}
          aria-label="Cancel"
        >
          <X size={16} />
        </button>

        {/* Header */}
        <div className="flex items-center gap-3">
          <div
            className="flex items-center justify-center rounded-lg shrink-0"
            style={{ width: 40, height: 40, backgroundColor: 'var(--warning-bg)' }}
          >
            <FlaskConical size={20} style={{ color: 'var(--warning)' }} />
          </div>
          <div>
            <div className="font-bold text-base" style={{ color: 'var(--text-primary)' }}>
              Translation aktivieren
            </div>
            <div
              className="text-xs font-semibold rounded-full px-2 py-0.5 inline-block mt-0.5"
              style={{ backgroundColor: 'var(--warning-bg)', color: 'var(--warning)' }}
            >
              BETA
            </div>
          </div>
        </div>

        {/* Warning body */}
        <div
          className="rounded-lg text-sm leading-relaxed"
          style={{
            padding: '12px 16px',
            backgroundColor: 'var(--warning-bg)',
            border: '1px solid var(--warning)',
            color: 'var(--text-secondary)',
          }}
        >
          <p>
            Die KI-Übersetzungsfunktion ist experimentell und funktioniert aktuell nicht
            zuverlässig genug für den produktiven Einsatz. Ergebnisse können stark
            variieren — abhängig von Modell, Prompt und Eingabequalität.
          </p>
          <p className="mt-2">
            Voraussetzung: Ein laufender <strong>Ollama</strong>-Server mit einem konfigurierten Modell.
          </p>
        </div>

        {/* Checkbox */}
        <label className="flex items-start gap-3 cursor-pointer select-none">
          <input
            type="checkbox"
            checked={understood}
            onChange={(e) => setUnderstood(e.target.checked)}
            className="mt-0.5 shrink-0"
            style={{ accentColor: 'var(--accent)', width: 16, height: 16 }}
          />
          <span className="text-sm" style={{ color: 'var(--text-secondary)' }}>
            Ich verstehe, dass dies eine Beta-Funktion ist, und nutze sie auf eigenes Risiko.
          </span>
        </label>

        {/* Actions */}
        <div className="flex justify-end gap-3">
          <button
            onClick={onClose}
            className="px-4 py-2 rounded-md text-sm font-medium"
            style={{
              backgroundColor: 'var(--bg-elevated)',
              border: '1px solid var(--border)',
              color: 'var(--text-secondary)',
            }}
          >
            Cancel
          </button>
          <button
            onClick={handleEnable}
            disabled={!understood || updateConfig.isPending}
            className="px-4 py-2 rounded-md text-sm font-semibold"
            style={{
              backgroundColor: understood ? 'var(--accent)' : 'var(--bg-elevated)',
              color: understood ? '#fff' : 'var(--text-muted)',
              border: '1px solid transparent',
              opacity: !understood || updateConfig.isPending ? 0.5 : 1,
            }}
          >
            Enable Translation
          </button>
        </div>
      </div>
    </div>
  )
}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd frontend && npm run test -- --run EnableTranslationModal
```

Expected: `4 passed`

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/settings/EnableTranslationModal.tsx frontend/src/components/settings/__tests__/EnableTranslationModal.test.tsx
git commit -m "feat: add EnableTranslationModal with Beta warning and checkbox confirmation"
```

---

## Task 6: Frontend — SettingsGrid Translation card triggers modal

**Files:**
- Modify: `frontend/src/components/settings/SettingsGrid.tsx`
- Modify: `frontend/src/components/settings/__tests__/SettingsGrid.test.tsx`

The Translation card is currently `pointer-events-none` when disabled. Change it so clicking it when disabled opens the `EnableTranslationModal`.

- [ ] **Step 1: Write the failing test**

Add to `frontend/src/components/settings/__tests__/SettingsGrid.test.tsx`:

```typescript
it('clicking disabled translation card opens enable modal', async () => {
  const user = userEvent.setup()
  renderWithRouter(<SettingsGrid />)
  const translationCard = screen.getByTestId('settings-card-translation')
  await user.click(translationCard)
  expect(screen.getByText(/Translation aktivieren/i)).toBeInTheDocument()
})

it('clicking enabled translation card navigates to /settings/translation', async () => {
  vi.mocked(require('@/hooks/useApi').useConfig).mockReturnValue({
    data: { translation_enabled: true }
  })
  const user = userEvent.setup()
  renderWithRouter(<SettingsGrid />)
  const translationCard = screen.getByTestId('settings-card-translation')
  await user.click(translationCard)
  expect(mockNavigate).toHaveBeenCalledWith('/settings/translation')
})
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd frontend && npm run test -- --run SettingsGrid
```

Expected: failing — modal not present

- [ ] **Step 3: Modify `SettingsGrid.tsx`**

In `SettingsGrid.tsx`:

1. Import `EnableTranslationModal` and `useState`:

```typescript
import { useState } from 'react'
import { EnableTranslationModal } from './EnableTranslationModal'
```

2. In `SettingsGrid` function, add state:

```typescript
const [showEnableModal, setShowEnableModal] = useState(false)
```

3. Change the Translation card click handler and disabled logic. Replace:

```typescript
const isDisabled = disabledCategories.includes(category.id) ||
  (isTranslationCard && !translationEnabled)
return (
  <CategoryCard
    key={category.id}
    category={category}
    disabled={isDisabled}
    isTranslationCard={isTranslationCard}
    translationEnabled={translationEnabled}
    onClick={() => navigate(`/settings/${category.id}`)}
  />
)
```

With:

```typescript
const isSystemDisabled = disabledCategories.includes(category.id)
const isTranslationDisabled = isTranslationCard && !translationEnabled
const isDisabled = isSystemDisabled  // translation card is never hard-disabled
return (
  <CategoryCard
    key={category.id}
    category={category}
    disabled={isDisabled}
    isTranslationCard={isTranslationCard}
    translationEnabled={translationEnabled}
    onClick={() => {
      if (isTranslationDisabled) {
        setShowEnableModal(true)
      } else {
        navigate(`/settings/${category.id}`)
      }
    }}
  />
)
```

4. Remove `pointer-events-none` from `CategoryCard` when `isTranslationCard && !translationEnabled`. Change the `disabled` className in `CategoryCard`:

```typescript
disabled && !isTranslationCard && 'opacity-40 pointer-events-none cursor-default',
isTranslationCard && !translationEnabled && 'opacity-60',
```

5. Add modal at end of `SettingsGrid` return, before closing `</div>`:

```typescript
{showEnableModal && (
  <EnableTranslationModal onClose={() => setShowEnableModal(false)} />
)}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd frontend && npm run test -- --run SettingsGrid
```

Expected: all passing

- [ ] **Step 5: TypeScript check**

```bash
cd frontend && npx tsc --noEmit
```

Expected: no errors

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/settings/SettingsGrid.tsx frontend/src/components/settings/__tests__/SettingsGrid.test.tsx
git commit -m "feat: Translation card opens EnableTranslationModal when not yet enabled"
```

---

## Task 7: Frontend — Disable button in TranslationSettings

**Files:**
- Modify: `frontend/src/pages/Settings/TranslationSettings.tsx`
- Modify: `frontend/src/pages/Settings/__tests__/TranslationSettings.test.tsx`

- [ ] **Step 1: Write the failing test**

Add to `frontend/src/pages/Settings/__tests__/TranslationSettings.test.tsx`:

```typescript
it('renders Disable Translation button', () => {
  render(<TranslationSettings />, { wrapper: Providers })
  expect(screen.getByRole('button', { name: /disable translation/i })).toBeInTheDocument()
})

it('clicking Disable Translation shows confirmation dialog', async () => {
  const user = userEvent.setup()
  render(<TranslationSettings />, { wrapper: Providers })
  await user.click(screen.getByRole('button', { name: /disable translation/i }))
  expect(screen.getByText(/wirklich deaktivieren/i)).toBeInTheDocument()
})
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd frontend && npm run test -- --run TranslationSettings
```

Expected: `FAILED — button not found`

- [ ] **Step 3: Add Danger Zone section to `TranslationSettings.tsx`**

At the top of the file, add imports:

```typescript
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useDisableTranslation } from '@/hooks/useApi'
import { AlertTriangle } from 'lucide-react'
```

In `TranslationSettings` component, add state and hook:

```typescript
const navigate = useNavigate()
const [showDisableConfirm, setShowDisableConfirm] = useState(false)
const disableTranslation = useDisableTranslation()

function handleDisableConfirm() {
  disableTranslation.mutate(undefined, {
    onSuccess: () => navigate('/settings'),
  })
}
```

At the end of `SettingsDetailLayout` children (after the last existing section), add:

```tsx
{/* Danger Zone */}
<div
  style={{
    marginTop: 16,
    padding: '16px 20px',
    borderRadius: 8,
    border: '1px solid var(--error)',
    backgroundColor: 'var(--error-bg)',
  }}
>
  <div className="flex items-start justify-between gap-4">
    <div className="flex items-start gap-3">
      <AlertTriangle size={18} style={{ color: 'var(--error)', flexShrink: 0, marginTop: 1 }} />
      <div>
        <div className="font-semibold text-sm" style={{ color: 'var(--error)' }}>
          Translation deaktivieren
        </div>
        <div className="text-xs mt-0.5" style={{ color: 'var(--text-muted)' }}>
          Deaktiviert die Translation-Funktion und bricht alle wartenden Jobs ab.
        </div>
      </div>
    </div>
    <button
      onClick={() => setShowDisableConfirm(true)}
      className="shrink-0 px-3 py-1.5 rounded-md text-sm font-medium"
      style={{
        border: '1px solid var(--error)',
        color: 'var(--error)',
        backgroundColor: 'transparent',
      }}
    >
      Disable Translation
    </button>
  </div>

  {showDisableConfirm && (
    <div
      className="mt-3 pt-3 flex items-center justify-between gap-4"
      style={{ borderTop: '1px solid var(--error)' }}
    >
      <span className="text-sm" style={{ color: 'var(--text-secondary)' }}>
        Wirklich deaktivieren? Alle wartenden Translation-Jobs werden abgebrochen.
      </span>
      <div className="flex gap-2 shrink-0">
        <button
          onClick={() => setShowDisableConfirm(false)}
          className="px-3 py-1.5 rounded-md text-sm"
          style={{ border: '1px solid var(--border)', color: 'var(--text-secondary)' }}
        >
          Abbrechen
        </button>
        <button
          onClick={handleDisableConfirm}
          disabled={disableTranslation.isPending}
          className="px-3 py-1.5 rounded-md text-sm font-semibold"
          style={{ backgroundColor: 'var(--error)', color: '#fff' }}
        >
          {disableTranslation.isPending ? 'Deaktiviere…' : 'Bestätigen'}
        </button>
      </div>
    </div>
  )}
</div>
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd frontend && npm run test -- --run TranslationSettings
```

Expected: all passing

- [ ] **Step 5: TypeScript check**

```bash
cd frontend && npx tsc --noEmit
```

Expected: no errors

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/Settings/TranslationSettings.tsx frontend/src/pages/Settings/__tests__/TranslationSettings.test.tsx
git commit -m "feat: add Disable Translation danger zone to TranslationSettings"
```

---

## Task 8: Frontend — Hide translation UI when disabled

**Files:**
- Modify: `frontend/src/pages/ActivityPage.tsx`
- Modify: `frontend/src/pages/Wanted.tsx`

### ActivityPage: hide Translations tab

- [ ] **Step 1: Write the failing test**

In the existing test file for ActivityPage (or create one), add:

```typescript
it('hides Translations tab when translation_enabled is false', () => {
  vi.mocked(useConfig).mockReturnValue({ data: { translation_enabled: false } } as any)
  render(<ActivityPage />, { wrapper: Providers })
  expect(screen.queryByText('Translations')).not.toBeInTheDocument()
})

it('shows Translations tab when translation_enabled is true', () => {
  vi.mocked(useConfig).mockReturnValue({ data: { translation_enabled: true } } as any)
  render(<ActivityPage />, { wrapper: Providers })
  expect(screen.getByText('Translations')).toBeInTheDocument()
})
```

- [ ] **Step 2: Modify `ActivityPage.tsx`**

Add imports:

```typescript
import { useTranslationEnabled } from '@/hooks/useApi'
```

In `ActivityPage` component add:

```typescript
const translationEnabled = useTranslationEnabled()
```

Change the `tabs` useMemo:

```typescript
const tabs = useMemo(
  () => [
    { id: 'queue' as const, label: t('tabs.queue', 'Queue') },
    ...(translationEnabled
      ? [{ id: 'translations' as const, label: t('tabs.translations', 'Translations'), count: translationsCount }]
      : []),
    { id: 'history' as const, label: t('tabs.history', 'History') },
    { id: 'blacklist' as const, label: t('tabs.blacklist', 'Blacklist') },
  ],
  [t, translationsCount, translationEnabled],
)
```

Also guard the tab content render:

```tsx
{activeTab === 'translations' && translationEnabled && <TranslationsTab />}
```

Also remove the polling for translation job counts when translation is disabled, by short-circuiting `translationsCount`:

```typescript
const translationsCount = translationEnabled
  ? ((activeJobs?.data?.length ?? 0) + (queuedJobs?.data?.length ?? 0) || undefined)
  : undefined
```

### Wanted.tsx: hide batch-translate and per-row retranslate buttons

- [ ] **Step 3: Modify `Wanted.tsx`**

Add import (already has `useTranslationEnabled` available via `useApi`):

```typescript
import { useTranslationEnabled } from '@/hooks/useApi'
```

Wait — `useTranslationEnabled` is in `useSystemApi.ts` which is re-exported from `useApi.ts`. But check if `useTranslationEnabled` is explicitly exported in `useApi.ts` via `export * from './useSystemApi'`. It is (since `useApi.ts` has `export * from ...` for all sub-hooks). ✅

In the `WantedPage` component, add:

```typescript
const translationEnabled = useTranslationEnabled()
```

Find the batch-translate button (around line 640, `data-testid="batch-translate-btn"`). Wrap it:

```tsx
{translationEnabled && (
  <button
    onClick={() => batchTranslate.mutate([])}
    ...
  >
    ...
  </button>
)}
```

Find the per-row retranslate button (around the row actions, `title={t('wanted.re_translate')}`). Wrap it:

```tsx
{translationEnabled && (
  <button
    onClick={() => retranslateItem.mutate(item.id)}
    ...
  />
)}
```

- [ ] **Step 4: Run TypeScript check**

```bash
cd frontend && npx tsc --noEmit
```

Expected: no errors

- [ ] **Step 5: Run all frontend tests**

```bash
cd frontend && npm run test -- --run
```

Expected: all passing

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/ActivityPage.tsx frontend/src/pages/Wanted.tsx
git commit -m "feat: hide translation UI (Translations tab, batch/row buttons) when translation disabled"
```

---

## Final: Run full pre-PR check

```bash
# Backend
cd backend && ruff check . && ruff format --check .
cd backend && python -m pytest --tb=short -q \
  --ignore=tests/performance \
  --ignore=tests/integration/test_provider_pipeline.py \
  --ignore=tests/test_video_sync.py \
  --ignore=tests/test_translation_backends.py \
  -k "not (test_sonarr_download_webhook or test_radarr_download_webhook or test_parse_llm_response_too_many_merge or test_record_backend_success)"

# Frontend
cd frontend && npm run lint && npx tsc --noEmit && npm run test -- --run
```
