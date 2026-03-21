/**
 * MovieDetail.test.tsx — Tests for MovieDetailPage.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { MovieDetailPage } from '../MovieDetail'

// ─── Mocks ───────────────────────────────────────────────────────────────────

const mockUseMovieDetail = vi.fn()

vi.mock('@/hooks/useApi', () => ({
  useMovieDetail: (id: number | null) => mockUseMovieDetail(id),
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
