import { describe, it, expect, vi, beforeAll } from 'vitest'
import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { FC } from 'react'

vi.mock('@/hooks/useSystemApi', () => ({
  useCleanupRules: () => ({ data: [], isLoading: false }),
  useCreateCleanupRule: () => ({ mutate: vi.fn(), isPending: false }),
  useUpdateCleanupRule: () => ({ mutate: vi.fn() }),
  useDeleteCleanupRule: () => ({ mutate: vi.fn() }),
  useRunCleanupRule: () => ({ mutate: vi.fn(), isPending: false }),
  useRulePreview: () => ({ mutate: vi.fn(), isPending: false }),
  useCleanupStats: () => ({ data: null, isLoading: false }),
  useStartCleanupScan: () => ({ mutate: vi.fn(), isPending: false }),
  useCleanupScanStatus: () => ({ data: null }),
  useDuplicates: () => ({ data: null, refetch: vi.fn() }),
  useDeleteDuplicates: () => ({ mutate: vi.fn(), isPending: false }),
  useOrphanedScan: () => ({ mutate: vi.fn(), isPending: false }),
  useOrphanedFiles: () => ({ data: null, refetch: vi.fn() }),
  useDeleteOrphaned: () => ({ mutate: vi.fn(), isPending: false }),
  useCleanupHistory: () => ({ data: null }),
  useCleanupPreview: () => ({ mutate: vi.fn() }),
}))

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (_k: string, fb: string) => fb ?? _k }),
}))

let CleanupSettings: FC

beforeAll(async () => {
  const mod = await import('../CleanupSettings')
  CleanupSettings = mod.CleanupSettings
})

function wrap(ui: React.ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>)
}

describe('CleanupSettings', () => {
  it('renders the page heading', () => {
    wrap(<CleanupSettings />)
    expect(screen.getByRole('heading', { level: 1 })).toBeTruthy()
    expect(screen.getByRole('heading', { level: 1 }).textContent).toBe('Bereinigung')
  })

  it('shows the automatic cleanup section', () => {
    wrap(<CleanupSettings />)
    expect(screen.getByText('Automatische Bereinigung')).toBeTruthy()
  })

  it('renders the 5 fixed operation cards', () => {
    wrap(<CleanupSettings />)
    expect(screen.getByText(/Sprachen-Filter/i)).toBeTruthy()
    expect(screen.getByText(/Format-Upgrade/i)).toBeTruthy()
  })
})
