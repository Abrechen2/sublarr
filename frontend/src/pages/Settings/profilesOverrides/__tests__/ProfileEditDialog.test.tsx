import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { ProfileEditDialog } from '../ProfileEditDialog'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k: string, fb?: string) => fb ?? k }),
}))

describe('ProfileEditDialog', () => {
  it('renders Add mode with empty fields', () => {
    render(<ProfileEditDialog mode="add" onClose={() => {}} onSubmit={() => Promise.resolve()} />)
    expect(screen.getByRole('dialog')).toBeInTheDocument()
    expect(screen.getByLabelText(/name/i)).toHaveValue('')
  })

  it('Edit mode pre-fills name', () => {
    render(<ProfileEditDialog mode="edit" initialName="Anime DE" initialId={1}
                              onClose={() => {}} onSubmit={() => Promise.resolve()} />)
    expect(screen.getByLabelText(/name/i)).toHaveValue('Anime DE')
  })

  it('Delete mode shows confirm + impact count', () => {
    render(<ProfileEditDialog mode="delete" initialId={1} initialName="Anime DE"
                              impact={{ series_count: 3, movies_count: 1 }}
                              onClose={() => {}} onSubmit={() => Promise.resolve()} />)
    expect(screen.getByText(/3 series/i)).toBeInTheDocument()
    expect(screen.getByText(/1.*movie/i)).toBeInTheDocument()
  })

  it('Add submit calls onSubmit with name', async () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined)
    render(<ProfileEditDialog mode="add" onClose={() => {}} onSubmit={onSubmit} />)
    fireEvent.change(screen.getByLabelText(/name/i), { target: { value: 'Live Action' } })
    fireEvent.click(screen.getByRole('button', { name: /save/i }))
    await new Promise((r) => setTimeout(r, 0))
    expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({ name: 'Live Action' }))
  })
})
