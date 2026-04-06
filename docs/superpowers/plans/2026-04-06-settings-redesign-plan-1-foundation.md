# Settings Redesign — Plan 1: Foundation Components

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend `SettingsSection` to display advanced-field count with i18n, add `advanced` mode to `FormGroup` (amber badge + tooltip instead of inline hint), and add all required i18n keys.

**Architecture:** Two existing component modifications + i18n key additions. No new files created. All other plans depend on this foundation being in place first. `AdvancedSettingsContext` already exists and persists state to localStorage — do not replace it.

**Tech Stack:** React 19, TypeScript, react-i18next (namespace `settings`), Vitest + @testing-library/react

**Branch:** `feature/settings-redesign`

---

## File Map

| File | Change |
|------|--------|
| `frontend/src/components/settings/SettingsSection.tsx` | Add `advancedCount?: number` prop, i18n toggle label |
| `frontend/src/components/settings/FormGroup.tsx` | Add `advanced?: boolean` prop with badge + tooltip mode |
| `frontend/src/i18n/locales/en/settings.json` | Add `advanced_toggle`, `advanced_badge` keys |
| `frontend/src/i18n/locales/de/settings.json` | Same keys in German |
| `frontend/src/components/settings/__tests__/FormGroup.test.tsx` | New: tests for advanced mode |
| `frontend/src/components/settings/__tests__/SettingsSection.test.tsx` | New: tests for count display |

---

### Task 1: Add i18n keys for the advanced system

**Files:**
- Modify: `frontend/src/i18n/locales/en/settings.json`
- Modify: `frontend/src/i18n/locales/de/settings.json`

- [ ] **Step 1: Add keys to EN settings.json**

Open `frontend/src/i18n/locales/en/settings.json`. Add at the top level (after `"title": "Settings"`):

```json
  "advanced_toggle_one": "1 advanced setting",
  "advanced_toggle_other": "{{count}} advanced settings",
  "advanced_badge": "Advanced",
```

- [ ] **Step 2: Add keys to DE settings.json**

Open `frontend/src/i18n/locales/de/settings.json`. Add the same keys:

```json
  "advanced_toggle_one": "1 erweiterte Einstellung",
  "advanced_toggle_other": "{{count}} erweiterte Einstellungen",
  "advanced_badge": "Erweitert",
```

- [ ] **Step 3: Verify the keys load**

Run the frontend dev server and navigate to any settings page. The keys don't appear yet (they'll be used in the next tasks) but the JSON must be valid:

```bash
cd frontend && npx tsc --noEmit
```

Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/i18n/locales/en/settings.json frontend/src/i18n/locales/de/settings.json
git commit -m "feat: add i18n keys for advanced settings system"
```

---

### Task 2: Update SettingsSection to show advanced field count

**Files:**
- Modify: `frontend/src/components/settings/SettingsSection.tsx`
- Test: `frontend/src/components/settings/__tests__/SettingsSection.test.tsx`

Current state: the advanced toggle button hardcodes "Advanced" in English. It does not show how many fields are hidden.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/components/settings/__tests__/SettingsSection.test.tsx`:

```tsx
import { describe, it, expect } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { I18nextProvider } from 'react-i18next'
import i18n from '@/i18n'
import { SettingsSection } from '../SettingsSection'

describe('SettingsSection advanced toggle', () => {
  it('shows count in toggle label when advancedCount is provided', () => {
    render(
      <I18nextProvider i18n={i18n}>
        <SettingsSection
          title="Test"
          advanced={<div>hidden field</div>}
          advancedCount={3}
        >
          <div>normal field</div>
        </SettingsSection>
      </I18nextProvider>
    )

    expect(screen.getByTestId('settings-section-advanced-toggle')).toHaveTextContent('3')
    expect(screen.getByTestId('settings-section-advanced-content')).not.toBeVisible()
  })

  it('shows advanced content when toggle is clicked', () => {
    render(
      <I18nextProvider i18n={i18n}>
        <SettingsSection
          title="Test"
          advanced={<div data-testid="adv-field">hidden</div>}
          advancedCount={1}
        >
          <div>normal</div>
        </SettingsSection>
      </I18nextProvider>
    )

    fireEvent.click(screen.getByTestId('settings-section-advanced-toggle'))
    expect(screen.getByTestId('adv-field')).toBeVisible()
  })

  it('renders toggle without count when advancedCount is not provided', () => {
    render(
      <I18nextProvider i18n={i18n}>
        <SettingsSection
          title="Test"
          advanced={<div>hidden</div>}
        >
          <div>normal</div>
        </SettingsSection>
      </I18nextProvider>
    )

    // Toggle still renders when advanced prop is provided
    expect(screen.getByTestId('settings-section-advanced-toggle')).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd frontend && npm run test -- --run --reporter=verbose src/components/settings/__tests__/SettingsSection.test.tsx
```

Expected: FAIL — `advancedCount` prop does not exist yet.

- [ ] **Step 3: Update SettingsSection**

Replace the content of `frontend/src/components/settings/SettingsSection.tsx` with:

```tsx
import React, { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { cn } from '@/lib/utils'

interface SettingsSectionProps {
  readonly title: string
  readonly description?: string
  readonly icon?: React.ReactNode
  readonly children: React.ReactNode
  readonly advanced?: React.ReactNode
  readonly advancedCount?: number
  readonly className?: string
}

export function SettingsSection({
  title,
  description,
  icon,
  children,
  advanced,
  advancedCount,
  className,
}: SettingsSectionProps) {
  const [advancedOpen, setAdvancedOpen] = useState(false)
  const { t } = useTranslation('settings')

  const toggleLabel =
    advancedCount !== undefined
      ? t('advanced_toggle', { count: advancedCount })
      : t('advanced_toggle', { count: 0 })

  return (
    <div
      data-testid="settings-section"
      className={cn(
        'border border-[var(--border)] bg-[var(--bg-surface)]',
        className,
      )}
      style={{ borderRadius: 'var(--radius-lg)', padding: '22px 24px', marginBottom: 0 }}
    >
      {/* Card header */}
      <div
        data-testid="settings-section-header"
        className="flex items-center gap-[10px] pb-3 mb-[18px] border-b border-[var(--border)]"
      >
        {icon && (
          <div
            data-testid="settings-section-icon"
            className="flex items-center justify-center w-8 h-8 flex-shrink-0"
            style={{ backgroundColor: 'var(--accent-bg)', borderRadius: '8px' }}
          >
            {icon}
          </div>
        )}
        <div className="flex flex-col gap-0.5 min-w-0">
          <h3
            data-testid="settings-section-title"
            className="text-[14px] font-semibold text-[var(--text-primary)] leading-tight"
          >
            {title}
          </h3>
          {description && (
            <p
              data-testid="settings-section-description"
              className="text-[11px] text-[var(--text-muted)] mt-px"
            >
              {description}
            </p>
          )}
        </div>
      </div>

      {/* Content area */}
      <div data-testid="settings-section-content">
        {children}
      </div>

      {/* Optional advanced expandable area */}
      {advanced && (
        <div data-testid="settings-section-advanced">
          <button
            type="button"
            data-testid="settings-section-advanced-toggle"
            aria-expanded={advancedOpen}
            onClick={() => setAdvancedOpen((prev) => !prev)}
            className={cn(
              'flex items-center gap-1.5 pt-[10px]',
              'text-[12px] font-medium text-[var(--text-secondary)]',
              'hover:text-[var(--accent)] transition-colors cursor-pointer select-none',
            )}
          >
            <span
              className={cn(
                'text-[10px] transition-transform duration-200 inline-block',
                advancedOpen && 'rotate-90',
              )}
            >
              &#9654;
            </span>
            <span>{toggleLabel}</span>
          </button>

          {advancedOpen && (
            <div
              data-testid="settings-section-advanced-content"
              className="pt-3 mt-[10px]"
              style={{ borderTop: '1px dashed var(--border)' }}
            >
              {advanced}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd frontend && npm run test -- --run --reporter=verbose src/components/settings/__tests__/SettingsSection.test.tsx
```

Expected: 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/settings/SettingsSection.tsx frontend/src/components/settings/__tests__/SettingsSection.test.tsx
git commit -m "feat: add advancedCount prop to SettingsSection with i18n toggle label"
```

---

### Task 3: Add `advanced` mode to FormGroup

**Files:**
- Modify: `frontend/src/components/settings/FormGroup.tsx`
- Test: `frontend/src/components/settings/__tests__/FormGroup.test.tsx`

When `advanced={true}`, FormGroup renders:
1. An amber "Erweitert" badge next to the label
2. A ⓘ icon — hover shows the `hint` text as tooltip
3. No inline hint text (hint only appears in tooltip)

When `advanced` is false or not provided: existing behavior unchanged.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/components/settings/__tests__/FormGroup.test.tsx`:

```tsx
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { I18nextProvider } from 'react-i18next'
import i18n from '@/i18n'
import { FormGroup } from '../FormGroup'

describe('FormGroup', () => {
  it('renders hint inline when advanced is false', () => {
    render(
      <I18nextProvider i18n={i18n}>
        <FormGroup label="My Field" hint="This is a hint">
          <input />
        </FormGroup>
      </I18nextProvider>
    )

    expect(screen.getByTestId('form-group-hint')).toBeInTheDocument()
    expect(screen.getByTestId('form-group-hint')).toHaveTextContent('This is a hint')
    expect(screen.queryByTestId('form-group-advanced-badge')).not.toBeInTheDocument()
  })

  it('renders badge and no inline hint when advanced is true', () => {
    render(
      <I18nextProvider i18n={i18n}>
        <FormGroup label="My Field" hint="Tooltip text" advanced>
          <input />
        </FormGroup>
      </I18nextProvider>
    )

    expect(screen.queryByTestId('form-group-hint')).not.toBeInTheDocument()
    expect(screen.getByTestId('form-group-advanced-badge')).toBeInTheDocument()
    expect(screen.getByTestId('form-group-info-icon')).toBeInTheDocument()
  })

  it('shows tooltip text on info icon hover when advanced is true', async () => {
    const user = userEvent.setup()
    render(
      <I18nextProvider i18n={i18n}>
        <FormGroup label="My Field" hint="Secret tooltip text" advanced>
          <input />
        </FormGroup>
      </I18nextProvider>
    )

    const icon = screen.getByTestId('form-group-info-icon')
    await user.hover(icon)
    expect(screen.getByTestId('form-group-tooltip')).toHaveTextContent('Secret tooltip text')
  })

  it('renders nothing for hint when advanced is true and no hint provided', () => {
    render(
      <I18nextProvider i18n={i18n}>
        <FormGroup label="My Field" advanced>
          <input />
        </FormGroup>
      </I18nextProvider>
    )

    expect(screen.queryByTestId('form-group-hint')).not.toBeInTheDocument()
    expect(screen.queryByTestId('form-group-tooltip')).not.toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd frontend && npm run test -- --run --reporter=verbose src/components/settings/__tests__/FormGroup.test.tsx
```

Expected: FAIL — `advanced` prop does not exist, `form-group-advanced-badge` not found.

- [ ] **Step 3: Update FormGroup**

Replace the content of `frontend/src/components/settings/FormGroup.tsx` with:

```tsx
import React, { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { cn } from '@/lib/utils'

interface FormGroupProps {
  readonly label: string
  readonly hint?: string
  readonly htmlFor?: string
  readonly children: React.ReactNode
  readonly className?: string
  readonly 'data-testid'?: string
  /** When true: renders amber badge + ⓘ tooltip instead of inline hint */
  readonly advanced?: boolean
}

export function FormGroup({
  label,
  hint,
  htmlFor,
  children,
  className,
  'data-testid': testId,
  advanced = false,
}: FormGroupProps) {
  const { t } = useTranslation('settings')
  const [tooltipVisible, setTooltipVisible] = useState(false)

  return (
    <div
      data-testid={testId ?? 'form-group'}
      className={cn(
        'flex flex-col md:flex-row md:items-start md:justify-between gap-2',
        'last:border-b-0 last:pb-0 first:pt-0',
        className,
      )}
      style={{
        padding: '12px 0',
        borderBottom: '1px solid rgba(42, 46, 56, 0.5)',
      }}
    >
      {/* Label group — left side */}
      <div className="flex flex-col gap-0.5 flex-1 min-w-0" style={{ maxWidth: '320px' }}>
        <div className="flex items-center gap-1.5 flex-wrap">
          {htmlFor ? (
            <label
              htmlFor={htmlFor}
              data-testid="form-group-label"
              className="text-[13px] font-medium text-[var(--text-primary)] cursor-pointer"
            >
              {label}
            </label>
          ) : (
            <span
              data-testid="form-group-label"
              className="text-[13px] font-medium text-[var(--text-primary)]"
            >
              {label}
            </span>
          )}

          {advanced && (
            <>
              <span
                data-testid="form-group-advanced-badge"
                style={{
                  fontSize: '10px',
                  fontWeight: 600,
                  color: 'var(--warning, #f59e0b)',
                  background: 'rgba(245,158,11,0.12)',
                  border: '1px solid rgba(245,158,11,0.3)',
                  borderRadius: '3px',
                  padding: '1px 6px',
                  lineHeight: '1.4',
                }}
              >
                {t('advanced_badge')}
              </span>

              {hint && (
                <div
                  style={{ position: 'relative', display: 'inline-flex', alignItems: 'center' }}
                  onMouseEnter={() => setTooltipVisible(true)}
                  onMouseLeave={() => setTooltipVisible(false)}
                >
                  <button
                    type="button"
                    data-testid="form-group-info-icon"
                    aria-label="Show hint"
                    style={{
                      width: '15px',
                      height: '15px',
                      borderRadius: '50%',
                      background: 'var(--accent-bg)',
                      border: '1px solid var(--accent-dim)',
                      color: 'var(--accent)',
                      fontSize: '9px',
                      fontWeight: 700,
                      display: 'inline-flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      cursor: 'default',
                      flexShrink: 0,
                    }}
                  >
                    i
                  </button>
                  {tooltipVisible && (
                    <div
                      data-testid="form-group-tooltip"
                      role="tooltip"
                      style={{
                        position: 'absolute',
                        left: '20px',
                        top: '-4px',
                        zIndex: 100,
                        background: 'var(--bg-elevated)',
                        border: '1px solid var(--accent-dim)',
                        borderRadius: '6px',
                        padding: '8px 10px',
                        fontSize: '11px',
                        color: 'var(--text-secondary)',
                        width: '220px',
                        lineHeight: '1.5',
                        whiteSpace: 'normal',
                        boxShadow: '0 8px 24px rgba(0,0,0,0.4)',
                        pointerEvents: 'none',
                      }}
                    >
                      {hint}
                    </div>
                  )}
                </div>
              )}
            </>
          )}
        </div>

        {/* Inline hint — only when not advanced */}
        {!advanced && hint && (
          <span
            data-testid="form-group-hint"
            className="text-[11px] leading-relaxed text-[var(--text-muted)]"
          >
            {hint}
          </span>
        )}
      </div>

      {/* Control group — right side */}
      <div
        data-testid="form-group-control"
        className="flex items-center gap-2"
        style={{ minWidth: '260px', justifyContent: 'flex-end' }}
      >
        {children}
      </div>
    </div>
  )
}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd frontend && npm run test -- --run --reporter=verbose src/components/settings/__tests__/FormGroup.test.tsx
```

Expected: 4 tests PASS.

- [ ] **Step 5: Run the full frontend test suite to check for regressions**

```bash
cd frontend && npm run test -- --run
```

Expected: all tests pass. If any existing test breaks due to the FormGroup change, the test was checking the internal structure of FormGroup — update it to reflect the new prop interface.

- [ ] **Step 6: Run TypeScript check**

```bash
cd frontend && npx tsc --noEmit
```

Expected: no errors.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/settings/FormGroup.tsx frontend/src/components/settings/__tests__/FormGroup.test.tsx
git commit -m "feat: add advanced mode to FormGroup (badge + tooltip instead of inline hint)"
```

---

### Task 4: Verify visually in browser

- [ ] **Step 1: Start dev server**

```bash
npm run dev
```

Navigate to http://localhost:5173/settings/general

- [ ] **Step 2: Manually verify FormGroup behavior**

Find any FormGroup with a `hint`. Verify:
- Hint renders inline as small gray text below the label ✓

Now temporarily add `advanced` to a FormGroup in GeneralSettings to verify the badge mode. In `frontend/src/pages/settings/GeneralSettings.tsx`, find a FormGroup and add `advanced`:

```tsx
// Find this line (around line 100+):
<FormGroup label={t('general_page.log_level')} hint="...">
// Change to:
<FormGroup label={t('general_page.log_level')} hint="Controls verbosity of server logs." advanced>
```

Navigate to /settings/general. Verify:
- Amber "Erweitert"/"Advanced" badge appears next to "Log Level" label ✓
- No inline hint text visible ✓
- Hover over ⓘ icon shows tooltip with hint text ✓

- [ ] **Step 3: Revert the test change**

Remove the `advanced` prop you just added — it was a manual test only. The actual `advanced` props will be added in Plan 3.

- [ ] **Step 4: Final lint check**

```bash
cd frontend && npm run lint
```

Expected: no errors.

- [ ] **Step 5: Commit**

```bash
git commit -m "chore: verify FormGroup advanced mode visually"
```

(If no files changed, skip this commit.)
