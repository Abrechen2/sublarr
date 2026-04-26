import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { BrowserRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ConnectionsSettings } from '../ConnectionsSettings'

// ─── Mocks ────────────────────────────────────────────────────────────────────

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
      return lookupKey(dict, key) ?? key
    },
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

const mockStandaloneScan = vi.fn()
vi.mock('@/hooks/useSystemApi', () => ({
  useStandaloneStatus: () => ({
    data: { enabled: false, watcher_running: false, folders_count: 0, scanner_scanning: false, arr_configured: false, auto_activated: false },
  }),
  useTriggerStandaloneScan: () => ({ mutate: mockStandaloneScan, isPending: false }),
}))

const mockConfig: Record<string, unknown> = {
  sonarr_url: 'http://localhost:8989',
  sonarr_api_key: '',
  radarr_url: '',
  radarr_api_key: '',
  path_mapping: '',
  sonarr_instances_json: JSON.stringify([
    { id: 'inst-1', name: 'Sonarr Home', url: 'http://localhost:8989', api_key: 'abc' },
  ]),
  radarr_instances_json: JSON.stringify([
    { id: 'rinst-1', name: 'Radarr Home', url: 'http://localhost:7878', api_key: 'xyz' },
  ]),
  tmdb_api_key: '',
  tvdb_api_key: '',
  tvdb_pin: '',
  metadata_cache_ttl_days: '7',
  ffmpeg_timeout: '30',
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

  it('renders all 5 settings sections', () => {
    renderWithProviders(<ConnectionsSettings />)
    const sections = screen.getAllByTestId('settings-section')
    expect(sections.length).toBeGreaterThanOrEqual(5)
  })

  // ── Media Servers section ──

  it('renders the Media Servers section', () => {
    renderWithProviders(<ConnectionsSettings />)
    expect(screen.getByText(/No media servers configured/i)).toBeInTheDocument()
  })

  // ── Standalone section ──

  it('renders the Standalone Mode section', () => {
    renderWithProviders(<ConnectionsSettings />)
    // FormLayout TOC also renders "Standalone Mode" — pick the section heading
    const headings = screen.getAllByText('Standalone Mode')
    const sectionHeading = headings.find(
      (el) => el.getAttribute('data-testid') === 'settings-section-title',
    )
    expect(sectionHeading).toBeInTheDocument()
    expect(screen.getByText('Scan library now')).toBeInTheDocument()
  })
})

// ─── Step 25: SonarrMultiInstanceSection ──────────────────────────────────────

describe('SonarrMultiInstanceSection (Step 25)', () => {
  beforeEach(() => { vi.clearAllMocks() })

  it('renders the sonarr multi-instance container', () => {
    renderWithProviders(<ConnectionsSettings />)
    expect(screen.getByTestId('sonarr-multi-instance')).toBeInTheDocument()
  })

  it('renders an instance card for each entry in sonarr_instances_json', () => {
    renderWithProviders(<ConnectionsSettings />)
    expect(screen.getByTestId('sonarr-instance-card-inst-1')).toBeInTheDocument()
  })

  it('renders the Add instance button', () => {
    renderWithProviders(<ConnectionsSettings />)
    expect(screen.getByTestId('sonarr-add-instance-btn')).toBeInTheDocument()
  })

  it('clicking Add calls updateConfig with a new instance appended', async () => {
    renderWithProviders(<ConnectionsSettings />)
    fireEvent.click(screen.getByTestId('sonarr-add-instance-btn'))
    await waitFor(() => {
      expect(mockMutate).toHaveBeenCalledWith(
        expect.objectContaining({
          sonarr_instances_json: expect.stringContaining('Sonarr 2'),
        }),
      )
    })
  })

  it('clicking Remove calls updateConfig without that instance', async () => {
    renderWithProviders(<ConnectionsSettings />)
    fireEvent.click(screen.getByTestId('sonarr-instance-remove-btn-inst-1'))
    await waitFor(() => {
      expect(mockMutate).toHaveBeenCalledWith(
        expect.objectContaining({ sonarr_instances_json: '[]' }),
      )
    })
  })
})

// ─── Step 26: RadarrMultiInstanceSection ──────────────────────────────────────

describe('RadarrMultiInstanceSection (Step 26)', () => {
  beforeEach(() => { vi.clearAllMocks() })

  it('renders the radarr multi-instance container', () => {
    renderWithProviders(<ConnectionsSettings />)
    expect(screen.getByTestId('radarr-multi-instance')).toBeInTheDocument()
  })

  it('renders an instance card for each entry in radarr_instances_json', () => {
    renderWithProviders(<ConnectionsSettings />)
    expect(screen.getByTestId('radarr-instance-card-rinst-1')).toBeInTheDocument()
  })

  it('renders the Add instance button', () => {
    renderWithProviders(<ConnectionsSettings />)
    expect(screen.getByTestId('radarr-add-instance-btn')).toBeInTheDocument()
  })

  it('clicking Add calls updateConfig with a new radarr instance appended', async () => {
    renderWithProviders(<ConnectionsSettings />)
    fireEvent.click(screen.getByTestId('radarr-add-instance-btn'))
    await waitFor(() => {
      expect(mockMutate).toHaveBeenCalledWith(
        expect.objectContaining({
          radarr_instances_json: expect.stringContaining('Radarr 2'),
        }),
      )
    })
  })

  it('clicking Remove calls updateConfig without that instance', async () => {
    renderWithProviders(<ConnectionsSettings />)
    fireEvent.click(screen.getByTestId('radarr-instance-remove-btn-rinst-1'))
    await waitFor(() => {
      expect(mockMutate).toHaveBeenCalledWith(
        expect.objectContaining({ radarr_instances_json: '[]' }),
      )
    })
  })
})

// ─── Step 27: MetadataApiKeysSection ─────────────────────────────────────────

describe('MetadataApiKeysSection (Step 27)', () => {
  beforeEach(() => { vi.clearAllMocks() })

  it('renders the metadata API keys section', () => {
    renderWithProviders(<ConnectionsSettings />)
    expect(screen.getByTestId('metadata-api-keys-section')).toBeInTheDocument()
  })

  it('renders TMDB API key input', () => {
    renderWithProviders(<ConnectionsSettings />)
    expect(screen.getByTestId('metadata-tmdb-api-key')).toBeInTheDocument()
  })

  it('renders TVDB API key input', () => {
    renderWithProviders(<ConnectionsSettings />)
    expect(screen.getByTestId('metadata-tvdb-api-key')).toBeInTheDocument()
  })

  it('renders TVDB PIN input', () => {
    renderWithProviders(<ConnectionsSettings />)
    expect(screen.getByTestId('metadata-tvdb-pin')).toBeInTheDocument()
  })

  it('renders cache TTL input', () => {
    renderWithProviders(<ConnectionsSettings />)
    expect(screen.getByTestId('metadata-cache-ttl')).toBeInTheDocument()
  })

  it('Save calls updateConfig with all metadata fields', async () => {
    renderWithProviders(<ConnectionsSettings />)
    fireEvent.click(screen.getByTestId('metadata-save-btn'))
    await waitFor(() => {
      expect(mockMutate).toHaveBeenCalledWith(
        expect.objectContaining({
          tmdb_api_key: expect.any(String),
          tvdb_api_key: expect.any(String),
          tvdb_pin: expect.any(String),
          metadata_cache_ttl_days: expect.any(String),
        }),
        expect.any(Object),
      )
    })
  })

  it('ffmpeg_timeout is not in metadata section (moved to Automation)', () => {
    renderWithProviders(<ConnectionsSettings />)
    expect(screen.queryByTestId('metadata-ffmpeg-timeout')).toBeNull()
  })
})
