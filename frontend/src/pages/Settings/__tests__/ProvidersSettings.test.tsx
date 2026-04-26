import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { BrowserRouter } from 'react-router-dom'
import { ProvidersSettings } from '../ProvidersSettings'

// ─── i18n ─────────────────────────────────────────────────────────────────────

import enCommon from '../../../i18n/locales/en/common.json'
import enSettings from '../../../i18n/locales/en/settings.json'

function lookupKey(ns: Record<string, unknown>, key: string): string | undefined {
  const parts = key.split('.')
  let v: unknown = ns
  for (const p of parts) {
    if (typeof v !== 'object' || v === null) return undefined
    v = (v as Record<string, unknown>)[p]
  }
  return typeof v === 'string' ? v : undefined
}

vi.mock('react-i18next', () => ({
  useTranslation: (ns?: string) => ({
    t: (key: string, opts?: string | Record<string, unknown>) => {
      if (typeof opts === 'string') return opts
      if (opts !== undefined && typeof opts === 'object' && 'count' in opts)
        return `${key}:${String(opts.count)}`
      const dict = ns === 'settings' ? enSettings : enCommon
      return lookupKey(dict, key) ?? key.split('.').pop() ?? key
    },
    i18n: { language: 'en', changeLanguage: vi.fn() },
  }),
}))

// ─── API hooks ────────────────────────────────────────────────────────────────
const mockUpdateConfig = vi.fn()
const mockClearCache = vi.fn()

vi.mock('@/hooks/useApi', () => ({
  useConfig: () => ({
    data: {
      anti_captcha_provider: '',
      anti_captcha_api_key: '',
      providers_hidden: '',
      dedup_on_download: false,
      provider_auto_prioritize: false,
      provider_rate_limit_enabled: false,
      provider_search_timeout: 30,
      provider_cache_ttl_minutes: 60,
      provider_auto_disable_cooldown_minutes: 30,
      github_token: '',
      plugins_dir: '',
      plugin_hot_reload: false,
      provider_reranking_enabled: false,
      provider_reranking_min_downloads: 10,
      provider_reranking_max_modifier: 0.3,
      provider_dynamic_timeout_enabled: false,
      provider_dynamic_timeout_min_samples: 5,
      provider_dynamic_timeout_multiplier: 1.5,
      provider_dynamic_timeout_buffer_secs: 2,
      provider_dynamic_timeout_min_secs: 5,
      provider_dynamic_timeout_max_secs: 60,
      circuit_breaker_failure_threshold: 5,
      circuit_breaker_cooldown_seconds: 300,
      // Download Limits (Step 44)
      max_concurrent_provider_searches: '3',
      max_subtitle_file_size_kb: '2048',
      download_delay_between_providers_ms: '0',
    },
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

vi.mock('@/hooks/useProvidersApi', () => ({
  useProviderHealth: () => ({ data: undefined, isLoading: false }),
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

  it('renders the CollectionLayout master-detail scaffold for the provider list', () => {
    renderPage()
    expect(screen.getByTestId('settings.providers.collection-view')).toBeInTheDocument()
    expect(screen.getByTestId('collection-layout')).toBeInTheDocument()
  })

  it('renders section title "Global provider settings"', () => {
    renderPage()
    // FormLayout TOC also lists this title — pick the section heading by testid
    const headings = screen.getAllByText('Global provider settings')
    const sectionHeading = headings.find(
      (el) => el.getAttribute('data-testid') === 'settings-section-title',
    )
    expect(sectionHeading).toBeInTheDocument()
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

  it('renders all main page slots', () => {
    renderPage()
    expect(screen.getByTestId('providers-installed-content')).toBeInTheDocument()
    expect(screen.getByTestId('providers-global-section')).toBeInTheDocument()
    expect(screen.getByTestId('providers-marketplace-content')).toBeInTheDocument()
    expect(screen.getByTestId('providers-anticaptcha-content')).toBeInTheDocument()
    expect(screen.getByTestId('providers-cache-content')).toBeInTheDocument()
  })

  describe('Step 15 — installed section fields', () => {
    it('renders providers_hidden text input', () => {
      renderPage()
      expect(screen.getByTestId('input-providers-hidden')).toBeInTheDocument()
    })

    it('renders dedup_on_download toggle', () => {
      renderPage()
      expect(screen.getByTestId('toggle-dedup-on-download')).toBeInTheDocument()
    })

    it('renders provider_auto_prioritize toggle', () => {
      renderPage()
      expect(screen.getByTestId('toggle-provider-auto-prioritize')).toBeInTheDocument()
    })

    it('renders provider_rate_limit_enabled toggle', () => {
      renderPage()
      expect(screen.getByTestId('toggle-provider-rate-limit-enabled')).toBeInTheDocument()
    })

    it('renders provider_search_timeout number input', () => {
      renderPage()
      expect(screen.getByTestId('input-provider-search-timeout')).toBeInTheDocument()
    })

    it('renders provider_cache_ttl_minutes number input', () => {
      renderPage()
      expect(screen.getByTestId('input-provider-cache-ttl-minutes')).toBeInTheDocument()
    })

    it('renders provider_auto_disable_cooldown_minutes number input', () => {
      renderPage()
      expect(screen.getByTestId('input-provider-auto-disable-cooldown-minutes')).toBeInTheDocument()
    })

    it('calls updateConfig when providers_hidden changes', () => {
      renderPage()
      fireEvent.change(screen.getByTestId('input-providers-hidden'), {
        target: { value: 'opensubtitles' },
      })
      expect(mockUpdateConfig).toHaveBeenCalledWith({ providers_hidden: 'opensubtitles' })
    })

    it('calls updateConfig when dedup_on_download toggle is clicked', () => {
      renderPage()
      const wrapper = screen.getByTestId('toggle-dedup-on-download')
      const btn = wrapper.querySelector('[role="switch"]') as HTMLElement
      fireEvent.click(btn)
      expect(mockUpdateConfig).toHaveBeenCalledWith({ dedup_on_download: true })
    })

    it('calls updateConfig when provider_search_timeout changes', () => {
      renderPage()
      fireEvent.change(screen.getByTestId('input-provider-search-timeout'), {
        target: { value: '45' },
      })
      expect(mockUpdateConfig).toHaveBeenCalledWith({ provider_search_timeout: 45 })
    })
  })

  describe('Step 16 — marketplace section fields', () => {
    it('renders github_token password input', () => {
      renderPage()
      expect(screen.getByTestId('input-github-token')).toBeInTheDocument()
    })

    it('github_token is type="password"', () => {
      renderPage()
      expect(screen.getByTestId('input-github-token')).toHaveAttribute('type', 'password')
    })

    it('renders plugins_dir text input', () => {
      renderPage()
      expect(screen.getByTestId('input-plugins-dir')).toBeInTheDocument()
    })

    it('renders plugin_hot_reload toggle', () => {
      renderPage()
      expect(screen.getByTestId('toggle-plugin-hot-reload')).toBeInTheDocument()
    })

    it('calls updateConfig when github_token changes', () => {
      renderPage()
      fireEvent.change(screen.getByTestId('input-github-token'), {
        target: { value: 'ghp_abc123' },
      })
      expect(mockUpdateConfig).toHaveBeenCalledWith({ github_token: 'ghp_abc123' })
    })
  })

  describe('Step 17 — anti-captcha design alignment', () => {
    it('anti-captcha backend select is wrapped in a FormGroup', () => {
      renderPage()
      expect(screen.getByTestId('form-group-anti-captcha-backend')).toBeInTheDocument()
    })
  })

  describe('Step 18 — advanced section', () => {
    it('renders the advanced settings section', () => {
      renderPage()
      expect(screen.getByTestId('providers-advanced-section')).toBeInTheDocument()
    })

    it('advanced section has an Advanced toggle button', () => {
      renderPage()
      expect(screen.getByTestId('settings-section-advanced-toggle')).toBeInTheDocument()
    })

    it('advanced content is hidden by default (collapsed)', () => {
      renderPage()
      expect(screen.queryByTestId('settings-section-advanced-content')).not.toBeInTheDocument()
    })

    it('clicking Advanced toggle reveals the advanced content', () => {
      renderPage()
      fireEvent.click(screen.getByTestId('settings-section-advanced-toggle'))
      expect(screen.getByTestId('settings-section-advanced-content')).toBeInTheDocument()
    })

    it('advanced content contains provider_reranking_enabled toggle after expand', () => {
      renderPage()
      fireEvent.click(screen.getByTestId('settings-section-advanced-toggle'))
      expect(screen.getByTestId('toggle-provider-reranking-enabled')).toBeInTheDocument()
    })

    it('advanced content contains circuit_breaker_failure_threshold input after expand', () => {
      renderPage()
      fireEvent.click(screen.getByTestId('settings-section-advanced-toggle'))
      expect(
        screen.getByTestId('input-circuit-breaker-failure-threshold'),
      ).toBeInTheDocument()
    })

    it('calls updateConfig when provider_reranking_enabled is toggled', () => {
      renderPage()
      fireEvent.click(screen.getByTestId('settings-section-advanced-toggle'))
      const wrapper = screen.getByTestId('toggle-provider-reranking-enabled')
      const btn = wrapper.querySelector('[role="switch"]') as HTMLElement
      fireEvent.click(btn)
      expect(mockUpdateConfig).toHaveBeenCalledWith({ provider_reranking_enabled: true })
    })

    it('calls updateConfig when circuit_breaker_cooldown_seconds changes', () => {
      renderPage()
      fireEvent.click(screen.getByTestId('settings-section-advanced-toggle'))
      fireEvent.change(screen.getByTestId('input-circuit-breaker-cooldown-seconds'), {
        target: { value: '600' },
      })
      expect(mockUpdateConfig).toHaveBeenCalledWith({ circuit_breaker_cooldown_seconds: 600 })
    })
  })
})

// ─── Download Limits section (Step 44) ───────────────────────────────────────

describe('Download Limits section', () => {
  beforeEach(() => { vi.clearAllMocks() })

  it('renders heading "Download Limits"', () => {
    renderPage()
    const wrapper = screen.getByTestId('section-download-limits')
    const title = wrapper.querySelector('[data-testid="settings-section-title"]')
    expect(title).toHaveTextContent('Download Limits')
  })

  it('input-max-concurrent-provider-searches renders with value 3', () => {
    renderPage()
    const input = screen.getByTestId('input-max-concurrent-provider-searches') as HTMLInputElement
    expect(Number(input.value)).toBe(3)
  })

  it('input-max-subtitle-file-size-kb renders with value 2048', () => {
    renderPage()
    const input = screen.getByTestId('input-max-subtitle-file-size-kb') as HTMLInputElement
    expect(Number(input.value)).toBe(2048)
  })

  it('input-download-delay-between-providers-ms renders with value 0', () => {
    renderPage()
    const input = screen.getByTestId('input-download-delay-between-providers-ms') as HTMLInputElement
    expect(Number(input.value)).toBe(0)
  })

  it('changing concurrent searches calls updateConfig with max_concurrent_provider_searches: "5"', () => {
    renderPage()
    const input = screen.getByTestId('input-max-concurrent-provider-searches')
    fireEvent.change(input, { target: { value: '5' } })
    expect(mockUpdateConfig).toHaveBeenCalledWith({ max_concurrent_provider_searches: '5' })
  })
})
