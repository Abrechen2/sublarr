import { describe, it, expect, vi, beforeAll, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import type { FC } from 'react'

const mockUpdateConfigMutate = vi.fn()

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
  useConfig: () => ({ data: { cleanup_signs_removal_level: 'off' }, isLoading: false }),
  useUpdateConfig: () => ({ mutate: mockUpdateConfigMutate, isPending: false }),
}))

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (_k: string, opts?: unknown) =>
      typeof opts === 'string' ? opts : ((opts as { defaultValue?: string })?.defaultValue ?? _k),
  }),
}))

let CleanupSettings: FC

beforeAll(async () => {
  const mod = await import('../CleanupSettings')
  CleanupSettings = mod.CleanupSettings
})

function wrap(ui: React.ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('CleanupSettings', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders the page heading', () => {
    wrap(<CleanupSettings />)
    expect(screen.getByRole('heading', { level: 1 })).toBeTruthy()
    expect(screen.getByRole('heading', { level: 1 }).textContent).toBe('Bereinigung')
  })

  it('shows the automatic cleanup section', () => {
    wrap(<CleanupSettings />)
    expect(screen.getByText('cleanup.auto_cleanup_heading')).toBeTruthy()
  })

  it('renders the 5 fixed operation cards', () => {
    wrap(<CleanupSettings />)
    expect(screen.getByText(/Sprachen-Filter/i)).toBeTruthy()
    expect(screen.getByText(/Format-Upgrade/i)).toBeTruthy()
  })

  it('renders the signs removal level dropdown and posts changes', () => {
    wrap(<CleanupSettings />)

    const select = screen.getByTestId('select-signs-removal-level') as HTMLSelectElement
    expect(select).toBeTruthy()

    // Option for signs_forced must exist
    const options = Array.from(select.options).map((o) => o.value)
    expect(options).toContain('signs_forced')

    // Selecting signs_forced triggers the config mutation
    fireEvent.change(select, { target: { value: 'signs_forced' } })
    expect(mockUpdateConfigMutate).toHaveBeenCalledWith({ cleanup_signs_removal_level: 'signs_forced' })
  })
})
