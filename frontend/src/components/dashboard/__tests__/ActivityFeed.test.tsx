import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { BrowserRouter } from 'react-router-dom'
import React from 'react'
import { ActivityFeed } from '../ActivityFeed'

const mockUseHistory = vi.fn()

vi.mock('@/hooks/useProvidersApi', () => ({
  useHistory: (...args: unknown[]) => mockUseHistory(...args),
}))
vi.mock('@/components/dashboard/AttentionBanner', () => ({
  AttentionBanner: () => <div data-testid="attention-banner-mock" />,
}))
vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}))

const DEFAULT_HISTORY = {
  data: {
    data: [
      { id: 1, file_path: '/media/anime/One Piece - S01E04.mkv', provider_name: 'jimaku', language: 'de', format: 'ass', score: 91, downloaded_at: '2026-04-05T10:00:00Z' },
      { id: 2, file_path: '/media/anime/Attack on Titan - S02E01.mkv', provider_name: 'animetosho', language: 'de', format: 'ass', score: 85, downloaded_at: '2026-04-05T09:50:00Z' },
      { id: 3, file_path: '/media/anime/Demon Slayer - S03E01.mkv', provider_name: 'opensubtitles', language: 'de', format: 'srt', score: 72, downloaded_at: '2026-04-05T09:40:00Z' },
    ],
    total: 47,
  },
}

beforeEach(() => {
  mockUseHistory.mockClear()
  mockUseHistory.mockReturnValue(DEFAULT_HISTORY)
})

function wrap(ui: React.ReactElement) {
  return render(<BrowserRouter>{ui}</BrowserRouter>)
}

describe('ActivityFeed', () => {
  it('renders the feed container', () => {
    wrap(<ActivityFeed />)
    expect(screen.getByTestId('activity-feed')).toBeInTheDocument()
  })

  it('renders a row for each history entry', () => {
    wrap(<ActivityFeed />)
    expect(screen.getByTestId('feed-item-1')).toBeInTheDocument()
    expect(screen.getByTestId('feed-item-2')).toBeInTheDocument()
    expect(screen.getByTestId('feed-item-3')).toBeInTheDocument()
  })

  it('renders green dot for each entry', () => {
    wrap(<ActivityFeed />)
    expect(screen.getByTestId('feed-dot-1')).toHaveAttribute('data-status', 'completed')
  })

  it('renders "View all" link to /activity history tab', () => {
    wrap(<ActivityFeed />)
    const link = screen.getByTestId('feed-view-all')
    expect(link).toHaveAttribute('href', '/activity?tab=history')
  })

  it('renders AttentionBanner inside the feed', () => {
    wrap(<ActivityFeed />)
    expect(screen.getByTestId('attention-banner-mock')).toBeInTheDocument()
  })

  it('shows empty state when no history entries', () => {
    mockUseHistory.mockReturnValue({ data: { data: [], total: 0 } })
    wrap(<ActivityFeed />)
    expect(screen.getByTestId('feed-empty')).toBeInTheDocument()
  })

  it('shows "more events" footer when total exceeds limit', () => {
    // DEFAULT_HISTORY has total: 47 which exceeds FEED_LIMIT=20
    wrap(<ActivityFeed />)
    expect(screen.getByTestId('feed-more-events')).toBeInTheDocument()
  })
})
