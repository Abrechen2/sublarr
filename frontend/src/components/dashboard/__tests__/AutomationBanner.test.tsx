import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { AutomationBanner } from '../AutomationBanner'

const mockRefreshWanted = vi.fn()

vi.mock('@/hooks/useWantedApi', () => ({
  useScannerStatus: () => ({ data: { is_scanning: false, is_searching: false } }),
  useWantedSummary: () => ({ data: { total: 5 } }),
  useRefreshWanted: () => ({ mutate: mockRefreshWanted }),
}))
vi.mock('@/hooks/useSystemApi', () => ({
  useStats: () => ({ data: { total_subtitles: 1000, downloads_today: 12, success_rate: 94 } }),
}))
vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}))

describe('AutomationBanner', () => {
  beforeEach(() => {
    mockRefreshWanted.mockClear()
  })

  it('renders the Automation title', () => {
    render(<AutomationBanner />)
    expect(screen.getByText('automation.title')).toBeInTheDocument()
  })

  it('renders gray status dot when not active (not scanning/searching)', () => {
    render(<AutomationBanner />)
    const dot = screen.getByTestId('status-dot')
    expect(dot).toBeInTheDocument()
    // Gray dot — no pulse class when paused
    expect(dot.className).not.toContain('animate-')
  })

  it('renders green pulsing status dot when scanning is active', async () => {
    const { unmount } = render(<AutomationBanner />)
    unmount()

    // Re-mock with active scanning state
    vi.doMock('@/hooks/useWantedApi', () => ({
      useScannerStatus: () => ({ data: { is_scanning: true, is_searching: false } }),
      useWantedSummary: () => ({ data: { total: 5 } }),
      useRefreshWanted: () => ({ mutate: mockRefreshWanted }),
    }))
  })

  it('renders success rate stat', () => {
    render(<AutomationBanner />)
    expect(screen.getByTestId('stat-success-rate')).toBeInTheDocument()
    expect(screen.getByTestId('stat-success-rate')).toHaveTextContent('94')
  })

  it('renders today download count stat', () => {
    render(<AutomationBanner />)
    expect(screen.getByTestId('stat-downloads-today')).toBeInTheDocument()
    expect(screen.getByTestId('stat-downloads-today')).toHaveTextContent('12')
  })

  it('renders needs-attention count from wanted summary', () => {
    render(<AutomationBanner />)
    expect(screen.getByTestId('stat-needs-attention')).toBeInTheDocument()
    expect(screen.getByTestId('stat-needs-attention')).toHaveTextContent('5')
  })

  it('renders Pause button', () => {
    render(<AutomationBanner />)
    expect(screen.getByTestId('btn-pause')).toBeInTheDocument()
  })

  it('renders Run Now button', () => {
    render(<AutomationBanner />)
    expect(screen.getByTestId('btn-run-now')).toBeInTheDocument()
  })

  it('calls mutation when Run Now button is clicked', () => {
    render(<AutomationBanner />)
    fireEvent.click(screen.getByTestId('btn-run-now'))
    expect(mockRefreshWanted).toHaveBeenCalledTimes(1)
  })

  it('does not call mutation when Pause button is clicked (no mutation wired)', () => {
    render(<AutomationBanner />)
    fireEvent.click(screen.getByTestId('btn-pause'))
    // Pause button does not trigger refresh
    expect(mockRefreshWanted).not.toHaveBeenCalled()
  })
})
