/**
 * MarketplaceTab.test.tsx — Tests for plugin marketplace rendering,
 * capability warning modal, and search filtering.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MarketplaceTab } from '@/pages/Settings/providers/MarketplaceTab'

const mockPlugin = {
  name: 'test-provider',
  display_name: 'Test Provider',
  author: 'testuser',
  version: '1.0.0',
  description: 'A test provider',
  github_url: 'https://github.com/testuser/test-provider',
  zip_url: 'https://github.com/testuser/test-provider/releases/download/v1.0.0/plugin.zip',
  sha256: 'abc123',
  capabilities: ['network'],
  min_sublarr_version: '0.22.0',
  is_official: false,
}

const mockRiskyPlugin = {
  ...mockPlugin,
  name: 'risky-provider',
  display_name: 'Risky Provider',
  capabilities: ['network', 'filesystem'],
}

vi.mock('@/hooks/useApi', () => ({
  useMarketplaceBrowse: () => ({
    data: { plugins: [mockPlugin, mockRiskyPlugin] },
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

vi.mock('@/components/shared/Toast', () => ({
  toast: vi.fn(),
}))

function renderWithQuery(ui: React.ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>)
}

describe('MarketplaceTab', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders plugin cards', () => {
    renderWithQuery(<MarketplaceTab />)
    expect(screen.getByText('Test Provider')).toBeInTheDocument()
    expect(screen.getByText('Risky Provider')).toBeInTheDocument()
  })

  it('shows Community badge for non-official plugins', () => {
    renderWithQuery(<MarketplaceTab />)
    const badges = screen.getAllByText('Community')
    expect(badges.length).toBeGreaterThanOrEqual(1)
  })

  it('shows capability warning modal for risky community plugin', async () => {
    renderWithQuery(<MarketplaceTab />)
    const installButtons = screen.getAllByText('Install')
    // Risky plugin is second card
    fireEvent.click(installButtons[1])
    await waitFor(() => {
      expect(screen.getByRole('dialog')).toBeInTheDocument()
      expect(screen.getByText(/Elevated Permissions/i)).toBeInTheDocument()
    })
  })

  it('does NOT show capability warning for safe (network-only) plugin', () => {
    renderWithQuery(<MarketplaceTab />)
    const installButtons = screen.getAllByText('Install')
    // Safe plugin is first — network-only, no dialog expected
    fireEvent.click(installButtons[0])
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('filters plugins by search text', () => {
    renderWithQuery(<MarketplaceTab />)
    const searchInput = screen.getByPlaceholderText('Search plugins...')
    fireEvent.change(searchInput, { target: { value: 'risky' } })
    expect(screen.queryByText('Test Provider')).not.toBeInTheDocument()
    expect(screen.getByText('Risky Provider')).toBeInTheDocument()
  })
})
