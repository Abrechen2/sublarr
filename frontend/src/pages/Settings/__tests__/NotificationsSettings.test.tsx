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
import { render, screen, fireEvent } from '@testing-library/react'
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

  it('Quiet Hours expands and shows content after clicking toggle', () => {
    renderPage()
    const wrapper = screen.getByTestId('section-quiet-hours')
    const toggle = wrapper.querySelector(
      '[data-testid="settings-section-advanced-toggle"]',
    ) as HTMLElement
    fireEvent.click(toggle)
    expect(
      wrapper.querySelector('[data-testid="settings-section-advanced-content"]'),
    ).toBeInTheDocument()
    expect(screen.getByTestId('quiet-hours-advanced-content')).toBeInTheDocument()
  })
})
