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

  it('shows paused label when not active', async () => {
    const { StatusStripe } = await import('../StatusStripe')
    render(<StatusStripe />)
    expect(screen.getByTestId('status-label')).toHaveTextContent('statusStripe.paused')
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
  })
})
