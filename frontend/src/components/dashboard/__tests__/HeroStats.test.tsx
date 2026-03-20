import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'

vi.mock('@/hooks/useSystemApi', () => ({
  useStats: () => ({
    data: {
      total_subtitles: 12847,
      downloads_today: 48,
      success_rate: 87.3,
      average_score: 87.3,
      low_score_count: 12,
    },
  }),
}))

vi.mock('@/hooks/useWantedApi', () => ({
  useWantedSummary: () => ({
    data: { total: 234 },
  }),
}))

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}))

// Import after mocks are set up
const { HeroStats } = await import('../HeroStats')

describe('HeroStats', () => {
  it('renders 4 stat cards', () => {
    render(<HeroStats />)
    const cards = screen.getAllByTestId('hero-stat-card')
    expect(cards).toHaveLength(4)
  })

  it('renders Subtitles Total card with correct value', () => {
    render(<HeroStats />)
    expect(screen.getByTestId('hero-stat-subtitles-total')).toBeInTheDocument()
    expect(screen.getByTestId('hero-stat-subtitles-total')).toHaveTextContent('12847')
  })

  it('renders Missing card with correct value', () => {
    render(<HeroStats />)
    expect(screen.getByTestId('hero-stat-missing')).toBeInTheDocument()
    expect(screen.getByTestId('hero-stat-missing')).toHaveTextContent('234')
  })

  it('renders Quality Avg card with correct value', () => {
    render(<HeroStats />)
    expect(screen.getByTestId('hero-stat-quality-avg')).toBeInTheDocument()
    expect(screen.getByTestId('hero-stat-quality-avg')).toHaveTextContent('87.3')
  })

  it('renders Low Score card with correct value', () => {
    render(<HeroStats />)
    expect(screen.getByTestId('hero-stat-low-score')).toBeInTheDocument()
    expect(screen.getByTestId('hero-stat-low-score')).toHaveTextContent('12')
  })

  it('renders delta badge for Subtitles Total showing downloads_today', () => {
    render(<HeroStats />)
    expect(screen.getByTestId('delta-subtitles-total')).toBeInTheDocument()
    expect(screen.getByTestId('delta-subtitles-total')).toHaveTextContent('48')
  })

  it('renders delta badge for Missing with warning color when > 0', () => {
    render(<HeroStats />)
    const delta = screen.getByTestId('delta-missing')
    expect(delta).toBeInTheDocument()
    // Should have warning color styling when total > 0
    expect(delta).toHaveAttribute('data-variant', 'warning')
  })

  it('renders delta badge for Low Score with upgrade color when > 0', () => {
    render(<HeroStats />)
    const delta = screen.getByTestId('delta-low-score')
    expect(delta).toBeInTheDocument()
    expect(delta).toHaveAttribute('data-variant', 'upgrade')
  })

  it('renders stat labels (i18n keys)', () => {
    render(<HeroStats />)
    expect(screen.getByText('heroStats.subtitlesTotal')).toBeInTheDocument()
    expect(screen.getByText('heroStats.missing')).toBeInTheDocument()
    expect(screen.getByText('heroStats.qualityAvg')).toBeInTheDocument()
    expect(screen.getByText('heroStats.lowScore')).toBeInTheDocument()
  })

  it('renders sub-text for each card', () => {
    render(<HeroStats />)
    expect(screen.getByTestId('subtext-subtitles-total')).toBeInTheDocument()
    expect(screen.getByTestId('subtext-missing')).toBeInTheDocument()
    expect(screen.getByTestId('subtext-quality-avg')).toBeInTheDocument()
    expect(screen.getByTestId('subtext-low-score')).toBeInTheDocument()
  })

  it('has success color on Subtitles Total delta badge', () => {
    render(<HeroStats />)
    const delta = screen.getByTestId('delta-subtitles-total')
    expect(delta).toHaveAttribute('data-variant', 'success')
  })

  it('has accent color on Quality Avg card', () => {
    render(<HeroStats />)
    const card = screen.getByTestId('hero-stat-card-quality-avg')
    expect(card).toHaveAttribute('data-color', 'accent')
  })
})
