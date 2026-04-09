/**
 * MovieDetail.test.tsx — Tests for MovieDetailPage.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { MovieDetailPage } from '../MovieDetail'

// ─── Mocks ───────────────────────────────────────────────────────────────────

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => {
      const translations: Record<string, string> = {
        'title': 'Library',
        'movie_detail.back_to_library': 'Back to Library',
        'movie_detail.load_error': 'Failed to load movie',
        'movie_detail.file_info': 'File Info',
        'movie_detail.path': 'Path',
        'movie_detail.subtitles': 'Subtitles',
        'movie_detail.no_missing': 'No missing subtitles',
        'movie_detail.search': 'Search',
        'movie_detail.skip': 'Skip',
        'movie_detail.re_enable': 'Re-enable',
        'movie_detail.searches': 'searches',
        'movie_detail.missing': 'Missing',
      }
      return translations[key] ?? key.split('.').pop() ?? key
    },
    i18n: { language: 'de', changeLanguage: vi.fn() },
  }),
}))

const mockUseMovieDetail = vi.fn()
const mockUseWantedItems = vi.fn()
const mockUseSearchWantedItem = vi.fn()
const mockUseUpdateWantedStatus = vi.fn()

vi.mock('@/hooks/useApi', () => ({
  useMovieDetail: (id: number | null) => mockUseMovieDetail(id),
  useWantedItems: (...args: unknown[]) => mockUseWantedItems(...args),
  useSearchWantedItem: () => mockUseSearchWantedItem(),
  useUpdateWantedStatus: () => mockUseUpdateWantedStatus(),
}))

vi.mock('@/hooks/useLibraryApi', () => ({
  useMovieSubtitles: () => ({ data: { subtitles: [], video_path: '' }, isLoading: false, refetch: vi.fn() }),
}))

vi.mock('@/components/shared/Breadcrumb', () => ({
  Breadcrumb: ({ items }: { items: { label: string; to?: string }[] }) => (
    <nav>{items.map((i) => <span key={i.label}>{i.label}</span>)}</nav>
  ),
}))

// ─── Helpers ─────────────────────────────────────────────────────────────────

function renderPage(id = '42') {
  return render(
    <MemoryRouter initialEntries={[`/movies/${id}`]}>
      <Routes>
        <Route path="/movies/:id" element={<MovieDetailPage />} />
      </Routes>
    </MemoryRouter>,
  )
}

// ─── Tests ───────────────────────────────────────────────────────────────────

describe('MovieDetailPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    // Default mock for wanted items (empty list)
    mockUseWantedItems.mockReturnValue({ data: { data: [], total: 0, page: 1, per_page: 50 }, isLoading: false })
    mockUseSearchWantedItem.mockReturnValue({ mutate: vi.fn(), isPending: false })
    mockUseUpdateWantedStatus.mockReturnValue({ mutate: vi.fn(), isPending: false })
  })

  it('shows loading spinner while data is loading', () => {
    mockUseMovieDetail.mockReturnValue({ data: null, isLoading: true, error: null })
    renderPage()
    expect(screen.getByTestId('movie-loading')).toBeInTheDocument()
  })

  it('shows error state when load fails', () => {
    mockUseMovieDetail.mockReturnValue({ data: null, isLoading: false, error: new Error('fail') })
    renderPage()
    expect(screen.getByTestId('movie-error')).toBeInTheDocument()
  })

  it('renders movie title when loaded', () => {
    mockUseMovieDetail.mockReturnValue({
      data: {
        id: 42,
        title: 'My Test Movie',
        year: 2023,
        file_path: '/media/movie.mkv',
        wanted_count: 1,
        poster_url: '',
        tmdb_id: null,
        imdb_id: '',
        metadata_source: '',
        created_at: '2024-01-01T00:00:00Z',
        updated_at: '2024-01-01T00:00:00Z',
      },
      isLoading: false,
      error: null,
    })
    renderPage()
    expect(screen.getAllByText('My Test Movie').length).toBeGreaterThan(0)
  })

  it('renders breadcrumb with Library link', () => {
    mockUseMovieDetail.mockReturnValue({
      data: { id: 42, title: 'Test', year: 2023, file_path: '/media/m.mkv', poster_url: '', tmdb_id: null, imdb_id: '', metadata_source: '', created_at: '', updated_at: '' },
      isLoading: false,
      error: null,
    })
    renderPage()
    expect(screen.getByText('Library')).toBeInTheDocument()
  })
})
