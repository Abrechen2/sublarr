import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { BrowserRouter } from 'react-router-dom'
import React from 'react'
import { ActivityFeed } from '../ActivityFeed'

const mockUseJobs = vi.fn()

vi.mock('@/hooks/useSystemApi', () => ({
  useJobs: (...args: unknown[]) => mockUseJobs(...args),
}))
vi.mock('@/components/dashboard/AttentionBanner', () => ({
  AttentionBanner: () => <div data-testid="attention-banner-mock" />,
}))
vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}))

const DEFAULT_JOBS = {
  data: {
    data: [
      { id: '1', file_path: '/media/anime/one-piece/S01E04.mkv', status: 'completed', created_at: '2026-04-05T10:00:00Z' },
      { id: '2', file_path: '/media/anime/aot/S02E01.mkv', status: 'failed', created_at: '2026-04-05T09:50:00Z' },
      { id: '3', file_path: '/media/anime/demon-slayer/S03E01.mkv', status: 'pending', created_at: '2026-04-05T09:40:00Z' },
    ],
    total: 47,
  },
}

beforeEach(() => {
  mockUseJobs.mockClear()
  mockUseJobs.mockReturnValue(DEFAULT_JOBS)
})

function wrap(ui: React.ReactElement) {
  return render(<BrowserRouter>{ui}</BrowserRouter>)
}

describe('ActivityFeed', () => {
  it('renders the feed container', () => {
    wrap(<ActivityFeed />)
    expect(screen.getByTestId('activity-feed')).toBeInTheDocument()
  })

  it('renders a row for each job', () => {
    wrap(<ActivityFeed />)
    expect(screen.getByTestId('feed-item-1')).toBeInTheDocument()
    expect(screen.getByTestId('feed-item-2')).toBeInTheDocument()
    expect(screen.getByTestId('feed-item-3')).toBeInTheDocument()
  })

  it('renders green dot for completed job', () => {
    wrap(<ActivityFeed />)
    expect(screen.getByTestId('feed-dot-1')).toHaveAttribute('data-status', 'completed')
  })

  it('renders red dot for failed job', () => {
    wrap(<ActivityFeed />)
    expect(screen.getByTestId('feed-dot-2')).toHaveAttribute('data-status', 'failed')
  })

  it('renders "View all" link to /activity', () => {
    wrap(<ActivityFeed />)
    const link = screen.getByTestId('feed-view-all')
    expect(link).toHaveAttribute('href', '/activity')
  })

  it('renders AttentionBanner inside the feed', () => {
    wrap(<ActivityFeed />)
    expect(screen.getByTestId('attention-banner-mock')).toBeInTheDocument()
  })

  it('shows empty state when no jobs', () => {
    mockUseJobs.mockReturnValue({ data: { data: [], total: 0 } })
    wrap(<ActivityFeed />)
    expect(screen.getByTestId('feed-empty')).toBeInTheDocument()
  })

  it('shows "more events" footer when total exceeds limit', () => {
    // DEFAULT_JOBS has total: 47 which exceeds FEED_LIMIT=20
    wrap(<ActivityFeed />)
    expect(screen.getByTestId('feed-more-events')).toBeInTheDocument()
  })
})
