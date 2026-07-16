import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { useDebouncedConfigSave } from '../system/core'

// Override only the PUT so we can observe the debounced network calls; all
// other api/client exports stay real (core.ts imports several at module load).
const updateConfigMock = vi.fn().mockResolvedValue({ status: 'saved' })
vi.mock('@/api/client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/client')>()
  return {
    ...actual,
    updateConfig: (values: Record<string, unknown>) => updateConfigMock(values),
  }
})

describe('useDebouncedConfigSave', () => {
  let qc: QueryClient
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  )

  beforeEach(() => {
    vi.clearAllMocks()
    vi.useFakeTimers()
    qc = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    })
    qc.setQueryData(['config'], { items_per_page: 25 })
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('echoes each patch to the config cache immediately, before the debounce fires', () => {
    const { result } = renderHook(() => useDebouncedConfigSave(400), { wrapper })
    act(() => result.current({ items_per_page: 26 }))
    // Optimistic echo is synchronous; the PUT has not fired yet.
    expect(qc.getQueryData(['config'])).toMatchObject({ items_per_page: 26 })
    expect(updateConfigMock).not.toHaveBeenCalled()
  })

  it('collapses rapid edits to one field into a single PUT with the latest value', async () => {
    const { result } = renderHook(() => useDebouncedConfigSave(400), { wrapper })
    act(() => {
      result.current({ items_per_page: 26 })
      result.current({ items_per_page: 27 })
      result.current({ items_per_page: 28 })
    })
    expect(updateConfigMock).not.toHaveBeenCalled()
    await act(async () => {
      await vi.advanceTimersByTimeAsync(400)
    })
    expect(updateConfigMock).toHaveBeenCalledTimes(1)
    expect(updateConfigMock).toHaveBeenCalledWith({ items_per_page: 28 })
  })

  it('debounces different keys independently', async () => {
    const { result } = renderHook(() => useDebouncedConfigSave(400), { wrapper })
    act(() => {
      result.current({ items_per_page: 26 })
      result.current({ log_level: 'DEBUG' })
    })
    await act(async () => {
      await vi.advanceTimersByTimeAsync(400)
    })
    expect(updateConfigMock).toHaveBeenCalledTimes(2)
    expect(updateConfigMock).toHaveBeenCalledWith({ items_per_page: 26 })
    expect(updateConfigMock).toHaveBeenCalledWith({ log_level: 'DEBUG' })
  })
})
