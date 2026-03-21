import { render, screen, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { MemoryRouter } from 'react-router-dom'

// ─── Mocks ───────────────────────────────────────────────────────────────────

const mockBatchTranslateMutate = vi.fn()
const mockRefreshMutate = vi.fn()
const mockCleanupMutate = vi.fn()

vi.mock('@/hooks/useTranslationApi', () => ({
  useBatchTranslate: () => ({ mutate: mockBatchTranslateMutate, isPending: false }),
}))

vi.mock('@/hooks/useApi', () => ({
  useWantedItems: () => ({ data: { data: [], total: 0 }, isLoading: false }),
  useWantedSummary: () => ({ data: { total: 0, by_status: {}, by_type: {}, upgradeable: 0, by_subtitle_type: {} } }),
  useRefreshWanted: () => ({ mutate: mockRefreshMutate, isPending: false }),
  useUpdateWantedStatus: () => ({ mutate: vi.fn() }),
  useSearchWantedItem: () => ({ mutate: vi.fn() }),
  useProcessWantedItem: () => ({ mutate: vi.fn() }),
  useExtractEmbeddedSub: () => ({ mutate: vi.fn() }),
  useStartWantedBatch: () => ({ mutate: vi.fn(), isPending: false }),
  useWantedBatchStatus: () => ({ data: null }),
  useWantedBatchExtractStatus: () => ({ data: null, refetch: vi.fn() }),
  useWantedBatchProbeStatus: () => ({ data: null }),
  useStartBatchProbe: () => ({ mutate: vi.fn(), isPending: false }),
  useRetranslateSingle: () => ({ mutate: vi.fn() }),
  useAddToBlacklist: () => ({ mutate: vi.fn() }),
  useCleanupSidecars: () => ({ mutate: mockCleanupMutate, isPending: false }),
  // Barrel re-exports (useBatchTranslate comes from useTranslationApi, handled separately)
  useBatchTranslate: () => ({ mutate: mockBatchTranslateMutate, isPending: false }),
}))

vi.mock('@/stores/selectionStore', () => ({
  useSelectionStore: (selector: (s: Record<string, unknown>) => unknown) =>
    selector({
      selections: {},
      toggleItem: vi.fn(),
      selectAll: vi.fn(),
      clearSelection: vi.fn(),
    }),
}))

vi.mock('@/hooks/useWebSocket', () => ({
  useWebSocket: () => ({}),
}))

vi.mock('@tanstack/react-query', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@tanstack/react-query')>()
  return { ...actual, useQueryClient: () => ({ invalidateQueries: vi.fn() }) }
})

vi.mock('@/components/wanted/VirtualWantedTable', () => ({
  useWantedVirtualizer: () => ({ parentRef: { current: null }, virtualItems: [], paddingTop: 0, paddingBottom: 0 }),
}))

vi.mock('@/components/filters/FilterBar', () => ({
  FilterBar: () => <div data-testid="filter-bar" />,
}))

vi.mock('@/components/filters/FilterPresetMenu', () => ({
  FilterPresetMenu: () => <div data-testid="filter-preset-menu" />,
}))

vi.mock('@/components/batch/BatchActionBar', () => ({
  BatchActionBar: () => <div data-testid="batch-action-bar" />,
}))

vi.mock('@/components/editor/SubtitleEditorModal', () => ({
  default: () => null,
}))

vi.mock('@/components/wanted/InteractiveSearchModal', () => ({
  InteractiveSearchModal: () => null,
}))

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: 'en' },
  }),
}))

vi.mock('@/components/shared/Toast', () => ({
  toast: vi.fn(),
}))

vi.mock('@/components/shared/StatusBadge', () => ({
  StatusBadge: () => null,
  SubtitleTypeBadge: () => null,
}))

vi.mock('@/lib/utils', () => ({
  formatRelativeTime: () => '',
  truncatePath: (p: string) => p,
}))

// ─── Tests ───────────────────────────────────────────────────────────────────

async function renderWanted() {
  const { WantedPage } = await import('../Wanted')
  return render(
    <MemoryRouter>
      <WantedPage />
    </MemoryRouter>
  )
}

describe('Wanted toolbar buttons (Steps 56 & 57)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders batch-translate-btn', async () => {
    await renderWanted()
    expect(screen.getByTestId('batch-translate-btn')).toBeTruthy()
  })

  it('calls batchTranslate.mutate when batch translate button is clicked', async () => {
    await renderWanted()
    fireEvent.click(screen.getByTestId('batch-translate-btn'))
    expect(mockBatchTranslateMutate).toHaveBeenCalledTimes(1)
  })

  it('renders wanted-refresh-btn', async () => {
    await renderWanted()
    expect(screen.getByTestId('wanted-refresh-btn')).toBeTruthy()
  })

  it('calls refreshWanted.mutate when refresh button is clicked', async () => {
    await renderWanted()
    fireEvent.click(screen.getByTestId('wanted-refresh-btn'))
    expect(mockRefreshMutate).toHaveBeenCalledTimes(1)
  })

  it('renders wanted-cleanup-btn', async () => {
    await renderWanted()
    expect(screen.getByTestId('wanted-cleanup-btn')).toBeTruthy()
  })
})
