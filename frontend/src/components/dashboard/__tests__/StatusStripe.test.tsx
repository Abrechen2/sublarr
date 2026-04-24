import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'

const mockMutate = vi.fn()

vi.mock('@/hooks/useWantedApi', () => ({
  useScannerStatus: vi.fn(() => ({ data: { is_scanning: false, is_searching: false, last_scan_at: '2026-04-05T10:00:00Z', last_search_at: null } })),
  useWantedSummary: vi.fn(() => ({ data: { total: 3 } })),
  useRefreshWanted: vi.fn(() => ({ mutate: mockMutate, isPending: false })),
}))
vi.mock('@/hooks/useSystemApi', () => ({
  useStats: vi.fn(() => ({ data: { total_subtitles: 5000, downloads_today: 22, success_rate: 95, average_score: 88.0, low_score_count: 4 } })),
}))
vi.mock('@/hooks/useSchedulerJobs', () => ({
  useSchedulerJobs: vi.fn(() => ({
    data: {
      jobs: [
        { id: 'wanted_scanner', paused: false },
        { id: 'wanted_search', paused: false },
      ],
    },
  })),
}))
vi.mock('react-i18next', () => ({
  useTranslation: vi.fn(() => ({ t: (key: string) => key })),
}))

describe('StatusStripe', () => {
  beforeEach(() => mockMutate.mockClear())

  it('renders the stripe container', async () => {
    const { StatusStripe } = await import('../StatusStripe')
    render(<StatusStripe />)
    expect(screen.getByTestId('status-stripe')).toBeInTheDocument()
  })

  it('shows IDLE label when armed and waiting (no jobs paused, not scanning)', async () => {
    const { StatusStripe } = await import('../StatusStripe')
    render(<StatusStripe />)
    expect(screen.getByTestId('status-label')).toHaveTextContent('statusStripe.idle')
    expect(screen.getByTestId('status-dot').getAttribute('data-state')).toBe('idle')
  })

  it('shows PAUSED label only when BOTH scheduler jobs are paused', async () => {
    const { useSchedulerJobs } = await import('@/hooks/useSchedulerJobs')
    ;(useSchedulerJobs as ReturnType<typeof vi.fn>).mockReturnValueOnce({
      data: {
        jobs: [
          { id: 'wanted_scanner', paused: true },
          { id: 'wanted_search', paused: true },
        ],
      },
    })

    const { StatusStripe } = await import('../StatusStripe')
    render(<StatusStripe />)
    expect(screen.getByTestId('status-label')).toHaveTextContent('statusStripe.paused')
    expect(screen.getByTestId('status-dot').getAttribute('data-state')).toBe('paused')
  })

  it('stays IDLE when only one job is paused (partial pause)', async () => {
    const { useSchedulerJobs } = await import('@/hooks/useSchedulerJobs')
    ;(useSchedulerJobs as ReturnType<typeof vi.fn>).mockReturnValueOnce({
      data: {
        jobs: [
          { id: 'wanted_scanner', paused: true },
          { id: 'wanted_search', paused: false },
        ],
      },
    })

    const { StatusStripe } = await import('../StatusStripe')
    render(<StatusStripe />)
    expect(screen.getByTestId('status-dot').getAttribute('data-state')).toBe('idle')
  })

  it('exposes an aria-live status region for screen readers', async () => {
    const { StatusStripe } = await import('../StatusStripe')
    render(<StatusStripe />)
    const live = screen.getByTestId('status-stripe').querySelector('[aria-live="polite"]')
    expect(live).not.toBeNull()
    expect(live?.getAttribute('aria-label')).toBeTruthy()
  })

  it('shows total_subtitles', async () => {
    const { StatusStripe } = await import('../StatusStripe')
    render(<StatusStripe />)
    expect(screen.getByTestId('status-total')).toHaveTextContent('5000')
  })

  it('shows success_rate', async () => {
    const { StatusStripe } = await import('../StatusStripe')
    render(<StatusStripe />)
    expect(screen.getByTestId('status-rate')).toHaveTextContent('95')
  })

  it('shows downloads_today', async () => {
    const { StatusStripe } = await import('../StatusStripe')
    render(<StatusStripe />)
    expect(screen.getByTestId('status-today')).toHaveTextContent('22')
  })

  it('shows missing count from wantedSummary', async () => {
    const { StatusStripe } = await import('../StatusStripe')
    render(<StatusStripe />)
    expect(screen.getByTestId('status-missing')).toHaveTextContent('3')
  })

  it('renders Run Now button', async () => {
    const { StatusStripe } = await import('../StatusStripe')
    render(<StatusStripe />)
    expect(screen.getByTestId('btn-run-now')).toBeInTheDocument()
  })

  it('calls refreshWanted when Run Now is clicked', async () => {
    const { StatusStripe } = await import('../StatusStripe')
    render(<StatusStripe />)
    fireEvent.click(screen.getByTestId('btn-run-now'))
    expect(mockMutate).toHaveBeenCalledTimes(1)
  })

  it('shows active label when scanning', async () => {
    const { useScannerStatus } = await import('@/hooks/useWantedApi')
    const mockScannerStatus = useScannerStatus as ReturnType<typeof vi.fn>
    mockScannerStatus.mockReturnValueOnce({
      data: { is_scanning: true, is_searching: false, last_scan_at: null, last_search_at: null },
    })

    const { StatusStripe } = await import('../StatusStripe')
    render(<StatusStripe />)
    expect(screen.getByTestId('status-label')).toHaveTextContent('statusStripe.active')
    expect(screen.getByTestId('status-dot').getAttribute('data-state')).toBe('active')
    expect(screen.getByTestId('status-dot').className).toContain('automation-pulse')
  })

  it('falls back to IDLE when scheduler data is still loading (undefined)', async () => {
    const { useSchedulerJobs } = await import('@/hooks/useSchedulerJobs')
    ;(useSchedulerJobs as ReturnType<typeof vi.fn>).mockReturnValueOnce({ data: undefined })

    const { StatusStripe } = await import('../StatusStripe')
    render(<StatusStripe />)
    // Without scheduler data we cannot prove paused → default to idle, not paused
    expect(screen.getByTestId('status-dot').getAttribute('data-state')).toBe('idle')
  })
})
