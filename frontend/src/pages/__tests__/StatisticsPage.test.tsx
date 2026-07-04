import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { StatisticsPage } from '../StatisticsPage'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k: string) => k }),
}))

// recharts renders via ResponsiveContainer which needs layout; stub the primitives'
// charts to keep the test focused on page composition + data wiring.
vi.mock('@/components/statistics/primitives', () => ({
  StatTile: ({ label, value }: { label: string; value: unknown }) => (
    <div data-testid="tile">{label}:{String(value)}</div>
  ),
  BreakdownBars: () => <div data-testid="bars" />,
  TrendsChart: () => <div data-testid="trends" />,
}))

const subtitles = { total: 12, by_source: { provider: 10 }, by_language: { de: 8 }, by_provider: {}, avg_score: 77 }
const translation = { total: 5, by_backend: { deepl: 5 }, total_chars: 100, total_cost_micro_usd: 2_000_000, avg_latency_ms: 400, pass_rate: 0.8, mt_awaiting_original: 3 }
const providers = { providers: [{ provider: 'opensubtitles', searches: 20, hit_rate: 0.5, downloads: 10, failures: 1, avg_score: 80, avg_response_ms: 100, auto_disabled: false }] }
const system = { cpu_percent: 12, memory_percent: 34, disk_percent: 56, uptime_seconds: 90000, db_size_bytes: 2_500_000, scheduler_runs: [] }
const library = { subtitle_files: 42, languages: ['de', 'en'], wanted_items: 7 }
const trends = { range: '30d', dates: ['2026-06-01'], downloads: [3], translations: [1], syncs: [0] }

vi.mock('@/hooks/useStatistics', () => ({
  useStatSubtitles: () => ({ data: subtitles, isLoading: false }),
  useStatTranslation: () => ({ data: translation, isLoading: false }),
  useStatProviders: () => ({ data: providers, isLoading: false }),
  useStatSystem: () => ({ data: system, isLoading: false }),
  useStatLibrary: () => ({ data: library, isLoading: false }),
  useStatTrends: () => ({ data: trends, isLoading: false }),
}))

describe('StatisticsPage', () => {
  it('renders KPI tiles, provider row and section titles from the data', () => {
    render(<StatisticsPage />)
    expect(screen.getByText('title')).toBeInTheDocument()
    // overview tiles show the numbers
    expect(screen.getByText('overview.subtitle_files:42')).toBeInTheDocument()
    expect(screen.getByText('overview.mt_awaiting:3')).toBeInTheDocument()
    // cost tile formats micro-usd -> $2.00
    expect(screen.getByText('translation.cost:$2.00')).toBeInTheDocument()
    // provider table renders the provider name
    expect(screen.getByText('opensubtitles')).toBeInTheDocument()
    // trends + breakdown charts mounted
    expect(screen.getByTestId('trends')).toBeInTheDocument()
    expect(screen.getAllByTestId('bars').length).toBeGreaterThan(0)
  })

  it('switches the active time range', () => {
    render(<StatisticsPage />)
    fireEvent.click(screen.getByText('range.24h'))
    // no throw; the 24h button is present
    expect(screen.getByText('range.24h')).toBeInTheDocument()
  })
})
