/**
 * SubtitlesSettings.test.tsx — Tests for the Subtitles settings page.
 *
 * Covers:
 * - Renders the page via SettingsDetailLayout
 * - All 8 sections are present (data-testid attributes)
 * - Sections 3-5 (Embedded Extraction, Language Profiles, Fansub Preferences)
 *   use the `advanced` prop and are collapsed by default
 * - Expanding an advanced section via toggle reveals its content
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { BrowserRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { SubtitlesSettings } from '../SubtitlesSettings'

// ─── Mocks ───────────────────────────────────────────────────────────────────

// Mock heavy lazy-loaded sub-tabs so tests don't require real API calls
vi.mock('@/pages/Settings/ScoringTab', () => ({
  ScoringTab: () => <div data-testid="mock-scoring-tab">Scoring Tab</div>,
}))

vi.mock('@/pages/Settings/AdvancedTab', () => ({
  LanguageProfilesTab: () => (
    <div data-testid="mock-language-profiles-tab">Language Profiles Tab</div>
  ),
  SubtitleToolsTab: () => <div data-testid="mock-subtitle-tools-tab">Subtitle Tools Tab</div>,
}))

const mockMutate = vi.fn()

vi.mock('@/hooks/useApi', () => ({
  useConfig: () => ({
    data: {
      wanted_auto_extract: 'false',
      use_embedded_subs: 'true',
      hi_removal_enabled: 'false',
      wanted_skip_srt_on_no_ass: 'true',
      credit_threshold_sec: 90,
      op_window_sec: 300,
      // Subtitle Naming (Step 38)
      subtitle_language_code_format: 'iso_639_1',
      subtitle_suffix_separator: 'dot',
      subtitle_hi_suffix: 'hi',
      subtitle_forced_suffix: 'forced',
      // Scan Filters (Step 42)
      scan_ignore_patterns: '[]',
      scan_min_file_size_mb: 0,
      scan_ignore_languages: '[]',
      // Per-Language Score Thresholds (Step 43)
      score_threshold_per_language: '{}',
    },
    isLoading: false,
  }),
  useUpdateConfig: () => ({
    mutate: mockMutate,
    isPending: false,
  }),
  useScoringWeights: () => ({ data: undefined }),
  useUpdateScoringWeights: () => ({ mutate: vi.fn() }),
  useResetScoringWeights: () => ({ mutate: vi.fn() }),
  useProviderModifiers: () => ({ data: undefined }),
  useUpdateProviderModifiers: () => ({ mutate: vi.fn() }),
  useScoringPresets: () => ({ data: undefined }),
  useImportScoringPreset: () => ({ mutate: vi.fn() }),
  useProviders: () => ({ data: { providers: [] } }),
  useLanguageProfiles: () => ({ data: [], isLoading: false }),
  useCreateProfile: () => ({ mutate: vi.fn() }),
  useUpdateProfile: () => ({ mutate: vi.fn() }),
  useDeleteProfile: () => ({ mutate: vi.fn() }),
}))

vi.mock('@/components/shared/Toast', () => ({
  toast: vi.fn(),
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
        <SubtitlesSettings />
      </QueryClientProvider>
    </BrowserRouter>,
  )
}

// ─── Tests ────────────────────────────────────────────────────────────────────

describe('SubtitlesSettings', () => {
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

  it('renders the Scoring section', () => {
    renderPage()
    expect(screen.getByTestId('section-scoring')).toBeInTheDocument()
  })

  it('renders the Format & Tools section', () => {
    renderPage()
    expect(screen.getByTestId('section-format-tools')).toBeInTheDocument()
  })

  it('renders the Embedded Extraction section', () => {
    renderPage()
    expect(screen.getByTestId('section-embedded-extraction')).toBeInTheDocument()
  })

  it('renders the Language Profiles section', () => {
    renderPage()
    expect(screen.getByTestId('section-language-profiles')).toBeInTheDocument()
  })

  it('renders the Fansub Preferences section', () => {
    renderPage()
    expect(screen.getByTestId('section-fansub-preferences')).toBeInTheDocument()
  })

  // ── Section titles ────────────────────────────────────────────────────────

  it('shows "Scoring" section title', () => {
    renderPage()
    const wrapper = screen.getByTestId('section-scoring')
    const title = wrapper.querySelector('[data-testid="settings-section-title"]')
    expect(title).toHaveTextContent('Scoring')
  })

  it('shows "Format & Tools" section title', () => {
    renderPage()
    const wrapper = screen.getByTestId('section-format-tools')
    const title = wrapper.querySelector('[data-testid="settings-section-title"]')
    expect(title).toHaveTextContent('Format & Tools')
  })

  it('shows "Embedded Extraction" section title', () => {
    renderPage()
    const wrapper = screen.getByTestId('section-embedded-extraction')
    const title = wrapper.querySelector('[data-testid="settings-section-title"]')
    expect(title).toHaveTextContent('Embedded Extraction')
  })

  it('shows "Language Profiles" section title', () => {
    renderPage()
    const wrapper = screen.getByTestId('section-language-profiles')
    const title = wrapper.querySelector('[data-testid="settings-section-title"]')
    expect(title).toHaveTextContent('Language Profiles')
  })

  it('shows "Fansub Preferences" section title', () => {
    renderPage()
    const wrapper = screen.getByTestId('section-fansub-preferences')
    const title = wrapper.querySelector('[data-testid="settings-section-title"]')
    expect(title).toHaveTextContent('Fansub Preferences')
  })

  // ── Advanced sections collapsed by default ────────────────────────────────

  it('Embedded Extraction advanced content is collapsed by default', () => {
    renderPage()
    const wrapper = screen.getByTestId('section-embedded-extraction')
    // Advanced toggle button exists
    const toggle = wrapper.querySelector('[data-testid="settings-section-advanced-toggle"]')
    expect(toggle).toBeInTheDocument()
    // Advanced content panel is NOT rendered yet
    expect(wrapper.querySelector('[data-testid="settings-section-advanced-content"]')).toBeNull()
  })

  it('Language Profiles advanced content is collapsed by default', () => {
    renderPage()
    const wrapper = screen.getByTestId('section-language-profiles')
    const toggle = wrapper.querySelector('[data-testid="settings-section-advanced-toggle"]')
    expect(toggle).toBeInTheDocument()
    expect(wrapper.querySelector('[data-testid="settings-section-advanced-content"]')).toBeNull()
  })

  it('Fansub Preferences advanced content is collapsed by default', () => {
    renderPage()
    const wrapper = screen.getByTestId('section-fansub-preferences')
    const toggle = wrapper.querySelector('[data-testid="settings-section-advanced-toggle"]')
    expect(toggle).toBeInTheDocument()
    expect(wrapper.querySelector('[data-testid="settings-section-advanced-content"]')).toBeNull()
  })

  // ── Non-advanced sections do NOT have an advanced toggle ─────────────────

  it('Scoring section does not have an advanced toggle', () => {
    renderPage()
    const wrapper = screen.getByTestId('section-scoring')
    expect(
      wrapper.querySelector('[data-testid="settings-section-advanced-toggle"]'),
    ).toBeNull()
  })

  it('Format & Tools section does not have an advanced toggle', () => {
    renderPage()
    const wrapper = screen.getByTestId('section-format-tools')
    expect(
      wrapper.querySelector('[data-testid="settings-section-advanced-toggle"]'),
    ).toBeNull()
  })

  // ── Expanding advanced sections ───────────────────────────────────────────

  it('Embedded Extraction expands and shows content after clicking toggle', () => {
    renderPage()
    const wrapper = screen.getByTestId('section-embedded-extraction')
    const toggle = wrapper.querySelector(
      '[data-testid="settings-section-advanced-toggle"]',
    ) as HTMLElement
    fireEvent.click(toggle)
    expect(
      wrapper.querySelector('[data-testid="settings-section-advanced-content"]'),
    ).toBeInTheDocument()
  })

  it('Fansub Preferences expands and shows content after clicking toggle', () => {
    renderPage()
    const wrapper = screen.getByTestId('section-fansub-preferences')
    const toggle = wrapper.querySelector(
      '[data-testid="settings-section-advanced-toggle"]',
    ) as HTMLElement
    fireEvent.click(toggle)
    expect(
      wrapper.querySelector('[data-testid="settings-section-advanced-content"]'),
    ).toBeInTheDocument()
    expect(screen.getByTestId('fansub-preferences-content')).toBeInTheDocument()
  })

  // ── Embedded Extraction field presence ───────────────────────────────────

  it('shows wanted_auto_extract toggle in Embedded Extraction advanced section', () => {
    renderPage()
    const wrapper = screen.getByTestId('section-embedded-extraction')
    const toggle = wrapper.querySelector('[data-testid="settings-section-advanced-toggle"]') as HTMLElement
    fireEvent.click(toggle)
    expect(screen.getByTestId('form-group-wanted-auto-extract')).toBeInTheDocument()
  })

  it('shows use_embedded_subs toggle in Embedded Extraction advanced section', () => {
    renderPage()
    const wrapper = screen.getByTestId('section-embedded-extraction')
    const toggle = wrapper.querySelector('[data-testid="settings-section-advanced-toggle"]') as HTMLElement
    fireEvent.click(toggle)
    expect(screen.getByTestId('form-group-use-embedded-subs')).toBeInTheDocument()
  })

  it('shows hi_removal_enabled toggle in Embedded Extraction advanced section', () => {
    renderPage()
    const wrapper = screen.getByTestId('section-embedded-extraction')
    const toggle = wrapper.querySelector('[data-testid="settings-section-advanced-toggle"]') as HTMLElement
    fireEvent.click(toggle)
    expect(screen.getByTestId('form-group-hi-removal-enabled')).toBeInTheDocument()
  })

  it('shows wanted_skip_srt_on_no_ass toggle in Embedded Extraction advanced section', () => {
    renderPage()
    const wrapper = screen.getByTestId('section-embedded-extraction')
    const toggle = wrapper.querySelector('[data-testid="settings-section-advanced-toggle"]') as HTMLElement
    fireEvent.click(toggle)
    expect(screen.getByTestId('form-group-wanted-skip-srt-on-no-ass')).toBeInTheDocument()
  })

  // ── Fansub Preferences field presence ────────────────────────────────────

  it('shows credit_threshold_sec input in Fansub Preferences advanced section', () => {
    renderPage()
    const wrapper = screen.getByTestId('section-fansub-preferences')
    const toggle = wrapper.querySelector('[data-testid="settings-section-advanced-toggle"]') as HTMLElement
    fireEvent.click(toggle)
    expect(screen.getByTestId('input-credit-threshold-sec')).toBeInTheDocument()
  })

  it('shows op_window_sec input in Fansub Preferences advanced section', () => {
    renderPage()
    const wrapper = screen.getByTestId('section-fansub-preferences')
    const toggle = wrapper.querySelector('[data-testid="settings-section-advanced-toggle"]') as HTMLElement
    fireEvent.click(toggle)
    expect(screen.getByTestId('input-op-window-sec')).toBeInTheDocument()
  })

  // ── Summary text for advanced sections ───────────────────────────────────

  it('shows a summary description inside the Embedded Extraction section', () => {
    renderPage()
    expect(screen.getByTestId('embedded-extraction-summary')).toBeInTheDocument()
  })

  it('shows a summary description inside the Language Profiles section', () => {
    renderPage()
    expect(screen.getByTestId('language-profiles-summary')).toBeInTheDocument()
  })

  it('shows a summary description inside the Fansub Preferences section', () => {
    renderPage()
    expect(screen.getByTestId('fansub-preferences-summary')).toBeInTheDocument()
  })

  // ── All sections exist ────────────────────────────────────────────────────

  it('renders exactly 8 settings sections', () => {
    renderPage()
    const sections = screen.getAllByTestId('settings-section')
    expect(sections).toHaveLength(8)
  })
})

// ─── Subtitle Naming section (Step 38) ───────────────────────────────────────

describe('Subtitle Naming section', () => {
  beforeEach(() => { vi.clearAllMocks() })

  it('renders heading "Subtitle Naming"', () => {
    renderPage()
    const wrapper = screen.getByTestId('section-subtitle-naming')
    const title = wrapper.querySelector('[data-testid="settings-section-title"]')
    expect(title).toHaveTextContent('Subtitle Naming')
  })

  it('select-subtitle-language-code-format defaults to "iso_639_1"', () => {
    renderPage()
    const sel = screen.getByTestId('select-subtitle-language-code-format') as HTMLSelectElement
    expect(sel.value).toBe('iso_639_1')
  })

  it('select-subtitle-suffix-separator defaults to "dot"', () => {
    renderPage()
    const sel = screen.getByTestId('select-subtitle-suffix-separator') as HTMLSelectElement
    expect(sel.value).toBe('dot')
  })

  it('input-subtitle-hi-suffix defaults to "hi"', () => {
    renderPage()
    const input = screen.getByTestId('input-subtitle-hi-suffix') as HTMLInputElement
    expect(input.value).toBe('hi')
  })

  it('input-subtitle-forced-suffix defaults to "forced"', () => {
    renderPage()
    const input = screen.getByTestId('input-subtitle-forced-suffix') as HTMLInputElement
    expect(input.value).toBe('forced')
  })

  it('changing separator calls updateConfig with { subtitle_suffix_separator: "dash" }', () => {
    renderPage()
    const sel = screen.getByTestId('select-subtitle-suffix-separator')
    fireEvent.change(sel, { target: { value: 'dash' } })
    expect(mockMutate).toHaveBeenCalledWith({ subtitle_suffix_separator: 'dash' })
  })
})

// ─── Scan Filters section (Step 42) ──────────────────────────────────────────

describe('Scan Filters section', () => {
  beforeEach(() => { vi.clearAllMocks() })

  it('renders heading "Scan Filters"', () => {
    renderPage()
    const wrapper = screen.getByTestId('section-scan-filters')
    const title = wrapper.querySelector('[data-testid="settings-section-title"]')
    expect(title).toHaveTextContent('Scan Filters')
  })

  it('textarea-scan-ignore-patterns renders with default value "[]"', () => {
    renderPage()
    const ta = screen.getByTestId('textarea-scan-ignore-patterns') as HTMLTextAreaElement
    expect(ta.value).toBe('[]')
  })

  it('input-scan-min-file-size-mb renders with value 0', () => {
    renderPage()
    const input = screen.getByTestId('input-scan-min-file-size-mb') as HTMLInputElement
    expect(Number(input.value)).toBe(0)
  })

  it('textarea-scan-ignore-languages renders with default value "[]"', () => {
    renderPage()
    const ta = screen.getByTestId('textarea-scan-ignore-languages') as HTMLTextAreaElement
    expect(ta.value).toBe('[]')
  })

  it('blurring textarea-scan-ignore-patterns calls updateConfig with { scan_ignore_patterns: \'["*.sample.*"]\' }', () => {
    renderPage()
    const ta = screen.getByTestId('textarea-scan-ignore-patterns')
    fireEvent.blur(ta, { target: { value: '["*.sample.*"]' } })
    expect(mockMutate).toHaveBeenCalledWith({ scan_ignore_patterns: '["*.sample.*"]' })
  })
})

// ─── Per-Language Score Thresholds section (Step 43) ─────────────────────────

describe('Per-Language Score Thresholds section', () => {
  beforeEach(() => { vi.clearAllMocks() })

  it('renders heading "Per-Language Score Thresholds"', () => {
    renderPage()
    const wrapper = screen.getByTestId('section-per-language-scores')
    const title = wrapper.querySelector('[data-testid="settings-section-title"]')
    expect(title).toHaveTextContent('Per-Language Score Thresholds')
  })

  it('textarea-score-threshold-per-language renders with default value "{}"', () => {
    renderPage()
    const ta = screen.getByTestId('textarea-score-threshold-per-language') as HTMLTextAreaElement
    expect(ta.value).toBe('{}')
  })

  it('blurring it calls updateConfig with { score_threshold_per_language: \'{"de":80}\' }', () => {
    renderPage()
    const ta = screen.getByTestId('textarea-score-threshold-per-language')
    fireEvent.blur(ta, { target: { value: '{"de":80}' } })
    expect(mockMutate).toHaveBeenCalledWith({ score_threshold_per_language: '{"de":80}' })
  })
})
