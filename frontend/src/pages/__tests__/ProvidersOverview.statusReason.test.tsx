/**
 * #201 (core) — the status pill must name the actual reason.
 *
 * Every `healthy: false` used to render as "Unreachable", so a provider that
 * merely had no account configured looked like a network outage. On the
 * reporting install that was `titlovi`, and it sent the owner looking at DNS
 * for a missing password.
 *
 * These render the real page rather than calling the mapper directly: the
 * mapper is private, and the thing that actually broke was what the user saw.
 */
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ProviderInfo, ProviderStatusReason } from '@/types/providers'
import { ProvidersOverviewPage } from '../ProvidersOverview'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k: string) => k }),
}))

vi.mock('@/components/shared/Toast', () => ({ toast: vi.fn() }))

const provider: ProviderInfo = {
  name: 'titlovi',
  enabled: true,
  initialized: false,
  healthy: false,
  message: '',
  priority: 1,
  downloads: 0,
  config_fields: [],
  stats: {
    total_searches: 0,
    successful_searches: 0,
    successful_downloads: 0,
    failed_downloads: 0,
    success_rate: 0,
    download_rate: 0,
    result_rate: 0,
    avg_score: 0,
    consecutive_failures: 0,
    last_success_at: null,
    last_failure_at: null,
    avg_response_time_ms: 0,
    last_response_time_ms: 0,
    auto_disabled: false,
    disabled_until: '',
  },
}

vi.mock('@/hooks/useApi', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/hooks/useApi')>()),
  useProviders: () => ({ data: { providers: [provider] }, isLoading: false }),
  useBudgetState: () => ({ data: undefined }),
}))

function renderWith(reason: ProviderStatusReason | undefined) {
  provider.status_reason = reason
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <ProvidersOverviewPage />
    </QueryClientProvider>,
  )
}

describe('ProvidersOverviewPage — status reason', () => {
  beforeEach(() => {
    provider.status_reason = undefined
  })

  it('shows "no credentials", not "unreachable", when the account is unset', () => {
    renderWith('no_credentials')
    const dot = screen.getByTestId('provider-status-titlovi')
    expect(dot.getAttribute('data-tier')).toBe('warn')
    expect(screen.getByText('providers_page.status.no_credentials')).toBeTruthy()
  })

  it('a provider that answers but never delivers is a warning, not an error', () => {
    renderWith('no_results')
    expect(screen.getByTestId('provider-status-titlovi').getAttribute('data-tier')).toBe('warn')
    expect(screen.getByText('providers_page.status.no_results')).toBeTruthy()
  })

  it('repeated failures stay an error', () => {
    renderWith('consecutive_failures')
    expect(screen.getByTestId('provider-status-titlovi').getAttribute('data-tier')).toBe('error')
    expect(screen.getByText('providers_page.status.consecutive_failures')).toBeTruthy()
  })

  it('a rejected key says so, instead of pointing at the network', () => {
    renderWith('credentials_rejected')
    expect(screen.getByText('providers_page.status.credentials_rejected')).toBeTruthy()
  })

  it('a host that no longer resolves says that instead', () => {
    renderWith('host_unreachable')
    expect(screen.getByText('providers_page.status.host_unreachable')).toBeTruthy()
  })

  it('falls back to the old label when the backend sends no reason', () => {
    renderWith(undefined)
    expect(screen.getByText('providers_page.status.unreachable')).toBeTruthy()
  })
})
