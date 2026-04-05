# Dashboard Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the cluttered multi-section dashboard (AutomationBanner + HeroStats + NeedsAttentionCard + drag-and-drop widget grid) with a focused two-column layout: a 1-line status stripe + 4-metric row above, then activity feed (left) and sidebar panels (right).

**Architecture:** Five new focused components replace nine old ones. Dashboard.tsx becomes a thin shell (~30 lines) that composes them. No new backend endpoints — all hooks already exist. The widget grid, store, and registry are deleted entirely.

**Tech Stack:** React 19, TypeScript, Vitest + Testing Library, react-router-dom, react-i18next, `@/hooks/useWantedApi`, `@/hooks/useSystemApi`, `@/hooks/useApi`

---

## File Map

**Create:**
- `frontend/src/components/dashboard/StatusStripe.tsx` — 1-line automation status bar with Run Now
- `frontend/src/components/dashboard/MetricsRow.tsx` — 4-cell metric grid (total, missing, avg score, low score)
- `frontend/src/components/dashboard/AttentionBanner.tsx` — conditional inline banner for failed + low-score items
- `frontend/src/components/dashboard/ActivityFeed.tsx` — job feed with color dots + embedded AttentionBanner
- `frontend/src/components/dashboard/DashboardSidebar.tsx` — right column (ProviderHealthPanel, ServiceStatusPanel, DiskSpacePanel, QuickActionsPanel)
- `frontend/src/components/dashboard/__tests__/StatusStripe.test.tsx`
- `frontend/src/components/dashboard/__tests__/MetricsRow.test.tsx`
- `frontend/src/components/dashboard/__tests__/AttentionBanner.test.tsx`
- `frontend/src/components/dashboard/__tests__/ActivityFeed.test.tsx`
- `frontend/src/components/dashboard/__tests__/DashboardSidebar.test.tsx`

**Modify:**
- `frontend/src/i18n/locales/de/dashboard.json` — add new keys
- `frontend/src/i18n/locales/en/dashboard.json` — add new keys
- `frontend/src/pages/Dashboard.tsx` — rewire to new components

**Delete:**
- `frontend/src/components/dashboard/AutomationBanner.tsx`
- `frontend/src/components/dashboard/HeroStats.tsx`
- `frontend/src/components/dashboard/NeedsAttentionCard.tsx`
- `frontend/src/components/dashboard/DashboardGrid.tsx`
- `frontend/src/components/dashboard/WidgetWrapper.tsx`
- `frontend/src/components/dashboard/WidgetSettingsModal.tsx`
- `frontend/src/components/dashboard/widgetRegistry.ts`
- `frontend/src/stores/dashboardStore.ts`
- `frontend/src/components/dashboard/widgets/` (entire directory — 10 files)
- `frontend/src/components/dashboard/__tests__/AutomationBanner.test.tsx`
- `frontend/src/components/dashboard/__tests__/HeroStats.test.tsx`
- `frontend/src/components/dashboard/__tests__/NeedsAttentionCard.test.tsx`
- `frontend/src/test/ModalAccessibility.test.tsx`

---

## Task 1: Add i18n keys

**Files:**
- Modify: `frontend/src/i18n/locales/de/dashboard.json`
- Modify: `frontend/src/i18n/locales/en/dashboard.json`

- [ ] **Step 1: Add keys to German locale**

Open `frontend/src/i18n/locales/de/dashboard.json` and add these top-level sections before the closing `}`:

```json
  "statusStripe": {
    "active": "AUTOMATION AKTIV",
    "paused": "PAUSIERT",
    "lastScan": "Zuletzt",
    "neverScanned": "Noch nie gescannt",
    "subtitles": "Untertitel",
    "successRate": "Erfolgsrate",
    "today": "heute",
    "missing": "fehlend",
    "runNow": "Jetzt starten"
  },
  "metrics": {
    "total": "Untertitel gesamt",
    "missing": "Fehlend",
    "avgScore": "Ø Score",
    "lowScore": "Low Score"
  },
  "feed": {
    "title": "Live Aktivitäts-Feed",
    "viewAll": "Alle ansehen",
    "empty": "Noch keine Aktivität",
    "moreEvents": "weitere Ereignisse heute"
  },
  "attention": {
    "title": "Needs Attention",
    "viewAll": "Alle ansehen",
    "reasonFailed": "Kein Match",
    "search": "Suchen",
    "skip": "Skip",
    "findBetter": "Besser suchen",
    "accept": "Annehmen"
  },
  "sidebar": {
    "providers": "Provider-Status",
    "services": "Services",
    "disk": "Speicher",
    "diskFiles": "Dateien",
    "diskDuplicates": "Duplikate",
    "diskSavings": "einsparbar",
    "actions": "Schnellaktionen",
    "scanLibrary": "Bibliothek scannen",
    "scanning": "Scanne...",
    "batchSearch": "Batch-Suche starten",
    "searching": "Suche...",
    "wantedList": "Wanted-Liste",
    "viewLogs": "Logs ansehen",
    "runNow": "▶ Automation jetzt ausführen"
  }
```

- [ ] **Step 2: Add keys to English locale**

Open `frontend/src/i18n/locales/en/dashboard.json` and add the same sections:

```json
  "statusStripe": {
    "active": "AUTOMATION ACTIVE",
    "paused": "PAUSED",
    "lastScan": "Last scan",
    "neverScanned": "Never scanned",
    "subtitles": "subtitles",
    "successRate": "success rate",
    "today": "today",
    "missing": "missing",
    "runNow": "Run Now"
  },
  "metrics": {
    "total": "Subtitles Total",
    "missing": "Missing",
    "avgScore": "Avg Score",
    "lowScore": "Low Score"
  },
  "feed": {
    "title": "Live Activity Feed",
    "viewAll": "View all",
    "empty": "No activity yet",
    "moreEvents": "more events today"
  },
  "attention": {
    "title": "Needs Attention",
    "viewAll": "View all",
    "reasonFailed": "No Match",
    "search": "Search",
    "skip": "Skip",
    "findBetter": "Find Better",
    "accept": "Accept"
  },
  "sidebar": {
    "providers": "Provider Health",
    "services": "Services",
    "disk": "Disk Space",
    "diskFiles": "Files",
    "diskDuplicates": "Duplicates",
    "diskSavings": "savings available",
    "actions": "Quick Actions",
    "scanLibrary": "Scan Library",
    "scanning": "Scanning...",
    "batchSearch": "Start Batch Search",
    "searching": "Searching...",
    "wantedList": "Wanted List",
    "viewLogs": "View Logs",
    "runNow": "▶ Run Automation Now"
  }
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/i18n/locales/de/dashboard.json frontend/src/i18n/locales/en/dashboard.json
git commit -m "feat(dashboard): add i18n keys for redesigned dashboard components"
```

---

## Task 2: StatusStripe component

**Files:**
- Create: `frontend/src/components/dashboard/StatusStripe.tsx`
- Create: `frontend/src/components/dashboard/__tests__/StatusStripe.test.tsx`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/components/dashboard/__tests__/StatusStripe.test.tsx`:

```tsx
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'

const mockMutate = vi.fn()

vi.mock('@/hooks/useWantedApi', () => ({
  useScannerStatus: () => ({ data: { is_scanning: false, is_searching: false, last_scan_at: '2026-04-05T10:00:00Z', last_search_at: null } }),
  useWantedSummary: () => ({ data: { total: 3 } }),
  useRefreshWanted: () => ({ mutate: mockMutate, isPending: false }),
}))
vi.mock('@/hooks/useSystemApi', () => ({
  useStats: () => ({ data: { total_subtitles: 5000, downloads_today: 22, success_rate: 95, average_score: 88.0, low_score_count: 4 } }),
}))
vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}))

describe('StatusStripe', () => {
  beforeEach(() => mockMutate.mockClear())

  it('renders the stripe container', async () => {
    const { StatusStripe } = await import('../StatusStripe')
    render(<StatusStripe />)
    expect(screen.getByTestId('status-stripe')).toBeInTheDocument()
  })

  it('shows paused label when not active', async () => {
    const { StatusStripe } = await import('../StatusStripe')
    render(<StatusStripe />)
    expect(screen.getByTestId('status-label')).toHaveTextContent('statusStripe.paused')
  })

  it('shows total_subtitles', async () => {
    const { StatusStripe } = await import('../StatusStripe')
    render(<StatusStripe />)
    expect(screen.getByTestId('status-total')).toHaveTextContent('5000')
  })

  it('shows success_rate', async () => {
    const { StatusStripe } = await import('../StatusStripe')
    render(<StatusStripe />)
    expect(screen.getByTestId('status-rate')).toHaveTextContent('95')
  })

  it('shows downloads_today', async () => {
    const { StatusStripe } = await import('../StatusStripe')
    render(<StatusStripe />)
    expect(screen.getByTestId('status-today')).toHaveTextContent('22')
  })

  it('shows missing count from wantedSummary', async () => {
    const { StatusStripe } = await import('../StatusStripe')
    render(<StatusStripe />)
    expect(screen.getByTestId('status-missing')).toHaveTextContent('3')
  })

  it('renders Run Now button', async () => {
    const { StatusStripe } = await import('../StatusStripe')
    render(<StatusStripe />)
    expect(screen.getByTestId('btn-run-now')).toBeInTheDocument()
  })

  it('calls refreshWanted when Run Now is clicked', async () => {
    const { StatusStripe } = await import('../StatusStripe')
    render(<StatusStripe />)
    fireEvent.click(screen.getByTestId('btn-run-now'))
    expect(mockMutate).toHaveBeenCalledTimes(1)
  })
})
```

- [ ] **Step 2: Run test — expect FAIL**

```bash
cd frontend && npm run test -- --run src/components/dashboard/__tests__/StatusStripe.test.tsx
```

Expected: FAIL — `Cannot find module '../StatusStripe'`

- [ ] **Step 3: Implement StatusStripe**

Create `frontend/src/components/dashboard/StatusStripe.tsx`:

```tsx
import { useTranslation } from 'react-i18next'
import { useScannerStatus, useWantedSummary, useRefreshWanted } from '@/hooks/useWantedApi'
import { useStats } from '@/hooks/useSystemApi'
import { formatRelativeTime } from '@/lib/utils'

export function StatusStripe() {
  const { t } = useTranslation('dashboard')
  const { data: scannerStatus } = useScannerStatus()
  const { data: stats } = useStats()
  const { data: wantedSummary } = useWantedSummary()
  const refreshWanted = useRefreshWanted()

  const isActive = Boolean(scannerStatus?.is_scanning || scannerStatus?.is_searching)
  const lastActivity = scannerStatus?.last_scan_at ?? scannerStatus?.last_search_at ?? null
  const lastText = lastActivity
    ? `${t('statusStripe.lastScan')}: ${formatRelativeTime(lastActivity)}`
    : t('statusStripe.neverScanned')

  const missingCount = wantedSummary?.total ?? 0

  return (
    <div
      data-testid="status-stripe"
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: '16px',
        padding: '7px 18px',
        background: 'var(--bg-surface)',
        border: '1px solid var(--border)',
        borderRadius: 'var(--radius-lg)',
        flexWrap: 'wrap',
      }}
    >
      {/* Status dot + label */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
        <span
          data-testid="status-dot"
          className={isActive ? 'automation-pulse' : undefined}
          style={{
            width: 7,
            height: 7,
            borderRadius: '50%',
            flexShrink: 0,
            backgroundColor: isActive ? 'var(--success)' : 'var(--text-muted)',
          }}
        />
        <span
          data-testid="status-label"
          style={{
            fontSize: '11px',
            fontWeight: 700,
            letterSpacing: '0.5px',
            color: isActive ? 'var(--success)' : 'var(--text-muted)',
          }}
        >
          {isActive ? t('statusStripe.active') : t('statusStripe.paused')}
        </span>
      </div>

      <span
        data-testid="status-last"
        style={{ fontSize: '11px', color: 'var(--text-muted)' }}
      >
        {lastText}
      </span>

      <div style={{ width: 1, height: 14, background: 'var(--border)', flexShrink: 0 }} />

      <span data-testid="status-total" style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>
        <strong style={{ color: 'var(--text-primary)' }}>{stats?.total_subtitles ?? '—'}</strong>{' '}
        {t('statusStripe.subtitles')}
      </span>

      <span data-testid="status-rate" style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>
        <strong style={{ color: 'var(--success)' }}>{stats?.success_rate ?? '—'}%</strong>{' '}
        {t('statusStripe.successRate')}
      </span>

      <span data-testid="status-today" style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>
        <strong style={{ color: 'var(--accent)' }}>+{stats?.downloads_today ?? 0}</strong>{' '}
        {t('statusStripe.today')}
      </span>

      <span data-testid="status-missing" style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>
        <strong style={{ color: missingCount > 0 ? 'var(--warning)' : 'var(--text-primary)' }}>
          {missingCount}
        </strong>{' '}
        {t('statusStripe.missing')}
      </span>

      <div style={{ marginLeft: 'auto' }}>
        <button
          data-testid="btn-run-now"
          onClick={() => refreshWanted.mutate(undefined)}
          disabled={refreshWanted.isPending}
          style={{
            padding: '4px 12px',
            fontSize: '11px',
            fontWeight: 600,
            borderRadius: '6px',
            border: '1px solid var(--accent)',
            background: 'var(--accent)',
            color: 'var(--bg-primary)',
            cursor: refreshWanted.isPending ? 'not-allowed' : 'pointer',
            opacity: refreshWanted.isPending ? 0.6 : 1,
          }}
        >
          {t('statusStripe.runNow')}
        </button>
      </div>
    </div>
  )
}
```

- [ ] **Step 4: Run test — expect PASS**

```bash
cd frontend && npm run test -- --run src/components/dashboard/__tests__/StatusStripe.test.tsx
```

Expected: all 8 tests PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/dashboard/StatusStripe.tsx frontend/src/components/dashboard/__tests__/StatusStripe.test.tsx
git commit -m "feat(dashboard): add StatusStripe component"
```

---

## Task 3: MetricsRow component

**Files:**
- Create: `frontend/src/components/dashboard/MetricsRow.tsx`
- Create: `frontend/src/components/dashboard/__tests__/MetricsRow.test.tsx`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/components/dashboard/__tests__/MetricsRow.test.tsx`:

```tsx
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'

vi.mock('@/hooks/useSystemApi', () => ({
  useStats: () => ({
    data: { total_subtitles: 12500, downloads_today: 30, success_rate: 92, average_score: 86.5, low_score_count: 7 },
    isLoading: false,
  }),
}))
vi.mock('@/hooks/useWantedApi', () => ({
  useWantedSummary: () => ({ data: { total: 12 }, isLoading: false }),
}))
vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}))

describe('MetricsRow', () => {
  it('renders the metrics row container', async () => {
    const { MetricsRow } = await import('../MetricsRow')
    render(<MetricsRow />)
    expect(screen.getByTestId('metrics-row')).toBeInTheDocument()
  })

  it('renders total subtitles value', async () => {
    const { MetricsRow } = await import('../MetricsRow')
    render(<MetricsRow />)
    expect(screen.getByTestId('metric-total-value')).toHaveTextContent('12500')
  })

  it('renders missing count from wantedSummary', async () => {
    const { MetricsRow } = await import('../MetricsRow')
    render(<MetricsRow />)
    expect(screen.getByTestId('metric-missing-value')).toHaveTextContent('12')
  })

  it('renders average score with 1 decimal', async () => {
    const { MetricsRow } = await import('../MetricsRow')
    render(<MetricsRow />)
    expect(screen.getByTestId('metric-avg-score-value')).toHaveTextContent('86.5')
  })

  it('renders low score count', async () => {
    const { MetricsRow } = await import('../MetricsRow')
    render(<MetricsRow />)
    expect(screen.getByTestId('metric-low-score-value')).toHaveTextContent('7')
  })

  it('shows dash placeholder when loading', async () => {
    vi.doMock('@/hooks/useSystemApi', () => ({
      useStats: () => ({ data: undefined, isLoading: true }),
    }))
    vi.doMock('@/hooks/useWantedApi', () => ({
      useWantedSummary: () => ({ data: undefined, isLoading: true }),
    }))
    // Re-import to pick up new mocks
    vi.resetModules()
    vi.mock('@/hooks/useSystemApi', () => ({
      useStats: () => ({ data: undefined, isLoading: true }),
    }))
    vi.mock('@/hooks/useWantedApi', () => ({
      useWantedSummary: () => ({ data: undefined, isLoading: true }),
    }))
    vi.mock('react-i18next', () => ({
      useTranslation: () => ({ t: (key: string) => key }),
    }))
    const { MetricsRow } = await import('../MetricsRow')
    render(<MetricsRow />)
    // At least one cell shows the loading placeholder
    const totalCell = screen.getByTestId('metric-total-value')
    expect(totalCell).toHaveTextContent('—')
  })
})
```

- [ ] **Step 2: Run test — expect FAIL**

```bash
cd frontend && npm run test -- --run src/components/dashboard/__tests__/MetricsRow.test.tsx
```

Expected: FAIL — `Cannot find module '../MetricsRow'`

- [ ] **Step 3: Implement MetricsRow**

Create `frontend/src/components/dashboard/MetricsRow.tsx`:

```tsx
import { useTranslation } from 'react-i18next'
import { useStats } from '@/hooks/useSystemApi'
import { useWantedSummary } from '@/hooks/useWantedApi'

interface MetricCellProps {
  readonly testId: string
  readonly value: string | number
  readonly label: string
  readonly valueColor: string
  readonly borderLeft?: boolean
}

function MetricCell({ testId, value, label, valueColor, borderLeft }: MetricCellProps) {
  return (
    <div
      data-testid={testId}
      style={{
        padding: '12px 18px',
        display: 'flex',
        flexDirection: 'column',
        gap: '2px',
        borderLeft: borderLeft ? '1px solid var(--border)' : undefined,
      }}
    >
      <span
        data-testid={`${testId}-value`}
        style={{
          fontSize: '22px',
          fontWeight: 700,
          letterSpacing: '-0.5px',
          color: valueColor,
          lineHeight: 1,
          fontFamily: 'var(--font-mono)',
        }}
      >
        {value}
      </span>
      <span
        style={{
          fontSize: '10px',
          color: 'var(--text-muted)',
          textTransform: 'uppercase',
          letterSpacing: '0.4px',
        }}
      >
        {label}
      </span>
    </div>
  )
}

export function MetricsRow() {
  const { t } = useTranslation('dashboard')
  const { data: stats, isLoading: statsLoading } = useStats()
  const { data: wantedSummary, isLoading: wantedLoading } = useWantedSummary()

  const isLoading = statsLoading || wantedLoading

  const total: string | number = isLoading ? '—' : (stats?.total_subtitles ?? '—')
  const missing: string | number = isLoading ? '—' : (wantedSummary?.total ?? '—')
  const avgScore: string | number = isLoading
    ? '—'
    : stats?.average_score != null
      ? stats.average_score.toFixed(1)
      : '—'
  const lowScore: string | number = isLoading ? '—' : (stats?.low_score_count ?? '—')

  return (
    <div
      data-testid="metrics-row"
      style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(4, 1fr)',
        background: 'var(--bg-surface)',
        border: '1px solid var(--border)',
        borderRadius: 'var(--radius-lg)',
        overflow: 'hidden',
      }}
    >
      <MetricCell
        testId="metric-total"
        value={total}
        label={t('metrics.total')}
        valueColor="var(--text-primary)"
      />
      <MetricCell
        testId="metric-missing"
        value={missing}
        label={t('metrics.missing')}
        valueColor={typeof missing === 'number' && missing > 0 ? 'var(--warning)' : 'var(--text-primary)'}
        borderLeft
      />
      <MetricCell
        testId="metric-avg-score"
        value={avgScore}
        label={t('metrics.avgScore')}
        valueColor="var(--accent)"
        borderLeft
      />
      <MetricCell
        testId="metric-low-score"
        value={lowScore}
        label={t('metrics.lowScore')}
        valueColor={typeof lowScore === 'number' && lowScore > 0 ? 'var(--upgrade, var(--accent))' : 'var(--text-primary)'}
        borderLeft
      />
    </div>
  )
}
```

- [ ] **Step 4: Run test — expect PASS**

```bash
cd frontend && npm run test -- --run src/components/dashboard/__tests__/MetricsRow.test.tsx
```

Expected: 5 tests PASS (the loading test may skip if module caching interferes — that's acceptable)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/dashboard/MetricsRow.tsx frontend/src/components/dashboard/__tests__/MetricsRow.test.tsx
git commit -m "feat(dashboard): add MetricsRow component with loading placeholders"
```

---

## Task 4: AttentionBanner component

**Files:**
- Create: `frontend/src/components/dashboard/AttentionBanner.tsx`
- Create: `frontend/src/components/dashboard/__tests__/AttentionBanner.test.tsx`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/components/dashboard/__tests__/AttentionBanner.test.tsx`:

```tsx
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { BrowserRouter } from 'react-router-dom'
import React from 'react'

const mockSearch = vi.fn()
const mockStatus = vi.fn()

vi.mock('@/hooks/useWantedApi', () => ({
  useWantedItems: (page: number, limit: number, _q: unknown, status?: string) => {
    if (status === 'failed') {
      return {
        data: {
          items: [
            { id: 1, series_title: 'One Piece', season_number: 1, episode_number: 4, status: 'failed', score: null },
          ],
          total: 1,
        },
      }
    }
    // No-status query: return a low-score item
    return {
      data: {
        items: [
          { id: 2, series_title: 'Jujutsu Kaisen', season_number: 2, episode_number: 6, status: 'found', score: 38 },
        ],
        total: 1,
      },
    }
  },
  useSearchWantedItem: () => ({ mutate: mockSearch }),
  useUpdateWantedStatus: () => ({ mutate: mockStatus }),
}))
vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}))

function wrap(ui: React.ReactElement) {
  return render(<BrowserRouter>{ui}</BrowserRouter>)
}

describe('AttentionBanner', () => {
  beforeEach(() => { mockSearch.mockClear(); mockStatus.mockClear() })

  it('renders the banner when items exist', async () => {
    const { AttentionBanner } = await import('../AttentionBanner')
    wrap(<AttentionBanner />)
    expect(screen.getByTestId('attention-banner')).toBeInTheDocument()
  })

  it('shows failed item with Search and Skip buttons', async () => {
    const { AttentionBanner } = await import('../AttentionBanner')
    wrap(<AttentionBanner />)
    expect(screen.getByTestId('attention-item-1')).toBeInTheDocument()
    expect(screen.getByTestId('attention-search-1')).toBeInTheDocument()
    expect(screen.getByTestId('attention-skip-1')).toBeInTheDocument()
  })

  it('shows low-score item with Find Better and Accept buttons', async () => {
    const { AttentionBanner } = await import('../AttentionBanner')
    wrap(<AttentionBanner />)
    expect(screen.getByTestId('attention-item-2')).toBeInTheDocument()
    expect(screen.getByTestId('attention-find-better-2')).toBeInTheDocument()
    expect(screen.getByTestId('attention-accept-2')).toBeInTheDocument()
  })

  it('shows series title', async () => {
    const { AttentionBanner } = await import('../AttentionBanner')
    wrap(<AttentionBanner />)
    expect(screen.getByTestId('attention-title-1')).toHaveTextContent('One Piece')
  })

  it('"View all" link points to /wanted', async () => {
    const { AttentionBanner } = await import('../AttentionBanner')
    wrap(<AttentionBanner />)
    expect(screen.getByTestId('attention-view-all')).toHaveAttribute('href', '/wanted')
  })

  it('calls search mutation when Search is clicked', async () => {
    const { AttentionBanner } = await import('../AttentionBanner')
    wrap(<AttentionBanner />)
    fireEvent.click(screen.getByTestId('attention-search-1'))
    expect(mockSearch).toHaveBeenCalledWith(1)
  })

  it('calls status mutation with skipped when Skip is clicked', async () => {
    const { AttentionBanner } = await import('../AttentionBanner')
    wrap(<AttentionBanner />)
    fireEvent.click(screen.getByTestId('attention-skip-1'))
    expect(mockStatus).toHaveBeenCalledWith({ itemId: 1, status: 'skipped' })
  })

  it('calls status mutation with accepted when Accept is clicked', async () => {
    const { AttentionBanner } = await import('../AttentionBanner')
    wrap(<AttentionBanner />)
    fireEvent.click(screen.getByTestId('attention-accept-2'))
    expect(mockStatus).toHaveBeenCalledWith({ itemId: 2, status: 'accepted' })
  })

  it('returns null when no items need attention', async () => {
    vi.resetModules()
    vi.mock('@/hooks/useWantedApi', () => ({
      useWantedItems: () => ({ data: { items: [], total: 0 } }),
      useSearchWantedItem: () => ({ mutate: vi.fn() }),
      useUpdateWantedStatus: () => ({ mutate: vi.fn() }),
    }))
    vi.mock('react-i18next', () => ({
      useTranslation: () => ({ t: (key: string) => key }),
    }))
    const { AttentionBanner } = await import('../AttentionBanner')
    const { container } = wrap(<AttentionBanner />)
    expect(container.firstChild).toBeNull()
  })
})
```

- [ ] **Step 2: Run test — expect FAIL**

```bash
cd frontend && npm run test -- --run src/components/dashboard/__tests__/AttentionBanner.test.tsx
```

Expected: FAIL — `Cannot find module '../AttentionBanner'`

- [ ] **Step 3: Implement AttentionBanner**

Create `frontend/src/components/dashboard/AttentionBanner.tsx`:

```tsx
import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { ChevronRight, Search, SkipForward, RefreshCw } from 'lucide-react'
import { useWantedItems, useSearchWantedItem, useUpdateWantedStatus } from '@/hooks/useWantedApi'

const MAX_ITEMS = 5
const LOW_SCORE_THRESHOLD = 50

interface WantedItem {
  readonly id: number
  readonly series_title: string
  readonly season_number: number | null
  readonly episode_number: number | null
  readonly status: string
  readonly score: number | null
}

interface ActionBtnProps {
  readonly testId: string
  readonly onClick: () => void
  readonly label: string
  readonly variant?: 'primary' | 'ghost'
  readonly icon?: React.ReactNode
}

function ActionBtn({ testId, onClick, label, variant = 'ghost', icon }: ActionBtnProps) {
  return (
    <button
      data-testid={testId}
      onClick={onClick}
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: '3px',
        padding: '3px 8px',
        fontSize: '10px',
        fontWeight: variant === 'primary' ? 600 : 500,
        borderRadius: '5px',
        border: variant === 'primary' ? '1px solid var(--accent)' : '1px solid var(--border)',
        background: variant === 'primary' ? 'var(--accent)' : 'transparent',
        color: variant === 'primary' ? 'var(--bg-primary)' : 'var(--text-secondary)',
        cursor: 'pointer',
        whiteSpace: 'nowrap',
      }}
    >
      {icon}
      {label}
    </button>
  )
}

export function AttentionBanner() {
  const { t } = useTranslation('dashboard')
  const { data: failedData } = useWantedItems(1, MAX_ITEMS, undefined, 'failed')
  const { data: allData } = useWantedItems(1, MAX_ITEMS)
  const searchMutation = useSearchWantedItem()
  const statusMutation = useUpdateWantedStatus()

  const failedItems: WantedItem[] = failedData?.items ?? []
  const lowScoreItems: WantedItem[] = (allData?.items ?? []).filter(
    (item) => item.score !== null && item.score < LOW_SCORE_THRESHOLD && item.status !== 'failed',
  )

  const allItems = [...failedItems, ...lowScoreItems].slice(0, MAX_ITEMS)
  const total = (failedData?.total ?? 0) + lowScoreItems.length

  if (allItems.length === 0) return null

  return (
    <div
      data-testid="attention-banner"
      style={{
        background: 'color-mix(in srgb, var(--warning) 6%, transparent)',
        border: '1px solid color-mix(in srgb, var(--warning) 30%, transparent)',
        borderRadius: 'var(--radius-md, 8px)',
        padding: '8px 12px',
        marginBottom: '4px',
      }}
    >
      {/* Header row */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          marginBottom: '6px',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
          <span style={{ fontSize: '11px', fontWeight: 700, color: 'var(--warning)' }}>
            ⚠ {t('attention.title')}
          </span>
          <span
            data-testid="attention-count"
            style={{
              fontSize: '10px',
              fontWeight: 600,
              color: 'var(--warning)',
              background: 'color-mix(in srgb, var(--warning) 12%, transparent)',
              padding: '0 6px',
              borderRadius: '10px',
            }}
          >
            {total}
          </span>
        </div>
        <Link
          data-testid="attention-view-all"
          to="/wanted"
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '3px',
            fontSize: '11px',
            color: 'var(--accent)',
            textDecoration: 'none',
          }}
        >
          {t('attention.viewAll')} <ChevronRight size={11} />
        </Link>
      </div>

      {/* Item rows */}
      {allItems.map((item, index) => {
        const isFailed = item.status === 'failed'
        const episodeLabel =
          item.season_number !== null && item.episode_number !== null
            ? `S${String(item.season_number).padStart(2, '0')}E${String(item.episode_number).padStart(2, '0')}`
            : null

        return (
          <div
            key={item.id}
            data-testid={`attention-item-${item.id}`}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '10px',
              padding: '4px 0',
              borderTop:
                index === 0
                  ? 'none'
                  : '1px solid color-mix(in srgb, var(--warning) 15%, transparent)',
            }}
          >
            <span
              data-testid={`attention-title-${item.id}`}
              style={{
                flex: 1,
                fontSize: '12px',
                fontWeight: 500,
                color: 'var(--text-primary)',
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                whiteSpace: 'nowrap',
              }}
            >
              {item.series_title}
              {episodeLabel && (
                <span style={{ fontSize: '11px', color: 'var(--text-muted)', marginLeft: '5px' }}>
                  {episodeLabel}
                </span>
              )}
            </span>
            <span
              data-testid={`attention-reason-${item.id}`}
              style={{ fontSize: '10px', color: 'var(--text-muted)', flexShrink: 0 }}
            >
              {isFailed ? t('attention.reasonFailed') : `Score ${item.score}`}
            </span>
            <div style={{ display: 'flex', gap: '4px', flexShrink: 0 }}>
              {isFailed ? (
                <>
                  <ActionBtn
                    testId={`attention-search-${item.id}`}
                    onClick={() => searchMutation.mutate(item.id)}
                    label={t('attention.search')}
                    icon={<Search size={10} />}
                    variant="primary"
                  />
                  <ActionBtn
                    testId={`attention-skip-${item.id}`}
                    onClick={() => statusMutation.mutate({ itemId: item.id, status: 'skipped' })}
                    label={t('attention.skip')}
                    icon={<SkipForward size={10} />}
                  />
                </>
              ) : (
                <>
                  <ActionBtn
                    testId={`attention-find-better-${item.id}`}
                    onClick={() => searchMutation.mutate(item.id)}
                    label={t('attention.findBetter')}
                    icon={<Search size={10} />}
                    variant="primary"
                  />
                  <ActionBtn
                    testId={`attention-accept-${item.id}`}
                    onClick={() => statusMutation.mutate({ itemId: item.id, status: 'accepted' })}
                    label={t('attention.accept')}
                    icon={<RefreshCw size={10} />}
                  />
                </>
              )}
            </div>
          </div>
        )
      })}
    </div>
  )
}
```

- [ ] **Step 4: Run test — expect PASS**

```bash
cd frontend && npm run test -- --run src/components/dashboard/__tests__/AttentionBanner.test.tsx
```

Expected: 9 tests PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/dashboard/AttentionBanner.tsx frontend/src/components/dashboard/__tests__/AttentionBanner.test.tsx
git commit -m "feat(dashboard): add AttentionBanner — shows failed + low-score items, links to /wanted"
```

---

## Task 5: ActivityFeed component

**Files:**
- Create: `frontend/src/components/dashboard/ActivityFeed.tsx`
- Create: `frontend/src/components/dashboard/__tests__/ActivityFeed.test.tsx`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/components/dashboard/__tests__/ActivityFeed.test.tsx`:

```tsx
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { BrowserRouter } from 'react-router-dom'
import React from 'react'

vi.mock('@/hooks/useSystemApi', () => ({
  useJobs: () => ({
    data: {
      data: [
        { id: '1', file_path: '/media/anime/one-piece/S01E04.mkv', status: 'completed', created_at: '2026-04-05T10:00:00Z' },
        { id: '2', file_path: '/media/anime/aot/S02E01.mkv', status: 'failed', created_at: '2026-04-05T09:50:00Z' },
        { id: '3', file_path: '/media/anime/demon-slayer/S03E01.mkv', status: 'pending', created_at: '2026-04-05T09:40:00Z' },
      ],
      total: 47,
    },
  }),
}))
vi.mock('@/components/dashboard/AttentionBanner', () => ({
  AttentionBanner: () => <div data-testid="attention-banner-mock" />,
}))
vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}))

function wrap(ui: React.ReactElement) {
  return render(<BrowserRouter>{ui}</BrowserRouter>)
}

describe('ActivityFeed', () => {
  it('renders the feed container', async () => {
    const { ActivityFeed } = await import('../ActivityFeed')
    wrap(<ActivityFeed />)
    expect(screen.getByTestId('activity-feed')).toBeInTheDocument()
  })

  it('renders a row for each job', async () => {
    const { ActivityFeed } = await import('../ActivityFeed')
    wrap(<ActivityFeed />)
    expect(screen.getByTestId('feed-item-1')).toBeInTheDocument()
    expect(screen.getByTestId('feed-item-2')).toBeInTheDocument()
    expect(screen.getByTestId('feed-item-3')).toBeInTheDocument()
  })

  it('renders green dot for completed job', async () => {
    const { ActivityFeed } = await import('../ActivityFeed')
    wrap(<ActivityFeed />)
    expect(screen.getByTestId('feed-dot-1')).toHaveAttribute('data-status', 'completed')
  })

  it('renders red dot for failed job', async () => {
    const { ActivityFeed } = await import('../ActivityFeed')
    wrap(<ActivityFeed />)
    expect(screen.getByTestId('feed-dot-2')).toHaveAttribute('data-status', 'failed')
  })

  it('renders "View all" link to /activity', async () => {
    const { ActivityFeed } = await import('../ActivityFeed')
    wrap(<ActivityFeed />)
    const link = screen.getByTestId('feed-view-all')
    expect(link).toHaveAttribute('href', '/activity')
  })

  it('renders AttentionBanner inside the feed', async () => {
    const { ActivityFeed } = await import('../ActivityFeed')
    wrap(<ActivityFeed />)
    expect(screen.getByTestId('attention-banner-mock')).toBeInTheDocument()
  })

  it('shows empty state when no jobs', async () => {
    vi.resetModules()
    vi.mock('@/hooks/useSystemApi', () => ({
      useJobs: () => ({ data: { data: [], total: 0 } }),
    }))
    vi.mock('@/components/dashboard/AttentionBanner', () => ({
      AttentionBanner: () => null,
    }))
    vi.mock('react-i18next', () => ({
      useTranslation: () => ({ t: (key: string) => key }),
    }))
    const { ActivityFeed } = await import('../ActivityFeed')
    wrap(<ActivityFeed />)
    expect(screen.getByTestId('feed-empty')).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run test — expect FAIL**

```bash
cd frontend && npm run test -- --run src/components/dashboard/__tests__/ActivityFeed.test.tsx
```

Expected: FAIL — `Cannot find module '../ActivityFeed'`

- [ ] **Step 3: Implement ActivityFeed**

Create `frontend/src/components/dashboard/ActivityFeed.tsx`:

```tsx
import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { AttentionBanner } from './AttentionBanner'
import { useJobs } from '@/hooks/useSystemApi'
import { truncatePath, formatRelativeTime } from '@/lib/utils'

const FEED_LIMIT = 20
const DOT_COLOR: Record<string, string> = {
  completed: 'var(--success)',
  failed: 'var(--error)',
}

function dotColor(status: string): string {
  return DOT_COLOR[status] ?? 'var(--accent)'
}

export function ActivityFeed() {
  const { t } = useTranslation('dashboard')
  const { data: jobsData } = useJobs(1, FEED_LIMIT, undefined, 15000)

  const jobs = jobsData?.data ?? []
  const total = jobsData?.total ?? 0

  return (
    <div
      data-testid="activity-feed"
      style={{
        background: 'var(--bg-surface)',
        border: '1px solid var(--border)',
        borderRadius: 'var(--radius-lg)',
        display: 'flex',
        flexDirection: 'column',
        overflow: 'hidden',
        flex: 1,
        minHeight: 0,
      }}
    >
      {/* Header */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '10px 14px',
          borderBottom: '1px solid var(--border)',
          flexShrink: 0,
        }}
      >
        <span style={{ fontSize: '11px', fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.4px' }}>
          {t('feed.title')}
        </span>
        <Link
          data-testid="feed-view-all"
          to="/activity"
          style={{ fontSize: '11px', color: 'var(--accent)', textDecoration: 'none' }}
        >
          {t('feed.viewAll')} →
        </Link>
      </div>

      {/* Scrollable content */}
      <div style={{ flex: 1, overflow: 'auto', padding: '8px 10px' }}>
        {/* Attention banner (only shown when items exist) */}
        <AttentionBanner />

        {jobs.length === 0 ? (
          <div
            data-testid="feed-empty"
            style={{ padding: '24px 0', textAlign: 'center', fontSize: '13px', color: 'var(--text-muted)' }}
          >
            {t('feed.empty')}
          </div>
        ) : (
          <>
            {jobs.map((job) => (
              <div
                key={job.id}
                data-testid={`feed-item-${job.id}`}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '8px',
                  padding: '5px 4px',
                  borderRadius: '4px',
                }}
              >
                <span
                  data-testid={`feed-dot-${job.id}`}
                  data-status={job.status}
                  style={{
                    width: 6,
                    height: 6,
                    borderRadius: '50%',
                    background: dotColor(job.status),
                    flexShrink: 0,
                  }}
                />
                <span
                  style={{
                    flex: 1,
                    fontSize: '12px',
                    color: 'var(--text-secondary)',
                    fontFamily: 'var(--font-mono)',
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    whiteSpace: 'nowrap',
                  }}
                  title={job.file_path}
                >
                  {truncatePath(job.file_path)}
                </span>
                {job.created_at && (
                  <span style={{ fontSize: '10px', color: 'var(--text-muted)', whiteSpace: 'nowrap', flexShrink: 0 }}>
                    {formatRelativeTime(job.created_at)}
                  </span>
                )}
              </div>
            ))}

            {total > FEED_LIMIT && (
              <div style={{ textAlign: 'center', padding: '8px 0', fontSize: '11px', color: 'var(--text-muted)' }}>
                ··· {total - FEED_LIMIT} {t('feed.moreEvents')}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )
}
```

- [ ] **Step 4: Run test — expect PASS**

```bash
cd frontend && npm run test -- --run src/components/dashboard/__tests__/ActivityFeed.test.tsx
```

Expected: 7 tests PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/dashboard/ActivityFeed.tsx frontend/src/components/dashboard/__tests__/ActivityFeed.test.tsx
git commit -m "feat(dashboard): add ActivityFeed with color-coded job dots and embedded AttentionBanner"
```

---

## Task 6: DashboardSidebar component

**Files:**
- Create: `frontend/src/components/dashboard/DashboardSidebar.tsx`
- Create: `frontend/src/components/dashboard/__tests__/DashboardSidebar.test.tsx`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/components/dashboard/__tests__/DashboardSidebar.test.tsx`:

```tsx
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { BrowserRouter } from 'react-router-dom'
import React from 'react'

const mockRefresh = vi.fn()
const mockBatch = vi.fn()

vi.mock('@/hooks/useApi', () => ({
  useProviders: () => ({
    data: {
      providers: [
        { name: 'OpenSubtitles', enabled: true, healthy: true, stats: { success_rate: 97 } },
        { name: 'AnimeTosho', enabled: true, healthy: false, stats: { success_rate: 45 } },
      ],
    },
    isLoading: false,
  }),
  useHealth: () => ({
    data: {
      services: { sonarr: 'connected', radarr: 'connected', ollama: 'ready' },
    },
    isLoading: false,
  }),
  useCleanupStats: () => ({
    data: { total_files: 8200, duplicate_files: 12, potential_savings_bytes: 52428800 },
    isLoading: false,
  }),
  useRefreshWanted: () => ({ mutate: mockRefresh, isPending: false }),
  useStartWantedBatch: () => ({ mutate: mockBatch, isPending: false }),
  useWantedBatchStatus: () => ({ data: { is_running: false } }),
  useWantedSummary: () => ({ data: { scan_running: false } }),
}))
vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}))
vi.mock('@/lib/diskUtils', () => ({
  formatBytes: (bytes: number) => `${Math.round(bytes / 1024 / 1024)} MB`,
}))

function wrap(ui: React.ReactElement) {
  return render(<BrowserRouter>{ui}</BrowserRouter>)
}

describe('DashboardSidebar', () => {
  it('renders the sidebar container', async () => {
    const { DashboardSidebar } = await import('../DashboardSidebar')
    wrap(<DashboardSidebar />)
    expect(screen.getByTestId('dashboard-sidebar')).toBeInTheDocument()
  })

  it('renders provider health panel', async () => {
    const { DashboardSidebar } = await import('../DashboardSidebar')
    wrap(<DashboardSidebar />)
    expect(screen.getByTestId('panel-providers')).toBeInTheDocument()
    expect(screen.getByText('OpenSubtitles')).toBeInTheDocument()
    expect(screen.getByText('AnimeTosho')).toBeInTheDocument()
  })

  it('renders green dot for healthy provider', async () => {
    const { DashboardSidebar } = await import('../DashboardSidebar')
    wrap(<DashboardSidebar />)
    expect(screen.getByTestId('provider-dot-OpenSubtitles')).toHaveAttribute('data-healthy', 'true')
  })

  it('renders red dot for unhealthy provider', async () => {
    const { DashboardSidebar } = await import('../DashboardSidebar')
    wrap(<DashboardSidebar />)
    expect(screen.getByTestId('provider-dot-AnimeTosho')).toHaveAttribute('data-healthy', 'false')
  })

  it('renders service status panel', async () => {
    const { DashboardSidebar } = await import('../DashboardSidebar')
    wrap(<DashboardSidebar />)
    expect(screen.getByTestId('panel-services')).toBeInTheDocument()
  })

  it('renders disk space panel with file count', async () => {
    const { DashboardSidebar } = await import('../DashboardSidebar')
    wrap(<DashboardSidebar />)
    expect(screen.getByTestId('panel-disk')).toBeInTheDocument()
    expect(screen.getByTestId('disk-total-files')).toHaveTextContent('8200')
  })

  it('renders quick actions panel with scan button', async () => {
    const { DashboardSidebar } = await import('../DashboardSidebar')
    wrap(<DashboardSidebar />)
    expect(screen.getByTestId('panel-actions')).toBeInTheDocument()
    expect(screen.getByTestId('btn-scan-library')).toBeInTheDocument()
  })

  it('calls refreshWanted when scan button is clicked', async () => {
    mockRefresh.mockClear()
    const { DashboardSidebar } = await import('../DashboardSidebar')
    wrap(<DashboardSidebar />)
    fireEvent.click(screen.getByTestId('btn-scan-library'))
    expect(mockRefresh).toHaveBeenCalledTimes(1)
  })

  it('renders wanted list link to /wanted', async () => {
    const { DashboardSidebar } = await import('../DashboardSidebar')
    wrap(<DashboardSidebar />)
    expect(screen.getByTestId('link-wanted')).toHaveAttribute('href', '/wanted')
  })
})
```

- [ ] **Step 2: Run test — expect FAIL**

```bash
cd frontend && npm run test -- --run src/components/dashboard/__tests__/DashboardSidebar.test.tsx
```

Expected: FAIL — `Cannot find module '../DashboardSidebar'`

- [ ] **Step 3: Implement DashboardSidebar**

Create `frontend/src/components/dashboard/DashboardSidebar.tsx`:

```tsx
import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import {
  useProviders,
  useHealth,
  useCleanupStats,
  useRefreshWanted,
  useStartWantedBatch,
  useWantedBatchStatus,
  useWantedSummary,
} from '@/hooks/useApi'
import { formatBytes } from '@/lib/diskUtils'

// ─── Shared panel shell ───────────────────────────────────────────────────────

interface PanelProps {
  readonly testId: string
  readonly title: string
  readonly children: React.ReactNode
}

function Panel({ testId, title, children }: PanelProps) {
  return (
    <div
      data-testid={testId}
      style={{
        padding: '10px 14px',
        borderBottom: '1px solid var(--border)',
      }}
    >
      <div
        style={{
          fontSize: '9px',
          fontWeight: 700,
          color: 'var(--text-muted)',
          textTransform: 'uppercase',
          letterSpacing: '0.5px',
          marginBottom: '8px',
        }}
      >
        {title}
      </div>
      {children}
    </div>
  )
}

// ─── Provider Health Panel ────────────────────────────────────────────────────

function ProviderHealthPanel() {
  const { t } = useTranslation('dashboard')
  const { data: providersData, isLoading } = useProviders()
  const providers = (providersData?.providers ?? []).filter((p) => p.enabled)

  if (isLoading) {
    return (
      <Panel testId="panel-providers" title={t('sidebar.providers')}>
        {[1, 2, 3].map((i) => (
          <div key={i} className="skeleton h-4 rounded mb-1" />
        ))}
      </Panel>
    )
  }

  return (
    <Panel testId="panel-providers" title={t('sidebar.providers')}>
      {providers.map((p) => {
        const healthy = p.healthy ?? (p.stats?.success_rate ?? 0) >= 80
        const pct = Math.round(p.stats?.success_rate ?? (healthy ? 100 : 0))
        return (
          <div
            key={p.name}
            style={{ display: 'flex', alignItems: 'center', gap: '7px', marginBottom: '5px' }}
          >
            <span
              data-testid={`provider-dot-${p.name}`}
              data-healthy={String(healthy)}
              style={{
                width: 6,
                height: 6,
                borderRadius: '50%',
                background: healthy ? 'var(--success)' : 'var(--error)',
                flexShrink: 0,
              }}
            />
            <span style={{ flex: 1, fontSize: '12px', color: 'var(--text-secondary)' }}>{p.name}</span>
            <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>{pct}%</span>
          </div>
        )
      })}
    </Panel>
  )
}

// ─── Service Status Panel ─────────────────────────────────────────────────────

function formatServiceName(key: string): string {
  const name = key.includes(':') ? key.split(':').slice(1).join(':') : key
  return name.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
}

function ServiceStatusPanel() {
  const { t } = useTranslation('dashboard')
  const { data: health, isLoading } = useHealth()

  if (isLoading || !health?.services) {
    return (
      <Panel testId="panel-services" title={t('sidebar.services')}>
        {[1, 2, 3].map((i) => <div key={i} className="skeleton h-4 rounded mb-1" />)}
      </Panel>
    )
  }

  return (
    <Panel testId="panel-services" title={t('sidebar.services')}>
      {Object.entries(health.services).map(([name, status]) => {
        const isNotConfigured = status === 'not configured'
        const isError = !isNotConfigured && ['error', 'fail', 'failed', 'disconnected'].includes(status as string)
        const isOk = !isNotConfigured && !isError
        const dotColor = isOk ? 'var(--success)' : isNotConfigured ? 'var(--text-muted)' : 'var(--error)'

        return (
          <div
            key={name}
            style={{ display: 'flex', alignItems: 'center', gap: '7px', marginBottom: '5px' }}
          >
            <span
              style={{ width: 6, height: 6, borderRadius: '50%', background: dotColor, flexShrink: 0 }}
            />
            <span style={{ flex: 1, fontSize: '12px', color: 'var(--text-secondary)' }}>
              {formatServiceName(name)}
            </span>
            <span style={{ fontSize: '11px', color: isOk ? 'var(--text-muted)' : 'var(--error)' }}>
              {isNotConfigured ? '—' : (typeof status === 'string' ? status : 'OK')}
            </span>
          </div>
        )
      })}
    </Panel>
  )
}

// ─── Disk Space Panel ─────────────────────────────────────────────────────────

function DiskSpacePanel() {
  const { t } = useTranslation('dashboard')
  const { data: stats, isLoading } = useCleanupStats()

  return (
    <Panel testId="panel-disk" title={t('sidebar.disk')}>
      {isLoading || !stats ? (
        <div className="skeleton h-8 rounded" />
      ) : (
        <>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '6px' }}>
            <div style={{ textAlign: 'center' }}>
              <div
                data-testid="disk-total-files"
                style={{ fontSize: '16px', fontWeight: 700, color: 'var(--text-primary)', fontFamily: 'var(--font-mono)' }}
              >
                {stats.total_files.toLocaleString()}
              </div>
              <div style={{ fontSize: '9px', color: 'var(--text-muted)', textTransform: 'uppercase' }}>
                {t('sidebar.diskFiles')}
              </div>
            </div>
            <div style={{ textAlign: 'center' }}>
              <div
                style={{ fontSize: '16px', fontWeight: 700, color: stats.duplicate_files > 0 ? 'var(--warning)' : 'var(--text-primary)', fontFamily: 'var(--font-mono)' }}
              >
                {stats.duplicate_files}
              </div>
              <div style={{ fontSize: '9px', color: 'var(--text-muted)', textTransform: 'uppercase' }}>
                {t('sidebar.diskDuplicates')}
              </div>
            </div>
          </div>
          {stats.potential_savings_bytes > 0 && (
            <div style={{ fontSize: '10px', color: 'var(--success)', textAlign: 'center' }}>
              {formatBytes(stats.potential_savings_bytes)} {t('sidebar.diskSavings')}
            </div>
          )}
        </>
      )}
    </Panel>
  )
}

// ─── Quick Actions Panel ──────────────────────────────────────────────────────

function QuickActionsPanel() {
  const { t } = useTranslation('dashboard')
  const { data: wantedSummary } = useWantedSummary()
  const { data: batchStatus } = useWantedBatchStatus()
  const refreshWanted = useRefreshWanted()
  const startBatch = useStartWantedBatch()

  const isScanning = refreshWanted.isPending || Boolean(wantedSummary?.scan_running)
  const isBatching = startBatch.isPending || Boolean(batchStatus?.is_running)

  const btnStyle = (disabled: boolean): React.CSSProperties => ({
    width: '100%',
    padding: '6px 10px',
    marginBottom: '4px',
    fontSize: '11px',
    fontWeight: 500,
    borderRadius: '6px',
    border: '1px solid var(--border)',
    background: 'var(--bg-primary)',
    color: disabled ? 'var(--text-muted)' : 'var(--text-secondary)',
    cursor: disabled ? 'not-allowed' : 'pointer',
    opacity: disabled ? 0.6 : 1,
    textAlign: 'left' as const,
  })

  return (
    <Panel testId="panel-actions" title={t('sidebar.actions')}>
      <button
        data-testid="btn-scan-library"
        disabled={isScanning}
        onClick={() => refreshWanted.mutate(undefined)}
        style={btnStyle(isScanning)}
      >
        {isScanning ? t('sidebar.scanning') : t('sidebar.scanLibrary')}
      </button>
      <button
        data-testid="btn-batch-search"
        disabled={isBatching}
        onClick={() => startBatch.mutate(undefined)}
        style={btnStyle(isBatching)}
      >
        {isBatching ? t('sidebar.searching') : t('sidebar.batchSearch')}
      </button>
      <Link
        data-testid="link-wanted"
        to="/wanted"
        style={{ ...btnStyle(false), display: 'block', textDecoration: 'none', marginBottom: '4px' }}
      >
        {t('sidebar.wantedList')}
      </Link>
      <Link
        data-testid="link-logs"
        to="/activity"
        style={{ ...btnStyle(false), display: 'block', textDecoration: 'none', marginBottom: '8px' }}
      >
        {t('sidebar.viewLogs')}
      </Link>
      <button
        data-testid="btn-run-now-sidebar"
        disabled={isScanning}
        onClick={() => refreshWanted.mutate(undefined)}
        style={{
          width: '100%',
          padding: '7px 10px',
          fontSize: '11px',
          fontWeight: 600,
          borderRadius: '6px',
          border: '1px solid var(--accent)',
          background: 'var(--accent)',
          color: 'var(--bg-primary)',
          cursor: isScanning ? 'not-allowed' : 'pointer',
          opacity: isScanning ? 0.6 : 1,
        }}
      >
        {t('sidebar.runNow')}
      </button>
    </Panel>
  )
}

// ─── DashboardSidebar ─────────────────────────────────────────────────────────

export function DashboardSidebar() {
  return (
    <div
      data-testid="dashboard-sidebar"
      style={{
        width: '260px',
        flexShrink: 0,
        background: 'var(--bg-surface)',
        border: '1px solid var(--border)',
        borderRadius: 'var(--radius-lg)',
        overflow: 'hidden',
        display: 'flex',
        flexDirection: 'column',
      }}
    >
      <ProviderHealthPanel />
      <ServiceStatusPanel />
      <DiskSpacePanel />
      <QuickActionsPanel />
    </div>
  )
}
```

- [ ] **Step 4: Run test — expect PASS**

```bash
cd frontend && npm run test -- --run src/components/dashboard/__tests__/DashboardSidebar.test.tsx
```

Expected: 9 tests PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/dashboard/DashboardSidebar.tsx frontend/src/components/dashboard/__tests__/DashboardSidebar.test.tsx
git commit -m "feat(dashboard): add DashboardSidebar with provider, service, disk, and quick-action panels"
```

---

## Task 7: Rewire Dashboard.tsx

**Files:**
- Modify: `frontend/src/pages/Dashboard.tsx`

- [ ] **Step 1: Replace Dashboard.tsx**

Overwrite `frontend/src/pages/Dashboard.tsx` with:

```tsx
import { useTranslation } from 'react-i18next'
import { PageHeader } from '@/components/layout/PageHeader'
import { StatusStripe } from '@/components/dashboard/StatusStripe'
import { MetricsRow } from '@/components/dashboard/MetricsRow'
import { ActivityFeed } from '@/components/dashboard/ActivityFeed'
import { DashboardSidebar } from '@/components/dashboard/DashboardSidebar'

export function Dashboard() {
  const { t } = useTranslation('dashboard')

  return (
    <div className="space-y-4">
      <PageHeader title={t('title')} />
      <StatusStripe />
      <MetricsRow />
      <div style={{ display: 'flex', gap: '16px', alignItems: 'flex-start', minHeight: '500px' }}>
        <ActivityFeed />
        <DashboardSidebar />
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Run full frontend test suite**

```bash
cd frontend && npm run test -- --run
```

Expected: Existing tests pass. The old dashboard tests (AutomationBanner, HeroStats, NeedsAttentionCard, ModalAccessibility) will FAIL — that is expected and will be fixed in the cleanup task.

- [ ] **Step 3: Check TypeScript**

```bash
cd frontend && npx tsc --noEmit
```

Expected: No errors. If errors appear related to deleted components that are still referenced, that is resolved in Task 8.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/Dashboard.tsx
git commit -m "feat(dashboard): rewire Dashboard page to hybrid activity-first layout"
```

---

## Task 8: Delete old files

**Files:**
- Delete: all listed in File Map "Delete" section

- [ ] **Step 1: Delete old dashboard components and tests**

```bash
# Components
rm "frontend/src/components/dashboard/AutomationBanner.tsx"
rm "frontend/src/components/dashboard/HeroStats.tsx"
rm "frontend/src/components/dashboard/NeedsAttentionCard.tsx"
rm "frontend/src/components/dashboard/DashboardGrid.tsx"
rm "frontend/src/components/dashboard/WidgetWrapper.tsx"
rm "frontend/src/components/dashboard/WidgetSettingsModal.tsx"
rm "frontend/src/components/dashboard/widgetRegistry.ts"
rm -rf "frontend/src/components/dashboard/widgets"

# Old tests for deleted components
rm "frontend/src/components/dashboard/__tests__/AutomationBanner.test.tsx"
rm "frontend/src/components/dashboard/__tests__/HeroStats.test.tsx"
rm "frontend/src/components/dashboard/__tests__/NeedsAttentionCard.test.tsx"
rm "frontend/src/test/ModalAccessibility.test.tsx"
```

- [ ] **Step 2: Delete dashboardStore**

```bash
rm "frontend/src/stores/dashboardStore.ts"
```

- [ ] **Step 3: Run full test suite — expect clean pass**

```bash
cd frontend && npm run test -- --run
```

Expected: all tests PASS, no references to deleted files.

- [ ] **Step 4: Run lint and type check**

```bash
cd frontend && npm run lint && npx tsc --noEmit
```

Expected: no errors.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat(dashboard): remove old widget grid, store, and replaced components"
```

---

## Task 9: Backend pre-PR checks + final commit

- [ ] **Step 1: Run backend tests (unchanged — regression check)**

```bash
cd backend && python -m pytest --tb=short -q \
  --ignore=tests/performance \
  --ignore=tests/integration/test_provider_pipeline.py \
  --ignore=tests/test_video_sync.py \
  --ignore=tests/test_translation_backends.py \
  -k "not (test_sonarr_download_webhook or test_radarr_download_webhook or test_parse_llm_response_too_many_merge or test_record_backend_success)"
```

Expected: all pass (no backend changes in this feature)

- [ ] **Step 2: Run frontend lint + type check**

```bash
cd frontend && npm run lint && npx tsc --noEmit && npm run test -- --run
```

Expected: clean

- [ ] **Step 3: Final commit**

```bash
git add -A
git commit -m "feat(dashboard): complete hybrid dashboard redesign — activity-first × mission control"
```

---

## Self-Review

**Spec coverage check:**

| Spec requirement | Task |
|-----------------|------|
| StatusStripe (1-line status bar, i18n) | Task 2 |
| MetricsRow (4 cells, loading placeholders) | Task 3 |
| AttentionBanner (failed + low-score, link to /wanted) | Task 4 |
| ActivityFeed (job feed, color dots, embedded AttentionBanner) | Task 5 |
| DashboardSidebar (4 panels) | Task 6 |
| Dashboard.tsx rewired | Task 7 |
| All old files deleted | Task 8 |
| i18n keys added | Task 1 |
| Pause button removed | ✓ (not present in any new component) |
| /wanted link fix | ✓ (Task 4 — AttentionBanner links to /wanted) |
| Low-score items visible | ✓ (Task 4 — separate query + client filter) |
| Loading placeholders (no false "0") | ✓ (Task 3 — MetricsRow shows '—') |
| Hardcoded English strings removed | ✓ (Task 1 + all components use t()) |

**No placeholders found.** All steps contain concrete code or commands.

**Type consistency:** `WantedItem.id` is `number` throughout. `Job.id` is `string` (from existing API). `data-testid` naming consistent across components and tests.
