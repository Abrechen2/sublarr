/**
 * NotificationsSettings.test.tsx — Tests for the Notifications settings page.
 *
 * Covers:
 * - Renders the page via SettingsDetailLayout
 * - All 3 sections are present (data-testid attributes)
 * - Section 3 (Quiet Hours) uses the `advanced` prop and is collapsed by default
 * - Expanding the advanced section via toggle reveals its content
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { BrowserRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { NotificationsSettings } from '../NotificationsSettings'

// ─── Mocks ───────────────────────────────────────────────────────────────────

vi.mock('../NotificationTemplatesTab', () => ({
  NotificationTemplatesTab: () => (
    <div data-testid="notification-templates-tab">NotificationTemplatesTab</div>
  ),
}))

vi.mock('../EventsTab', () => ({
  EventsHooksTab: () => <div data-testid="events-hooks-tab">EventsHooksTab</div>,
}))

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string, fallback?: string) => fallback ?? key }),
}))

const mockUpdateConfigMutate = vi.fn()

vi.mock('@/hooks/useApi', () => ({
  useConfig: () => ({
    data: {
      quiet_hours_enabled: 'false',
      quiet_hours_start: '23:00',
      quiet_hours_end: '07:00',
      quiet_hours_timezone: 'Europe/Berlin',
    },
  }),
  useUpdateConfig: () => ({ mutate: mockUpdateConfigMutate, isPending: false }),
}))

// ─── Test Helpers ─────────────────────────────────────────────────────────────

function makeQueryClient() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
}

function renderPage() {
  return render(
    <BrowserRouter>
      <QueryClientProvider client={makeQueryClient()}>
        <NotificationsSettings />
      </QueryClientProvider>
    </BrowserRouter>,
  )
}

// ─── Tests ────────────────────────────────────────────────────────────────────

describe('NotificationsSettings', () => {
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

  // ── Section presence ─────────────────────────────────────────────────────

  it('renders the Notification Channels section', () => {
    renderPage()
    expect(screen.getByTestId('section-notification-channels')).toBeInTheDocument()
  })

  it('renders the Events & Hooks section', () => {
    renderPage()
    expect(screen.getByTestId('section-events-hooks')).toBeInTheDocument()
  })

  it('renders the Quiet Hours section', () => {
    renderPage()
    expect(screen.getByTestId('section-quiet-hours')).toBeInTheDocument()
  })

  // ── All 3 sections ────────────────────────────────────────────────────────

  it('renders exactly 3 settings sections', () => {
    renderPage()
    const sections = screen.getAllByTestId('settings-section')
    expect(sections).toHaveLength(3)
  })

  // ── Section titles ────────────────────────────────────────────────────────

  it('shows "Notification Channels" section title', () => {
    renderPage()
    const wrapper = screen.getByTestId('section-notification-channels')
    const title = wrapper.querySelector('[data-testid="settings-section-title"]')
    expect(title).toHaveTextContent('Notification Channels')
  })

  it('shows "Events & Hooks" section title', () => {
    renderPage()
    const wrapper = screen.getByTestId('section-events-hooks')
    const title = wrapper.querySelector('[data-testid="settings-section-title"]')
    expect(title).toHaveTextContent('Events & Hooks')
  })

  it('shows "Quiet Hours" section title', () => {
    renderPage()
    const wrapper = screen.getByTestId('section-quiet-hours')
    const title = wrapper.querySelector('[data-testid="settings-section-title"]')
    expect(title).toHaveTextContent('Quiet Hours')
  })

  // ── Non-advanced sections do NOT have an advanced toggle ──────────────────

  it('Notification Channels section does not have an advanced toggle', () => {
    renderPage()
    const wrapper = screen.getByTestId('section-notification-channels')
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

  // ── Quiet Hours advanced section collapsed by default ─────────────────────

  it('Quiet Hours advanced content is collapsed by default', () => {
    renderPage()
    const wrapper = screen.getByTestId('section-quiet-hours')
    const toggle = wrapper.querySelector('[data-testid="settings-section-advanced-toggle"]')
    expect(toggle).toBeInTheDocument()
    expect(wrapper.querySelector('[data-testid="settings-section-advanced-content"]')).toBeNull()
  })

  it('shows a summary description inside the Quiet Hours section', () => {
    renderPage()
    expect(screen.getByTestId('quiet-hours-summary')).toBeInTheDocument()
  })

  // ── Expanding advanced section ─────────────────────────────────────────────

  it('Quiet Hours expands and shows the config stub after clicking toggle', () => {
    renderPage()
    const wrapper = screen.getByTestId('section-quiet-hours')
    const toggle = wrapper.querySelector(
      '[data-testid="settings-section-advanced-toggle"]',
    ) as HTMLElement
    fireEvent.click(toggle)
    expect(
      wrapper.querySelector('[data-testid="settings-section-advanced-content"]'),
    ).toBeInTheDocument()
    expect(screen.getByTestId('quiet-hours-config-stub')).toBeInTheDocument()
  })
})

// ─── Step 23: notify_manual_actions toggle verification ──────────────────────

describe('NotificationsSettings — notify_manual_actions (Step 23)', () => {
  beforeEach(() => { vi.clearAllMocks() })

  it('NotificationTemplatesTab mock renders inside Channels section', () => {
    renderPage()
    expect(screen.getByTestId('notification-templates-tab')).toBeInTheDocument()
  })
})

// ─── Step 24: Quiet Hours UI stub ────────────────────────────────────────────

describe('NotificationsSettings — Quiet Hours stub (Step 24)', () => {
  beforeEach(() => { vi.clearAllMocks() })

  it('Quiet Hours advanced section renders the stub when expanded', () => {
    renderPage()
    const wrapper = screen.getByTestId('section-quiet-hours')
    const toggle = wrapper.querySelector(
      '[data-testid="settings-section-advanced-toggle"]'
    ) as HTMLElement
    fireEvent.click(toggle)
    expect(screen.getByTestId('quiet-hours-config-stub')).toBeInTheDocument()
  })

  it('renders the stub info banner', () => {
    renderPage()
    const wrapper = screen.getByTestId('section-quiet-hours')
    fireEvent.click(
      wrapper.querySelector('[data-testid="settings-section-advanced-toggle"]') as HTMLElement
    )
    expect(screen.getByTestId('quiet-hours-stub-banner')).toBeInTheDocument()
  })

  it('renders all four quiet hours inputs after expanding', () => {
    renderPage()
    const wrapper = screen.getByTestId('section-quiet-hours')
    fireEvent.click(
      wrapper.querySelector('[data-testid="settings-section-advanced-toggle"]') as HTMLElement
    )
    expect(screen.getByTestId('quiet-hours-enabled-toggle')).toBeInTheDocument()
    expect(screen.getByTestId('quiet-hours-start-input')).toBeInTheDocument()
    expect(screen.getByTestId('quiet-hours-end-input')).toBeInTheDocument()
    expect(screen.getByTestId('quiet-hours-timezone-input')).toBeInTheDocument()
  })

  it('start input reads from config', () => {
    renderPage()
    const wrapper = screen.getByTestId('section-quiet-hours')
    fireEvent.click(
      wrapper.querySelector('[data-testid="settings-section-advanced-toggle"]') as HTMLElement
    )
    expect(screen.getByTestId('quiet-hours-start-input')).toHaveValue('23:00')
  })

  it('save button calls updateConfig with all four keys', async () => {
    renderPage()
    const wrapper = screen.getByTestId('section-quiet-hours')
    fireEvent.click(
      wrapper.querySelector('[data-testid="settings-section-advanced-toggle"]') as HTMLElement
    )
    fireEvent.click(screen.getByTestId('quiet-hours-save-btn'))
    await waitFor(() => {
      expect(mockUpdateConfigMutate).toHaveBeenCalledWith(
        expect.objectContaining({
          quiet_hours_enabled: 'false',
          quiet_hours_start: '23:00',
          quiet_hours_end: '07:00',
          quiet_hours_timezone: 'Europe/Berlin',
        }),
      )
    })
  })

  it('toggle button flips enabled state', () => {
    renderPage()
    const wrapper = screen.getByTestId('section-quiet-hours')
    fireEvent.click(
      wrapper.querySelector('[data-testid="settings-section-advanced-toggle"]') as HTMLElement
    )
    const toggle = screen.getByTestId('quiet-hours-enabled-toggle')
    expect(toggle).toHaveAttribute('aria-checked', 'false')
    fireEvent.click(toggle)
    expect(toggle).toHaveAttribute('aria-checked', 'true')
  })
})
