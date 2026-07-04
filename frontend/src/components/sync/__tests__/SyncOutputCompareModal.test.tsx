import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { SyncOutputCompareModal } from '../SyncOutputCompareModal'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string, opts?: Record<string, unknown>) => (opts ? `${key}:${JSON.stringify(opts)}` : key) }),
}))
vi.mock('@/components/shared/Toast', () => ({ toast: vi.fn() }))

const compareMock = vi.fn()
const startMock = vi.fn()
vi.mock('@/api/client', () => ({
  syncCompare: (...a: unknown[]) => compareMock(...a),
  startVideoSync: (...a: unknown[]) => startMock(...a),
}))

function renderModal() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <SyncOutputCompareModal
        subtitlePath="/m/ep.en.srt"
        videoPath="/m/ep.mkv"
        onClose={vi.fn()}
        onApplied={vi.fn()}
      />
    </QueryClientProvider>,
  )
}

describe('SyncOutputCompareModal', () => {
  beforeEach(() => vi.clearAllMocks())

  it('renders candidate cues and applies the chosen engine', async () => {
    compareMock.mockResolvedValue({
      original: [{ start: 1000, end: 3000, text: 'Hello' }],
      candidates: [{ engine: 'ffsubsync', status: 'ok', shift_ms: 500, cues: [{ start: 1500, end: 3500, text: 'Hello' }] }],
      any_output: true,
    })
    startMock.mockResolvedValue({ job_id: 'j1' })
    renderModal()

    await waitFor(() => expect(screen.getByText(/sync_compare.apply/)).toBeInTheDocument())
    fireEvent.click(screen.getByText(/sync_compare.apply/))

    await waitFor(() => expect(startMock).toHaveBeenCalledTimes(1))
    expect(startMock).toHaveBeenCalledWith(
      expect.objectContaining({ file_path: '/m/ep.en.srt', video_path: '/m/ep.mkv', engine: 'ffsubsync' }),
    )
  })

  it('shows the no-output failure surface when no engine produced output', async () => {
    compareMock.mockResolvedValue({
      original: [{ start: 1000, end: 3000, text: 'Hello' }],
      candidates: [{ engine: 'ffsubsync', status: 'unavailable', error: 'not installed' }],
      any_output: false,
    })
    renderModal()

    await waitFor(() => expect(screen.getByText(/sync_compare.no_output/)).toBeInTheDocument())
    // No apply button when there is no ok candidate.
    expect(screen.queryByText(/sync_compare.apply:/)).not.toBeInTheDocument()
  })
})
