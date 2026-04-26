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

const mockBulkMutate = vi.fn()

vi.mock('@/hooks/useApi', () => ({
  useLibrary: () => ({
    data: { series: mockSeries, movies: mockMovies },
    isLoading: false,
  }),
  useLanguageProfiles: () => ({
    data: [
      { id: 1, name: 'Default', is_default: true },
      { id: 2, name: 'English Only', is_default: false },
    ],
  }),
  useAssignProfile: () => ({ mutate: vi.fn() }),
  useBulkAssignProfile: () => ({ mutate: mockBulkMutate, isPending: false }),
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
  VirtualLibraryTable: ({
    items,
    selectedSeries,
    onToggleSeries,
  }: {
    items: Array<{ id: number; title: string }>
    selectedSeries: Set<number>
    onToggleSeries: (id: number) => void
  }) => (
    <div data-testid="virtual-table">
      {items.map((i) => (
        <div key={i.title}>
          {i.title}
          <input
            type="checkbox"
            data-testid={`row-checkbox-${i.id}`}
            checked={selectedSeries.has(i.id)}
            onChange={() => onToggleSeries(i.id)}
          />
        </div>
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

  it('bulk toolbar is hidden when no series selected', () => {
    renderLibrary()
    // Switch to table view so checkboxes are accessible
    fireEvent.click(screen.getByTestId('library-view-table'))
    expect(screen.queryByTestId('library-bulk-toolbar')).not.toBeInTheDocument()
  })

  it('bulk toolbar appears after selecting a row in table view', () => {
    renderLibrary()
    fireEvent.click(screen.getByTestId('library-view-table'))
    const checkbox = screen.getByTestId('row-checkbox-1')
    fireEvent.click(checkbox)
    expect(screen.getByTestId('library-bulk-toolbar')).toBeInTheDocument()
  })

  it('bulk toolbar disappears after clicking clear', () => {
    renderLibrary()
    fireEvent.click(screen.getByTestId('library-view-table'))
    fireEvent.click(screen.getByTestId('row-checkbox-1'))
    expect(screen.getByTestId('library-bulk-toolbar')).toBeInTheDocument()
    fireEvent.click(screen.getByTestId('library-bulk-clear'))
    expect(screen.queryByTestId('library-bulk-toolbar')).not.toBeInTheDocument()
  })

  it('bulk toolbar disappears on tab switch', () => {
    renderLibrary()
    fireEvent.click(screen.getByTestId('library-view-table'))
    fireEvent.click(screen.getByTestId('row-checkbox-1'))
    expect(screen.getByTestId('library-bulk-toolbar')).toBeInTheDocument()
    fireEvent.click(screen.getByTestId('tab-movies'))
    expect(screen.queryByTestId('library-bulk-toolbar')).not.toBeInTheDocument()
  })

  it('bulk-assign mutation fires with correct payload on profile select', () => {
    renderLibrary()
    fireEvent.click(screen.getByTestId('library-view-table'))
    fireEvent.click(screen.getByTestId('row-checkbox-1'))
    const select = screen.getByTestId('library-bulk-profile-select')
    fireEvent.change(select, { target: { value: '2' } })
    expect(mockBulkMutate).toHaveBeenCalledWith(
      { type: 'series', arrIds: [1], profileId: 2 },
      expect.any(Object),
    )
  })
})
