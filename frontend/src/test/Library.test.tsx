/**
 * Library.test.tsx — Render and tab interaction tests for the LibraryPage.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { LibraryPage } from '@/pages/Library'

// ─── i18n ─────────────────────────────────────────────────────────────────────

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) => {
      const base = key.split('.').pop() ?? key
      if (opts && typeof opts.count === 'number') return `${base} ${opts.count}`
      return base
    },
  }),
}))

// ─── API hooks ────────────────────────────────────────────────────────────────

const mockSeries = [
  {
    id: 1,
    title: 'Attack on Titan',
    seasons: 4,
    episodes: 87,
    episodes_with_files: 87,
    missing_count: 0,
    status: 'ended',
    profile_name: null,
    poster_url: null,
  },
]

const mockMovies = [
  {
    id: 10,
    title: 'Spirited Away',
    missing_count: 0,
    profile_name: null,
    poster_url: null,
  },
]

vi.mock('@/hooks/useApi', () => ({
  useLibrary: () => ({
    data: { series: mockSeries, movies: mockMovies },
    isLoading: false,
  }),
  useLanguageProfiles: () => ({ data: [] }),
  useAssignProfile: () => ({ mutate: vi.fn() }),
}))

// ─── Routing ──────────────────────────────────────────────────────────────────

vi.mock('react-router-dom', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router-dom')>()
  return {
    ...actual,
    useNavigate: () => vi.fn(),
  }
})

// ─── WebSocket ────────────────────────────────────────────────────────────────

vi.mock('@/hooks/useWebSocket', () => ({
  useWebSocket: () => undefined,
}))

// ─── Toast ────────────────────────────────────────────────────────────────────

vi.mock('@/components/shared/Toast', () => ({
  toast: vi.fn(),
}))

// ─── Sub-components that do heavy lifting (keep tests focused) ────────────────

vi.mock('@/components/library/LibraryCard', () => ({
  LibraryCard: ({ item }: { item: { title: string } }) => (
    <div data-testid="library-card">{item.title}</div>
  ),
}))

vi.mock('@/components/library/VirtualLibraryTable', () => ({
  VirtualLibraryTable: ({ items }: { items: Array<{ title: string }> }) => (
    <div data-testid="virtual-table">
      {items.map((i) => (
        <div key={i.title}>{i.title}</div>
      ))}
    </div>
  ),
}))

vi.mock('@/components/shared/FilterChips', () => ({
  FilterChips: () => <div data-testid="filter-chips" />,
}))

vi.mock('@/components/filters/FilterPresetMenu', () => ({
  FilterPresetMenu: () => <div data-testid="filter-preset-menu" />,
}))

vi.mock('@/api/client', () => ({
  autoSyncBulk: vi.fn(),
  startSeriesBatchSearch: vi.fn(),
}))

// ─── Helpers ──────────────────────────────────────────────────────────────────

function renderLibrary() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <LibraryPage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

// ─── Tests ────────────────────────────────────────────────────────────────────

describe('LibraryPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders series tab by default and shows series item', () => {
    renderLibrary()
    // Series tab is active by default; LibraryCard renders the series title
    expect(screen.getByText('Attack on Titan')).toBeInTheDocument()
  })

  it('renders movies tab button and clicking it switches context', () => {
    renderLibrary()
    const moviesTab = screen.getByTestId('tab-movies')
    expect(moviesTab).toBeInTheDocument()
    fireEvent.click(moviesTab)
    // After clicking movies tab the movies item should appear
    expect(screen.getByText('Spirited Away')).toBeInTheDocument()
  })

  it('renders view toggle buttons', () => {
    renderLibrary()
    expect(screen.getByTestId('library-view-table')).toBeInTheDocument()
    expect(screen.getByTestId('library-view-grid')).toBeInTheDocument()
  })
})
