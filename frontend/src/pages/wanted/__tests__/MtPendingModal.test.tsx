import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { MtPendingModal } from '../MtPendingModal'
import type { MtPendingItem } from '@/api/wanted'

const mockApproveMutate = vi.fn()
const mockRejectMutate = vi.fn()
let mockQueryState: { data: { data: MtPendingItem[]; total: number } | undefined; isLoading: boolean; isError: boolean } = {
  data: { data: [], total: 0 },
  isLoading: false,
  isError: false,
}

vi.mock('@/hooks/useApi', () => ({
  useMtPendingItems: () => mockQueryState,
  useApproveMtPending: () => ({ mutate: mockApproveMutate, isPending: false }),
  useRejectMtPending: () => ({ mutate: mockRejectMutate, isPending: false }),
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
})
