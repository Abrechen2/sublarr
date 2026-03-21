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
  episode: { words: 50, season: 50, episode: 50, resolution: 40, source: 40 },
  movie: { words: 50, year: 40, resolution: 40, source: 40 },
  defaults: {
    episode: { words: 50, season: 50, episode: 50, resolution: 40, source: 40 },
    movie: { words: 50, year: 40, resolution: 40, source: 40 },
  },
}

vi.mock('@/hooks/useApi', () => ({
  useScoringWeights: () => ({ data: mockScoringWeights }),
  useUpdateScoringWeights: () => ({ mutate: mockUpdateWeights, isPending: false }),
  useResetScoringWeights: () => ({ mutate: mockResetWeights, isPending: false }),
  useProviderModifiers: () => ({ data: { OpenSubtitles: 0, Subscene: 10 } }),
  useUpdateProviderModifiers: () => ({ mutate: mockUpdateModifiers, isPending: false }),
  useScoringPresets: () => ({ data: [{ name: 'Anime', description: 'Optimised for anime' }] }),
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

  // ── Root container ───────────────────────────────────────────────────────

  it('renders the scoring-tab root container', () => {
    renderTab()
    expect(screen.getByTestId('scoring-tab')).toBeInTheDocument()
  })

  // ── Preset section ───────────────────────────────────────────────────────

  it('renders the preset select', () => {
    renderTab()
    expect(screen.getByTestId('select-preset')).toBeInTheDocument()
  })

  it('renders the Apply preset button', () => {
    renderTab()
    expect(screen.getByTestId('btn-apply-preset')).toBeInTheDocument()
  })

  it('renders the Custom JSON toggle button', () => {
    renderTab()
    expect(screen.getByTestId('btn-toggle-custom-import')).toBeInTheDocument()
  })

  it('shows custom JSON textarea after clicking the Custom JSON button', () => {
    renderTab()
    fireEvent.click(screen.getByTestId('btn-toggle-custom-import'))
    expect(screen.getByTestId('textarea-custom-preset')).toBeInTheDocument()
  })

  // ── Scoring weights ──────────────────────────────────────────────────────

  it('renders the weight-tables container', () => {
    renderTab()
    expect(screen.getByTestId('weight-tables')).toBeInTheDocument()
  })

  it('renders the episode-weights group', () => {
    renderTab()
    expect(screen.getByTestId('episode-weights')).toBeInTheDocument()
  })

  it('renders the movie-weights group', () => {
    renderTab()
    expect(screen.getByTestId('movie-weights')).toBeInTheDocument()
  })

  it('renders sliders for each episode weight', () => {
    renderTab()
    for (const key of Object.keys(mockScoringWeights.episode)) {
      expect(screen.getAllByTestId(`slider-weight-${key}`).length).toBeGreaterThanOrEqual(1)
    }
  })

  it('renders number inputs for each episode weight', () => {
    renderTab()
    for (const key of Object.keys(mockScoringWeights.episode)) {
      expect(screen.getAllByTestId(`input-weight-${key}`).length).toBeGreaterThanOrEqual(1)
    }
  })

  it('renders at least one Save button', () => {
    renderTab()
    expect(screen.getAllByTestId('btn-save-weights').length).toBeGreaterThanOrEqual(1)
  })

  it('renders the Reset to Defaults button', () => {
    renderTab()
    expect(screen.getByTestId('btn-reset-weights')).toBeInTheDocument()
  })

  // ── Provider modifiers ───────────────────────────────────────────────────

  it('renders the provider-modifiers container', () => {
    renderTab()
    expect(screen.getByTestId('provider-modifiers')).toBeInTheDocument()
  })

  it('renders a slider for each provider modifier', () => {
    renderTab()
    expect(screen.getByTestId('slider-modifier-OpenSubtitles')).toBeInTheDocument()
    expect(screen.getByTestId('slider-modifier-Subscene')).toBeInTheDocument()
  })

  it('renders multiple Save buttons (one per section)', () => {
    renderTab()
    expect(screen.getAllByTestId('btn-save-weights').length).toBeGreaterThanOrEqual(2)
  })

  // ── Release group filter ─────────────────────────────────────────────────

  it('renders the preferred groups input with loaded value', () => {
    renderTab()
    const input = screen.getByTestId('input-rg-prefer') as HTMLInputElement
    expect(input.value).toBe('SubsPlease')
  })

  it('renders the blocked groups input', () => {
    renderTab()
    expect(screen.getByTestId('input-rg-exclude')).toBeInTheDocument()
  })

  it('renders the prefer bonus input with loaded value', () => {
    renderTab()
    const input = screen.getByTestId('input-rg-bonus') as HTMLInputElement
    expect(input.value).toBe('20')
  })

  // ── MT Detection (advanced section) ─────────────────────────────────────

  it('MT detection advanced content is collapsed by default', () => {
    renderTab()
    // advanced content panel not shown until toggle clicked
    expect(screen.queryByTestId('mt-detection-advanced')).toBeNull()
  })

  it('MT detection shows controls after expanding the advanced toggle', () => {
    renderTab()
    // Find the MT Detection section by its known section title
    const allSections = document.querySelectorAll('[data-testid="settings-section"]')
    // Last section is MT Detection
    const mtSection = Array.from(allSections).find(
      (el) => el.querySelector('[data-testid="settings-section-title"]')?.textContent === 'Machine Translation Detection',
    ) as HTMLElement
    expect(mtSection).toBeTruthy()
    const toggle = mtSection.querySelector('[data-testid="settings-section-advanced-toggle"]') as HTMLElement
    expect(toggle).toBeTruthy()
    fireEvent.click(toggle)
    expect(screen.getByTestId('slider-mt-penalty')).toBeInTheDocument()
    expect(screen.getByTestId('slider-mt-threshold')).toBeInTheDocument()
    expect(screen.getByTestId('input-mt-penalty')).toBeInTheDocument()
    expect(screen.getByTestId('input-mt-threshold')).toBeInTheDocument()
  })
})
