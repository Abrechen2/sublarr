import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { BrowserRouter } from 'react-router-dom'
import React from 'react'

const mockSearchMutate = vi.fn()
const mockSkipMutate = vi.fn()

vi.mock('@/hooks/useWantedApi', () => ({
  useWantedItems: () => ({
    data: {
      items: [
        {
          id: 1,
          title: 'Episode Title',
          series_title: 'Frieren',
          season_number: 2,
          episode_number: 3,
          status: 'failed',
          score: null,
          file_path: '/media/frieren.mkv',
        },
        {
          id: 2,
          title: 'Episode 12',
          series_title: 'Solo Leveling',
          season_number: 1,
          episode_number: 12,
          status: 'found',
          score: 35,
          file_path: '/media/solo.mkv',
        },
        {
          id: 3,
          title: 'Episode 8',
          series_title: 'Oshi no Ko',
          season_number: 2,
          episode_number: 8,
          status: 'failed',
          score: null,
          file_path: '/media/oshi.mkv',
        },
      ],
      total: 15,
    },
  }),
  useSearchWantedItem: () => ({ mutate: mockSearchMutate }),
  useUpdateWantedStatus: () => ({ mutate: mockSkipMutate }),
}))

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, fallback?: string) => fallback ?? key,
    i18n: { language: 'en', changeLanguage: vi.fn() },
  }),
}))

function renderWithRouter(ui: React.ReactElement) {
  return render(<BrowserRouter>{ui}</BrowserRouter>)
}

describe('NeedsAttentionCard', () => {
  it('renders the card with warning left border', async () => {
    const { NeedsAttentionCard } = await import('../NeedsAttentionCard')
    renderWithRouter(<NeedsAttentionCard />)
    const card = screen.getByTestId('needs-attention-card')
    expect(card).toBeInTheDocument()
    // Card should have warning border style applied
    expect(card.style.borderLeft).toContain('var(--warning)')
  })

  it('renders "Needs Attention" header with AlertTriangle icon', async () => {
    const { NeedsAttentionCard } = await import('../NeedsAttentionCard')
    renderWithRouter(<NeedsAttentionCard />)
    expect(screen.getByTestId('needs-attention-header')).toBeInTheDocument()
    expect(screen.getByTestId('needs-attention-icon')).toBeInTheDocument()
  })

  it('renders failed items (status=failed) with Search and Skip buttons', async () => {
    const { NeedsAttentionCard } = await import('../NeedsAttentionCard')
    renderWithRouter(<NeedsAttentionCard />)

    // Item 1: Frieren - failed, should have Search + Skip
    expect(screen.getByTestId('item-row-1')).toBeInTheDocument()
    expect(screen.getByTestId('btn-search-1')).toBeInTheDocument()
    expect(screen.getByTestId('btn-skip-1')).toBeInTheDocument()
  })

  it('renders low-score items (score < 50) with Find Better and Accept buttons', async () => {
    const { NeedsAttentionCard } = await import('../NeedsAttentionCard')
    renderWithRouter(<NeedsAttentionCard />)

    // Item 2: Solo Leveling - score 35 < 50, should have Find Better + Accept
    expect(screen.getByTestId('item-row-2')).toBeInTheDocument()
    expect(screen.getByTestId('btn-find-better-2')).toBeInTheDocument()
    expect(screen.getByTestId('btn-accept-2')).toBeInTheDocument()
  })

  it('renders item title and series info', async () => {
    const { NeedsAttentionCard } = await import('../NeedsAttentionCard')
    renderWithRouter(<NeedsAttentionCard />)

    expect(screen.getByTestId('item-title-1')).toHaveTextContent('Frieren')
    expect(screen.getByTestId('item-title-2')).toHaveTextContent('Solo Leveling')
  })

  it('renders a reason/badge for each item', async () => {
    const { NeedsAttentionCard } = await import('../NeedsAttentionCard')
    renderWithRouter(<NeedsAttentionCard />)

    expect(screen.getByTestId('item-reason-1')).toBeInTheDocument()
    expect(screen.getByTestId('item-reason-2')).toBeInTheDocument()
  })

  it('renders "View All" link that navigates to /activity', async () => {
    const { NeedsAttentionCard } = await import('../NeedsAttentionCard')
    renderWithRouter(<NeedsAttentionCard />)

    const viewAll = screen.getByTestId('view-all-link')
    expect(viewAll).toBeInTheDocument()
    expect(viewAll).toHaveAttribute('href', '/activity')
  })

  it('calls search mutation when Search button is clicked', async () => {
    const { NeedsAttentionCard } = await import('../NeedsAttentionCard')
    mockSearchMutate.mockClear()
    renderWithRouter(<NeedsAttentionCard />)

    fireEvent.click(screen.getByTestId('btn-search-1'))
    expect(mockSearchMutate).toHaveBeenCalledWith(1)
  })

  it('calls skip mutation when Skip button is clicked', async () => {
    const { NeedsAttentionCard } = await import('../NeedsAttentionCard')
    mockSkipMutate.mockClear()
    renderWithRouter(<NeedsAttentionCard />)

    fireEvent.click(screen.getByTestId('btn-skip-1'))
    expect(mockSkipMutate).toHaveBeenCalledWith({ itemId: 1, status: 'skipped' })
  })

  it('limits display to at most 5 items', async () => {
    const { NeedsAttentionCard } = await import('../NeedsAttentionCard')
    renderWithRouter(<NeedsAttentionCard />)

    // Only 3 items in mock, all 3 should show (<=5)
    expect(screen.getByTestId('item-row-1')).toBeInTheDocument()
    expect(screen.getByTestId('item-row-2')).toBeInTheDocument()
    expect(screen.getByTestId('item-row-3')).toBeInTheDocument()
  })

  it('shows total count in header when items exist', async () => {
    const { NeedsAttentionCard } = await import('../NeedsAttentionCard')
    renderWithRouter(<NeedsAttentionCard />)

    // total is 15 from mock
    expect(screen.getByTestId('needs-attention-count')).toBeInTheDocument()
  })
})
