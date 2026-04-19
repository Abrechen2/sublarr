import { render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) => {
      if (opts && typeof opts === 'object' && 'defaultValue' in opts) {
        return (opts.defaultValue as string) ?? key
      }
      return key
    },
  }),
}))

vi.mock('@/api/translation', () => ({
  getCostSummary: vi.fn().mockResolvedValue({
    today: { cost_usd: 0.5, events: 10, cache_hits: 2 },
    last_7d: { cost_usd: 3.2, events: 80, cache_hits: 20 },
    last_30d: { cost_usd: 12.1, events: 300, cache_hits: 80 },
  }),
  getCostByBackend: vi.fn().mockResolvedValue({
    window: '7d',
    backends: [
      {
        backend: 'claude',
        events: 50,
        cost_usd: 2.5,
        avg_latency_ms: 1400,
        error_rate: 0.02,
      },
    ],
  }),
  getMemoryTelemetry: vi.fn().mockResolvedValue({
    rows: 1200,
    size_bytes: 1_500_000,
    hit_rate_7d: 0.25,
  }),
  purgeMemory: vi.fn(),
  getConcurrency: vi.fn(),
  setConcurrency: vi.fn(),
}))

vi.mock('@/components/settings/SettingsDetailLayout', () => ({
  SettingsDetailLayout: ({
    title,
    subtitle,
    children,
  }: {
    title: string
    subtitle: string
    children: React.ReactNode
  }) => (
    <div>
      <h1>{title}</h1>
      <p>{subtitle}</p>
      {children}
    </div>
  ),
}))

vi.mock('@/components/shared/Toast', () => ({
  toast: vi.fn(),
}))

const { CostMemoryPage } = await import('../CostMemoryPage')

function renderPage() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <CostMemoryPage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('CostMemoryPage', () => {
  it('renders today cost summary', async () => {
    renderPage()
    await waitFor(() => {
      expect(screen.getByText('$0.50')).toBeInTheDocument()
    })
  })

  it('renders per-backend cost table with claude row', async () => {
    renderPage()
    await waitFor(() => {
      expect(screen.getByText('claude')).toBeInTheDocument()
    })
    expect(screen.getByText('$2.5000')).toBeInTheDocument()
  })

  it('shows TM stats including hit rate', async () => {
    renderPage()
    await waitFor(() => {
      expect(screen.getByText(/1[,.\s]200/)).toBeInTheDocument()
    })
    expect(screen.getByText('25.0%')).toBeInTheDocument()
  })
})
