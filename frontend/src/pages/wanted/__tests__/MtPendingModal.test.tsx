import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { MtPendingModal } from '../MtPendingModal'
import type { MtPendingItem } from '@/api/wanted'

const mockApproveMutate = vi.fn()
const mockRejectMutate = vi.fn()
const mockBatchMutate = vi.fn()
type BatchState = { running: boolean; total: number; done: number; installed: number; kept: number }
let mockQueryState: {
  data: { data: MtPendingItem[]; total: number; batch?: BatchState } | undefined
  isLoading: boolean
  isError: boolean
} = {
  data: { data: [], total: 0 },
  isLoading: false,
  isError: false,
}

vi.mock('@/hooks/useApi', () => ({
  useMtPendingItems: () => mockQueryState,
  useApproveMtPending: () => ({ mutate: mockApproveMutate, isPending: false }),
  useRejectMtPending: () => ({ mutate: mockRejectMutate, isPending: false }),
  useApproveMtPendingBatch: () => ({ mutate: mockBatchMutate, isPending: false }),
}))

const mockToast = vi.fn()
vi.mock('@/components/shared/Toast', () => ({
  toast: (...args: unknown[]) => mockToast(...args),
}))

const SAMPLE_ITEM: MtPendingItem = {
  id: 42,
  title: 'Attack on Titan',
  season_episode: 'S01E01',
  file_path: '/media/anime/aot/S01E01.mkv',
  item_type: 'episode',
  mt_pending_original: {
    provider: 'opensubtitles',
    score: 87,
    output_path: '/media/anime/aot/S01E01.en.srt',
    format: 'srt',
    found_at: new Date().toISOString(),
  },
}

describe('MtPendingModal', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockQueryState = { data: { data: [], total: 0 }, isLoading: false, isError: false }
  })

  it('renders nothing when closed', () => {
    const { container } = render(<MtPendingModal open={false} onClose={vi.fn()} />)
    expect(container).toBeEmptyDOMElement()
  })

  it('shows a loading indicator while fetching', () => {
    mockQueryState = { data: undefined, isLoading: true, isError: false }
    render(<MtPendingModal open onClose={vi.fn()} />)
    expect(screen.getByText(/Loading/i)).toBeInTheDocument()
  })

  it('shows an error message when the fetch fails', () => {
    mockQueryState = { data: undefined, isLoading: false, isError: true }
    render(<MtPendingModal open onClose={vi.fn()} />)
    expect(screen.getByText(/Failed to load pending originals/i)).toBeInTheDocument()
  })

  it('shows an empty state when there are no pending originals', () => {
    render(<MtPendingModal open onClose={vi.fn()} />)
    expect(screen.getByText(/No pending originals/i)).toBeInTheDocument()
  })

  it('renders a row per pending item with provider, score, and title', () => {
    mockQueryState = { data: { data: [SAMPLE_ITEM], total: 1 }, isLoading: false, isError: false }
    render(<MtPendingModal open onClose={vi.fn()} />)
    expect(screen.getByText(/Attack on Titan/)).toBeInTheDocument()
    expect(screen.getByText('opensubtitles')).toBeInTheDocument()
    expect(screen.getByText('87')).toBeInTheDocument()
  })

  it('calls approveMtPending and shows a success toast on Approve click', () => {
    mockQueryState = { data: { data: [SAMPLE_ITEM], total: 1 }, isLoading: false, isError: false }
    mockApproveMutate.mockImplementation((_id, opts) => opts?.onSuccess?.())
    render(<MtPendingModal open onClose={vi.fn()} />)
    fireEvent.click(screen.getByTestId('mt-pending-approve-42'))
    expect(mockApproveMutate).toHaveBeenCalledWith(42, expect.any(Object))
    expect(mockToast).toHaveBeenCalledWith(expect.any(String), 'success')
  })

  it('says the machine translation was kept when the original could not be installed', () => {
    mockQueryState = { data: { data: [SAMPLE_ITEM], total: 1 }, isLoading: false, isError: false }
    mockApproveMutate.mockImplementation((_id, opts) =>
      opts?.onError?.({ response: { status: 409 } }),
    )
    render(<MtPendingModal open onClose={vi.fn()} />)
    fireEvent.click(screen.getByTestId('mt-pending-approve-42'))
    expect(mockToast).toHaveBeenCalledWith(
      expect.stringMatching(/machine translation was kept/i),
      'error',
    )
  })

  it('shows the generic failure toast for other approve errors', () => {
    mockQueryState = { data: { data: [SAMPLE_ITEM], total: 1 }, isLoading: false, isError: false }
    mockApproveMutate.mockImplementation((_id, opts) =>
      opts?.onError?.({ response: { status: 500 } }),
    )
    render(<MtPendingModal open onClose={vi.fn()} />)
    fireEvent.click(screen.getByTestId('mt-pending-approve-42'))
    expect(mockToast).toHaveBeenCalledWith(
      expect.stringMatching(/Could not approve the original/i),
      'error',
    )
  })

  it('calls rejectMtPending and shows a success toast on Reject click', () => {
    mockQueryState = { data: { data: [SAMPLE_ITEM], total: 1 }, isLoading: false, isError: false }
    mockRejectMutate.mockImplementation((_id, opts) => opts?.onSuccess?.())
    render(<MtPendingModal open onClose={vi.fn()} />)
    fireEvent.click(screen.getByTestId('mt-pending-reject-42'))
    expect(mockRejectMutate).toHaveBeenCalledWith(42, expect.any(Object))
    expect(mockToast).toHaveBeenCalledWith(expect.any(String), 'success')
  })

  it('calls onClose when the close button is clicked', () => {
    const onClose = vi.fn()
    render(<MtPendingModal open onClose={onClose} />)
    fireEvent.click(screen.getByLabelText(/Close/i))
    expect(onClose).toHaveBeenCalled()
  })

  describe('bulk approval', () => {
    const SECOND: MtPendingItem = { ...SAMPLE_ITEM, id: 43, title: 'Bleach' }

    it('approves exactly the selected items', () => {
      mockQueryState = { data: { data: [SAMPLE_ITEM, SECOND], total: 2 }, isLoading: false, isError: false }
      render(<MtPendingModal open onClose={vi.fn()} />)

      fireEvent.click(screen.getByTestId('mt-pending-select-43'))
      fireEvent.click(screen.getByTestId('mt-pending-approve-selected'))

      expect(mockBatchMutate).toHaveBeenCalledWith([43], expect.any(Object))
    })

    it('selects and deselects all with the header checkbox', () => {
      mockQueryState = { data: { data: [SAMPLE_ITEM, SECOND], total: 2 }, isLoading: false, isError: false }
      render(<MtPendingModal open onClose={vi.fn()} />)

      fireEvent.click(screen.getByTestId('mt-pending-select-all'))
      expect(screen.getByTestId('mt-pending-selected-count')).toHaveTextContent('2')

      fireEvent.click(screen.getByTestId('mt-pending-approve-selected'))
      expect(mockBatchMutate).toHaveBeenCalledWith([42, 43], expect.any(Object))

      fireEvent.click(screen.getByTestId('mt-pending-select-all'))
      expect(screen.getByTestId('mt-pending-approve-selected')).toBeDisabled()
    })

    it('cannot approve an empty selection', () => {
      mockQueryState = { data: { data: [SAMPLE_ITEM], total: 1 }, isLoading: false, isError: false }
      render(<MtPendingModal open onClose={vi.fn()} />)

      expect(screen.getByTestId('mt-pending-approve-selected')).toBeDisabled()
    })

    it('shows progress and blocks approvals while a batch runs', () => {
      mockQueryState = {
        data: {
          data: [SAMPLE_ITEM],
          total: 1,
          batch: { running: true, total: 30, done: 12, installed: 11, kept: 1 },
        },
        isLoading: false,
        isError: false,
      }
      render(<MtPendingModal open onClose={vi.fn()} />)

      expect(screen.getByTestId('mt-pending-batch-progress')).toHaveTextContent('12')
      expect(screen.getByTestId('mt-pending-batch-progress')).toHaveTextContent('30')
      expect(screen.getByTestId('mt-pending-approve-42')).toBeDisabled()
      expect(screen.getByTestId('mt-pending-select-all')).toBeDisabled()
    })

    it('lays the table out to fit the dialog instead of scrolling sideways', () => {
      mockQueryState = { data: { data: [SAMPLE_ITEM], total: 1 }, isLoading: false, isError: false }
      render(<MtPendingModal open onClose={vi.fn()} />)

      expect(screen.getByRole('dialog').className).toMatch(/max-w-5xl/)
      expect(screen.getByRole('table').className).toMatch(/table-fixed/)
      expect(screen.getByText(SAMPLE_ITEM.file_path).className).toMatch(/break-all/)
    })
  })
})
