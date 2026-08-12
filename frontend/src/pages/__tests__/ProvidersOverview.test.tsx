import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ProviderInfo } from '@/types/providers'
import { ProvidersOverviewPage } from '../ProvidersOverview'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k: string) => k }),
}))

const mockToast = vi.fn()
vi.mock('@/components/shared/Toast', () => ({
  toast: (message: string, type?: string) => mockToast(message, type),
}))

// Only the network boundary is stubbed. `useTestProvider` runs for real so the
// argument shape this page hands it is actually exercised — mocking the hook
// instead is what let a call with the wrong shape ship in 1.11.0.
const mockTestProvider = vi.fn()
vi.mock('@/api/providers', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/api/providers')>()),
  testProvider: (name: string, withDownload?: boolean) => mockTestProvider(name, withDownload),
}))

const provider: ProviderInfo = {
  name: 'opensubtitles',
  enabled: true,
  initialized: true,
  healthy: true,
  message: '',
  priority: 1,
  downloads: 42,
  config_fields: [],
  stats: {
    total_searches: 100,
    successful_searches: 80,
    successful_downloads: 60,
    failed_downloads: 2,
    success_rate: 0.6,
    download_rate: 0.6,
    result_rate: 0.8,
    avg_score: 88,
    consecutive_failures: 0,
    last_success_at: null,
    last_failure_at: null,
    avg_response_time_ms: 120,
    last_response_time_ms: 110,
    auto_disabled: false,
    disabled_until: '',
  },
}

vi.mock('@/hooks/useApi', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/hooks/useApi')>()),
  useProviders: () => ({ data: { providers: [provider] }, isLoading: false }),
  useBudgetState: () => ({ data: undefined }),
}))

function renderPage() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return render(
    <QueryClientProvider client={client}>
      <ProvidersOverviewPage />
    </QueryClientProvider>,
  )
}

describe('ProvidersOverviewPage — test button', () => {
  beforeEach(() => {
    mockTestProvider.mockReset()
    mockToast.mockReset()
  })

  it('tests the provider the card belongs to, not undefined', async () => {
    mockTestProvider.mockResolvedValue({
      provider: 'opensubtitles',
      healthy: true,
      message: 'All good',
    })

    renderPage()
    fireEvent.click(screen.getByText('providers_page.test'))

    await waitFor(() => expect(mockTestProvider).toHaveBeenCalled())
    expect(mockTestProvider).toHaveBeenCalledWith('opensubtitles', false)
  })

  it('surfaces the provider message on success', async () => {
    mockTestProvider.mockResolvedValue({
      provider: 'opensubtitles',
      healthy: true,
      message: 'All good',
    })

    renderPage()
    fireEvent.click(screen.getByText('providers_page.test'))

    await waitFor(() => expect(mockToast).toHaveBeenCalled())
    expect(mockToast).toHaveBeenCalledWith(expect.stringContaining('All good'), 'success')
  })

  it('falls back to the failure toast when the call rejects', async () => {
    mockTestProvider.mockRejectedValue(new Error('boom'))

    renderPage()
    fireEvent.click(screen.getByText('providers_page.test'))

    await waitFor(() => expect(mockToast).toHaveBeenCalled())
    expect(mockToast).toHaveBeenCalledWith('providers_page.test_failed', 'error')
  })
})
