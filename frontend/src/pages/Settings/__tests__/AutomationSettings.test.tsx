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
      wanted_search_frequency: '60',
      auto_search_on_download: 'true',
      scan_on_start: 'false',
      auto_upgrade_enabled: 'false',
      auto_upgrade_threshold: '10',
      upgrade_check_frequency: '360',
      auto_translate: 'false',
      auto_sync: 'false',
      auto_cleanup: 'false',
      keep_original_subs: 'true',
      sidecar_format: 'srt',
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

  it('renders exactly 6 settings sections', () => {
    renderPage()
    const sections = screen.getAllByTestId('settings-section')
    expect(sections).toHaveLength(6)
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

  it('renders the Sidecar & Cleanup section', () => {
    renderPage()
    expect(screen.getByTestId('section-sidecar-cleanup')).toBeInTheDocument()
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

  it('shows "Sidecar & Cleanup" section title', () => {
    renderPage()
    const wrapper = screen.getByTestId('section-sidecar-cleanup')
    const title = wrapper.querySelector('[data-testid="settings-section-title"]')
    expect(title).toHaveTextContent('Sidecar & Cleanup')
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

  it('displays wanted_search_frequency value from config', () => {
    renderPage()
    const input = screen.getByTestId('input-wanted-search-frequency') as HTMLInputElement
    expect(input.value).toBe('60')
  })

  it('calls updateConfig with wanted_search_frequency on change', () => {
    renderPage()
    const input = screen.getByTestId('input-wanted-search-frequency')
    fireEvent.change(input, { target: { value: '120' } })
    expect(mockMutate).toHaveBeenCalledWith({ wanted_search_frequency: '120' })
  })

  it('auto_search_on_download toggle reflects config value (true)', () => {
    renderPage()
    const formGroup = screen.getByTestId('form-group-auto-search-on-download')
    const toggle = formGroup.querySelector('[role="switch"]')
    expect(toggle).toHaveAttribute('aria-checked', 'true')
  })

  it('scan_on_start toggle reflects config value (false)', () => {
    renderPage()
    const formGroup = screen.getByTestId('form-group-scan-on-start')
    const toggle = formGroup.querySelector('[role="switch"]')
    expect(toggle).toHaveAttribute('aria-checked', 'false')
  })

  it('calls updateConfig with scan_on_start=true when toggle is clicked', () => {
    renderPage()
    const formGroup = screen.getByTestId('form-group-scan-on-start')
    const toggle = formGroup.querySelector('[role="switch"]') as HTMLElement
    fireEvent.click(toggle)
    expect(mockMutate).toHaveBeenCalledWith({ scan_on_start: true })
  })

  // ── Upgrade Rules interactions ─────────────────────────────────────────────

  it('displays auto_upgrade_threshold value from config', () => {
    renderPage()
    const input = screen.getByTestId('input-auto-upgrade-threshold') as HTMLInputElement
    expect(input.value).toBe('10')
  })

  it('calls updateConfig with auto_upgrade_threshold as number on change', () => {
    renderPage()
    const input = screen.getByTestId('input-auto-upgrade-threshold')
    fireEvent.change(input, { target: { value: '20' } })
    expect(mockMutate).toHaveBeenCalledWith({ auto_upgrade_threshold: 20 })
  })

  it('auto_upgrade_enabled toggle reflects config value (false)', () => {
    renderPage()
    const formGroup = screen.getByTestId('form-group-auto-upgrade-enabled')
    const toggle = formGroup.querySelector('[role="switch"]')
    expect(toggle).toHaveAttribute('aria-checked', 'false')
  })

  it('calls updateConfig with auto_upgrade_enabled=true when toggle is clicked', () => {
    renderPage()
    const formGroup = screen.getByTestId('form-group-auto-upgrade-enabled')
    const toggle = formGroup.querySelector('[role="switch"]') as HTMLElement
    fireEvent.click(toggle)
    expect(mockMutate).toHaveBeenCalledWith({ auto_upgrade_enabled: true })
  })

  // ── Processing Pipeline interactions ──────────────────────────────────────

  it('auto_translate toggle reflects config value (false)', () => {
    renderPage()
    const formGroup = screen.getByTestId('form-group-auto-translate')
    const toggle = formGroup.querySelector('[role="switch"]')
    expect(toggle).toHaveAttribute('aria-checked', 'false')
  })

  it('calls updateConfig with auto_translate=true when toggle is clicked', () => {
    renderPage()
    const formGroup = screen.getByTestId('form-group-auto-translate')
    const toggle = formGroup.querySelector('[role="switch"]') as HTMLElement
    fireEvent.click(toggle)
    expect(mockMutate).toHaveBeenCalledWith({ auto_translate: true })
  })

  it('calls updateConfig with auto_sync=true when toggle is clicked', () => {
    renderPage()
    const formGroup = screen.getByTestId('form-group-auto-sync')
    const toggle = formGroup.querySelector('[role="switch"]') as HTMLElement
    fireEvent.click(toggle)
    expect(mockMutate).toHaveBeenCalledWith({ auto_sync: true })
  })

  it('calls updateConfig with auto_cleanup=true when toggle is clicked', () => {
    renderPage()
    const formGroup = screen.getByTestId('form-group-auto-cleanup')
    const toggle = formGroup.querySelector('[role="switch"]') as HTMLElement
    fireEvent.click(toggle)
    expect(mockMutate).toHaveBeenCalledWith({ auto_cleanup: true })
  })

  // ── Sidecar & Cleanup interactions ────────────────────────────────────────

  it('keep_original_subs toggle reflects config value (true)', () => {
    renderPage()
    const formGroup = screen.getByTestId('form-group-keep-original-subs')
    const toggle = formGroup.querySelector('[role="switch"]')
    expect(toggle).toHaveAttribute('aria-checked', 'true')
  })

  it('calls updateConfig with keep_original_subs=false when toggle is clicked', () => {
    renderPage()
    const formGroup = screen.getByTestId('form-group-keep-original-subs')
    const toggle = formGroup.querySelector('[role="switch"]') as HTMLElement
    fireEvent.click(toggle)
    expect(mockMutate).toHaveBeenCalledWith({ keep_original_subs: false })
  })

  it('displays sidecar_format value from config', () => {
    renderPage()
    const input = screen.getByTestId('input-sidecar-format') as HTMLInputElement
    expect(input.value).toBe('srt')
  })

  it('calls updateConfig with sidecar_format on change', () => {
    renderPage()
    const input = screen.getByTestId('input-sidecar-format')
    fireEvent.change(input, { target: { value: 'ass' } })
    expect(mockMutate).toHaveBeenCalledWith({ sidecar_format: 'ass' })
  })
})
