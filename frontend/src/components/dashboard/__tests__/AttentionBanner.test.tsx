import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { BrowserRouter } from 'react-router-dom'
import React from 'react'
import { AttentionBanner } from '../AttentionBanner'

const mockSearch = vi.fn()
const mockStatus = vi.fn()
const mockUseWantedItems = vi.fn()

vi.mock('@/hooks/useWantedApi', () => ({
  useWantedItems: (...args: unknown[]) => mockUseWantedItems(...args),
  useSearchWantedItem: () => ({ mutate: mockSearch }),
  useUpdateWantedStatus: () => ({ mutate: mockStatus }),
}))
vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}))

function wrap(ui: React.ReactElement) {
  return render(<BrowserRouter>{ui}</BrowserRouter>)
}

// Shape mirrors PaginatedWanted: items live under `data`, scores in `current_score`,
// episode label pre-formatted in `season_episode`.
const ALL_ITEMS = {
  data: {
    data: [
      { id: 1, title: 'One Piece', season_episode: 'S01E04', status: 'failed', current_score: 0 },
      { id: 2, title: 'Jujutsu Kaisen', season_episode: 'S02E06', status: 'found', current_score: 38 },
    ],
    total: 2,
  },
  isLoading: false,
}

beforeEach(() => {
  mockSearch.mockClear()
  mockStatus.mockClear()
  mockUseWantedItems.mockClear()
  mockUseWantedItems.mockReturnValue(ALL_ITEMS)
})

describe('AttentionBanner', () => {
  it('renders the banner when items exist', () => {
    wrap(<AttentionBanner />)
    expect(screen.getByTestId('attention-banner')).toBeInTheDocument()
  })

  it('shows failed item with Search and Skip buttons', () => {
    wrap(<AttentionBanner />)
    expect(screen.getByTestId('attention-item-1')).toBeInTheDocument()
    expect(screen.getByTestId('attention-search-1')).toBeInTheDocument()
    expect(screen.getByTestId('attention-skip-1')).toBeInTheDocument()
  })

  it('shows low-score item with Find Better and Accept buttons', () => {
    wrap(<AttentionBanner />)
    expect(screen.getByTestId('attention-item-2')).toBeInTheDocument()
    expect(screen.getByTestId('attention-find-better-2')).toBeInTheDocument()
    expect(screen.getByTestId('attention-accept-2')).toBeInTheDocument()
  })

  it('shows series title', () => {
    wrap(<AttentionBanner />)
    expect(screen.getByTestId('attention-title-1')).toHaveTextContent('One Piece')
  })

  it('"View all" link points to /wanted', () => {
    wrap(<AttentionBanner />)
    expect(screen.getByTestId('attention-view-all')).toHaveAttribute('href', '/wanted')
  })

  it('calls search mutation when Search is clicked', () => {
    wrap(<AttentionBanner />)
    fireEvent.click(screen.getByTestId('attention-search-1'))
    expect(mockSearch).toHaveBeenCalledWith(1)
  })

  it('calls status mutation with skipped when Skip is clicked', () => {
    wrap(<AttentionBanner />)
    fireEvent.click(screen.getByTestId('attention-skip-1'))
    expect(mockStatus).toHaveBeenCalledWith({ itemId: 1, status: 'skipped' })
  })

  it('calls status mutation with accepted when Accept is clicked', () => {
    wrap(<AttentionBanner />)
    fireEvent.click(screen.getByTestId('attention-accept-2'))
    expect(mockStatus).toHaveBeenCalledWith({ itemId: 2, status: 'accepted' })
  })

  it('returns null when no items need attention', () => {
    mockUseWantedItems.mockReturnValue({ data: { data: [], total: 0 }, isLoading: false })
    const { container } = wrap(<AttentionBanner />)
    expect(container.firstChild).toBeNull()
  })

  it('returns null while loading', () => {
    mockUseWantedItems.mockReturnValue({ data: undefined, isLoading: true })
    const { container } = wrap(<AttentionBanner />)
    expect(container.firstChild).toBeNull()
  })
})
