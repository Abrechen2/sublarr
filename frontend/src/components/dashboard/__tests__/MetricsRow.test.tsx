import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MetricsRow } from '../MetricsRow'

const mockUseStats = vi.fn()
const mockUseWantedSummary = vi.fn()

vi.mock('@/hooks/useSystemApi', () => ({
  useStats: () => mockUseStats(),
}))
vi.mock('@/hooks/useWantedApi', () => ({
  useWantedSummary: () => mockUseWantedSummary(),
}))
vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}))

const DEFAULT_STATS = {
  data: { total_subtitles: 12500, downloads_today: 30, success_rate: 92, average_score: 86.5, low_score_count: 7 },
  isLoading: false,
}
const DEFAULT_WANTED = { data: { total: 12 }, isLoading: false }

beforeEach(() => {
  mockUseStats.mockReturnValue(DEFAULT_STATS)
  mockUseWantedSummary.mockReturnValue(DEFAULT_WANTED)
})

describe('MetricsRow', () => {
  it('renders the metrics row container', () => {
    render(<MetricsRow />)
    expect(screen.getByTestId('metrics-row')).toBeInTheDocument()
  })

  it('renders total subtitles value', () => {
    render(<MetricsRow />)
    // formatNumber renders locale thousands separators (e.g. "12,500"/"12.500")
    expect(screen.getByTestId('metric-total-value')).toHaveTextContent(/12[\s.,]500/)
  })

  it('renders missing count from wantedSummary', () => {
    render(<MetricsRow />)
    expect(screen.getByTestId('metric-missing-value')).toHaveTextContent('12')
  })

  it('renders average score with 1 decimal', () => {
    render(<MetricsRow />)
    expect(screen.getByTestId('metric-avg-score-value')).toHaveTextContent('86.5')
  })

  it('renders low score count', () => {
    render(<MetricsRow />)
    expect(screen.getByTestId('metric-low-score-value')).toHaveTextContent('7')
  })

  it('shows dash placeholder when loading', () => {
    mockUseStats.mockReturnValue({ data: undefined, isLoading: true })
    mockUseWantedSummary.mockReturnValue({ data: undefined, isLoading: true })
    render(<MetricsRow />)
    expect(screen.getByTestId('metric-total-value')).toHaveTextContent('—')
    expect(screen.getByTestId('metric-missing-value')).toHaveTextContent('—')
    expect(screen.getByTestId('metric-avg-score-value')).toHaveTextContent('—')
    expect(screen.getByTestId('metric-low-score-value')).toHaveTextContent('—')
  })

  it('shows dash for all metrics when optional fields are absent', () => {
    mockUseStats.mockReturnValue({ data: { total_translated: 0 }, isLoading: false })
    mockUseWantedSummary.mockReturnValue({ data: undefined, isLoading: false })
    render(<MetricsRow />)
    expect(screen.getByTestId('metric-total-value')).toHaveTextContent('—')
    expect(screen.getByTestId('metric-missing-value')).toHaveTextContent('—')
    expect(screen.getByTestId('metric-avg-score-value')).toHaveTextContent('—')
    expect(screen.getByTestId('metric-low-score-value')).toHaveTextContent('—')
  })
})
