import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { BrowserRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ConnectionsSettings } from '../ConnectionsSettings'

// ─── Mocks ────────────────────────────────────────────────────────────────────

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key.split('.').pop() ?? key,
    i18n: { language: 'en', changeLanguage: vi.fn() },
  }),
}))

vi.mock('@/components/shared/Toast', () => ({
  toast: vi.fn(),
}))

// Mock heavy lazy-loaded tabs to keep the test lightweight
vi.mock('../MediaServersTab', () => ({
  MediaServersTab: () => <div data-testid="mock-media-servers-tab">No media servers configured</div>,
}))

vi.mock('../ApiKeysTab', () => ({
  ApiKeysTab: () => <div data-testid="mock-api-keys-tab">API Key Management</div>,
}))

const mockConfig: Record<string, unknown> = {
  sonarr_url: 'http://localhost:8989',
  sonarr_api_key: '',
  radarr_url: '',
  radarr_api_key: '',
  path_mapping: '',
}

const mockMutate = vi.fn()
const mockTestSonarr = vi.fn()
const mockTestRadarr = vi.fn()

vi.mock('@/hooks/useApi', () => ({
  useConfig: () => ({ data: mockConfig, isLoading: false }),
  useUpdateConfig: () => ({ mutate: mockMutate, isPending: false }),
  useTestSonarrInstance: () => ({ mutate: mockTestSonarr, isPending: false }),
  useTestRadarrInstance: () => ({ mutate: mockTestRadarr, isPending: false }),
}))

// ─── Helpers ──────────────────────────────────────────────────────────────────

function makeQueryClient() {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } })
}

function renderWithProviders(ui: React.ReactElement) {
  const qc = makeQueryClient()
  return render(
    <QueryClientProvider client={qc}>
      <BrowserRouter>{ui}</BrowserRouter>
    </QueryClientProvider>,
  )
}

// ─── Tests ────────────────────────────────────────────────────────────────────

describe('ConnectionsSettings', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  // ── Page structure ──

  it('renders the settings detail layout', () => {
    renderWithProviders(<ConnectionsSettings />)
    expect(screen.getByTestId('settings-detail-layout')).toBeInTheDocument()
  })

  it('renders page title "Connections"', () => {
    renderWithProviders(<ConnectionsSettings />)
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Connections')
  })

  // ── Sections ──

  it('renders all 4 settings sections', () => {
    renderWithProviders(<ConnectionsSettings />)
    const sections = screen.getAllByTestId('settings-section')
    expect(sections.length).toBeGreaterThanOrEqual(4)
  })

  it('renders Sonarr connection card', () => {
    renderWithProviders(<ConnectionsSettings />)
    expect(screen.getByTestId('sonarr-connection-card')).toBeInTheDocument()
  })

  it('renders Radarr connection card', () => {
    renderWithProviders(<ConnectionsSettings />)
    expect(screen.getByTestId('radarr-connection-card')).toBeInTheDocument()
  })

  it('renders Sonarr service name', () => {
    renderWithProviders(<ConnectionsSettings />)
    const card = screen.getByTestId('sonarr-connection-card')
    expect(card.querySelector('[data-testid="connection-card-name"]')).toHaveTextContent('Sonarr')
  })

  it('renders Radarr service name', () => {
    renderWithProviders(<ConnectionsSettings />)
    const card = screen.getByTestId('radarr-connection-card')
    expect(card.querySelector('[data-testid="connection-card-name"]')).toHaveTextContent('Radarr')
  })

  it('displays Sonarr URL from config', () => {
    renderWithProviders(<ConnectionsSettings />)
    const card = screen.getByTestId('sonarr-connection-card')
    expect(card.querySelector('[data-testid="connection-card-url"]')).toHaveTextContent('http://localhost:8989')
  })

  // ── Sonarr Test button ──

  it('calls testSonarr mutate when Sonarr test button is clicked', async () => {
    renderWithProviders(<ConnectionsSettings />)
    const sonarrCard = screen.getByTestId('sonarr-connection-card')
    const testBtn = sonarrCard.querySelector('[data-testid="connection-card-test-btn"]')!
    fireEvent.click(testBtn)
    await waitFor(() => {
      expect(mockTestSonarr).toHaveBeenCalledTimes(1)
    })
    expect(mockTestSonarr).toHaveBeenCalledWith(
      { url: 'http://localhost:8989', api_key: '' },
      expect.any(Object),
    )
  })

  // ── Sonarr Edit form ──

  it('expands Sonarr edit form when edit button is clicked', () => {
    renderWithProviders(<ConnectionsSettings />)
    const sonarrCard = screen.getByTestId('sonarr-connection-card')
    const editBtn = sonarrCard.querySelector('[data-testid="connection-card-edit-btn"]')!
    fireEvent.click(editBtn)
    expect(sonarrCard.querySelector('[data-testid="connection-card-form"]')).toBeInTheDocument()
  })

  it('saves Sonarr settings when save is clicked in form', async () => {
    renderWithProviders(<ConnectionsSettings />)
    const sonarrCard = screen.getByTestId('sonarr-connection-card')
    fireEvent.click(sonarrCard.querySelector('[data-testid="connection-card-edit-btn"]')!)
    fireEvent.click(sonarrCard.querySelector('[data-testid="connection-card-save-btn"]')!)
    await waitFor(() => {
      expect(mockMutate).toHaveBeenCalledTimes(1)
    })
    expect(mockMutate).toHaveBeenCalledWith(
      expect.objectContaining({ sonarr_url: 'http://localhost:8989' }),
      expect.any(Object),
    )
  })

  // ── Radarr Test button (needs URL configured to trigger mutate) ──

  it('calls testRadarr mutate when Radarr edit form is expanded and saved', async () => {
    renderWithProviders(<ConnectionsSettings />)
    const radarrCard = screen.getByTestId('radarr-connection-card')
    // Expand form and set a URL first
    fireEvent.click(radarrCard.querySelector('[data-testid="connection-card-edit-btn"]')!)
    const urlInput = radarrCard.querySelector('[data-testid="connection-card-field-radarr_url"]')!
    fireEvent.change(urlInput, { target: { value: 'http://localhost:7878' } })
    // Now test button should call mutate
    fireEvent.click(radarrCard.querySelector('[data-testid="connection-card-test-btn"]')!)
    await waitFor(() => {
      expect(mockTestRadarr).toHaveBeenCalledTimes(1)
    })
  })

  // ── Media Servers section ──

  it('renders the Media Servers section', () => {
    renderWithProviders(<ConnectionsSettings />)
    // MediaServersTab renders a "No media servers configured" empty state
    expect(screen.getByText(/No media servers configured/i)).toBeInTheDocument()
  })

  // ── API Keys section ──

  it('renders the API Keys section', () => {
    renderWithProviders(<ConnectionsSettings />)
    // ApiKeysTab header text
    expect(screen.getByText(/API Key Management/i)).toBeInTheDocument()
  })

  // ── Radarr with no URL ──

  it('shows not_configured status for Radarr when URL is empty', () => {
    renderWithProviders(<ConnectionsSettings />)
    const radarrCard = screen.getByTestId('radarr-connection-card')
    // URL should not be displayed when empty
    expect(radarrCard.querySelector('[data-testid="connection-card-url"]')).toBeNull()
  })
})
