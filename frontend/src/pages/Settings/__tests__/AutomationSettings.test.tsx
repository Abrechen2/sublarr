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
      auto_nfo_export: 'false',
      jellyfin_play_translate_enabled: 'false',
      auto_cleanup_after_extract: 'false',
      auto_cleanup_keep_languages: 'de,en',
      auto_cleanup_keep_formats: 'ass,srt',
      subtitle_trash_retention_days: '7',
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

  it('renders exactly 7 settings sections', () => {
    renderPage()
    const sections = screen.getAllByTestId('settings-section')
    expect(sections).toHaveLength(7)
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

  it('renders the Provider Re-ranking section', () => {
    renderPage()
    expect(screen.getByTestId('section-provider-reranking')).toBeInTheDocument()
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

  it('displays wanted_search_max_items_per_run value from config', () => {
    renderPage()
    const input = screen.getByTestId('input-wanted-search-max-items-per-run') as HTMLInputElement
    expect(input.value).toBe('50')
  })

  it('calls updateConfig with wanted_search_max_items_per_run as number on change', () => {
    renderPage()
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

  it('calls updateConfig with wanted_auto_extract=true when toggled', () => {
    renderPage()
    const fg = screen.getByTestId('form-group-wanted-auto-extract')
    const toggle = fg.querySelector('[role="switch"]') as HTMLElement
    fireEvent.click(toggle)
    expect(mockMutate).toHaveBeenCalledWith({ wanted_auto_extract: true })
  })

  it('calls updateConfig with wanted_anime_only=true when toggled', () => {
    renderPage()
    const fg = screen.getByTestId('form-group-wanted-anime-only')
    const toggle = fg.querySelector('[role="switch"]') as HTMLElement
    fireEvent.click(toggle)
    expect(mockMutate).toHaveBeenCalledWith({ wanted_anime_only: true })
  })

  it('calls updateConfig with wanted_anime_movies_only=true when toggled', () => {
    renderPage()
    const fg = screen.getByTestId('form-group-wanted-anime-movies-only')
    const toggle = fg.querySelector('[role="switch"]') as HTMLElement
    fireEvent.click(toggle)
    expect(mockMutate).toHaveBeenCalledWith({ wanted_anime_movies_only: true })
  })

  it('calls updateConfig with wanted_skip_srt_on_no_ass=true when toggled', () => {
    renderPage()
    const fg = screen.getByTestId('form-group-wanted-skip-srt-on-no-ass')
    const toggle = fg.querySelector('[role="switch"]') as HTMLElement
    fireEvent.click(toggle)
    expect(mockMutate).toHaveBeenCalledWith({ wanted_skip_srt_on_no_ass: true })
  })

  it('calls updateConfig with wanted_adaptive_backoff_enabled=true when toggled', () => {
    renderPage()
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

  it('calls updateConfig with auto_process_common_fixes=true when toggled', () => {
    renderPage()
    const fg = screen.getByTestId('form-group-auto-process-common-fixes')
    const toggle = fg.querySelector('[role="switch"]') as HTMLElement
    fireEvent.click(toggle)
    expect(mockMutate).toHaveBeenCalledWith({ auto_process_common_fixes: true })
  })

  it('calls updateConfig with auto_process_hi_removal=true when toggled', () => {
    renderPage()
    const fg = screen.getByTestId('form-group-auto-process-hi-removal')
    const toggle = fg.querySelector('[role="switch"]') as HTMLElement
    fireEvent.click(toggle)
    expect(mockMutate).toHaveBeenCalledWith({ auto_process_hi_removal: true })
  })

  it('calls updateConfig with auto_process_credit_removal=true when toggled', () => {
    renderPage()
    const fg = screen.getByTestId('form-group-auto-process-credit-removal')
    const toggle = fg.querySelector('[role="switch"]') as HTMLElement
    fireEvent.click(toggle)
    expect(mockMutate).toHaveBeenCalledWith({ auto_process_credit_removal: true })
  })

  it('displays auto_process_sync_threshold value from config', () => {
    renderPage()
    const input = screen.getByTestId('input-auto-process-sync-threshold') as HTMLInputElement
    expect(input.value).toBe('80')
  })

  it('calls updateConfig with auto_process_sync_threshold as number on change', () => {
    renderPage()
    const input = screen.getByTestId('input-auto-process-sync-threshold')
    fireEvent.change(input, { target: { value: '90' } })
    expect(mockMutate).toHaveBeenCalledWith({ auto_process_sync_threshold: 90 })
  })

  it('calls updateConfig with auto_nfo_export=true when toggled', () => {
    renderPage()
    const fg = screen.getByTestId('form-group-auto-nfo-export')
    const toggle = fg.querySelector('[role="switch"]') as HTMLElement
    fireEvent.click(toggle)
    expect(mockMutate).toHaveBeenCalledWith({ auto_nfo_export: true })
  })

  it('calls updateConfig with jellyfin_play_translate_enabled=true when toggled', () => {
    renderPage()
    const fg = screen.getByTestId('form-group-jellyfin-play-translate-enabled')
    const toggle = fg.querySelector('[role="switch"]') as HTMLElement
    fireEvent.click(toggle)
    expect(mockMutate).toHaveBeenCalledWith({ jellyfin_play_translate_enabled: true })
  })

  // ── Cleanup interactions ───────────────────────────────────────────────────

  it('displays auto_cleanup_keep_languages value from config', () => {
    renderPage()
    const input = screen.getByTestId('input-auto-cleanup-keep-languages') as HTMLInputElement
    expect(input.value).toBe('de,en')
  })

  it('calls updateConfig with auto_cleanup_keep_languages on change', () => {
    renderPage()
    const input = screen.getByTestId('input-auto-cleanup-keep-languages')
    fireEvent.change(input, { target: { value: 'de' } })
    expect(mockMutate).toHaveBeenCalledWith({ auto_cleanup_keep_languages: 'de' })
  })

  it('displays auto_cleanup_keep_formats value from config', () => {
    renderPage()
    const input = screen.getByTestId('input-auto-cleanup-keep-formats') as HTMLInputElement
    expect(input.value).toBe('ass,srt')
  })

  it('calls updateConfig with auto_cleanup_keep_formats on change', () => {
    renderPage()
    const input = screen.getByTestId('input-auto-cleanup-keep-formats')
    fireEvent.change(input, { target: { value: 'ass' } })
    expect(mockMutate).toHaveBeenCalledWith({ auto_cleanup_keep_formats: 'ass' })
  })

  it('displays subtitle_trash_retention_days value from config', () => {
    renderPage()
    const input = screen.getByTestId('input-subtitle-trash-retention-days') as HTMLInputElement
    expect(input.value).toBe('7')
  })

  it('calls updateConfig with subtitle_trash_retention_days as number on change', () => {
    renderPage()
    const input = screen.getByTestId('input-subtitle-trash-retention-days')
    fireEvent.change(input, { target: { value: '14' } })
    expect(mockMutate).toHaveBeenCalledWith({ subtitle_trash_retention_days: 14 })
  })
})
