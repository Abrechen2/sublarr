import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

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

function wrap(ui: React.ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>)
}

describe('CleanupSettings', () => {
  it('renders the page heading', async () => {
    const { CleanupSettings } = await import('../CleanupSettings')
    wrap(<CleanupSettings />)
    expect(screen.getByText(/Cleanup Rules/i)).toBeTruthy()
  })

  it('shows empty state when no rules exist', async () => {
    const { CleanupSettings } = await import('../CleanupSettings')
    wrap(<CleanupSettings />)
    expect(screen.getByText(/Noch keine Regeln/i)).toBeTruthy()
  })

  it('shows "+ Neu" button in sidebar', async () => {
    const { CleanupSettings } = await import('../CleanupSettings')
    wrap(<CleanupSettings />)
    expect(screen.getByText('Neu')).toBeTruthy()
  })
})
