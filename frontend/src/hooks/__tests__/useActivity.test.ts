import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import React from 'react'
import { useActivity } from '../useSystemApi'

const mockGetActivity = vi.fn()

vi.mock('@/api/client', () => ({
  getActivity: (...args: unknown[]) => mockGetActivity(...args),
}))

beforeEach(() => {
  mockGetActivity.mockClear()
  mockGetActivity.mockResolvedValue({
    data: [
      { id: 1, event_type: 'download', file_path: '/media/ep1.mkv', status: 'success',
        details_json: null, created_at: '2026-04-05T10:00:00Z' },
    ],
    total: 1,
    page: 1,
    per_page: 50,
    total_pages: 1,
  })
})

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return React.createElement(QueryClientProvider, { client: qc }, children)
}

describe('useActivity', () => {
  it('returns activity data from the API', async () => {
    const { result } = renderHook(() => useActivity(), { wrapper })
    await waitFor(() => expect(result.current.data).toBeDefined())
    expect(result.current.data!.data).toHaveLength(1)
    expect(result.current.data!.data[0].event_type).toBe('download')
  })

  it('passes page and perPage to getActivity', async () => {
    renderHook(() => useActivity(2, 20), { wrapper })
    await waitFor(() => expect(mockGetActivity).toHaveBeenCalledWith(2, 20, undefined))
  })

  it('passes event_type filter when provided', async () => {
    renderHook(() => useActivity(1, 50, 'extract'), { wrapper })
    await waitFor(() => expect(mockGetActivity).toHaveBeenCalledWith(1, 50, 'extract'))
  })
})
