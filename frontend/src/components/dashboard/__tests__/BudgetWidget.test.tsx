import { describe, it, expect, vi, beforeEach, test } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { QueryClient, QueryClientProvider, useQuery } from '@tanstack/react-query'
import { BudgetWidget, applyBudgetUpdate } from '../BudgetWidget'
import type { BudgetResponse } from '@/api/health'

const mockUseBudgetState = vi.fn()

vi.mock('@/hooks/useSystemApi', () => ({
  useBudgetState: () => mockUseBudgetState(),
}))
vi.mock('@/hooks/useWebSocket', () => ({
  useWebSocket: () => ({ connected: false, emit: vi.fn(), socket: null }),
}))
vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) => {
      if (opts && 'time' in opts) return `${key}:${String(opts.time)}`
      return key
    },
  }),
}))

function makeClient(): QueryClient {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } })
}

function renderWith(
  data: BudgetResponse | undefined,
  extras: Partial<{ isLoading: boolean; error: unknown; client: QueryClient }> = {},
) {
  mockUseBudgetState.mockReturnValue({
    data,
    isLoading: extras.isLoading ?? false,
    error: extras.error ?? null,
  })
  const client = extras.client ?? makeClient()
  return render(
    <QueryClientProvider client={client}>
      <BudgetWidget />
    </QueryClientProvider>,
  )
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

  it('renders learning badge when adjustment_factor < 1.0', () => {
    renderWith({
      enabled: true,
      providers: [
        {
          name: 'opensubtitles',
          tier: 'free',
          limits: { day: 1000, hour: 200, second: 5 },
          usage: { day: 100, hour: 10, second: 0 },
          reset_seconds: { day: 3600, hour: 60, second: 1 },
          learning: {
            adjustment_factor: 0.81,
            consecutive_good_days: 2,
            last_429_at: null,
          },
        },
      ],
    })
    const badge = screen.getByTestId('budget-learning-opensubtitles')
    expect(badge).toBeInTheDocument()
    // 1 - 0.81 = 0.19 → rounded to 19 → rendered as "-19%"
    expect(badge).toHaveTextContent('-19%')
  })

  it('hides learning badge at factor 1.0', () => {
    renderWith({
      enabled: true,
      providers: [
        {
          name: 'opensubtitles',
          tier: 'free',
          limits: { day: 1000, hour: 200, second: 5 },
          usage: { day: 100, hour: 10, second: 0 },
          reset_seconds: { day: 3600, hour: 60, second: 1 },
          learning: {
            adjustment_factor: 1.0,
            consecutive_good_days: 7,
            last_429_at: null,
          },
        },
      ],
    })
    expect(screen.queryByTestId('budget-learning-opensubtitles')).toBeNull()
  })

  test('clicking a row with 2+ keys reveals per-key breakdown', () => {
    renderWith({
      enabled: true,
      providers: [
        {
          name: 'opensubtitles',
          tier: 'vip',
          limits: { second: 10, hour: 1000, day: 11000 },
          usage: { second: 0, hour: 0, day: 100 },
          reset_seconds: { second: 1, hour: 60, day: 36000 },
          keys: [
            {
              id: 1,
              label: 'primary',
              tier: 'vip',
              used: { second: 0, hour: 0, day: 90 },
              limit: { second: 10, hour: 1000, day: 10000 },
              last_429_at: null,
              last_used_at: null,
            },
            {
              id: 2,
              label: 'backup',
              tier: 'free',
              used: { second: 0, hour: 0, day: 10 },
              limit: { second: 1, hour: 20, day: 200 },
              last_429_at: null,
              last_used_at: null,
            },
          ],
        },
      ],
    })
    const row = screen.getByTestId('budget-row-opensubtitles')
    fireEvent.click(row)
    expect(screen.getByTestId('key-detail-1')).toHaveTextContent('primary')
    expect(screen.getByTestId('key-detail-2')).toHaveTextContent('backup')
  })
})

// ─── applyBudgetUpdate (pure) ───────────────────────────────────────────────

describe('applyBudgetUpdate', () => {
  const base: BudgetResponse = {
    enabled: true,
    providers: [
      {
        name: 'opensubtitles',
        tier: 'free',
        limits: { day: 1000, hour: 200, second: 5 },
        usage: { day: 820, hour: 80, second: 0 },
        reset_seconds: { day: 3600, hour: 60, second: 1 },
      },
      {
        name: 'subdl',
        tier: 'free',
        limits: { day: 100, hour: 50, second: 2 },
        usage: { day: 10, hour: 5, second: 0 },
        reset_seconds: { day: 3600, hour: 60, second: 1 },
      },
    ],
  }

  it('patches usage for the matching provider only', () => {
    const result = applyBudgetUpdate(base, {
      provider: 'opensubtitles',
      usage: { day: 900, hour: 90, second: 1 },
    })
    expect(result?.providers.find((p) => p.name === 'opensubtitles')?.usage.day).toBe(900)
    expect(result?.providers.find((p) => p.name === 'subdl')?.usage.day).toBe(10)
  })

  it('returns undefined when cache is empty', () => {
    expect(
      applyBudgetUpdate(undefined, { provider: 'x', usage: { day: 1, hour: 1, second: 1 } }),
    ).toBeUndefined()
  })

  it('is a no-op for unknown providers', () => {
    const result = applyBudgetUpdate(base, {
      provider: 'doesnotexist',
      usage: { day: 999, hour: 99, second: 9 },
    })
    expect(result?.providers).toHaveLength(2)
    expect(result?.providers[0].usage.day).toBe(820)
    expect(result?.providers[1].usage.day).toBe(10)
  })

  it('produces new object references to trigger re-renders', () => {
    const result = applyBudgetUpdate(base, {
      provider: 'opensubtitles',
      usage: { day: 900, hour: 90, second: 1 },
    })
    expect(result).not.toBe(base)
    expect(result?.providers).not.toBe(base.providers)
    const patched = result?.providers.find((p) => p.name === 'opensubtitles')
    const original = base.providers.find((p) => p.name === 'opensubtitles')
    expect(patched).not.toBe(original)
  })
})

// ─── Integration: cache mutation re-renders widget ──────────────────────────

describe('BudgetWidget live updates', () => {
  const KEY = ['system', 'budget'] as const
  const INITIAL: BudgetResponse = {
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
  }

  it('updates displayed usage when the cache is patched (simulated SocketIO event)', async () => {
    const client = makeClient()
    client.setQueryData(KEY, INITIAL)

    // Drive the widget from the real query cache so setQueryData triggers a
    // re-render. We override the mock for this test only.
    mockUseBudgetState.mockImplementation(() => {
      const q = useQuery<BudgetResponse>({
        queryKey: [...KEY],
        queryFn: () => Promise.resolve(INITIAL),
        staleTime: Infinity,
      })
      return { data: q.data, isLoading: q.isLoading, error: q.error }
    })

    render(
      <QueryClientProvider client={client}>
        <BudgetWidget />
      </QueryClientProvider>,
    )

    // Initial render: 820 / 1000 (thousand-separator varies by locale)
    expect(await screen.findByTestId('budget-usage-opensubtitles')).toHaveTextContent(
      /^\s*820\s*\/\s*1[.,]000\s*$/,
    )

    // Simulate the SocketIO event → same cache mutation the widget performs.
    client.setQueryData<BudgetResponse | undefined>(KEY, (prev) =>
      applyBudgetUpdate(prev, {
        provider: 'opensubtitles',
        usage: { day: 900, hour: 90, second: 1 },
      }),
    )

    expect(await screen.findByTestId('budget-usage-opensubtitles')).toHaveTextContent(
      /^\s*900\s*\/\s*1[.,]000\s*$/,
    )
  })
})
