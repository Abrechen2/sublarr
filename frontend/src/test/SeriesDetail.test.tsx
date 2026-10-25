/**
 * SeriesDetail.test.tsx — Render tests for the SeriesDetailPage.
 *
 * Heavy sub-components are stubbed so tests remain fast and focused on the
 * page-level behaviour: title rendering, season grouping, and navigation.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
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

const mockSeries: Record<string, unknown> = {
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

// Standalone series (docs/specs/standalone-ids.md): series and episodes have
// stable negative ids; the page still hands the file_path to the episode
// endpoints so a stale id resolves too.
const standaloneSeries = {
  ...mockSeries,
  id: -7,
  standalone_id: 7,
  title: 'My Show',
  source: 'standalone',
  episodes: [
    {
      id: -1,
      season: 1,
      episode: 2,
      title: 'My Show -- S01E02',
      has_file: true,
      file_path: '/media/my-show/s01e02.mkv',
      subtitles: { de: 'ass' },
      subtitle_scores: {},
      source: 'standalone',
      standalone_id: 1,
      wanted_id: null,
    },
  ],
}

let currentSeries: Record<string, unknown> = mockSeries
const episodeSearchMutate = vi.fn()
const interactiveModalProps = vi.fn()
const seasonGroupProps = vi.fn()
let currentWanted: unknown = null
const fansubPrefsIds = vi.fn()

// ─── API hooks ────────────────────────────────────────────────────────────────

vi.mock('@/hooks/useApi', () => ({
  useSeriesDetail: () => ({ data: currentSeries, isLoading: false, error: null }),
  useEpisodeSearch: () => ({ mutate: episodeSearchMutate, isPending: false }),
  useEpisodeHistory: () => ({ data: null }),
  useProcessWantedItem: () => ({ mutate: vi.fn(), isPending: false }),
  useStartWantedBatch: () => ({ mutate: vi.fn(), isPending: false }),
  useUpdateSeriesSettings: () => ({ mutate: vi.fn(), isPending: false }),
  useRefreshAnidbMapping: () => ({ mutate: vi.fn(), isPending: false }),
  useStreamingEnabled: () => ({ data: false }),
  useSeriesFansubPrefs: (id: number | null) => {
    fansubPrefsIds(id)
    return { data: { preferred_groups: [], excluded_groups: [] } }
  },
  useRescanSeries: () => ({ mutate: vi.fn(), isPending: false }),
}))

vi.mock('@/hooks/useWantedApi', () => ({
  useWantedItems: () => ({ data: currentWanted }),
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
  SeasonGroup: (props: {
    season: number
    episodes: unknown[]
    onSearch: (ep: unknown) => void
    onInteractiveSearch: (ep: unknown) => void
    onHistory: (ep: unknown) => void
  }) => {
    seasonGroupProps(props)
    const { season, episodes, onSearch, onInteractiveSearch, onHistory } = props
    return (
    <div data-testid={`season-group-${season}`}>
      Season {season}
      <button onClick={() => onSearch(episodes[0])}>stub-search</button>
      <button onClick={() => onInteractiveSearch(episodes[0])}>stub-interactive</button>
      <button onClick={() => onHistory(episodes[0])}>stub-history</button>
    </div>
    )
  },
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
  InteractiveSearchModal: (props: Record<string, unknown>) => {
    interactiveModalProps(props)
    return null
  },
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
    currentSeries = mockSeries
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

describe('SeriesDetailPage episode actions (#226)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    currentWanted = null
  })

  function lastWantedMap() {
    const calls = seasonGroupProps.mock.calls
    return (calls[calls.length - 1][0] as { episodeWantedMap: Map<number, number> })
      .episodeWantedMap
  }

  it('maps a standalone episode to the wanted row of its file for skip/accept', () => {
    currentSeries = standaloneSeries
    currentWanted = {
      data: [
        {
          id: 55,
          sonarr_episode_id: null,
          standalone_series_id: 7,
          file_path: '/media/my-show/s01e02.mkv',
        },
      ],
    }
    renderSeriesDetail('-7')
    expect(lastWantedMap().get(-1)).toBe(55)
    expect(lastWantedMap().has(55)).toBe(false)
  })

  it('prefers the wanted id the backend attaches to a standalone episode', () => {
    currentSeries = {
      ...standaloneSeries,
      episodes: [{ ...standaloneSeries.episodes[0], wanted_id: 77 }],
    }
    currentWanted = { data: [] }
    renderSeriesDetail('-7')
    expect(lastWantedMap().get(-1)).toBe(77)
  })

  it('asks for the fansub preferences of a negative standalone id', () => {
    currentSeries = standaloneSeries
    renderSeriesDetail('-7')
    expect(fansubPrefsIds).toHaveBeenCalledWith(-7)
  })

  it('maps Sonarr episodes by sonarr_episode_id', () => {
    currentSeries = mockSeries
    currentWanted = { data: [{ id: 9, sonarr_episode_id: 101 }] }
    renderSeriesDetail('1')
    expect(lastWantedMap().get(101)).toBe(9)
    expect(lastWantedMap().has(9)).toBe(false)
  })

  function lastModalProps() {
    const calls = interactiveModalProps.mock.calls
    return calls[calls.length - 1][0] as { episodeId?: number; episodeFilePath?: string }
  }

  it('sends the file path for a standalone episode search', () => {
    currentSeries = standaloneSeries
    renderSeriesDetail('-7')
    fireEvent.click(screen.getByText('stub-search'))
    expect(episodeSearchMutate).toHaveBeenCalledWith(
      { episodeId: -1, filePath: '/media/my-show/s01e02.mkv' },
      expect.any(Object),
    )
  })

  it('passes the file path to the interactive search modal for standalone', () => {
    currentSeries = standaloneSeries
    renderSeriesDetail('-7')
    fireEvent.click(screen.getByText('stub-interactive'))
    expect(lastModalProps()).toMatchObject({
      episodeId: -1,
      episodeFilePath: '/media/my-show/s01e02.mkv',
    })
  })

  it('requests standalone history with the file path', async () => {
    currentSeries = standaloneSeries
    const { episodeHistory } = await import('@/api/client')
    renderSeriesDetail('-7')
    fireEvent.click(screen.getByText('stub-history'))
    await waitFor(() =>
      expect(episodeHistory).toHaveBeenCalledWith(-1, '/media/my-show/s01e02.mkv'),
    )
  })

  it('keeps Sonarr episodes keyed by id only', () => {
    currentSeries = mockSeries
    renderSeriesDetail('1')
    fireEvent.click(screen.getByText('stub-search'))
    expect(episodeSearchMutate).toHaveBeenCalledWith(
      { episodeId: 101, filePath: undefined },
      expect.any(Object),
    )
    fireEvent.click(screen.getByText('stub-interactive'))
    expect(lastModalProps()).toMatchObject({ episodeId: 101, episodeFilePath: undefined })
  })
})
