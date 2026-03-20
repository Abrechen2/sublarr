import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { BrowserRouter } from 'react-router-dom'
import { ProvidersSettings } from '../ProvidersSettings'

// ─── i18n ─────────────────────────────────────────────────────────────────────
vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, fallback?: string) => fallback ?? key.split('.').pop() ?? key,
    i18n: { language: 'en', changeLanguage: vi.fn() },
  }),
}))

// ─── API hooks ────────────────────────────────────────────────────────────────
const mockUpdateConfig = vi.fn()
const mockClearCache = vi.fn()

vi.mock('@/hooks/useApi', () => ({
  useConfig: () => ({
    data: { anti_captcha_provider: '', anti_captcha_api_key: '' },
    isLoading: false,
  }),
  useUpdateConfig: () => ({
    mutate: mockUpdateConfig,
    isPending: false,
  }),
  useProviders: () => ({
    data: { providers: [] },
    isLoading: false,
  }),
  useTestProvider: () => ({ mutate: vi.fn() }),
  useProviderStats: () => ({ data: { cache: {} } }),
  useClearProviderCache: () => ({
    mutate: mockClearCache,
    isPending: false,
  }),
  useMarketplaceBrowse: () => ({
    data: { plugins: [] },
    isLoading: false,
  }),
  useInstalledPlugins: () => ({ data: { installed: [] } }),
  useInstallBrowsePlugin: () => ({
    mutateAsync: vi.fn().mockResolvedValue({}),
    isPending: false,
    variables: null,
  }),
  useUninstallBrowsePlugin: () => ({
    mutateAsync: vi.fn().mockResolvedValue({}),
    isPending: false,
  }),
  useRefreshMarketplaceBrowse: () => ({ mutate: vi.fn(), isPending: false }),
}))

// ─── Toast ────────────────────────────────────────────────────────────────────
const mockToast = vi.fn()
vi.mock('@/components/shared/Toast', () => ({
  toast: (msg: string, type?: string) => mockToast(msg, type),
}))

// ─── Helpers ──────────────────────────────────────────────────────────────────
function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <BrowserRouter>
      <QueryClientProvider client={queryClient}>
        <ProvidersSettings />
      </QueryClientProvider>
    </BrowserRouter>,
  )
}

// ─── Tests ────────────────────────────────────────────────────────────────────
describe('ProvidersSettings', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders the settings detail layout', () => {
    renderPage()
    expect(screen.getByTestId('settings-detail-layout')).toBeInTheDocument()
  })

  it('renders the page title "Providers"', () => {
    renderPage()
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Providers')
  })

  it('renders the installed providers section', () => {
    renderPage()
    expect(screen.getByTestId('providers-installed-content')).toBeInTheDocument()
  })

  it('renders section title "Installed Providers"', () => {
    renderPage()
    expect(screen.getByText('Installed Providers')).toBeInTheDocument()
  })

  it('renders the marketplace section', () => {
    renderPage()
    expect(screen.getByTestId('providers-marketplace-content')).toBeInTheDocument()
  })

  it('renders section title "Marketplace"', () => {
    renderPage()
    // Multiple elements with "Marketplace" exist (tab button + section heading) — find the section heading
    const headings = screen.getAllByText('Marketplace')
    const sectionHeading = headings.find(
      (el) => el.getAttribute('data-testid') === 'settings-section-title',
    )
    expect(sectionHeading).toBeInTheDocument()
  })

  it('renders the anti-captcha section', () => {
    renderPage()
    expect(screen.getByTestId('providers-anticaptcha-content')).toBeInTheDocument()
  })

  it('renders section title "Anti-Captcha"', () => {
    renderPage()
    // Multiple "Anti-Captcha" headings exist (ProvidersTab + our section header) — find ours by testid
    const headings = screen.getAllByText('Anti-Captcha')
    const sectionHeading = headings.find(
      (el) => el.getAttribute('data-testid') === 'settings-section-title',
    )
    expect(sectionHeading).toBeInTheDocument()
  })

  it('renders the backend select in the anti-captcha section', () => {
    renderPage()
    // Use the labeled select in our section (has htmlFor="anti-captcha-backend")
    const select = screen.getByRole('combobox', { name: /Backend/i })
    expect(select).toBeInTheDocument()
  })

  it('anti-captcha backend has Disabled option by default', () => {
    renderPage()
    const select = screen.getByRole('combobox', { name: /Backend/i })
    expect(select).toHaveValue('')
  })

  it('does not render API key field when captcha provider is empty', () => {
    renderPage()
    expect(screen.queryByLabelText(/API Key/i)).toBeNull()
  })

  it('renders the cache management section', () => {
    renderPage()
    expect(screen.getByTestId('providers-cache-content')).toBeInTheDocument()
  })

  it('renders section title "Cache Management"', () => {
    renderPage()
    expect(screen.getByText('Cache Management')).toBeInTheDocument()
  })

  it('renders the clear all cache button', () => {
    renderPage()
    expect(screen.getByTestId('clear-all-cache-btn')).toBeInTheDocument()
  })

  it('calls clearProviderCache mutation when clear-all-cache button is clicked', () => {
    renderPage()
    const btn = screen.getByTestId('clear-all-cache-btn')
    fireEvent.click(btn)
    expect(mockClearCache).toHaveBeenCalledWith(undefined, expect.any(Object))
  })

  it('shows success toast after clearing cache', async () => {
    // Override mockClearCache to invoke onSuccess immediately
    mockClearCache.mockImplementation((_arg: unknown, opts: { onSuccess?: () => void }) => {
      opts?.onSuccess?.()
    })
    renderPage()
    const btn = screen.getByTestId('clear-all-cache-btn')
    fireEvent.click(btn)
    await waitFor(() => {
      expect(mockToast).toHaveBeenCalledWith(
        expect.stringContaining('cleared'),
        undefined,
      )
    })
  })

  it('calls updateConfig when anti-captcha backend changes', () => {
    renderPage()
    const select = screen.getByRole('combobox', { name: /Backend/i })
    fireEvent.change(select, { target: { value: 'anticaptcha' } })
    expect(mockUpdateConfig).toHaveBeenCalledWith({ anti_captcha_provider: 'anticaptcha' })
  })

  it('renders default breadcrumb with Settings link', () => {
    renderPage()
    const settingsLink = screen.getByText('Settings').closest('a')
    expect(settingsLink).toHaveAttribute('href', '/settings')
  })

  it('renders all four sections', () => {
    renderPage()
    expect(screen.getByTestId('providers-installed-content')).toBeInTheDocument()
    expect(screen.getByTestId('providers-marketplace-content')).toBeInTheDocument()
    expect(screen.getByTestId('providers-anticaptcha-content')).toBeInTheDocument()
    expect(screen.getByTestId('providers-cache-content')).toBeInTheDocument()
  })
})
