/**
 * ProtokollTab.test.tsx — Support export modal (`SupportModal`).
 *
 * Covers the three states the modal must handle without crashing:
 * loading the preview, the preview request failing, and the ZIP download
 * itself failing after a successful preview. Also covers that the new
 * (optional, backend-added) bundle sections render generically and are
 * simply absent when the backend hasn't shipped them yet — see the
 * "additional bundle sections" describe block.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { SupportModal } from '../ProtokollTab'
import enSettings from '../../../i18n/locales/en/settings.json'
import type { SupportPreview } from '@/lib/types'

// ─── Mocks ───────────────────────────────────────────────────────────────────

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
  useTranslation: () => ({
    t: (key: string) => lookupKey(enSettings, key) ?? key,
  }),
}))

const mockFetchSupportPreview = vi.fn()
const mockDownloadSupportBundle = vi.fn()

vi.mock('@/api/client', () => ({
  fetchSupportPreview: (...args: unknown[]) => mockFetchSupportPreview(...args),
  downloadSupportBundle: (...args: unknown[]) => mockDownloadSupportBundle(...args),
  getConfig: vi.fn(),
  updateConfig: vi.fn(),
}))

// ProtokollTab.tsx (this module) also statically imports these — SupportModal
// itself never calls them, but the barrel is heavy (pulls in the whole API
// surface), so it's mocked here for isolation, same as other page tests do.
vi.mock('@/hooks/useApi', () => ({
  useLogRotation: () => ({ data: undefined }),
  useUpdateLogRotation: () => ({ mutate: vi.fn(), isPending: false }),
}))

const mockToast = vi.fn()
vi.mock('@/components/shared/Toast', () => ({
  toast: (...args: unknown[]) => mockToast(...args),
}))

// ─── Fixtures ────────────────────────────────────────────────────────────────

const baseDiagnostic: SupportPreview['diagnostic'] = {
  version: '1.15.0',
  timestamp_utc: '2026-09-26T00:00:00Z',
  uptime_minutes: 125,
  memory_mb: 256,
  top_errors: [],
  provider_status: [],
  wanted: { total: 10, pending: 2, extracted: 1, failed: 1 },
  translations: { total_requests: 5, successful: 4, failed: 1 },
  last_scan_ago_minutes: 5,
  config_entries_count: 42,
}

const baseRedaction: SupportPreview['redaction_summary'] = {
  log_files_found: 2,
  ips_redacted: 3,
  api_keys_redacted: 1,
  paths_redacted: 4,
  emails_redacted: 0,
  hostnames_redacted: 0,
  example_path_before: '/media/anime/show/file.mkv',
  example_path_after: '<path>',
  example_ip_before: '10.0.0.5',
  example_ip_after: '<ip>',
}

function fullPreview(extra: Partial<SupportPreview> = {}): SupportPreview {
  return { diagnostic: baseDiagnostic, redaction_summary: baseRedaction, ...extra }
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function renderModal(onClose = vi.fn()) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return render(
    <QueryClientProvider client={qc}>
      <SupportModal onClose={onClose} />
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
})

// ─── Tests ────────────────────────────────────────────────────────────────────

describe('SupportModal — loading state', () => {
  it('shows the loading message while the preview request is in flight', () => {
    mockFetchSupportPreview.mockReturnValue(new Promise(() => {})) // never resolves
    renderModal()
    expect(screen.getByText('Preparing preview...')).toBeInTheDocument()
  })

  it('does not render the diagnostic or redaction sections yet', () => {
    mockFetchSupportPreview.mockReturnValue(new Promise(() => {}))
    renderModal()
    expect(screen.queryByText('Diagnostic Report')).toBeNull()
    expect(screen.queryByText('Anonymization')).toBeNull()
  })
})

describe('SupportModal — preview load failure', () => {
  // The component's useQuery hard-codes `retry: 1`, which wins over the test
  // QueryClient's `retry: false` default (per-query options always override
  // client defaults) — so the first failure schedules one retry with
  // react-query's default ~1s backoff before `isError` settles.
  const REJECT_WAIT = { timeout: 3000 }

  it('shows the error message when the preview request rejects', async () => {
    mockFetchSupportPreview.mockRejectedValue(new Error('network down'))
    renderModal()
    await waitFor(() => {
      expect(screen.getByText('Preview could not be loaded')).toBeInTheDocument()
    }, REJECT_WAIT)
  })

  it('never crashes and still offers Cancel / Download actions', async () => {
    mockFetchSupportPreview.mockRejectedValue(new Error('network down'))
    renderModal()
    await waitFor(() => {
      expect(screen.getByText('Preview could not be loaded')).toBeInTheDocument()
    }, REJECT_WAIT)
    expect(screen.getByText('Cancel')).toBeInTheDocument()
    expect(screen.getByText('Download ZIP')).toBeInTheDocument()
  })
})

describe('SupportModal — download failure', () => {
  it('toasts an error and re-enables the button when the ZIP download rejects', async () => {
    mockFetchSupportPreview.mockResolvedValue(fullPreview())
    mockDownloadSupportBundle.mockRejectedValue(new Error('disk full'))
    renderModal()

    await waitFor(() => {
      expect(screen.getByText('Diagnostic Report')).toBeInTheDocument()
    })

    const downloadButton = screen.getByText('Download ZIP')
    fireEvent.click(downloadButton)

    await waitFor(() => {
      expect(mockToast).toHaveBeenCalledWith('Preview could not be loaded', 'error')
    })

    // Button must not be left permanently disabled after the failure.
    await waitFor(() => {
      expect(screen.getByText('Download ZIP')).not.toBeDisabled()
    })
  })
})

describe('SupportModal — rate limit', () => {
  it('explains a 429 instead of claiming the preview failed', async () => {
    mockFetchSupportPreview.mockResolvedValue(fullPreview())
    mockDownloadSupportBundle.mockRejectedValue({ response: { status: 429 } })
    renderModal()

    await waitFor(() => {
      expect(screen.getByText('Diagnostic Report')).toBeInTheDocument()
    })
    fireEvent.click(screen.getByText('Download ZIP'))

    await waitFor(() => {
      expect(mockToast).toHaveBeenCalledWith(
        'Too many requests — please wait a minute and try again',
        'error',
      )
    })
  })
})

describe('SupportModal — additional bundle sections render generically', () => {
  it('renders nothing extra when the backend has not shipped the new sections yet', async () => {
    mockFetchSupportPreview.mockResolvedValue(fullPreview())
    renderModal()
    await waitFor(() => {
      expect(screen.getByText('Diagnostic Report')).toBeInTheDocument()
    })
    expect(screen.queryByText('Database')).toBeNull()
    expect(screen.queryByText('Scheduler')).toBeNull()
    expect(screen.queryByText('Environment')).toBeNull()
  })

  it('renders a present section as key/value rows without crashing', async () => {
    mockFetchSupportPreview.mockResolvedValue(
      fullPreview({
        sections: {
          database: { backend: 'postgres', alembic_head: 'abc123' },
          providers: [{ provider: 'jimaku', state: 'closed' }],
        },
      }),
    )
    renderModal()

    await waitFor(() => {
      expect(screen.getByText('Database')).toBeInTheDocument()
    })
    expect(screen.getByText('postgres')).toBeInTheDocument()
    expect(screen.getByText('alembic_head')).toBeInTheDocument()

    expect(screen.getByText('Providers')).toBeInTheDocument()
    expect(screen.getByText('closed')).toBeInTheDocument()

    // Sections the backend still hasn't sent stay absent.
    expect(screen.queryByText('Scheduler')).toBeNull()
  })
})
