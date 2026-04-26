/**
 * SystemDiagnosticsPage.test.tsx — Tests for the observability + maintenance
 * sub-page split out from SystemSettings on 2026-04-26 (5 sections moved
 * here when the parent exceeded the FormLayout 6-cap).
 *
 * Sections covered:
 *   1. Log Viewer
 *   2. Disk Monitoring
 *   3. Cache Management
 *   4. Integrations  (advanced — collapsed by default)
 *   5. Migration     (advanced — collapsed by default)
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { SystemDiagnosticsPage } from '../SystemDiagnosticsPage'
import enSettings from '../../../i18n/locales/en/settings.json'

// ─── Mocks ───────────────────────────────────────────────────────────────────

function lookupKey(ns: Record<string, unknown>, key: string): string | undefined {
  const parts = key.split('.')
  let v: unknown = ns
  for (const p of parts) {
    if (typeof v !== 'object' || v === null) return undefined
    v = (v as Record<string, unknown>)[p]
  }
  return typeof v === 'string' ? v : undefined
}

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, opts?: string | Record<string, unknown>) => {
      if (typeof opts === 'string') return opts
      if (opts !== undefined && typeof opts === 'object' && 'count' in opts)
        return `${key}:${String(opts.count)}`
      return lookupKey(enSettings, key) ?? key.split('.').pop() ?? key
    },
  }),
}))

vi.mock('../ProtokollTab', () => ({
  ProtokollTab: () => <div data-testid="protokoll-tab">ProtokollTab</div>,
}))

vi.mock('../IntegrationsTab', () => ({
  IntegrationsTab: () => <div data-testid="integrations-tab">IntegrationsTab</div>,
}))

vi.mock('../MigrationTab', () => ({
  MigrationTab: () => <div data-testid="migration-tab">MigrationTab</div>,
}))

vi.mock('../CacheTab', () => ({
  CacheTab: () => <div data-testid="cache-tab">CacheTab</div>,
}))

const mockSaveConfig = vi.fn()

vi.mock('@/hooks/useApi', () => ({
  useConfig: () => ({
    data: {
      disk_warning_threshold_percent: 90,
      disk_warning_notify: 'true',
    },
    isLoading: false,
  }),
  useUpdateConfig: () => ({ mutate: mockSaveConfig, isPending: false }),
}))

// ─── Helpers ─────────────────────────────────────────────────────────────────

function renderPage() {
  return render(
    <MemoryRouter>
      <SystemDiagnosticsPage />
    </MemoryRouter>,
  )
}

// ─── Tests ────────────────────────────────────────────────────────────────────

describe('SystemDiagnosticsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  // ── Layout ────────────────────────────────────────────────────────────────

  it('renders inside SettingsDetailLayout', () => {
    renderPage()
    expect(screen.getByTestId('settings-detail-layout')).toBeInTheDocument()
  })

  it('renders the page heading "Diagnostics"', () => {
    renderPage()
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Diagnostics')
  })

  // ── Section presence ─────────────────────────────────────────────────────

  it('renders the Log Viewer section', () => {
    renderPage()
    expect(screen.getByTestId('section-log-viewer')).toBeInTheDocument()
  })

  it('renders the Disk Monitoring section', () => {
    renderPage()
    expect(screen.getByTestId('section-disk-monitoring')).toBeInTheDocument()
  })

  it('renders the Cache Management section', () => {
    renderPage()
    expect(screen.getByTestId('section-cache-management')).toBeInTheDocument()
  })

  it('renders the Integrations section', () => {
    renderPage()
    expect(screen.getByTestId('section-integrations')).toBeInTheDocument()
  })

  it('renders the Migration section', () => {
    renderPage()
    expect(screen.getByTestId('section-migration')).toBeInTheDocument()
  })

  it('renders exactly 5 settings sections', () => {
    renderPage()
    const sections = screen.getAllByTestId('settings-section')
    expect(sections).toHaveLength(5)
  })

  // ── Section titles ────────────────────────────────────────────────────────

  it('shows "Log Viewer" section title', () => {
    renderPage()
    const wrapper = screen.getByTestId('section-log-viewer')
    const title = wrapper.querySelector('[data-testid="settings-section-title"]')
    expect(title).toHaveTextContent('Log Viewer')
  })

  it('shows "Integrations" section title', () => {
    renderPage()
    const wrapper = screen.getByTestId('section-integrations')
    const title = wrapper.querySelector('[data-testid="settings-section-title"]')
    expect(title).toHaveTextContent('Integrations')
  })

  it('shows "Migration" section title', () => {
    renderPage()
    const wrapper = screen.getByTestId('section-migration')
    const title = wrapper.querySelector('[data-testid="settings-section-title"]')
    expect(title).toHaveTextContent('Migration')
  })

  // ── Advanced sections collapsed by default ────────────────────────────────

  it('Integrations advanced content is collapsed by default', () => {
    renderPage()
    const wrapper = screen.getByTestId('section-integrations')
    const toggle = wrapper.querySelector('[data-testid="settings-section-advanced-toggle"]')
    expect(toggle).toBeInTheDocument()
    expect(wrapper.querySelector('[data-testid="settings-section-advanced-content"]')).toBeNull()
  })

  it('Migration advanced content is collapsed by default', () => {
    renderPage()
    const wrapper = screen.getByTestId('section-migration')
    const toggle = wrapper.querySelector('[data-testid="settings-section-advanced-toggle"]')
    expect(toggle).toBeInTheDocument()
    expect(wrapper.querySelector('[data-testid="settings-section-advanced-content"]')).toBeNull()
  })

  it('Log Viewer section does not have an advanced toggle', () => {
    renderPage()
    const wrapper = screen.getByTestId('section-log-viewer')
    expect(
      wrapper.querySelector('[data-testid="settings-section-advanced-toggle"]'),
    ).toBeNull()
  })

  // ── Expanding advanced sections ───────────────────────────────────────────

  it('Integrations expands and shows content after clicking toggle', () => {
    renderPage()
    const wrapper = screen.getByTestId('section-integrations')
    const toggle = wrapper.querySelector(
      '[data-testid="settings-section-advanced-toggle"]',
    ) as HTMLElement
    fireEvent.click(toggle)
    expect(
      wrapper.querySelector('[data-testid="settings-section-advanced-content"]'),
    ).toBeInTheDocument()
  })

  it('Migration expands and shows content after clicking toggle', () => {
    renderPage()
    const wrapper = screen.getByTestId('section-migration')
    const toggle = wrapper.querySelector(
      '[data-testid="settings-section-advanced-toggle"]',
    ) as HTMLElement
    fireEvent.click(toggle)
    expect(
      wrapper.querySelector('[data-testid="settings-section-advanced-content"]'),
    ).toBeInTheDocument()
  })

  // ── Summary text ─────────────────────────────────────────────────────────

  it('shows a summary description inside the Integrations section', () => {
    renderPage()
    expect(screen.getByTestId('integrations-summary')).toBeInTheDocument()
  })

  it('shows a summary description inside the Migration section', () => {
    renderPage()
    expect(screen.getByTestId('migration-summary')).toBeInTheDocument()
  })
})

// ─── Disk Monitoring section ────────────────────────────────────────────────

describe('Disk Monitoring section', () => {
  beforeEach(() => { vi.clearAllMocks() })

  it('renders heading "Disk Monitoring"', () => {
    renderPage()
    const wrapper = screen.getByTestId('section-disk-monitoring')
    const title = wrapper.querySelector('[data-testid="settings-section-title"]')
    expect(title).toHaveTextContent('Disk Monitoring')
  })

  it('input-disk-warning-threshold-percent renders with value 90', () => {
    renderPage()
    const input = screen.getByTestId('input-disk-warning-threshold-percent') as HTMLInputElement
    expect(Number(input.value)).toBe(90)
  })

  it('toggle-disk-warning-notify renders checked by default', () => {
    renderPage()
    expect(screen.getByTestId('section-disk-monitoring')).toBeInTheDocument()
    const controls = screen.getByTestId('disk-monitoring-controls')
    const switches = controls.querySelectorAll('[role="switch"]')
    expect(switches[0]).toHaveAttribute('aria-checked', 'true')
  })

  it('changing threshold calls updateConfig with { disk_warning_threshold_percent: 85 }', () => {
    renderPage()
    const input = screen.getByTestId('input-disk-warning-threshold-percent')
    fireEvent.change(input, { target: { value: '85' } })
    expect(mockSaveConfig).toHaveBeenCalledWith({ disk_warning_threshold_percent: 85 })
  })
})
