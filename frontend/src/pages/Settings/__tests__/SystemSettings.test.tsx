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

vi.mock('../SecurityTab', () => ({
  SecurityTab: () => <div data-testid="security-tab">SecurityTab</div>,
}))

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

  // ── All 7 sections ────────────────────────────────────────────────────────

  it('renders exactly 7 settings sections', () => {
    renderPage()
    const sections = screen.getAllByTestId('settings-section')
    expect(sections).toHaveLength(7)
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
