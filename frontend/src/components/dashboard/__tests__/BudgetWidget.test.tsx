import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { BudgetWidget } from '../BudgetWidget'
import type { BudgetResponse } from '@/api/health'

const mockUseBudgetState = vi.fn()

vi.mock('@/hooks/useSystemApi', () => ({
  useBudgetState: () => mockUseBudgetState(),
}))
vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) => {
      if (opts && 'time' in opts) return `${key}:${String(opts.time)}`
      return key
    },
  }),
}))

function renderWith(data: BudgetResponse | undefined, extras: Partial<{ isLoading: boolean; error: unknown }> = {}) {
  mockUseBudgetState.mockReturnValue({
    data,
    isLoading: extras.isLoading ?? false,
    error: extras.error ?? null,
  })
  return render(<BudgetWidget />)
}

const SAMPLE: BudgetResponse = {
  enabled: true,
  providers: [
    {
      name: 'subdl',
      tier: 'free',
      limits: { day: 100, hour: 50, second: 2 },
      usage: { day: 10, hour: 5, second: 0 },
      reset_seconds: { day: 7200, hour: 60, second: 1 },
    },
    {
      name: 'opensubtitles',
      tier: 'free',
      limits: { day: 1000, hour: 200, second: 5 },
      usage: { day: 820, hour: 80, second: 0 },
      reset_seconds: { day: 3600, hour: 60, second: 1 },
    },
  ],
}

beforeEach(() => {
  mockUseBudgetState.mockReset()
})

describe('BudgetWidget', () => {
  it('renders a row per provider in alphabetical order', () => {
    renderWith(SAMPLE)
    const rows = screen.getAllByRole('listitem')
    expect(rows.map((r) => r.getAttribute('data-testid'))).toEqual([
      'budget-row-opensubtitles',
      'budget-row-subdl',
    ])
  })

  it('shows disabled card when enabled=false', () => {
    renderWith({ enabled: false, providers: [] })
    expect(screen.getByTestId('budget-widget-disabled')).toBeInTheDocument()
    expect(screen.getByText('budget.disabled')).toBeInTheDocument()
  })

  it('applies high-usage colour at >=90%', () => {
    renderWith({
      enabled: true,
      providers: [
        {
          name: 'addic7ed',
          tier: 'free',
          limits: { day: 100, hour: 50, second: 2 },
          usage: { day: 95, hour: 5, second: 0 },
          reset_seconds: { day: 3600, hour: 60, second: 1 },
        },
      ],
    })
    const bar = screen.getByRole('progressbar')
    expect(bar.getAttribute('aria-valuenow')).toBe('95')
    expect(bar.getAttribute('aria-valuemax')).toBe('100')
    const row = screen.getByTestId('budget-row-addic7ed')
    expect(row.getAttribute('data-colour')).toBe('red')
  })

  it('uses yellow colour between 70% and 90%', () => {
    renderWith({
      enabled: true,
      providers: [
        {
          name: 'opensubtitles',
          tier: 'free',
          limits: { day: 1000, hour: 200, second: 5 },
          usage: { day: 820, hour: 80, second: 0 },
          reset_seconds: { day: 3600, hour: 60, second: 1 },
        },
      ],
    })
    const row = screen.getByTestId('budget-row-opensubtitles')
    expect(row.getAttribute('data-colour')).toBe('yellow')
  })

  it('uses green colour under 70%', () => {
    renderWith({
      enabled: true,
      providers: [
        {
          name: 'subdl',
          tier: 'free',
          limits: { day: 100, hour: 50, second: 2 },
          usage: { day: 10, hour: 5, second: 0 },
          reset_seconds: { day: 7200, hour: 60, second: 1 },
        },
      ],
    })
    const row = screen.getByTestId('budget-row-subdl')
    expect(row.getAttribute('data-colour')).toBe('green')
  })

  it('shows the minimum day-reset countdown across providers', () => {
    renderWith(SAMPLE)
    // min(3600, 7200) = 3600 -> "1h 0min"
    expect(screen.getByTestId('budget-reset')).toHaveTextContent('budget.reset_in:1h 0min')
  })

  it('returns null when the query errors', () => {
    const { container } = renderWith(undefined, { error: new Error('boom') })
    expect(container.firstChild).toBeNull()
  })

  it('renders loading card while fetching', () => {
    renderWith(undefined, { isLoading: true })
    expect(screen.getByTestId('budget-widget-loading')).toBeInTheDocument()
  })
})
