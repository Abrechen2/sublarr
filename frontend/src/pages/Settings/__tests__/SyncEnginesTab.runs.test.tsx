import { render, screen } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'

vi.mock('@/api/syncEngines', () => ({
  fetchSyncEngines: async () => ({ engines: [], sanity_threshold_ms: 5000 }),
  fetchSyncRuns: async () =>
    Array.from({ length: 50 }, (_, i) => ({
      id: i + 1, engine: 'alass', status: 'success', offset_ms: 0, duration_ms: 10,
      created_at: null, reason: null,
    })),
}))
vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k: string) => k }),
}))

import { SyncEnginesTab } from '../SyncEnginesTab'

describe('SyncEnginesTab run history', () => {
  // The last 50 runs scroll in their own box instead of stretching the page.
  it('lists the runs in a scroll box', async () => {
    render(
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter><SyncEnginesTab /></MemoryRouter>
      </QueryClientProvider>,
    )
    const box = await screen.findByTestId('sync-runs-list')
    expect(box.className).toContain('overflow-y-auto')
    expect(box.querySelectorAll('li')).toHaveLength(50)
  })
})
