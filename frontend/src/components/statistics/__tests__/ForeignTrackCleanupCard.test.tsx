import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import type { ForeignTrackStats } from '@/api/client'
import { ForeignTrackCleanupCard } from '../ForeignTrackCleanupCard'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    // An unknown pause code falls back to the backend text via defaultValue.
    t: (k: string, o?: { defaultValue?: string }) =>
      k === 'sweep_pause.unknown' && o?.defaultValue ? o.defaultValue : k,
  }),
}))

type QueryState = { data?: ForeignTrackStats; isLoading: boolean; isError?: boolean }
let query: QueryState = { isLoading: true }

vi.mock('@/hooks/useStatistics', () => ({
  useStatForeignTracks: () => query,
}))

const base: ForeignTrackStats = {
  files_stripped: 1234,
  tracks_removed: 5678,
  bytes_freed_total: 3 * 1024 ** 3,
  bytes_freed_30d: 512 * 1024 ** 2,
  scan_counts: { pending: 0, clean: 10, affected: 2, stripped: 3, failed: 1 },
  phase: 'strip',
  paused_reason: null,
}

describe('ForeignTrackCleanupCard', () => {
  beforeEach(() => {
    query = { isLoading: true }
  })

  it('shows a loading indicator while the stats load', () => {
    render(<ForeignTrackCleanupCard />)
    expect(screen.getByRole('status')).toBeInTheDocument()
    expect(screen.queryByText('track_cleanup.files')).not.toBeInTheDocument()
  })

  it('renders files, tracks, freed space (total + 30 days) and the phase', () => {
    query = { isLoading: false, data: base }
    render(<ForeignTrackCleanupCard />)
    expect(screen.getByText('track_cleanup.files')).toBeInTheDocument()
    expect(screen.getByText((1234).toLocaleString())).toBeInTheDocument()
    expect(screen.getByText((5678).toLocaleString())).toBeInTheDocument()
    expect(screen.getByText('3.0 GB')).toBeInTheDocument()
    expect(screen.getByText(/512\.0 MB/)).toBeInTheDocument()
    expect(screen.getByText('track_cleanup.phase.strip')).toBeInTheDocument()
    expect(screen.queryByText('track_cleanup.empty')).not.toBeInTheDocument()
  })

  it('shows the paused reason when the sweep is paused', () => {
    query = { isLoading: false, data: { ...base, paused_reason: 'disk floor reached' } }
    render(<ForeignTrackCleanupCard />)
    expect(screen.getByText(/disk floor reached/)).toBeInTheDocument()
  })

  it('translates a known pause code instead of showing the backend text', () => {
    query = {
      isLoading: false,
      data: { ...base, paused_reason: 'disk floor reached (min_free_gb=500)', paused_code: 'disk_floor' },
    }
    render(<ForeignTrackCleanupCard />)
    expect(screen.getByText(/sweep_pause\.disk_floor/)).toBeInTheDocument()
    expect(screen.queryByText(/min_free_gb/)).toBeNull()
  })

  it('shows an empty state when nothing has been cleaned yet', () => {
    query = {
      isLoading: false,
      data: { ...base, files_stripped: 0, tracks_removed: 0, bytes_freed_total: 0, bytes_freed_30d: 0, phase: 'idle' },
    }
    render(<ForeignTrackCleanupCard />)
    expect(screen.getByText('track_cleanup.empty')).toBeInTheDocument()
    expect(screen.getByText('track_cleanup.phase.idle')).toBeInTheDocument()
  })

  it('shows an error line when the request fails', () => {
    query = { isLoading: false, isError: true }
    render(<ForeignTrackCleanupCard />)
    expect(screen.getByText('track_cleanup.error')).toBeInTheDocument()
  })
})
