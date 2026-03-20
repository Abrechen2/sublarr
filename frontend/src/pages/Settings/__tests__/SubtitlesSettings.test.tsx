/**
 * SubtitlesSettings.test.tsx — Tests for the Subtitles settings page.
 *
 * Covers:
 * - Renders the page via SettingsDetailLayout
 * - All 6 sections are present (data-testid attributes)
 * - Sections 4-6 (Embedded Extraction, Language Profiles, Fansub Preferences)
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
vi.mock('@/pages/Settings/EventsTab', () => ({
  ScoringTab: () => <div data-testid="mock-scoring-tab">Scoring Tab</div>,
}))

vi.mock('@/pages/Settings/AdvancedTab', () => ({
  LanguageProfilesTab: () => (
    <div data-testid="mock-language-profiles-tab">Language Profiles Tab</div>
  ),
  SubtitleToolsTab: () => <div data-testid="mock-subtitle-tools-tab">Subtitle Tools Tab</div>,
}))

vi.mock('@/pages/Settings/CleanupTab', () => ({
  CleanupTab: () => <div data-testid="mock-cleanup-tab">Cleanup Tab</div>,
}))

vi.mock('@/hooks/useApi', () => ({
  useConfig: () => ({
    data: { webhook_auto_scan: 'false' },
    isLoading: false,
  }),
  useUpdateConfig: () => ({
    mutate: vi.fn(),
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

  it('renders the Cleanup section', () => {
    renderPage()
    expect(screen.getByTestId('section-cleanup')).toBeInTheDocument()
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

  it('shows "Cleanup" section title', () => {
    renderPage()
    const wrapper = screen.getByTestId('section-cleanup')
    const title = wrapper.querySelector('[data-testid="settings-section-title"]')
    expect(title).toHaveTextContent('Cleanup')
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

  it('Cleanup section does not have an advanced toggle', () => {
    renderPage()
    const wrapper = screen.getByTestId('section-cleanup')
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

  // ── All 6 sections exist ──────────────────────────────────────────────────

  it('renders exactly 6 settings sections', () => {
    renderPage()
    const sections = screen.getAllByTestId('settings-section')
    expect(sections).toHaveLength(6)
  })
})
