import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import React from 'react'
import { TranslationsTab } from '../TranslationsTab'

const mockUseJobs = vi.fn()
const mockUseBatchStatus = vi.fn()
const mockCancelMutate = vi.fn()
const mockClearMutate = vi.fn()

vi.mock('@/hooks/useApi', () => ({
  useJobs: (...args: unknown[]) => mockUseJobs(...args),
  useBatchStatus: () => mockUseBatchStatus(),
  useCancelJob: () => ({ mutate: mockCancelMutate, isPending: false }),
  useClearQueuedJobs: () => ({ mutate: mockClearMutate, isPending: false }),
}))
vi.mock('@/components/shared/Toast', () => ({ toast: vi.fn() }))
vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, fallback?: unknown) => (typeof fallback === 'string' ? fallback : key),
  }),
}))

const RUNNING_JOBS = {
  data: [{ id: 'run-1', file_path: '/media/Show - S01E01.en.srt', status: 'running' }],
}
const QUEUED_JOBS = {
  data: [
    { id: 'q-1', file_path: '/media/Show - S01E02.en.srt', status: 'queued' },
    { id: 'q-2', file_path: '/media/Show - S01E03.en.srt', status: 'queued' },
  ],
}

function mockJobs(queued = QUEUED_JOBS, running = RUNNING_JOBS) {
  mockUseJobs.mockImplementation((_page, _perPage, status) =>
    status === 'queued' ? { data: queued } : { data: running },
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  mockJobs()
  mockUseBatchStatus.mockReturnValue({ data: undefined })
})

describe('TranslationsTab', () => {
  it('renders a cancel button for each queued row', () => {
    render(<TranslationsTab />)
    const cancelButtons = screen.getAllByLabelText('translations.cancel_job')
    expect(cancelButtons).toHaveLength(2)
  })

  it('does not render cancel buttons for running rows', () => {
    mockJobs({ data: [] }, RUNNING_JOBS)
    render(<TranslationsTab />)
    expect(screen.queryByLabelText('translations.cancel_job')).not.toBeInTheDocument()
  })

  it('calls the cancel mutation with the job id when clicked', () => {
    render(<TranslationsTab />)
    const [firstCancel] = screen.getAllByLabelText('translations.cancel_job')
    fireEvent.click(firstCancel)
    expect(mockCancelMutate).toHaveBeenCalledTimes(1)
    expect(mockCancelMutate.mock.calls[0][0]).toBe('q-1')
  })

  it('renders the clear-queued button and calls the mutation', () => {
    render(<TranslationsTab />)
    const clearButton = screen.getByRole('button', { name: 'translations.clear_queued' })
    expect(clearButton).toBeEnabled()
    fireEvent.click(clearButton)
    expect(mockClearMutate).toHaveBeenCalledTimes(1)
  })

  it('disables the clear-queued button when no jobs are queued', () => {
    mockJobs({ data: [] })
    render(<TranslationsTab />)
    const clearButton = screen.getByRole('button', { name: 'translations.clear_queued' })
    expect(clearButton).toBeDisabled()
    fireEvent.click(clearButton)
    expect(mockClearMutate).not.toHaveBeenCalled()
  })
})
