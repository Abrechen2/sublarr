import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { BrowserRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ScoringTab } from '../ScoringTab'

// ─── Mocks ────────────────────────────────────────────────────────────────────

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key.split('.').pop() ?? key,
    i18n: { language: 'en', changeLanguage: vi.fn() },
  }),
}))

const mockUpdateWeights = vi.fn()
const mockResetWeights = vi.fn()
const mockUpdateModifiers = vi.fn()
const mockImportPreset = vi.fn()
const mockUpdateConfig = vi.fn()

const mockScoringWeights = {
  episode: { words: 50, season: 50, episode: 50, resolution: 40, format_bonus: 30 },
  movie: { words: 50, year: 40, resolution: 40, format_bonus: 30 },
  defaults: {
    episode: { words: 50, season: 50, episode: 50, resolution: 40, format_bonus: 0 },
    movie: { words: 50, year: 40, resolution: 40, format_bonus: 0 },
  },
}

vi.mock('@/hooks/useApi', () => ({
  useScoringWeights: () => ({ data: mockScoringWeights }),
  useUpdateScoringWeights: () => ({ mutate: mockUpdateWeights, isPending: false }),
  useResetScoringWeights: () => ({ mutate: mockResetWeights, isPending: false }),
  useProviderModifiers: () => ({ data: { OpenSubtitles: 0, Subscene: 10 } }),
  useUpdateProviderModifiers: () => ({ mutate: mockUpdateModifiers, isPending: false }),
  useScoringPresets: () => ({
    data: [
      { name: 'Anime', description: 'Optimised for anime' },
      { name: 'General', description: 'Balanced for any content' },
    ],
  }),
  useImportScoringPreset: () => ({ mutate: mockImportPreset, isPending: false }),
  useProviders: () => ({ data: { providers: [{ name: 'OpenSubtitles' }, { name: 'Subscene' }] } }),
  useConfig: () => ({
    data: {
      release_group_prefer: 'SubsPlease',
      release_group_exclude: '',
      release_group_prefer_bonus: 20,
      'providers.mt_penalty': -30,
      'providers.mt_confidence_threshold': 50,
    },
  }),
  useUpdateConfig: () => ({ mutate: mockUpdateConfig, isPending: false }),
  // Plan B4 — penalty rules hooks consumed by ScoringPenaltyRules section
  usePenaltyRules: () => ({ data: { rules: [] }, isLoading: false }),
  useUpdatePenaltyRule: () => ({ mutate: vi.fn(), isPending: false }),
}))

vi.mock('@/components/shared/Toast', () => ({ toast: vi.fn() }))

// ─── Test helpers ─────────────────────────────────────────────────────────────

function renderTab() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <BrowserRouter>
        <ScoringTab />
      </BrowserRouter>
    </QueryClientProvider>,
  )
}

// ─── Tests ────────────────────────────────────────────────────────────────────

describe('ScoringTab', () => {
  beforeEach(() => vi.clearAllMocks())

  // ── Root ──────────────────────────────────────────────────────────────────

  it('renders the scoring-tab root container', () => {
    renderTab()
    expect(screen.getByTestId('scoring-tab')).toBeInTheDocument()
  })

  // ── Presets ───────────────────────────────────────────────────────────────

  it('renders preset buttons', () => {
    renderTab()
    expect(screen.getByTestId('preset-buttons')).toBeInTheDocument()
  })

  it('renders a button for each preset', () => {
    renderTab()
    expect(screen.getByTestId('btn-preset-anime')).toBeInTheDocument()
    expect(screen.getByTestId('btn-preset-general')).toBeInTheDocument()
  })

  // ── What Matters Most ─────────────────────────────────────────────────────

  it('renders the prefer-ass toggle', () => {
    renderTab()
    expect(screen.getByTestId('form-group-prefer-ass')).toBeInTheDocument()
  })

  it('renders the penalize-mt toggle', () => {
    renderTab()
    expect(screen.getByTestId('form-group-penalize-mt')).toBeInTheDocument()
  })

  it('prefer-ass toggle reflects current weight value (format_bonus > 0 = checked)', () => {
    renderTab()
    // format_bonus = 30 in mock → toggle should be ON
    const toggle = screen.getByTestId('form-group-prefer-ass').querySelector('[role="switch"]') as HTMLElement
    expect(toggle?.getAttribute('aria-checked')).toBe('true')
  })

  it('penalize-mt toggle reflects mt_penalty < 0 (= checked)', () => {
    renderTab()
    // mt_penalty = -30 → checked
    const toggle = screen.getByTestId('form-group-penalize-mt').querySelector('[role="switch"]') as HTMLElement
    expect(toggle?.getAttribute('aria-checked')).toBe('true')
  })

  // ── Release Group ─────────────────────────────────────────────────────────

  it('renders the preferred groups input with loaded value', () => {
    renderTab()
    const input = screen.getByTestId('input-rg-prefer') as HTMLInputElement
    expect(input.value).toBe('SubsPlease')
  })

  it('renders the blocked groups input', () => {
    renderTab()
    expect(screen.getByTestId('input-rg-exclude')).toBeInTheDocument()
  })

  it('shows prefer bonus input when preferred groups are set', () => {
    renderTab()
    // rgPrefer = 'SubsPlease' → bonus field visible
    expect(screen.getByTestId('input-rg-bonus')).toBeInTheDocument()
  })

  it('renders the release group Save button', () => {
    renderTab()
    expect(screen.getByTestId('btn-save-release-group')).toBeInTheDocument()
  })

  // ── Advanced (collapsed by default) ──────────────────────────────────────

  it('advanced content is hidden by default', () => {
    renderTab()
    expect(screen.queryByTestId('advanced-scoring-content')).toBeNull()
  })

  it('shows the advanced toggle button', () => {
    renderTab()
    expect(screen.getByTestId('btn-toggle-advanced')).toBeInTheDocument()
  })

  it('expands advanced section after clicking toggle', () => {
    renderTab()
    fireEvent.click(screen.getByTestId('btn-toggle-advanced'))
    expect(screen.getByTestId('advanced-scoring-content')).toBeInTheDocument()
  })

  it('shows episode-weights after expanding advanced', () => {
    renderTab()
    fireEvent.click(screen.getByTestId('btn-toggle-advanced'))
    expect(screen.getByTestId('episode-weights')).toBeInTheDocument()
  })

  it('shows movie-weights after expanding advanced', () => {
    renderTab()
    fireEvent.click(screen.getByTestId('btn-toggle-advanced'))
    expect(screen.getByTestId('movie-weights')).toBeInTheDocument()
  })

  it('shows weight sliders for each episode weight after expanding', () => {
    renderTab()
    fireEvent.click(screen.getByTestId('btn-toggle-advanced'))
    for (const key of Object.keys(mockScoringWeights.episode)) {
      expect(screen.getAllByTestId(`slider-weight-${key}`).length).toBeGreaterThanOrEqual(1)
    }
  })

  it('shows provider modifiers sliders after expanding', () => {
    renderTab()
    fireEvent.click(screen.getByTestId('btn-toggle-advanced'))
    expect(screen.getByTestId('provider-modifiers')).toBeInTheDocument()
    expect(screen.getByTestId('slider-modifier-OpenSubtitles')).toBeInTheDocument()
    expect(screen.getByTestId('slider-modifier-Subscene')).toBeInTheDocument()
  })

  it('shows MT detection controls after expanding', () => {
    renderTab()
    fireEvent.click(screen.getByTestId('btn-toggle-advanced'))
    expect(screen.getByTestId('slider-mt-penalty')).toBeInTheDocument()
    expect(screen.getByTestId('slider-mt-threshold')).toBeInTheDocument()
  })

  it('shows Save Weights and Reset buttons after expanding', () => {
    renderTab()
    fireEvent.click(screen.getByTestId('btn-toggle-advanced'))
    expect(screen.getByTestId('btn-save-weights')).toBeInTheDocument()
    expect(screen.getByTestId('btn-reset-weights')).toBeInTheDocument()
  })
})
