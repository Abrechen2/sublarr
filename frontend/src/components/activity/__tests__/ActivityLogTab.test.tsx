import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { BrowserRouter } from 'react-router-dom'
import React from 'react'
import { ActivityLogTab } from '../ActivityLogTab'

const mockUseActivity = vi.fn()

vi.mock('@/hooks/useSystemApi', () => ({
  useActivity: (...args: unknown[]) => mockUseActivity(...args),
}))
vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string, fallback?: string) => fallback ?? key }),
}))

const SAMPLE_DATA = {
  data: {
    data: [
      { id: 1, event_type: 'download', file_path: '/media/One Piece - S01E01.mkv',
        status: 'success', details: { provider: 'jimaku', score: 90 },
        created_at: '2026-04-05T10:00:00Z' },
      { id: 2, event_type: 'extract', file_path: '/media/Attack on Titan - S02E01.mkv',
        status: 'success', details: null, created_at: '2026-04-05T09:50:00Z' },
      { id: 3, event_type: 'delete', file_path: '/media/Demon Slayer.de.ass',
        status: 'success', details: null, created_at: '2026-04-05T09:40:00Z' },
      { id: 4, event_type: 'scan', file_path: null,
        status: 'success', details: { found: 3, total: 10 },
        created_at: '2026-04-05T09:30:00Z' },
    ],
    total: 4,
    page: 1,
    per_page: 50,
    total_pages: 1,
  },
  isLoading: false,
}

beforeEach(() => {
  mockUseActivity.mockClear()
  mockUseActivity.mockReturnValue(SAMPLE_DATA)
})

function wrap(ui: React.ReactElement) {
  return render(<BrowserRouter>{ui}</BrowserRouter>)
}

describe('ActivityLogTab', () => {
  it('renders the tab container', () => {
    wrap(<ActivityLogTab />)
    expect(screen.getByTestId('activity-log-tab')).toBeInTheDocument()
  })

  it('renders a row for each activity entry', () => {
    wrap(<ActivityLogTab />)
    expect(screen.getByTestId('activity-row-1')).toBeInTheDocument()
    expect(screen.getByTestId('activity-row-2')).toBeInTheDocument()
    expect(screen.getByTestId('activity-row-3')).toBeInTheDocument()
    expect(screen.getByTestId('activity-row-4')).toBeInTheDocument()
  })

  it('shows event type badge for each row', () => {
    wrap(<ActivityLogTab />)
    expect(screen.getByTestId('activity-type-1')).toHaveAttribute('data-type', 'download')
    expect(screen.getByTestId('activity-type-2')).toHaveAttribute('data-type', 'extract')
    expect(screen.getByTestId('activity-type-3')).toHaveAttribute('data-type', 'delete')
    expect(screen.getByTestId('activity-type-4')).toHaveAttribute('data-type', 'scan')
  })

  it('shows empty state when no entries', () => {
    mockUseActivity.mockReturnValue({
      data: { data: [], total: 0, page: 1, per_page: 50, total_pages: 1 },
      isLoading: false,
    })
    wrap(<ActivityLogTab />)
    expect(screen.getByTestId('activity-empty')).toBeInTheDocument()
  })

  it('shows loading state while fetching', () => {
    mockUseActivity.mockReturnValue({ data: undefined, isLoading: true })
    wrap(<ActivityLogTab />)
    expect(screen.getByTestId('activity-loading')).toBeInTheDocument()
  })

  it('renders media title from file_path for non-scan events', () => {
    wrap(<ActivityLogTab />)
    expect(screen.getByTestId('activity-row-1')).toHaveTextContent('One Piece')
  })

  it('renders scan label for scan events without file_path', () => {
    wrap(<ActivityLogTab />)
    expect(screen.getByTestId('activity-row-4')).toHaveTextContent('Wanted scan')
  })

  it('renders a translate filter pill alongside download/extract/delete/scan', () => {
    wrap(<ActivityLogTab />)
    // Mocked t(key, fallback) => fallback -- the pill's fallback is the raw type name.
    expect(screen.getByText('translate')).toBeInTheDocument()
  })
})
