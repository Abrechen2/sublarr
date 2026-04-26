import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { BrowserRouter } from 'react-router-dom'
import { ProfilesOverridesPage } from '../ProfilesOverridesPage'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k: string, fb?: string) => fb ?? k }),
}))

vi.mock('@/api/profilesOverrides', () => ({
  getScopesTree: vi.fn().mockResolvedValue({
    profiles: [], unassigned_series: [], unassigned_movies: [],
  }),
  getResolved: vi.fn().mockResolvedValue({
    scope: { type: 'global', id: null, name: 'Global default' },
    settings: {
      cleanup_foreign_tracks: { effective: null, source: 'global', chain: [] },
      forced_preference: { effective: null, source: 'global', chain: [] },
      hi_preference: { effective: null, source: 'global', chain: [] },
      forced_scoring: { effective: null, source: 'global', chain: [] },
      target_languages: { effective: null, source: 'global', chain: [] },
      cutoff_language: { effective: null, source: 'global', chain: [] },
      must_contain: { effective: null, source: 'global', chain: [] },
      must_not_contain: { effective: null, source: 'global', chain: [] },
      audio_exclude_languages: { effective: null, source: 'global', chain: [] },
      preferred_audio_track_index: { effective: null, source: 'global', chain: [] },
      priority_override: { effective: null, source: 'global', chain: [] },
      min_attempts_per_day: { effective: null, source: 'global', chain: [] },
    },
  }),
  patchOverride: vi.fn().mockResolvedValue({ ok: true }),
  resetOverrides: vi.fn().mockResolvedValue({ ok: true }),
  createSeriesOverride: vi.fn().mockResolvedValue({ created: true }),
  createMovieOverride: vi.fn().mockResolvedValue({ created: true }),
  deleteSeriesScope: vi.fn().mockResolvedValue({ deleted: true }),
  deleteMovieScope: vi.fn().mockResolvedValue({ deleted: true }),
}))

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <BrowserRouter>
      <QueryClientProvider client={qc}><ProfilesOverridesPage /></QueryClientProvider>
    </BrowserRouter>
  )
}

describe('ProfilesOverridesPage', () => {
  beforeEach(() => vi.clearAllMocks())

  it('renders the RulesLayout primitive', async () => {
    renderPage()
    await waitFor(() => expect(screen.getByTestId('rules-layout')).toBeInTheDocument())
  })

  it('shows the scope tree by default', async () => {
    renderPage()
    await waitFor(() => expect(screen.getByTestId('rules-scope-tree')).toBeInTheDocument())
  })

  it('shows global scope detail by default', async () => {
    renderPage()
    await waitFor(() => expect(screen.getAllByText(/global default/i).length).toBeGreaterThan(0))
  })

  it('shows empty-state hint banner above the detail panel when tree has no series or movies', async () => {
    // Default mock returns empty tree. Since 0.76.3-beta the empty-state is a
    // small banner ABOVE the ScopeDetail rather than a panel-replacement, so
    // both should be present (the hint AND the detail with global default).
    renderPage()
    await waitFor(() =>
      expect(screen.getByTestId('profiles-overrides-empty-hint')).toBeInTheDocument()
    )
  })
})
