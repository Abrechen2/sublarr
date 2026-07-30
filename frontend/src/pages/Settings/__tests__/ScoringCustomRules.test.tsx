import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { ScoringCustomRules } from '../ScoringCustomRules'
import type { CustomScoringRule } from '@/api/settings'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key.split('.').pop() ?? key,
    i18n: { language: 'en', changeLanguage: vi.fn() },
  }),
}))

const mockCreate = vi.fn()
const mockUpdate = vi.fn()
const mockDelete = vi.fn()
let mockRules: CustomScoringRule[] = []

vi.mock('@/hooks/useApi', () => ({
  useCustomScoringRules: () => ({ data: { rules: mockRules }, isLoading: false }),
  useCreateCustomScoringRule: () => ({ mutate: mockCreate, isPending: false }),
  useUpdateCustomScoringRule: () => ({ mutate: mockUpdate, isPending: false }),
  useDeleteCustomScoringRule: () => ({ mutate: mockDelete, isPending: false }),
}))

vi.mock('@/components/shared/Toast', () => ({ toast: vi.fn() }))

const RULE: CustomScoringRule = {
  id: 1,
  name: 'Dual audio',
  pattern: 'dual[ .-]?audio',
  weight: 15,
  enabled: true,
}

describe('ScoringCustomRules', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockRules = []
  })

  it('shows the empty state when no rules exist', () => {
    render(<ScoringCustomRules />)
    expect(screen.getByText('empty')).toBeInTheDocument()
  })

  it('renders rule rows with name, pattern, and weight', () => {
    mockRules = [RULE]
    render(<ScoringCustomRules />)
    expect(screen.getByText('Dual audio')).toBeInTheDocument()
    expect(screen.getByText('dual[ .-]?audio')).toBeInTheDocument()
    expect(screen.getByText('+15')).toBeInTheDocument()
  })

  it('creates a rule from the add form', () => {
    render(<ScoringCustomRules />)
    fireEvent.change(screen.getByTestId('input-custom-rule-name'), { target: { value: 'Uncensored' } })
    fireEvent.change(screen.getByTestId('input-custom-rule-pattern'), { target: { value: 'uncensored' } })
    fireEvent.change(screen.getByTestId('input-custom-rule-weight'), { target: { value: '20' } })
    fireEvent.click(screen.getByTestId('btn-custom-rule-add'))
    expect(mockCreate).toHaveBeenCalledWith(
      { name: 'Uncensored', pattern: 'uncensored', weight: 20, enabled: true },
      expect.anything(),
    )
  })

  it('disables the add button when name or pattern is empty', () => {
    render(<ScoringCustomRules />)
    expect(screen.getByTestId('btn-custom-rule-add')).toBeDisabled()
  })

  it('toggles a rule enabled state', () => {
    mockRules = [RULE]
    render(<ScoringCustomRules />)
    fireEvent.click(screen.getByTestId('custom-rule-toggle-1'))
    expect(mockUpdate).toHaveBeenCalledWith({ ...RULE, enabled: false }, expect.anything())
  })

  it('deletes a rule', () => {
    mockRules = [RULE]
    render(<ScoringCustomRules />)
    fireEvent.click(screen.getByTestId('custom-rule-delete-1'))
    expect(mockDelete).toHaveBeenCalledWith(1, expect.anything())
  })
})
