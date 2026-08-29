/**
 * #200 — the page has to answer "which providers earn their place?".
 *
 * Determining that previously meant reading container logs and querying
 * subtitle_downloads by hand; six providers on the reporting install turned
 * out to contribute nothing and nobody could see it.
 */
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ProviderInfo } from '@/types/providers'
import { ProvidersOverviewPage } from '../ProvidersOverview'

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k: string) => k }) }))
vi.mock('@/components/shared/Toast', () => ({ toast: vi.fn() }))

const stats = {
  total_searches: 500,
  successful_searches: 100,
  successful_downloads: 0,
  failed_downloads: 0,
  success_rate: 0,
  download_rate: 0,
  result_rate: 0.2,
  avg_score: 0,
  consecutive_failures: 0,
  last_success_at: null,
  last_failure_at: null,
  avg_response_time_ms: 100,
  last_response_time_ms: 100,
  auto_disabled: false,
  disabled_until: '',
}

function make(name: string, over: Partial<ProviderInfo>): ProviderInfo {
  return {
    name,
    enabled: true,
    initialized: true,
    healthy: true,
    message: '',
    priority: 1,
    downloads: 0,
    config_fields: [],
    stats: { ...stats },
    ...over,
  }
}

const providers: ProviderInfo[] = []

vi.mock('@/hooks/useApi', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/hooks/useApi')>()),
  useProviders: () => ({ data: { providers }, isLoading: false }),
  useBudgetState: () => ({ data: undefined }),
}))

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <ProvidersOverviewPage />
    </QueryClientProvider>,
  )
}

describe('ProvidersOverviewPage — contribution', () => {
  beforeEach(() => {
    providers.length = 0
  })

  it('flags a provider that searches a lot and never wins', () => {
    providers.push(make('napisy24', { earns_its_place: false, contribution_share: 0 }))
    renderPage()
    expect(screen.getByTestId('provider-no-contribution-napisy24')).toBeTruthy()
  })

  it('does not accuse a provider with no evidence yet', () => {
    providers.push(make('freshone', { earns_its_place: null, contribution_share: 0 }))
    renderPage()
    expect(screen.queryByTestId('provider-no-contribution-freshone')).toBeNull()
  })

  it('leaves a contributor alone', () => {
    providers.push(make('opensubtitles', { earns_its_place: true, contribution_share: 0.62, downloads: 620 }))
    renderPage()
    expect(screen.queryByTestId('provider-no-contribution-opensubtitles')).toBeNull()
  })

  it('orders the biggest contributor first', () => {
    providers.push(make('small', { contribution_share: 0.05, earns_its_place: true }))
    providers.push(make('big', { contribution_share: 0.7, earns_its_place: true }))
    renderPage()
    const cards = screen.getAllByTestId(/^provider-card-/)
    expect(cards[0].getAttribute('data-testid')).toBe('provider-card-big')
  })
})
