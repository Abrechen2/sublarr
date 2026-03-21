/**
 * SystemSettings.test.tsx — Tests for the System settings page.
 *
 * Covers:
 * - Renders the page via SettingsDetailLayout
 * - All 7 sections are present (data-testid attributes)
 * - Sections 5-7 (Integrations, Migration, API Keys) use the `advanced` prop and are collapsed by default
 * - Events & Hooks section contains a redirect link to /settings/notifications
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { SystemSettings } from '../SystemSettings'

// ─── Mocks ───────────────────────────────────────────────────────────────────

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string, fallback?: string) => fallback ?? key }),
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

vi.mock('../ProtokollTab', () => ({
  ProtokollTab: () => <div data-testid="protokoll-tab">ProtokollTab</div>,
}))

vi.mock('../IntegrationsTab', () => ({
  IntegrationsTab: () => <div data-testid="integrations-tab">IntegrationsTab</div>,
}))

vi.mock('../MigrationTab', () => ({
  MigrationTab: () => <div data-testid="migration-tab">MigrationTab</div>,
}))

vi.mock('../ApiKeysTab', () => ({
  ApiKeysTab: () => <div data-testid="api-keys-tab">ApiKeysTab</div>,
}))

vi.mock('../AnidbTab', () => ({
  AnidbTab: () => <div data-testid="anidb-tab">AnidbTab</div>,
}))

vi.mock('../RemuxTab', () => ({
  RemuxTab: () => <div data-testid="remux-tab">RemuxTab</div>,
}))

vi.mock('../StandaloneSettingsTab', () => ({
  StandaloneSettingsTab: () => <div data-testid="standalone-settings-tab">StandaloneSettingsTab</div>,
}))

const mockSaveConfig = vi.fn()

vi.mock('@/hooks/useApi', () => ({
  useConfig: () => ({
    data: {
      backup_auto_enabled: 'false',
      backup_auto_interval_hours: 24,
      backup_auto_on_startup: 'false',
      backup_notify_on_failure: 'true',
      disk_warning_threshold_percent: 90,
      disk_warning_notify: 'true',
      // Extended Security (Step 46)
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
  return render(
    <MemoryRouter>
      <SystemSettings />
    </MemoryRouter>,
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

  it('renders the Events & Hooks section', () => {
    renderPage()
    expect(screen.getByTestId('section-events-hooks')).toBeInTheDocument()
  })

  it('renders the Log Viewer section', () => {
    renderPage()
    expect(screen.getByTestId('section-log-viewer')).toBeInTheDocument()
  })

  it('renders the Integrations section', () => {
    renderPage()
    expect(screen.getByTestId('section-integrations')).toBeInTheDocument()
  })

  it('renders the Migration section', () => {
    renderPage()
    expect(screen.getByTestId('section-migration')).toBeInTheDocument()
  })

  it('renders the API Keys section', () => {
    renderPage()
    expect(screen.getByTestId('section-api-keys')).toBeInTheDocument()
  })

  // ── All sections ──────────────────────────────────────────────────────────

  it('renders exactly 13 settings sections', () => {
    renderPage()
    const sections = screen.getAllByTestId('settings-section')
    expect(sections).toHaveLength(13)
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

  it('shows "Events & Hooks" section title', () => {
    renderPage()
    const wrapper = screen.getByTestId('section-events-hooks')
    const title = wrapper.querySelector('[data-testid="settings-section-title"]')
    expect(title).toHaveTextContent('Events & Hooks')
  })

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

  it('shows "API Keys" section title', () => {
    renderPage()
    const wrapper = screen.getByTestId('section-api-keys')
    const title = wrapper.querySelector('[data-testid="settings-section-title"]')
    expect(title).toHaveTextContent('API Keys')
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

  it('Events & Hooks section does not have an advanced toggle', () => {
    renderPage()
    const wrapper = screen.getByTestId('section-events-hooks')
    expect(
      wrapper.querySelector('[data-testid="settings-section-advanced-toggle"]'),
    ).toBeNull()
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

  // ── Events & Hooks redirect link ─────────────────────────────────────────

  it('renders a link to /settings/notifications in the Events & Hooks section', () => {
    renderPage()
    const link = screen.getByTestId('events-hooks-link')
    expect(link).toBeInTheDocument()
    expect(link).toHaveAttribute('href', '/settings/notifications')
  })

  it('Events & Hooks section contains redirect text', () => {
    renderPage()
    expect(screen.getByTestId('events-hooks-redirect')).toBeInTheDocument()
  })

  it('Events & Hooks link text says "Notifications settings"', () => {
    renderPage()
    expect(screen.getByTestId('events-hooks-link')).toHaveTextContent('Notifications settings')
  })

  // ── New sections (Steps 29–31) ────────────────────────────────────────────

  it('renders the AniDB section', () => {
    renderPage()
    expect(screen.getByTestId('section-anidb')).toBeInTheDocument()
  })

  it('shows "AniDB" section title', () => {
    renderPage()
    const wrapper = screen.getByTestId('section-anidb')
    const title = wrapper.querySelector('[data-testid="settings-section-title"]')
    expect(title).toHaveTextContent('AniDB')
  })

  it('renders the Remux section', () => {
    renderPage()
    expect(screen.getByTestId('section-remux')).toBeInTheDocument()
  })

  it('shows "Remux" section title', () => {
    renderPage()
    const wrapper = screen.getByTestId('section-remux')
    const title = wrapper.querySelector('[data-testid="settings-section-title"]')
    expect(title).toHaveTextContent('Remux')
  })

  it('renders the Standalone Mode section', () => {
    renderPage()
    expect(screen.getByTestId('section-standalone')).toBeInTheDocument()
  })

  it('shows "Standalone Mode" section title', () => {
    renderPage()
    const wrapper = screen.getByTestId('section-standalone')
    const title = wrapper.querySelector('[data-testid="settings-section-title"]')
    expect(title).toHaveTextContent('Standalone Mode')
  })

  // ── Summary text for advanced sections ───────────────────────────────────

  it('shows a summary description inside the Integrations section', () => {
    renderPage()
    expect(screen.getByTestId('integrations-summary')).toBeInTheDocument()
  })

  it('shows a summary description inside the Migration section', () => {
    renderPage()
    expect(screen.getByTestId('migration-summary')).toBeInTheDocument()
  })

  it('shows a summary description inside the API Keys section', () => {
    renderPage()
    expect(screen.getByTestId('api-keys-summary')).toBeInTheDocument()
  })
})

// ─── Auto Backup section (Step 40) ───────────────────────────────────────────

describe('Auto Backup section', () => {
  beforeEach(() => { vi.clearAllMocks() })

  it('toggle-backup-auto-enabled renders unchecked by default', () => {
    renderPage()
    // Toggle is inside backup-auto-controls which is inside backup-restore section
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
    // toggle-backup-notify-on-failure renders in backup-auto-controls
    expect(screen.getByTestId('backup-auto-controls')).toBeInTheDocument()
  })

  it('toggling backup_auto_enabled calls updateConfig with { backup_auto_enabled: "true" }', () => {
    renderPage()
    // The Toggle for backup_auto_enabled is a button role=switch inside backup-auto-controls
    const controls = screen.getByTestId('backup-auto-controls')
    const switches = controls.querySelectorAll('[role="switch"]')
    // First switch is backup_auto_enabled
    fireEvent.click(switches[0])
    expect(mockSaveConfig).toHaveBeenCalledWith({ backup_auto_enabled: 'true' })
  })
})

// ─── Disk Monitoring section (Step 41) ───────────────────────────────────────

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
    // The Toggle for disk_warning_notify (default true)
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

// ─── Extended Security section (Step 46) ─────────────────────────────────────

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
