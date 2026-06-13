import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { EnableTranslationModal } from '../EnableTranslationModal'

const mockMutate = vi.fn()
vi.mock('@/hooks/useApi', () => ({
  useUpdateConfig: () => ({ mutate: mockMutate, isPending: false }),
}))

describe('EnableTranslationModal', () => {
  beforeEach(() => {
    mockMutate.mockClear()
  })

  it('renders beta warning text', () => {
    render(<EnableTranslationModal onClose={vi.fn()} />)
    expect(screen.getByText('BETA')).toBeInTheDocument()
    expect(screen.getByText(/experimental/i)).toBeInTheDocument()
  })

  it('Enable button is disabled until checkbox is checked', () => {
    render(<EnableTranslationModal onClose={vi.fn()} />)
    const enableBtn = screen.getByRole('button', { name: /enable translation/i })
    expect(enableBtn).toBeDisabled()
    fireEvent.click(screen.getByRole('checkbox'))
    expect(enableBtn).not.toBeDisabled()
  })

  it('calls updateConfig with translation_enabled=true on confirm', () => {
    render(<EnableTranslationModal onClose={vi.fn()} />)
    fireEvent.click(screen.getByRole('checkbox'))
    fireEvent.click(screen.getByRole('button', { name: /enable translation/i }))
    expect(mockMutate).toHaveBeenCalledWith({ translation_enabled: 'true' }, expect.any(Object))
  })

  it('calls onClose when Cancel is clicked', () => {
    const onClose = vi.fn()
    render(<EnableTranslationModal onClose={onClose} />)
    fireEvent.click(screen.getByRole('button', { name: /^cancel$/i }))
    expect(onClose).toHaveBeenCalled()
  })
})
