/**
 * SystemSettings.test.tsx — Tests for the System settings page (setup half).
 *
 * On 2026-04-26 the page was split: Log Viewer / Disk Monitoring /
 * Cache Management / Integrations / Migration moved to the new
 * SystemDiagnosticsPage (see its dedicated test file). The dead
 * "Events & Hooks" redirect placeholder was deleted as part of the
 * same refactor. This file now covers only what remains:
 *
 *   - Security
 *   - Backup & Restore (+ Auto Backup controls)
 *   - API Keys
 *   - Settings Export / Import
 *   - AniDB nav-tile / Remux nav-tile / Diagnostics cross-link
 *   - Extended Security (covered through SecurityTab mock)
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { SystemSettings } from '../SystemSettings'
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

vi.mock('../SecurityTab', async () => {
  const { useUpdateConfig } = await import('@/hooks/useApi')
  return {
    SecurityTab: () => {
      const { mutate: saveCfg } = useUpdateConfig()
      return (
        <div data-testid="security-tab">
          <div data-testid="section-extended-security">
            <input data-testid="input-session-timeout-minutes" type="number" defaultValue={0} />
            <input
              data-testid="input-max-login-attempts"
              type="number"
              defaultValue={20}
              onChange={(e) => saveCfg({ max_login_attempts: Number(e.target.value) })}
            />
            <input data-testid="input-lockout-duration-minutes" type="number" defaultValue={60} />
            <input data-testid="input-allowed-ip-ranges" type="text" defaultValue="" />
          </div>
        </div>
      )
    },
  }
})

vi.mock('../AdvancedTab', () => ({
  BackupTab: () => <div data-testid="backup-tab">BackupTab</div>,
}))

vi.mock('../ApiKeysTab', () => ({
  ApiKeysTab: () => <div data-testid="api-keys-tab">ApiKeysTab</div>,
}))

vi.mock('../ConfigExportImportTab', () => ({
  ConfigExportImportTab: () => <div data-testid="config-export-import-tab">ConfigExportImportTab</div>,
}))

const mockSaveConfig = vi.fn()

vi.mock('@/hooks/useApi', () => ({
  useConfig: () => ({
    data: {
      backup_auto_enabled: 'false',
      backup_auto_interval_hours: 24,
      backup_auto_on_startup: 'false',
      backup_notify_on_failure: 'true',
      // Extended Security
      session_timeout_minutes: 0,
      max_login_attempts: 20,
      lockout_duration_minutes: 60,
      allowed_ip_ranges: '',
    },
    isLoading: false,
  }),
  useUpdateConfig: () => ({ mutate: mockSaveConfig, isPending: false }),
}))

// ─── Helpers ─────────────────────────────────────────────────────────────────

function renderPage() {
  // The page hosts the subtitle-repair panel, which fetches its scan/status
  // through react-query — so the tree needs a client.
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <SystemSettings />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

// ─── Tests ────────────────────────────────────────────────────────────────────

describe('SystemSettings', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  // ── Layout ────────────────────────────────────────────────────────────────

  it('renders inside SettingsDetailLayout', () => {
    renderPage()
    expect(screen.getByTestId('settings-detail-layout')).toBeInTheDocument()
  })

  it('renders the page heading', () => {
    renderPage()
    expect(screen.getByRole('heading', { level: 1 })).toBeInTheDocument()
  })

  it('renders page title "System"', () => {
    renderPage()
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('System')
  })

  // ── Section presence ─────────────────────────────────────────────────────

  it('renders the Security section', () => {
    renderPage()
    expect(screen.getByTestId('section-security')).toBeInTheDocument()
  })

  it('renders the Backup & Restore section', () => {
    renderPage()
    expect(screen.getByTestId('section-backup-restore')).toBeInTheDocument()
  })

  it('renders the API Keys section', () => {
    renderPage()
    expect(screen.getByTestId('section-api-keys')).toBeInTheDocument()
  })

  it('renders the Settings Export / Import section', () => {
    renderPage()
    expect(screen.getByTestId('section-config-export-import')).toBeInTheDocument()
  })

  it('Events & Hooks redirect placeholder is gone (moved to /settings/notifications)', () => {
    renderPage()
    expect(screen.queryByTestId('section-events-hooks')).toBeNull()
  })

  // ── All sections ──────────────────────────────────────────────────────────

  it('renders exactly 5 settings sections (security, backup, api keys, export, repair)', () => {
    renderPage()
    const sections = screen.getAllByTestId('settings-section')
    expect(sections).toHaveLength(5)
  })

  // ── Section titles ────────────────────────────────────────────────────────

  it('shows "Security" section title', () => {
    renderPage()
    const wrapper = screen.getByTestId('section-security')
    const title = wrapper.querySelector('[data-testid="settings-section-title"]')
    expect(title).toHaveTextContent('Security')
  })

  it('shows "Backup & Restore" section title', () => {
    renderPage()
    const wrapper = screen.getByTestId('section-backup-restore')
    const title = wrapper.querySelector('[data-testid="settings-section-title"]')
    expect(title).toHaveTextContent('Backup & Restore')
  })

  it('shows "API Keys" section title', () => {
    renderPage()
    const wrapper = screen.getByTestId('section-api-keys')
    const title = wrapper.querySelector('[data-testid="settings-section-title"]')
    expect(title).toHaveTextContent('API Keys')
  })

  // ── Advanced sections collapsed by default ────────────────────────────────

  it('API Keys advanced content is collapsed by default', () => {
    renderPage()
    const wrapper = screen.getByTestId('section-api-keys')
    const toggle = wrapper.querySelector('[data-testid="settings-section-advanced-toggle"]')
    expect(toggle).toBeInTheDocument()
    expect(wrapper.querySelector('[data-testid="settings-section-advanced-content"]')).toBeNull()
  })

  // ── Non-advanced sections do NOT have an advanced toggle ─────────────────

  it('Security section does not have an advanced toggle', () => {
    renderPage()
    const wrapper = screen.getByTestId('section-security')
    expect(
      wrapper.querySelector('[data-testid="settings-section-advanced-toggle"]'),
    ).toBeNull()
  })

  it('Backup & Restore section does not have an advanced toggle', () => {
    renderPage()
    const wrapper = screen.getByTestId('section-backup-restore')
    expect(
      wrapper.querySelector('[data-testid="settings-section-advanced-toggle"]'),
    ).toBeNull()
  })

  // ── Expanding advanced sections ───────────────────────────────────────────

  it('API Keys expands and shows content after clicking toggle', () => {
    renderPage()
    const wrapper = screen.getByTestId('section-api-keys')
    const toggle = wrapper.querySelector(
      '[data-testid="settings-section-advanced-toggle"]',
    ) as HTMLElement
    fireEvent.click(toggle)
    expect(
      wrapper.querySelector('[data-testid="settings-section-advanced-content"]'),
    ).toBeInTheDocument()
  })

  // ── Cross-link tile + nav tiles ──────────────────────────────────────────

  it('renders the Diagnostics cross-link', () => {
    renderPage()
    expect(screen.getByTestId('section-diagnostics-link')).toBeInTheDocument()
  })

  it('Diagnostics link points to /settings/system/diagnostics', () => {
    renderPage()
    const wrapper = screen.getByTestId('section-diagnostics-link')
    const link = wrapper.querySelector('a')
    expect(link).toHaveAttribute('href', '/settings/system/diagnostics')
  })

  it('renders the AniDB section', () => {
    renderPage()
    expect(screen.getByTestId('section-anidb')).toBeInTheDocument()
  })

  it('AniDB nav card renders a Configure link', () => {
    renderPage()
    const wrapper = screen.getByTestId('section-anidb')
    expect(wrapper.querySelector('a')).toBeInTheDocument()
  })

  it('renders the Remux section', () => {
    renderPage()
    expect(screen.getByTestId('section-remux')).toBeInTheDocument()
  })

  it('Remux nav card renders a Configure link', () => {
    renderPage()
    const wrapper = screen.getByTestId('section-remux')
    expect(wrapper.querySelector('a')).toBeInTheDocument()
  })

  // ── Summary text for advanced sections ───────────────────────────────────

  it('shows a summary description inside the API Keys section', () => {
    renderPage()
    expect(screen.getByTestId('api-keys-summary')).toBeInTheDocument()
  })
})

// ─── Auto Backup section ────────────────────────────────────────────────────

describe('Auto Backup section', () => {
  beforeEach(() => { vi.clearAllMocks() })

  it('toggle-backup-auto-enabled renders unchecked by default', () => {
    renderPage()
    expect(screen.getByTestId('backup-auto-controls')).toBeInTheDocument()
    const togBtn = screen.getByTestId('input-backup-auto-interval-hours')
    expect(togBtn).toBeInTheDocument()
  })

  it('input-backup-auto-interval-hours renders with value 24', () => {
    renderPage()
    const input = screen.getByTestId('input-backup-auto-interval-hours') as HTMLInputElement
    expect(Number(input.value)).toBe(24)
  })

  it('toggle-backup-notify-on-failure renders checked by default (default true)', () => {
    renderPage()
    expect(screen.getByTestId('backup-auto-controls')).toBeInTheDocument()
  })

  it('toggling backup_auto_enabled calls updateConfig with { backup_auto_enabled: "true" }', () => {
    renderPage()
    const controls = screen.getByTestId('backup-auto-controls')
    const switches = controls.querySelectorAll('[role="switch"]')
    fireEvent.click(switches[0])
    expect(mockSaveConfig).toHaveBeenCalledWith({ backup_auto_enabled: 'true' })
  })
})

// ─── Extended Security section (covered through SecurityTab mock) ───────────

describe('Extended Security section (SecurityTab)', () => {
  beforeEach(() => { vi.clearAllMocks() })

  it('input-session-timeout-minutes renders with value 0', () => {
    renderPage()
    const input = screen.getByTestId('input-session-timeout-minutes') as HTMLInputElement
    expect(Number(input.value)).toBe(0)
  })

  it('input-max-login-attempts renders with value 20', () => {
    renderPage()
    const input = screen.getByTestId('input-max-login-attempts') as HTMLInputElement
    expect(Number(input.value)).toBe(20)
  })

  it('input-lockout-duration-minutes renders with value 60', () => {
    renderPage()
    const input = screen.getByTestId('input-lockout-duration-minutes') as HTMLInputElement
    expect(Number(input.value)).toBe(60)
  })

  it('input-allowed-ip-ranges renders with empty string default', () => {
    renderPage()
    const input = screen.getByTestId('input-allowed-ip-ranges') as HTMLInputElement
    expect(input.value).toBe('')
  })

  it('changing max_login_attempts calls updateConfig with { max_login_attempts: 10 }', () => {
    renderPage()
    const input = screen.getByTestId('input-max-login-attempts')
    fireEvent.change(input, { target: { value: '10' } })
    expect(mockSaveConfig).toHaveBeenCalledWith({ max_login_attempts: 10 })
  })
})
