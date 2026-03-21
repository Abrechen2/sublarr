/**
 * AutomationSettings.test.tsx — Tests for the Automation settings page.
 *
 * Covers:
 * - Renders the page via SettingsDetailLayout
 * - All 6 sections are present (data-testid attributes)
 * - Section 6 (Scheduled Tasks) uses the `advanced` prop and is collapsed by default
 * - Expanding the advanced section via toggle reveals its content
 * - Toggle interactions call updateConfig with the correct payload
 * - Input changes call updateConfig with the correct payload
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { BrowserRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { AutomationSettings } from '../AutomationSettings'

// ─── Mocks ───────────────────────────────────────────────────────────────────

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string, fallback?: string) => fallback ?? key }),
}))

vi.mock('@/pages/Settings/EventsTab', () => ({
  ScoringTab: () => <div data-testid="mock-scoring-tab">ScoringTab</div>,
}))

const mockMutate = vi.fn()

vi.mock('@/hooks/useApi', () => ({
  useConfig: () => ({
    data: {
      wanted_search_interval_hours: '6',
      webhook_auto_search: 'true',
      wanted_search_on_startup: 'false',
      upgrade_enabled: 'false',
      upgrade_min_score_delta: '10',
      upgrade_scan_interval_hours: '24',
      wanted_auto_translate: 'false',
      auto_sync_after_download: 'false',
      auto_cleanup_after_extract: 'false',
    },
    isLoading: false,
  }),
  useUpdateConfig: () => ({ mutate: mockMutate, isPending: false }),
  // Scoring tab deps (lazy-loaded but mocked away)
  useScoringWeights: () => ({ data: undefined }),
  useUpdateScoringWeights: () => ({ mutate: vi.fn() }),
  useResetScoringWeights: () => ({ mutate: vi.fn() }),
  useProviderModifiers: () => ({ data: undefined }),
  useUpdateProviderModifiers: () => ({ mutate: vi.fn() }),
  useScoringPresets: () => ({ data: undefined }),
  useImportScoringPreset: () => ({ mutate: vi.fn() }),
  useProviders: () => ({ data: { providers: [] } }),
}))

vi.mock('@/components/shared/Toast', () => ({
  toast: vi.fn(),
}))

// ─── Test helpers ─────────────────────────────────────────────────────────────

function makeQueryClient() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
}

function renderPage() {
  return render(
    <BrowserRouter>
      <QueryClientProvider client={makeQueryClient()}>
        <AutomationSettings />
      </QueryClientProvider>
    </BrowserRouter>,
  )
}

// ─── Tests ────────────────────────────────────────────────────────────────────

describe('AutomationSettings', () => {
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

  it('renders exactly 5 settings sections', () => {
    renderPage()
    const sections = screen.getAllByTestId('settings-section')
    expect(sections).toHaveLength(5)
  })

  // ── Section presence ─────────────────────────────────────────────────────

  it('renders the Search & Scan section', () => {
    renderPage()
    expect(screen.getByTestId('section-search-scan')).toBeInTheDocument()
  })

  it('renders the Upgrade Rules section', () => {
    renderPage()
    expect(screen.getByTestId('section-upgrade-rules')).toBeInTheDocument()
  })

  it('renders the Provider Re-ranking section', () => {
    renderPage()
    expect(screen.getByTestId('section-provider-reranking')).toBeInTheDocument()
  })

  it('renders the Processing Pipeline section', () => {
    renderPage()
    expect(screen.getByTestId('section-processing-pipeline')).toBeInTheDocument()
  })

  it('renders the Scheduled Tasks section', () => {
    renderPage()
    expect(screen.getByTestId('section-scheduled-tasks')).toBeInTheDocument()
  })

  // ── Section titles ────────────────────────────────────────────────────────

  it('shows "Search & Scan" section title', () => {
    renderPage()
    const wrapper = screen.getByTestId('section-search-scan')
    const title = wrapper.querySelector('[data-testid="settings-section-title"]')
    expect(title).toHaveTextContent('Search & Scan')
  })

  it('shows "Upgrade Rules" section title', () => {
    renderPage()
    const wrapper = screen.getByTestId('section-upgrade-rules')
    const title = wrapper.querySelector('[data-testid="settings-section-title"]')
    expect(title).toHaveTextContent('Upgrade Rules')
  })

  it('shows "Provider Re-ranking" section title', () => {
    renderPage()
    const wrapper = screen.getByTestId('section-provider-reranking')
    const title = wrapper.querySelector('[data-testid="settings-section-title"]')
    expect(title).toHaveTextContent('Provider Re-ranking')
  })

  it('shows "Processing Pipeline" section title', () => {
    renderPage()
    const wrapper = screen.getByTestId('section-processing-pipeline')
    const title = wrapper.querySelector('[data-testid="settings-section-title"]')
    expect(title).toHaveTextContent('Processing Pipeline')
  })

  it('shows "Scheduled Tasks" section title', () => {
    renderPage()
    const wrapper = screen.getByTestId('section-scheduled-tasks')
    const title = wrapper.querySelector('[data-testid="settings-section-title"]')
    expect(title).toHaveTextContent('Scheduled Tasks')
  })

  // ── Scheduled Tasks — advanced collapsed by default ───────────────────────

  it('Scheduled Tasks advanced content is collapsed by default', () => {
    renderPage()
    const wrapper = screen.getByTestId('section-scheduled-tasks')
    const toggle = wrapper.querySelector('[data-testid="settings-section-advanced-toggle"]')
    expect(toggle).toBeInTheDocument()
    expect(wrapper.querySelector('[data-testid="settings-section-advanced-content"]')).toBeNull()
  })

  it('Scheduled Tasks expands and shows content after clicking toggle', () => {
    renderPage()
    const wrapper = screen.getByTestId('section-scheduled-tasks')
    const toggle = wrapper.querySelector(
      '[data-testid="settings-section-advanced-toggle"]',
    ) as HTMLElement
    fireEvent.click(toggle)
    expect(
      wrapper.querySelector('[data-testid="settings-section-advanced-content"]'),
    ).toBeInTheDocument()
    expect(screen.getByTestId('scheduled-tasks-content')).toBeInTheDocument()
  })

  // ── Non-advanced sections do NOT have an advanced toggle ─────────────────

  it('Search & Scan section does not have an advanced toggle', () => {
    renderPage()
    const wrapper = screen.getByTestId('section-search-scan')
    expect(
      wrapper.querySelector('[data-testid="settings-section-advanced-toggle"]'),
    ).toBeNull()
  })

  it('Upgrade Rules section does not have an advanced toggle', () => {
    renderPage()
    const wrapper = screen.getByTestId('section-upgrade-rules')
    expect(
      wrapper.querySelector('[data-testid="settings-section-advanced-toggle"]'),
    ).toBeNull()
  })

  it('Processing Pipeline section does not have an advanced toggle', () => {
    renderPage()
    const wrapper = screen.getByTestId('section-processing-pipeline')
    expect(
      wrapper.querySelector('[data-testid="settings-section-advanced-toggle"]'),
    ).toBeNull()
  })

  // ── Scheduled Tasks summary ───────────────────────────────────────────────

  it('shows a summary description inside the Scheduled Tasks section', () => {
    renderPage()
    expect(screen.getByTestId('scheduled-tasks-summary')).toBeInTheDocument()
  })

  // ── Search & Scan interactions ────────────────────────────────────────────

  it('displays wanted_search_interval_hours value from config', () => {
    renderPage()
    const input = screen.getByTestId('input-wanted-search-interval-hours') as HTMLInputElement
    expect(input.value).toBe('6')
  })

  it('calls updateConfig with wanted_search_interval_hours as number on change', () => {
    renderPage()
    const input = screen.getByTestId('input-wanted-search-interval-hours')
    fireEvent.change(input, { target: { value: '12' } })
    expect(mockMutate).toHaveBeenCalledWith({ wanted_search_interval_hours: 12 })
  })

  it('webhook_auto_search toggle reflects config value (true)', () => {
    renderPage()
    const formGroup = screen.getByTestId('form-group-webhook-auto-search')
    const toggle = formGroup.querySelector('[role="switch"]')
    expect(toggle).toHaveAttribute('aria-checked', 'true')
  })

  it('wanted_search_on_startup toggle reflects config value (false)', () => {
    renderPage()
    const formGroup = screen.getByTestId('form-group-wanted-search-on-startup')
    const toggle = formGroup.querySelector('[role="switch"]')
    expect(toggle).toHaveAttribute('aria-checked', 'false')
  })

  it('calls updateConfig with wanted_search_on_startup=true when toggle is clicked', () => {
    renderPage()
    const formGroup = screen.getByTestId('form-group-wanted-search-on-startup')
    const toggle = formGroup.querySelector('[role="switch"]') as HTMLElement
    fireEvent.click(toggle)
    expect(mockMutate).toHaveBeenCalledWith({ wanted_search_on_startup: true })
  })

  // ── Upgrade Rules interactions ─────────────────────────────────────────────

  it('displays upgrade_min_score_delta value from config', () => {
    renderPage()
    const input = screen.getByTestId('input-upgrade-min-score-delta') as HTMLInputElement
    expect(input.value).toBe('10')
  })

  it('calls updateConfig with upgrade_min_score_delta as number on change', () => {
    renderPage()
    const input = screen.getByTestId('input-upgrade-min-score-delta')
    fireEvent.change(input, { target: { value: '20' } })
    expect(mockMutate).toHaveBeenCalledWith({ upgrade_min_score_delta: 20 })
  })

  it('upgrade_enabled toggle reflects config value (false)', () => {
    renderPage()
    const formGroup = screen.getByTestId('form-group-upgrade-enabled')
    const toggle = formGroup.querySelector('[role="switch"]')
    expect(toggle).toHaveAttribute('aria-checked', 'false')
  })

  it('calls updateConfig with upgrade_enabled=true when toggle is clicked', () => {
    renderPage()
    const formGroup = screen.getByTestId('form-group-upgrade-enabled')
    const toggle = formGroup.querySelector('[role="switch"]') as HTMLElement
    fireEvent.click(toggle)
    expect(mockMutate).toHaveBeenCalledWith({ upgrade_enabled: true })
  })

  // ── Processing Pipeline interactions ──────────────────────────────────────

  it('wanted_auto_translate toggle reflects config value (false)', () => {
    renderPage()
    const formGroup = screen.getByTestId('form-group-wanted-auto-translate')
    const toggle = formGroup.querySelector('[role="switch"]')
    expect(toggle).toHaveAttribute('aria-checked', 'false')
  })

  it('calls updateConfig with wanted_auto_translate=true when toggle is clicked', () => {
    renderPage()
    const formGroup = screen.getByTestId('form-group-wanted-auto-translate')
    const toggle = formGroup.querySelector('[role="switch"]') as HTMLElement
    fireEvent.click(toggle)
    expect(mockMutate).toHaveBeenCalledWith({ wanted_auto_translate: true })
  })

  it('calls updateConfig with auto_sync_after_download=true when toggle is clicked', () => {
    renderPage()
    const formGroup = screen.getByTestId('form-group-auto-sync-after-download')
    const toggle = formGroup.querySelector('[role="switch"]') as HTMLElement
    fireEvent.click(toggle)
    expect(mockMutate).toHaveBeenCalledWith({ auto_sync_after_download: true })
  })

  it('calls updateConfig with auto_cleanup_after_extract=true when toggle is clicked', () => {
    renderPage()
    const formGroup = screen.getByTestId('form-group-auto-cleanup-after-extract')
    const toggle = formGroup.querySelector('[role="switch"]') as HTMLElement
    fireEvent.click(toggle)
    expect(mockMutate).toHaveBeenCalledWith({ auto_cleanup_after_extract: true })
  })
})
