# Version Display & Update Indicator — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Zeige die aktuelle Versionsnummer in der StatusBar und einen pulsierenden Amber-Dot auf dem Settings-Icon + ein Update-Chip neben der Versionsnummer im Sidebar, wenn ein neueres Release verfügbar ist.

**Architecture:** `useUpdateInfo()` existiert bereits in `useSystemApi.ts` und ist via `useApi.ts` barrel-exportiert. Der Hook wird in `IconSidebar.tsx` und `StatusBar.tsx` zusätzlich aufgerufen. Kein neues Backend, keine neuen Hooks.

**Tech Stack:** React 19, TypeScript, Tailwind CSS (`animate-ping`, `animate-pulse`), react-i18next (`common` namespace)

---

## Dateiübersicht

- Modify: `frontend/src/components/layout/IconSidebar.tsx` — update dot auf Settings-Icon, chip neben Version
- Modify: `frontend/src/components/layout/StatusBar.tsx` — amber dot + klickbarer Popover
- Modify: `frontend/src/i18n/locales/de/common.json` — `update` block
- Modify: `frontend/src/i18n/locales/en/common.json` — `update` block
- Modify: `frontend/src/components/layout/__tests__/IconSidebar.test.tsx` — neue Tests
- Modify: `frontend/src/components/layout/__tests__/StatusBar.test.tsx` — neue Tests (Datei existiert möglicherweise noch nicht)

---

### Task 1: i18n Keys

**Files:**
- Modify: `frontend/src/i18n/locales/de/common.json`
- Modify: `frontend/src/i18n/locales/en/common.json`

- [ ] **Keys in de/common.json hinzufügen**

READ die Datei zuerst. Vor dem schließenden `}` einfügen:

```json
"update": {
  "available": "verfügbar",
  "view_release": "Jetzt auf GitHub ansehen →"
}
```

- [ ] **Keys in en/common.json hinzufügen**

READ die Datei zuerst. Vor dem schließenden `}` einfügen:

```json
"update": {
  "available": "available",
  "view_release": "View on GitHub →"
}
```

- [ ] **Commit**

```bash
cd D:/Sublarr_Projekt/Sublarr
git add frontend/src/i18n/locales/de/common.json \
  frontend/src/i18n/locales/en/common.json
git commit -m "feat: i18n keys for update indicator"
```

---

### Task 2: IconSidebar — Update-Dot + Version-Chip

**Files:**
- Modify: `frontend/src/components/layout/IconSidebar.tsx`
- Modify: `frontend/src/components/layout/__tests__/IconSidebar.test.tsx`

> **Kontext:** `useUpdateInfo` ist bereits im Test-Mock vorhanden (`useUpdateInfo: () => ({ data: null })`). `IconSidebar` importiert bisher nur `useHealth` aus `@/hooks/useApi`. Die Versionsnummer wird im Logo-Bereich (Zeile 69-74) angezeigt. Der Settings-Icon wird via `SidebarNavItem` generisch gerendert — wir fügen `showUpdateDot` als optionalen Prop hinzu.

- [ ] **Failing Tests schreiben**

In `frontend/src/components/layout/__tests__/IconSidebar.test.tsx` am Ende des `describe`-Blocks hinzufügen:

```tsx
it('shows update dot on settings icon when update available', () => {
  vi.mocked(require('@/hooks/useApi').useUpdateInfo).mockReturnValue({
    data: { available: true, latest: '0.42.0', current: '0.41.8', url: 'https://github.com/abrechen2/sublarr/releases/tag/v0.42.0' },
  })
  renderWithRouter(<IconSidebar />)
  expect(screen.getByTestId('settings-update-dot')).toBeInTheDocument()
})

it('does not show update dot when no update available', () => {
  renderWithRouter(<IconSidebar />)
  expect(screen.queryByTestId('settings-update-dot')).not.toBeInTheDocument()
})

it('shows update chip next to version when update available', () => {
  vi.mocked(require('@/hooks/useApi').useUpdateInfo).mockReturnValue({
    data: { available: true, latest: '0.42.0', current: '0.41.8', url: 'https://github.com/abrechen2/sublarr/releases/tag/v0.42.0' },
  })
  renderWithRouter(<IconSidebar />)
  expect(screen.getByTestId('sidebar-update-chip')).toBeInTheDocument()
  expect(screen.getByTestId('sidebar-update-chip')).toHaveTextContent('0.42.0')
})

it('does not show update chip when no update available', () => {
  renderWithRouter(<IconSidebar />)
  expect(screen.queryByTestId('sidebar-update-chip')).not.toBeInTheDocument()
})
```

Damit der `vi.mocked(require(...))` Ansatz funktioniert, muss der Mock im `beforeEach` resettet werden. Füge am Anfang des Describe-Blocks hinzu:

```tsx
import { beforeEach } from 'vitest'

// ...existing mocks bleiben unverändert, aber useUpdateInfo wird als vi.fn() gesetzt:
vi.mock('@/hooks/useApi', () => ({
  useHealth: () => ({ data: { status: 'healthy', version: '0.33.0' } }),
  useUpdateInfo: vi.fn(() => ({ data: null })),
  useWantedSummary: () => ({ data: { total: 5 } }),
}))

// In describe block:
beforeEach(() => {
  vi.mocked(useUpdateInfo).mockReturnValue({ data: null })
})
```

Importiere `useUpdateInfo` am Anfang der Testdatei:

```tsx
import { useUpdateInfo } from '@/hooks/useApi'
```

Der komplette Anfang der Testdatei sieht dann so aus:

```tsx
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { BrowserRouter } from 'react-router-dom'
import { useUpdateInfo } from '@/hooks/useApi'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key.split('.').pop() ?? key,
    i18n: { language: 'en', changeLanguage: vi.fn() },
  }),
}))

vi.mock('@/hooks/useApi', () => ({
  useHealth: () => ({ data: { status: 'healthy', version: '0.33.0' } }),
  useUpdateInfo: vi.fn(() => ({ data: null })),
}))

vi.mock('@/hooks/useWantedApi', () => ({
  useWantedSummary: () => ({ data: { total: 5 } }),
  useScannerStatus: () => ({ data: { is_scanning: false, is_searching: false } }),
}))

vi.mock('@/components/shared/ThemeToggle', () => ({
  ThemeToggle: () => <button data-testid="theme-toggle">Theme</button>,
}))

import { IconSidebar } from '../IconSidebar'

function renderWithRouter(ui: React.ReactElement, { route = '/' } = {}) {
  window.history.pushState({}, 'Test page', route)
  return render(<BrowserRouter>{ui}</BrowserRouter>)
}

describe('IconSidebar', () => {
  beforeEach(() => {
    vi.mocked(useUpdateInfo).mockReturnValue({ data: null })
  })

  // ...alle bestehenden Tests bleiben unverändert...
```

- [ ] **Tests ausführen — Fehler bestätigen**

```bash
cd D:/Sublarr_Projekt/Sublarr/frontend && npm run test -- --run --reporter=verbose src/components/layout/__tests__/IconSidebar.test.tsx
```

Erwartet: die 4 neuen Tests schlagen fehl (settings-update-dot und sidebar-update-chip nicht gefunden).

- [ ] **IconSidebar.tsx implementieren**

READ `frontend/src/components/layout/IconSidebar.tsx` vollständig zuerst.

Dann diese Änderungen vornehmen:

**1. Import-Zeile (Zeile 5) erweitern:**
```tsx
import { useHealth, useUpdateInfo } from '@/hooks/useApi'
```

**2. In `IconSidebar()` nach `const { data: wantedSummary }` hinzufügen:**
```tsx
const { data: updateInfo } = useUpdateInfo()
const hasUpdate = updateInfo?.available === true
```

**3. Logo-Bereich — Version + Chip (ersetzt Zeilen 69-75):**
```tsx
<div className="flex items-center">
  <span
    data-testid="sidebar-version"
    className="text-[10px] truncate"
    style={{ color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}
  >
    v{health?.version ?? '...'}
  </span>
  {hasUpdate && (
    <span
      data-testid="sidebar-update-chip"
      className="sidebar-label text-[10px] px-1 rounded font-mono ml-1 shrink-0"
      style={{ backgroundColor: 'rgba(251,191,36,0.2)', color: 'rgb(251,191,36)' }}
    >
      ↑ v{updateInfo?.latest}
    </span>
  )}
</div>
```

**4. `SidebarNavItemProps` Interface erweitern (nach Zeile 119):**
```tsx
interface SidebarNavItemProps {
  readonly item: NavItem
  readonly label: string
  readonly badgeCount: number
  readonly showUpdateDot?: boolean
}
```

**5. Bottom-Items render (ersetzt Zeilen 99-106) — `showUpdateDot` für Settings:**
```tsx
{bottomNavItems.map((item) => (
  <SidebarNavItem
    key={item.to}
    item={item}
    label={t(item.labelKey)}
    badgeCount={0}
    showUpdateDot={item.to === '/settings' && hasUpdate}
  />
))}
```

**6. `SidebarNavItem` Funktion — `showUpdateDot` destructuren und Icon in `relative` div wrappen:**

Ändere die Funktionssignatur:
```tsx
function SidebarNavItem({ item, label, badgeCount, showUpdateDot = false }: SidebarNavItemProps) {
```

Ersetze die Icon-Zeile (aktuell: `<Icon size={20} strokeWidth={isActive ? 2.2 : 1.8} className="shrink-0" />`):
```tsx
<div className="relative shrink-0">
  <Icon size={20} strokeWidth={isActive ? 2.2 : 1.8} />
  {showUpdateDot && (
    <>
      <span
        data-testid="settings-update-dot"
        className="absolute top-0 right-0 w-2 h-2 rounded-full animate-ping opacity-75"
        style={{ backgroundColor: 'rgb(251,191,36)' }}
      />
      <span
        className="absolute top-0 right-0 w-2 h-2 rounded-full"
        style={{ backgroundColor: 'rgb(251,191,36)' }}
      />
    </>
  )}
</div>
```

- [ ] **Tests ausführen — alle grün**

```bash
cd D:/Sublarr_Projekt/Sublarr/frontend && npm run test -- --run --reporter=verbose src/components/layout/__tests__/IconSidebar.test.tsx
```

Erwartet: alle Tests grün (inkl. bestehende).

- [ ] **Commit**

```bash
cd D:/Sublarr_Projekt/Sublarr
git add frontend/src/components/layout/IconSidebar.tsx \
  frontend/src/components/layout/__tests__/IconSidebar.test.tsx
git commit -m "feat: update dot on settings icon + version chip in sidebar"
```

---

### Task 3: StatusBar — Update-Dot + Popover

**Files:**
- Modify: `frontend/src/components/layout/StatusBar.tsx`
- Create: `frontend/src/components/layout/__tests__/StatusBar.test.tsx`

> **Kontext:** StatusBar zeigt die Version aktuell als statischen `<span>` (Zeile 65-67). Kein Test existiert für StatusBar. Beim Update wird daraus ein Button mit Amber-Dot + Popover direkt darüber.

- [ ] **Failing Tests schreiben**

Erstelle `frontend/src/components/layout/__tests__/StatusBar.test.tsx`:

```tsx
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { useUpdateInfo } from '@/hooks/useApi'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key.split('.').pop() ?? key,
    i18n: { language: 'en', changeLanguage: vi.fn() },
  }),
}))

vi.mock('@/hooks/useApi', () => ({
  useHealth: () => ({ data: { status: 'healthy', version: '0.41.8' } }),
  useUpdateInfo: vi.fn(() => ({ data: null })),
}))

vi.mock('@/hooks/useWantedApi', () => ({
  useScannerStatus: () => ({ data: { is_scanning: false, is_searching: false } }),
}))

import { StatusBar } from '../StatusBar'

describe('StatusBar', () => {
  beforeEach(() => {
    vi.mocked(useUpdateInfo).mockReturnValue({ data: null })
  })

  it('renders version as plain text when no update available', () => {
    render(<StatusBar />)
    const version = screen.getByTestId('status-bar-version')
    expect(version.tagName).toBe('SPAN')
    expect(version).toHaveTextContent('0.41.8')
  })

  it('renders version as button when update available', () => {
    vi.mocked(useUpdateInfo).mockReturnValue({
      data: { available: true, latest: '0.42.0', current: '0.41.8', url: 'https://github.com/abrechen2/sublarr/releases/tag/v0.42.0' },
    })
    render(<StatusBar />)
    const version = screen.getByTestId('status-bar-version')
    expect(version.tagName).toBe('BUTTON')
  })

  it('shows update dot when update available', () => {
    vi.mocked(useUpdateInfo).mockReturnValue({
      data: { available: true, latest: '0.42.0', current: '0.41.8', url: 'https://github.com/abrechen2/sublarr/releases/tag/v0.42.0' },
    })
    render(<StatusBar />)
    expect(screen.getByTestId('status-bar-update-dot')).toBeInTheDocument()
  })

  it('does not show update dot when no update available', () => {
    render(<StatusBar />)
    expect(screen.queryByTestId('status-bar-update-dot')).not.toBeInTheDocument()
  })

  it('opens popover when version button is clicked', () => {
    vi.mocked(useUpdateInfo).mockReturnValue({
      data: { available: true, latest: '0.42.0', current: '0.41.8', url: 'https://github.com/abrechen2/sublarr/releases/tag/v0.42.0' },
    })
    render(<StatusBar />)
    expect(screen.queryByTestId('status-bar-update-popover')).not.toBeInTheDocument()
    fireEvent.click(screen.getByTestId('status-bar-version'))
    expect(screen.getByTestId('status-bar-update-popover')).toBeInTheDocument()
    expect(screen.getByTestId('status-bar-update-popover')).toHaveTextContent('0.42.0')
  })

  it('popover contains GitHub link', () => {
    vi.mocked(useUpdateInfo).mockReturnValue({
      data: { available: true, latest: '0.42.0', current: '0.41.8', url: 'https://github.com/abrechen2/sublarr/releases/tag/v0.42.0' },
    })
    render(<StatusBar />)
    fireEvent.click(screen.getByTestId('status-bar-version'))
    const link = screen.getByRole('link')
    expect(link).toHaveAttribute('href', 'https://github.com/abrechen2/sublarr/releases/tag/v0.42.0')
    expect(link).toHaveAttribute('target', '_blank')
  })
})
```

- [ ] **Tests ausführen — Fehler bestätigen**

```bash
cd D:/Sublarr_Projekt/Sublarr/frontend && npm run test -- --run --reporter=verbose src/components/layout/__tests__/StatusBar.test.tsx
```

Erwartet: alle Tests schlagen fehl (status-bar-update-dot, status-bar-update-popover nicht vorhanden; version ist kein Button).

- [ ] **StatusBar.tsx implementieren**

READ `frontend/src/components/layout/StatusBar.tsx` vollständig zuerst.

Ersetze die komplette Datei:

```tsx
import { useState, useEffect, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { useHealth, useUpdateInfo } from '@/hooks/useApi'
import { useScannerStatus } from '@/hooks/useWantedApi'

export function StatusBar() {
  const { t } = useTranslation('common')
  const { data: health } = useHealth()
  const { data: updateInfo } = useUpdateInfo()
  const { data: scannerStatus } = useScannerStatus()
  const [popoverOpen, setPopoverOpen] = useState(false)
  const popoverRef = useRef<HTMLDivElement>(null)

  const isHealthy = health?.status === 'healthy'
  const isScanning = scannerStatus?.is_scanning ?? false
  const isSearching = scannerStatus?.is_searching ?? false
  const isAutomationActive = isScanning || isSearching
  const hasUpdate = updateInfo?.available === true

  const automationLabel = isAutomationActive
    ? t('status.automation_active', 'Automation: active')
    : t('status.automation_paused', 'Automation: paused')

  useEffect(() => {
    if (!popoverOpen) return
    function handleClick(e: MouseEvent) {
      if (popoverRef.current && !popoverRef.current.contains(e.target as Node)) {
        setPopoverOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [popoverOpen])

  return (
    <div
      data-testid="status-bar"
      className="fixed bottom-0 left-0 right-0 z-30 hidden md:flex items-center"
      style={{
        height: 26,
        backgroundColor: 'var(--bg-primary)',
        borderTop: '1px solid var(--border)',
        marginLeft: 'var(--sidebar-width, 60px)',
        padding: '0 14px',
        gap: '14px',
        fontSize: 10,
        color: 'var(--text-muted)',
        fontFamily: 'var(--font-mono)',
      }}
    >
      {/* Health status dot */}
      <div className="flex items-center gap-1.5">
        <div
          data-testid="status-bar-health"
          className="w-1.5 h-1.5 rounded-full shrink-0"
          style={{
            backgroundColor: isHealthy ? 'var(--success)' : 'var(--error)',
          }}
        />
        <span>{isHealthy ? t('app.online', 'Online') : t('app.offline', 'Offline')}</span>
      </div>

      {/* Separator */}
      <div className="h-3" style={{ borderLeft: '1px solid var(--border)' }} />

      {/* Automation status */}
      <span data-testid="status-bar-automation">{automationLabel}</span>

      {/* Separator */}
      <div className="h-3" style={{ borderLeft: '1px solid var(--border)' }} />

      {/* Version — plain or clickable depending on update state */}
      <div className="relative" ref={popoverRef}>
        {hasUpdate ? (
          <button
            data-testid="status-bar-version"
            onClick={() => setPopoverOpen((o) => !o)}
            className="flex items-center gap-1 cursor-pointer"
            style={{ color: 'rgb(251,191,36)', fontFamily: 'var(--font-mono)', fontSize: 10, background: 'none', border: 'none', padding: 0 }}
          >
            <span
              data-testid="status-bar-update-dot"
              className="w-1.5 h-1.5 rounded-full shrink-0 animate-pulse"
              style={{ backgroundColor: 'rgb(251,191,36)' }}
            />
            v{health?.version ?? '...'}
          </button>
        ) : (
          <span data-testid="status-bar-version">
            v{health?.version ?? '...'}
          </span>
        )}

        {hasUpdate && popoverOpen && (
          <div
            data-testid="status-bar-update-popover"
            className="absolute bottom-full mb-2 left-0 rounded shadow-lg"
            style={{
              backgroundColor: 'var(--bg-secondary)',
              border: '1px solid var(--border)',
              padding: '8px 10px',
              fontSize: 11,
              minWidth: 200,
              fontFamily: 'var(--font-sans)',
              color: 'var(--text-primary)',
              whiteSpace: 'nowrap',
            }}
          >
            <div style={{ color: 'rgb(251,191,36)', fontWeight: 600, marginBottom: 4 }}>
              ↑ v{updateInfo?.latest} {t('update.available')}
            </div>
            <a
              href={updateInfo?.url ?? '#'}
              target="_blank"
              rel="noopener noreferrer"
              style={{ color: 'var(--accent)', textDecoration: 'none' }}
            >
              {t('update.view_release')}
            </a>
          </div>
        )}
      </div>

      {/* Spacer */}
      <div className="flex-1" />

      {/* Scanner status */}
      {isAutomationActive && (
        <span data-testid="status-bar-scanning" className="flex items-center gap-1">
          <span
            className="w-1.5 h-1.5 rounded-full"
            style={{
              backgroundColor: 'var(--accent)',
              animation: 'dotGlow 1.5s ease-in-out infinite',
            }}
          />
          {isScanning
            ? t('status.scanning', 'Scanning...')
            : t('status.searching', 'Searching...')}
        </span>
      )}
    </div>
  )
}
```

- [ ] **Tests ausführen — alle grün**

```bash
cd D:/Sublarr_Projekt/Sublarr/frontend && npm run test -- --run --reporter=verbose src/components/layout/__tests__/StatusBar.test.tsx
```

Erwartet: alle 6 Tests grün.

- [ ] **Commit**

```bash
cd D:/Sublarr_Projekt/Sublarr
git add frontend/src/components/layout/StatusBar.tsx \
  frontend/src/components/layout/__tests__/StatusBar.test.tsx
git commit -m "feat: update dot + popover in StatusBar"
```

---

### Task 4: Lint + TypeCheck + Full Test Suite

**Files:** Keine Änderungen — Verifikation

- [ ] **ESLint ausführen**

```bash
cd D:/Sublarr_Projekt/Sublarr/frontend && npm run lint
```

Erwartet: Keine neuen Errors (pre-existing warnings OK).

- [ ] **TypeScript-Check**

```bash
cd D:/Sublarr_Projekt/Sublarr/frontend && npx tsc --noEmit
```

Erwartet: Keine Ausgabe (= kein Fehler).

- [ ] **Alle Frontend-Tests**

```bash
cd D:/Sublarr_Projekt/Sublarr/frontend && npm run test -- --run
```

Erwartet: Alle Tests grün.

- [ ] **Commit falls Fixes nötig**

```bash
git add -A && git commit -m "fix: lint/type fixes for update indicator"
```

- [ ] **Push**

```bash
cd D:/Sublarr_Projekt/Sublarr && git push
```

---

## Self-Review

**Spec Coverage:**
- ✅ Pulsierender Dot auf Settings-Icon (collapsed) → Task 2 `settings-update-dot` mit `animate-ping`
- ✅ Update-Chip neben Versionsnummer (expanded) → Task 2 `sidebar-update-chip`
- ✅ StatusBar: Amber-Dot neben Version → Task 3 `status-bar-update-dot` mit `animate-pulse`
- ✅ StatusBar: Anklickbar → Task 3 Button + `setPopoverOpen`
- ✅ Popover mit Versionsnummer + GitHub-Link → Task 3 `status-bar-update-popover`
- ✅ Popover schließt bei Klick außerhalb → Task 3 `useEffect` + `mousedown`
- ✅ i18n keys → Task 1

**Placeholder-Scan:** Keine TODOs, alle Code-Blöcke vollständig.

**Type-Konsistenz:** `updateInfo?.latest`, `updateInfo?.available`, `updateInfo?.url` durchgängig identisch in Tasks 2 und 3.
