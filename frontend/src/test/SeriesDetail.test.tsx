/**
 * SeriesDetail.test.tsx — Render tests for the SeriesDetailPage.
 *
 * Heavy sub-components are stubbed so tests remain fast and focused on the
 * page-level behaviour: title rendering, season grouping, and navigation.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { SeriesDetailPage } from '@/pages/SeriesDetail'

// ─── i18n ─────────────────────────────────────────────────────────────────────

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key.split('.').pop() ?? key,
  }),
}))

// ─── Mock data ────────────────────────────────────────────────────────────────

const mockSeries = {
  id: 1,
  title: 'Attack on Titan',
  sonarr_id: 1,
  sonarr_series_id: 1,
  tvdb_id: 12345,
  seasons: 4,
  status: 'ended',
  target_languages: ['de'],
  absolute_order: false,
  profile_name: null,
  poster_url: null,
  episodes: [
    {
      id: 101,
      sonarr_episode_id: 101,
      season: 1,
      episode: 1,
      title: 'To You, in 2000 Years',
      has_file: true,
      file_path: '/media/aot/s01e01.mkv',
      subtitles: {},
      subtitle_scores: {},
    },
  ],
}

// ─── API hooks ────────────────────────────────────────────────────────────────

vi.mock('@/hooks/useApi', () => ({
  useSeriesDetail: () => ({ data: mockSeries, isLoading: false, error: null }),
  useEpisodeSearch: () => ({ mutate: vi.fn(), isPending: false }),
  useEpisodeHistory: () => ({ data: null }),
  useProcessWantedItem: () => ({ mutate: vi.fn(), isPending: false }),
  useStartWantedBatch: () => ({ mutate: vi.fn(), isPending: false }),
  useUpdateSeriesSettings: () => ({ mutate: vi.fn(), isPending: false }),
  useRefreshAnidbMapping: () => ({ mutate: vi.fn(), isPending: false }),
  useStreamingEnabled: () => ({ data: false }),
  useSeriesFansubPrefs: () => ({
    data: { preferred_groups: [], excluded_groups: [] },
  }),
  useRescanSeries: () => ({ mutate: vi.fn(), isPending: false }),
}))

vi.mock('@/hooks/useWantedApi', () => ({
  useWantedItems: () => ({ data: null }),
  useUpdateWantedStatus: () => ({ mutate: vi.fn() }),
}))

vi.mock('@/hooks/useWebSocket', () => ({
  useWebSocket: () => undefined,
}))

// ─── Toast ────────────────────────────────────────────────────────────────────

vi.mock('@/components/shared/Toast', () => ({
  toast: vi.fn(),
}))

// ─── API client functions ─────────────────────────────────────────────────────

vi.mock('@/api/client', () => ({
  autoSyncFile: vi.fn(),
  batchExtractAllTracks: vi.fn(),
  listSeriesSubtitles: vi.fn().mockResolvedValue({ subtitles: {} }),
  deleteSubtitles: vi.fn(),
  getSeriesSubtitleExportUrl: vi.fn().mockReturnValue('/export/1'),
  exportSeriesNfo: vi.fn(),
  episodeHistory: vi.fn().mockResolvedValue({ entries: [] }),
}))

// ─── Sub-component stubs ──────────────────────────────────────────────────────

vi.mock('@/components/shared/Breadcrumb', () => ({
  Breadcrumb: ({ items }: { items: Array<{ label: string }> }) => (
    <nav>{items.map((i) => <span key={i.label}>{i.label}</span>)}</nav>
  ),
}))

vi.mock('@/components/series/SeriesHero', () => ({
  SeriesHero: ({ series }: { series: { title: string } }) => (
    <div data-testid="series-hero">{series.title}</div>
  ),
}))

vi.mock('@/components/series/SeasonTabs', () => ({
  SeasonTabs: ({ seasons }: { seasons: number[] }) => (
    <div data-testid="season-tabs">
      {seasons.map((s) => (
        <button key={s}>Season {s}</button>
      ))}
    </div>
  ),
}))

vi.mock('@/components/series/SeasonGroup', () => ({
  SeasonGroup: ({ season }: { season: number }) => (
    <div data-testid={`season-group-${season}`}>Season {season}</div>
  ),
}))

vi.mock('@/components/series/EpisodeGrid', () => ({
  EpisodeGridHeader: () => <div data-testid="episode-grid-header" />,
}))

vi.mock('@/components/series/SeriesSettingsPanel', () => ({
  SeriesSettingsPanel: () => <div data-testid="series-settings-panel" />,
}))

vi.mock('@/components/series/GlossaryPanel', () => ({
  GlossaryPanel: () => <div data-testid="glossary-panel" />,
}))

vi.mock('@/components/series/FansubOverrideModal', () => ({
  FansubOverrideModal: () => null,
}))

vi.mock('@/components/library/SeasonSummaryBar', () => ({
  SeasonSummaryBar: () => <div data-testid="season-summary-bar" />,
}))

vi.mock('@/components/shared/ProgressBar', () => ({
  ProgressBar: () => <div data-testid="progress-bar" />,
}))

vi.mock('@/components/shared/SubtitleCleanupModal', () => ({
  SubtitleCleanupModal: () => null,
}))

vi.mock('@/components/wanted/InteractiveSearchModal', () => ({
  InteractiveSearchModal: () => null,
}))

vi.mock('@/components/comparison/ComparisonSelector', () => ({
  ComparisonSelector: () => null,
}))

vi.mock('@/components/editor/SubtitleEditorModal', () => ({
  default: () => null,
}))

vi.mock('@/components/player/PlayerModal', () => ({
  PlayerModal: () => null,
}))

vi.mock('@/components/series/seriesUtils', () => ({
  deriveSubtitlePath: vi.fn().mockReturnValue('/subtitle.ass'),
}))

// ─── Helpers ──────────────────────────────────────────────────────────────────

function renderSeriesDetail(seriesId = '1') {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[`/library/series/${seriesId}`]}>
        <Routes>
          <Route path="/library/series/:id" element={<SeriesDetailPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

// ─── Tests ────────────────────────────────────────────────────────────────────

describe('SeriesDetailPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders series title via SeriesHero', () => {
    renderSeriesDetail()
    expect(screen.getByTestId('series-hero')).toBeInTheDocument()
    // Title appears in both Breadcrumb and SeriesHero — use getAllByText
    expect(screen.getAllByText('Attack on Titan').length).toBeGreaterThanOrEqual(1)
  })

  it('renders season tabs for the available seasons', () => {
    renderSeriesDetail()
    expect(screen.getByTestId('season-tabs')).toBeInTheDocument()
    // "Season 1" may appear in multiple places (tabs + season group stub)
    expect(screen.getAllByText(/season\s*1/i).length).toBeGreaterThanOrEqual(1)
  })

  it('renders season summary bar for the current season', () => {
    renderSeriesDetail()
    expect(screen.getByTestId('season-summary-bar')).toBeInTheDocument()
  })
})
