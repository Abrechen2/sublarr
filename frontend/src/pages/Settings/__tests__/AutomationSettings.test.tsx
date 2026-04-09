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
import userEvent from '@testing-library/user-event'
import { BrowserRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { AutomationSettings } from '../AutomationSettings'

// ─── Mocks ───────────────────────────────────────────────────────────────────

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, opts?: string | Record<string, unknown>) => {
      if (typeof opts === 'string') return opts
      if (opts !== undefined && typeof opts === 'object' && 'count' in opts)
        return `${key}:${String(opts.count)}`
      return key
    },
  }),
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
      wanted_scan_interval_hours: '0',
      wanted_scan_on_startup: 'false',
      wanted_search_max_items_per_run: '50',
      wanted_max_search_attempts: '3',
      wanted_auto_extract: 'false',
      wanted_anime_only: 'false',
      wanted_anime_movies_only: 'false',
      wanted_adaptive_backoff_enabled: 'false',
      wanted_backoff_base_hours: '1',
      wanted_backoff_cap_hours: '24',
      wanted_skip_srt_on_no_ass: 'false',
      upgrade_enabled: 'false',
      upgrade_min_score_delta: '10',
      upgrade_scan_interval_hours: '24',
      upgrade_window_days: '30',
      upgrade_prefer_ass: 'false',
      webhook_delay_minutes: '5',
      webhook_auto_scan: 'false',
      webhook_auto_translate: 'false',
      wanted_auto_translate: 'false',
      auto_sync_after_download: 'false',
      auto_process_common_fixes: 'false',
      auto_process_hi_removal: 'false',
      auto_process_credit_removal: 'false',
      auto_process_sync_threshold: '80',
      auto_process_sync_fallback_engine: 'ffsubsync',
      auto_nfo_export: 'false',
      streaming_enabled: 'false',
      jellyfin_play_translate_enabled: 'false',
      auto_cleanup_after_extract: 'false',
      auto_cleanup_keep_languages: 'de,en',
      auto_cleanup_keep_formats: 'ass,srt',
      subtitle_trash_retention_days: '30',
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

  it('renders exactly 4 settings sections', () => {
    renderPage()
    const sections = screen.getAllByTestId('settings-section')
    expect(sections).toHaveLength(4)
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

  it('renders the Webhook section', () => {
    renderPage()
    expect(screen.getByTestId('section-webhook')).toBeInTheDocument()
  })

  it('renders the Processing Pipeline section', () => {
    renderPage()
    expect(screen.getByTestId('section-processing-pipeline')).toBeInTheDocument()
  })

  it('renders the Cleanup section', () => {
    renderPage()
    expect(screen.getByTestId('section-cleanup')).toBeInTheDocument()
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

  it('Processing Pipeline nav card renders a Configure link', () => {
    renderPage()
    const wrapper = screen.getByTestId('section-processing-pipeline')
    expect(wrapper.querySelector('a')).toBeInTheDocument()
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

  it('Search & Scan section has an advanced toggle (advancedCount=8)', () => {
    renderPage()
    const wrapper = screen.getByTestId('section-search-scan')
    expect(
      wrapper.querySelector('[data-testid="settings-section-advanced-toggle"]'),
    ).toBeInTheDocument()
  })

  it('Upgrade Rules section has an advanced toggle (advancedCount=1)', () => {
    renderPage()
    const wrapper = screen.getByTestId('section-upgrade-rules')
    expect(
      wrapper.querySelector('[data-testid="settings-section-advanced-toggle"]'),
    ).toBeInTheDocument()
  })

  it('Processing Pipeline nav card does not have an advanced toggle', () => {
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

  it('displays wanted_search_max_items_per_run value from config (in advanced)', () => {
    renderPage()
    const wrapper = screen.getByTestId('section-search-scan')
    const toggle = wrapper.querySelector('[data-testid="settings-section-advanced-toggle"]') as HTMLElement
    fireEvent.click(toggle)
    const input = screen.getByTestId('input-wanted-search-max-items-per-run') as HTMLInputElement
    expect(input.value).toBe('50')
  })

  it('calls updateConfig with wanted_search_max_items_per_run as number on change (in advanced)', () => {
    renderPage()
    const wrapper = screen.getByTestId('section-search-scan')
    const toggle = wrapper.querySelector('[data-testid="settings-section-advanced-toggle"]') as HTMLElement
    fireEvent.click(toggle)
    const input = screen.getByTestId('input-wanted-search-max-items-per-run')
    fireEvent.change(input, { target: { value: '100' } })
    expect(mockMutate).toHaveBeenCalledWith({ wanted_search_max_items_per_run: 100 })
  })

  it('displays wanted_max_search_attempts value from config', () => {
    renderPage()
    const input = screen.getByTestId('input-wanted-max-search-attempts') as HTMLInputElement
    expect(input.value).toBe('3')
  })

  it('calls updateConfig with wanted_max_search_attempts as number on change', () => {
    renderPage()
    const input = screen.getByTestId('input-wanted-max-search-attempts')
    fireEvent.change(input, { target: { value: '5' } })
    expect(mockMutate).toHaveBeenCalledWith({ wanted_max_search_attempts: 5 })
  })


  it('calls updateConfig with wanted_anime_only=true when toggled (in advanced)', () => {
    renderPage()
    const wrapper = screen.getByTestId('section-search-scan')
    const advToggle = wrapper.querySelector('[data-testid="settings-section-advanced-toggle"]') as HTMLElement
    fireEvent.click(advToggle)
    const fg = screen.getByTestId('form-group-wanted-anime-only')
    const toggle = fg.querySelector('[role="switch"]') as HTMLElement
    fireEvent.click(toggle)
    expect(mockMutate).toHaveBeenCalledWith({ wanted_anime_only: true })
  })

  it('calls updateConfig with wanted_anime_movies_only=true when toggled (in advanced)', () => {
    renderPage()
    const wrapper = screen.getByTestId('section-search-scan')
    const advToggle = wrapper.querySelector('[data-testid="settings-section-advanced-toggle"]') as HTMLElement
    fireEvent.click(advToggle)
    const fg = screen.getByTestId('form-group-wanted-anime-movies-only')
    const toggle = fg.querySelector('[role="switch"]') as HTMLElement
    fireEvent.click(toggle)
    expect(mockMutate).toHaveBeenCalledWith({ wanted_anime_movies_only: true })
  })


  it('calls updateConfig with wanted_adaptive_backoff_enabled=true when toggled (in advanced)', () => {
    renderPage()
    const wrapper = screen.getByTestId('section-search-scan')
    const advToggle = wrapper.querySelector('[data-testid="settings-section-advanced-toggle"]') as HTMLElement
    fireEvent.click(advToggle)
    const fg = screen.getByTestId('form-group-wanted-adaptive-backoff-enabled')
    const toggle = fg.querySelector('[role="switch"]') as HTMLElement
    fireEvent.click(toggle)
    expect(mockMutate).toHaveBeenCalledWith({ wanted_adaptive_backoff_enabled: true })
  })

  it('backoff hour fields are hidden when wanted_adaptive_backoff_enabled is false', () => {
    renderPage()
    expect(screen.queryByTestId('input-wanted-backoff-base-hours')).toBeNull()
    expect(screen.queryByTestId('input-wanted-backoff-cap-hours')).toBeNull()
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

  it('displays upgrade_window_days value from config', () => {
    renderPage()
    const input = screen.getByTestId('input-upgrade-window-days') as HTMLInputElement
    expect(input.value).toBe('30')
  })

  it('calls updateConfig with upgrade_window_days as number on change', () => {
    renderPage()
    const input = screen.getByTestId('input-upgrade-window-days')
    fireEvent.change(input, { target: { value: '14' } })
    expect(mockMutate).toHaveBeenCalledWith({ upgrade_window_days: 14 })
  })

  it('calls updateConfig with upgrade_prefer_ass=true when toggled', () => {
    renderPage()
    const fg = screen.getByTestId('form-group-upgrade-prefer-ass')
    const toggle = fg.querySelector('[role="switch"]') as HTMLElement
    fireEvent.click(toggle)
    expect(mockMutate).toHaveBeenCalledWith({ upgrade_prefer_ass: true })
  })

  // ── Webhook interactions ───────────────────────────────────────────────────

  it('displays webhook_delay_minutes value from config', () => {
    renderPage()
    const input = screen.getByTestId('input-webhook-delay-minutes') as HTMLInputElement
    expect(input.value).toBe('5')
  })

  it('calls updateConfig with webhook_delay_minutes as number on change', () => {
    renderPage()
    const input = screen.getByTestId('input-webhook-delay-minutes')
    fireEvent.change(input, { target: { value: '10' } })
    expect(mockMutate).toHaveBeenCalledWith({ webhook_delay_minutes: 10 })
  })

  it('calls updateConfig with webhook_auto_scan=true when toggled', () => {
    renderPage()
    const fg = screen.getByTestId('form-group-webhook-auto-scan')
    const toggle = fg.querySelector('[role="switch"]') as HTMLElement
    fireEvent.click(toggle)
    expect(mockMutate).toHaveBeenCalledWith({ webhook_auto_scan: true })
  })

  it('calls updateConfig with webhook_auto_translate=true when toggled', () => {
    renderPage()
    const fg = screen.getByTestId('form-group-webhook-auto-translate')
    const toggle = fg.querySelector('[role="switch"]') as HTMLElement
    fireEvent.click(toggle)
    expect(mockMutate).toHaveBeenCalledWith({ webhook_auto_translate: true })
  })

  // ── Processing Pipeline nav card — renders a Configure link ─────────────────

  it('Processing Pipeline nav card renders a link to /settings/automation/post-processing', () => {
    renderPage()
    const wrapper = screen.getByTestId('section-processing-pipeline')
    const link = wrapper.querySelector('a')
    expect(link).toBeInTheDocument()
    expect(link).toHaveAttribute('href', '/settings/automation/post-processing')
  })

  // ── Cleanup nav card — renders a Configure link ───────────────────────────

  it('Cleanup nav card renders a link to /settings/cleanup', () => {
    renderPage()
    const wrapper = screen.getByTestId('section-cleanup')
    const link = wrapper.querySelector('a')
    expect(link).toBeInTheDocument()
    expect(link).toHaveAttribute('href', '/settings/cleanup')
  })

  // ── Search & Scan — sub-group headings ────────────────────────────────────

  describe('Search & Scan — sub-group headings', () => {
    it('renders "Bibliotheks-Scan" sub-group heading inside section-search-scan', () => {
      renderPage()
      const section = screen.getByTestId('section-search-scan')
      expect(section).toHaveTextContent('automation_page.subheading_library_scan')
    })

    it('renders "Untertitel-Suche" sub-group heading inside section-search-scan', () => {
      renderPage()
      const section = screen.getByTestId('section-search-scan')
      expect(section).toHaveTextContent('automation_page.subheading_subtitle_search')
    })

    it('"Bibliotheks-Scan" heading appears before "Untertitel-Suche" heading in the DOM', () => {
      renderPage()
      const section = screen.getByTestId('section-search-scan')
      const headings = section.querySelectorAll('[data-testid^="search-scan-subheading-"]')
      expect(headings).toHaveLength(2)
      expect(headings[0]).toHaveAttribute('data-testid', 'search-scan-subheading-scan')
      expect(headings[1]).toHaveAttribute('data-testid', 'search-scan-subheading-search')
    })

    it('wanted_scan_interval_hours input appears before wanted_search_interval_hours input in the DOM', () => {
      renderPage()
      const section = screen.getByTestId('section-search-scan')
      const allInputs = section.querySelectorAll('input[type="number"]')
      const ids = Array.from(allInputs).map((el) => el.getAttribute('data-testid'))
      const scanIdx = ids.indexOf('input-wanted-scan-interval-hours')
      const searchIdx = ids.indexOf('input-wanted-search-interval-hours')
      expect(scanIdx).toBeGreaterThanOrEqual(0)
      expect(searchIdx).toBeGreaterThanOrEqual(0)
      expect(scanIdx).toBeLessThan(searchIdx)
    })
  })

  // ── Search & Scan — scan interval ─────────────────────────────────────────

  describe('Search & Scan — scan interval', () => {
    it('renders form-group for wanted_scan_interval_hours', () => {
      renderPage()
      expect(screen.getByTestId('form-group-wanted-scan-interval-hours')).toBeInTheDocument()
    })

    it('displays wanted_scan_interval_hours value from config', () => {
      renderPage()
      const input = screen.getByTestId('input-wanted-scan-interval-hours') as HTMLInputElement
      expect(input.value).toBe('0')
    })

    it('input has min="0" attribute (0 = disabled)', () => {
      renderPage()
      const input = screen.getByTestId('input-wanted-scan-interval-hours') as HTMLInputElement
      expect(input).toHaveAttribute('min', '0')
    })

    it('calls updateConfig with wanted_scan_interval_hours as number on change', () => {
      renderPage()
      const input = screen.getByTestId('input-wanted-scan-interval-hours')
      fireEvent.change(input, { target: { value: '4' } })
      expect(mockMutate).toHaveBeenCalledWith({ wanted_scan_interval_hours: 4 })
    })

    it('calls updateConfig with 0 when input value is "0"', async () => {
      // The mock config starts with '0'. Use userEvent.clear + type to bypass
      // React 19 controlled-input deduplication (fireEvent.change is suppressed
      // when the target value matches the current React prop value).
      const user = userEvent.setup()
      renderPage()
      const input = screen.getByTestId('input-wanted-scan-interval-hours')
      await user.clear(input)
      await user.type(input, '0')
      expect(mockMutate).toHaveBeenCalledWith({ wanted_scan_interval_hours: 0 })
    })
  })

  // ── Search & Scan — scan on startup ───────────────────────────────────────

  describe('Search & Scan — scan on startup', () => {
    it('renders form-group for wanted_scan_on_startup', () => {
      renderPage()
      expect(screen.getByTestId('form-group-wanted-scan-on-startup')).toBeInTheDocument()
    })

    it('wanted_scan_on_startup toggle reflects config value (false)', () => {
      renderPage()
      const fg = screen.getByTestId('form-group-wanted-scan-on-startup')
      const toggle = fg.querySelector('[role="switch"]')
      expect(toggle).toHaveAttribute('aria-checked', 'false')
    })

    it('calls updateConfig with wanted_scan_on_startup=true when toggled', () => {
      renderPage()
      const fg = screen.getByTestId('form-group-wanted-scan-on-startup')
      const toggle = fg.querySelector('[role="switch"]') as HTMLElement
      fireEvent.click(toggle)
      expect(mockMutate).toHaveBeenCalledWith({ wanted_scan_on_startup: true })
    })
  })
})
