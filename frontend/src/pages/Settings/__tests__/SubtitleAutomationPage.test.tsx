/**
 * SubtitleAutomationPage — 0.71.1 follow-up #2.
 *
 * Covers the three goals from the original 0.71.0 plan:
 *  - renders_master_and_granular_toggles
 *  - shows_queue_last_run_and_error
 *  - master_toggle_updates_package_keys
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { SubtitleAutomationPage } from '../SubtitleAutomationPage'

// ─── i18n ─────────────────────────────────────────────────────────────────────
vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (_key: string, defaultValueOrOpts?: string | { defaultValue?: string }) => {
      if (typeof defaultValueOrOpts === 'string') return defaultValueOrOpts
      return defaultValueOrOpts?.defaultValue ?? _key
    },
  }),
}))

// ─── Hooks the page depends on ────────────────────────────────────────────────
const updateMutate = vi.fn()
const runNowMutate = vi.fn()

let mockConfig: Record<string, unknown> = {}
let mockStatus: {
  enabled: boolean
  queue: { pending: number; running: number; failed: number; done: number }
  last_run_at: string | null
  last_run_status: string | null
  last_error: string | null
} = {
  enabled: true,
  queue: { pending: 0, running: 0, failed: 0, done: 0 },
  last_run_at: null,
  last_run_status: null,
  last_error: null,
}

vi.mock('@/hooks/useSystemApi', () => ({
  useConfig: () => ({ data: mockConfig, isLoading: false }),
  useUpdateConfig: () => ({ mutate: updateMutate, isPending: false }),
}))

vi.mock('@/hooks/useWantedApi', () => ({
  useAutomationStatus: () => ({ data: mockStatus, isLoading: false }),
  useRunAutomationNow: () => ({ mutate: runNowMutate, isPending: false }),
}))

vi.mock('@/components/shared/Toast', () => ({
  toast: vi.fn(),
}))

// Layout passthroughs — the page's content is what we want to assert on.
vi.mock('@/components/settings/SettingsDetailLayout', () => ({
  SettingsDetailLayout: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}))

vi.mock('@/components/settings/SettingsSection', () => ({
  SettingsSection: ({
    title,
    children,
  }: {
    title: string
    children: React.ReactNode
  }) => (
    <section>
      <h2>{title}</h2>
      {children}
    </section>
  ),
}))

vi.mock('@/components/shared/SettingRow', () => ({
  SettingRow: ({ label, children }: { label: string; children: React.ReactNode }) => (
    <div>
      <label>{label}</label>
      {children}
    </div>
  ),
}))

// Real Toggle would bring in its own styles — a thin stub is enough for
// behavioural testing: click → fires onChange with the negation of checked.
vi.mock('@/components/shared/Toggle', () => ({
  Toggle: ({
    checked,
    onChange,
  }: {
    checked: boolean
    onChange: (v: boolean) => void
  }) => (
    <input
      type="checkbox"
      role="switch"
      checked={checked}
      onChange={(e) => onChange(e.target.checked)}
      readOnly={false}
    />
  ),
}))

function resetMocks() {
  updateMutate.mockReset()
  runNowMutate.mockReset()
  mockConfig = {}
  mockStatus = {
    enabled: true,
    queue: { pending: 0, running: 0, failed: 0, done: 0 },
    last_run_at: null,
    last_run_status: null,
    last_error: null,
  }
}

describe('SubtitleAutomationPage', () => {
  beforeEach(resetMocks)

  it('renders master + all granular toggles', () => {
    mockConfig = {
      subtitle_automation_enabled: false,
      subtitle_automation_queue_enabled: true,
      subtitle_automation_drain_interval_minutes: 2,
      embedded_allow_sdh: true,
      embedded_sdh_penalty: 5,
      cleanup_foreign_tracks_default: false,
      cleanup_foreign_tracks_keep_und: false,
    }
    render(<SubtitleAutomationPage />)

    // Master section
    expect(screen.getByText('Enable full automation')).toBeInTheDocument()
    // Queue section
    expect(screen.getByText('Drain worker')).toBeInTheDocument()
    expect(screen.getByText('Drain interval (minutes)')).toBeInTheDocument()
    // SDH section
    expect(screen.getByText('Allow SDH as source')).toBeInTheDocument()
    expect(screen.getByText('SDH score penalty')).toBeInTheDocument()
    // Cleanup section
    expect(screen.getByText('Remove extracted streams from container')).toBeInTheDocument()
    expect(screen.getByText('Strip by default')).toBeInTheDocument()
    expect(screen.getByText('Keep undetermined (und)')).toBeInTheDocument()

    // 6 toggles (master + queue + SDH + 3x cleanup) — interval + penalty are numbers
    const toggles = screen.getAllByRole('switch')
    expect(toggles).toHaveLength(6)
  })

  it('shows queue counts, last_run_at and last_error', () => {
    mockStatus = {
      enabled: true,
      queue: { pending: 7, running: 2, failed: 3, done: 42 },
      last_run_at: '2026-04-24T12:34:56Z',
      last_run_status: 'ok',
      last_error: 'provider timeout',
    }
    render(<SubtitleAutomationPage />)

    // Queue counts rendered with their labels
    expect(screen.getByText(/pending/i).parentElement?.textContent).toContain('7')
    expect(screen.getByText(/running/i).parentElement?.textContent).toContain('2')
    expect(screen.getByText(/failed/i).parentElement?.textContent).toContain('3')
    expect(screen.getByText(/done/i).parentElement?.textContent).toContain('42')

    // last_run_at is formatted via toLocaleString — just confirm it's not the '—' placeholder
    const lastRunRow = screen.getByText(/last run/i).parentElement
    expect(lastRunRow?.textContent).not.toMatch(/—\s*$/)

    // last_error surface visible
    expect(screen.getByText(/provider timeout/)).toBeInTheDocument()
  })

  it('flipping the master toggle calls update with subtitle_automation_enabled', () => {
    mockConfig = { subtitle_automation_enabled: false }
    render(<SubtitleAutomationPage />)

    // The master toggle is the first <input role="switch"> on the page
    const toggles = screen.getAllByRole('switch')
    fireEvent.click(toggles[0])

    expect(updateMutate).toHaveBeenCalledTimes(1)
    expect(updateMutate).toHaveBeenCalledWith(
      { subtitle_automation_enabled: true },
      expect.any(Object),
    )
  })
})
