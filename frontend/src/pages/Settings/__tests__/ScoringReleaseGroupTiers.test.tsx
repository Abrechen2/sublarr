import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { ScoringReleaseGroupTiers } from '../ScoringReleaseGroupTiers'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key.split('.').pop() ?? key,
    i18n: { language: 'en', changeLanguage: vi.fn() },
  }),
}))

const mockMutate = vi.fn()
let mockTiers: { tiers: string[]; step: number } = { tiers: [], step: 10 }

vi.mock('@/hooks/useApi', () => ({
  useReleaseGroupTiers: () => ({ data: mockTiers, isLoading: false }),
  useUpdateReleaseGroupTiers: () => ({ mutate: mockMutate, isPending: false }),
}))

vi.mock('@/components/shared/Toast', () => ({ toast: vi.fn() }))

describe('ScoringReleaseGroupTiers', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockTiers = { tiers: [], step: 10 }
  })

  it('shows the empty state when no tiers are configured', () => {
    render(<ScoringReleaseGroupTiers />)
    expect(screen.getByText('empty')).toBeInTheDocument()
  })

  it('renders tier rows with computed bonus values', () => {
    mockTiers = { tiers: ['Erai-raws', 'SubsPlease'], step: 10 }
    render(<ScoringReleaseGroupTiers />)
    expect(screen.getByText('Erai-raws')).toBeInTheDocument()
    expect(screen.getByText('SubsPlease')).toBeInTheDocument()
    // Top tier: 10 * (2 - 0) = 20; second tier: 10 * (2 - 1) = 10
    expect(screen.getByText('+20')).toBeInTheDocument()
    expect(screen.getByText('+10')).toBeInTheDocument()
  })

  it('adds a group via the input and saves', () => {
    render(<ScoringReleaseGroupTiers />)
    fireEvent.change(screen.getByTestId('input-tier-add'), { target: { value: 'Judas' } })
    fireEvent.click(screen.getByTestId('btn-tier-add'))
    expect(screen.getByText('Judas')).toBeInTheDocument()

    fireEvent.click(screen.getByTestId('btn-save-tiers'))
    expect(mockMutate).toHaveBeenCalledWith(
      { tiers: ['Judas'], step: 10 },
      expect.anything(),
    )
  })

  it('moves a tier up', () => {
    mockTiers = { tiers: ['Erai-raws', 'SubsPlease'], step: 10 }
    render(<ScoringReleaseGroupTiers />)
    fireEvent.click(screen.getByTestId('tier-up-1'))
    fireEvent.click(screen.getByTestId('btn-save-tiers'))
    expect(mockMutate).toHaveBeenCalledWith(
      { tiers: ['SubsPlease', 'Erai-raws'], step: 10 },
      expect.anything(),
    )
  })

  it('removes a tier', () => {
    mockTiers = { tiers: ['Erai-raws', 'SubsPlease'], step: 10 }
    render(<ScoringReleaseGroupTiers />)
    fireEvent.click(screen.getByTestId('tier-remove-0'))
    expect(screen.queryByText('Erai-raws')).not.toBeInTheDocument()
  })

  it('does not add a duplicate group (case-insensitive)', () => {
    mockTiers = { tiers: ['Erai-raws'], step: 10 }
    render(<ScoringReleaseGroupTiers />)
    fireEvent.change(screen.getByTestId('input-tier-add'), { target: { value: 'erai-RAWS' } })
    fireEvent.click(screen.getByTestId('btn-tier-add'))
    expect(screen.getAllByText(/erai-raws/i)).toHaveLength(1)
  })
})
