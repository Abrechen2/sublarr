import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { FilterChips } from '../FilterChips'

const chips = [
  { id: 'all', label: 'All' },
  { id: 'wanted', label: 'Wanted' },
  { id: 'found', label: 'Found' },
]

describe('FilterChips', () => {
  it('renders all chips', () => {
    render(<FilterChips chips={chips} activeChip="all" onChange={vi.fn()} />)
    expect(screen.getByText('All')).toBeInTheDocument()
    expect(screen.getByText('Wanted')).toBeInTheDocument()
    expect(screen.getByText('Found')).toBeInTheDocument()
  })

  it('highlights active chip with accent styling', () => {
    render(<FilterChips chips={chips} activeChip="wanted" onChange={vi.fn()} />)
    const wantedButton = screen.getByText('Wanted').closest('button')!
    expect(wantedButton.className).toContain('bg-[var(--accent-bg)]')
    expect(wantedButton.className).toContain('border-[var(--accent)]')
    const allButton = screen.getByText('All').closest('button')!
    expect(allButton.className).not.toContain('bg-[var(--accent-bg)]')
  })

  it('calls onChange when a chip is clicked', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(<FilterChips chips={chips} activeChip="all" onChange={onChange} />)
    await user.click(screen.getByText('Found'))
    expect(onChange).toHaveBeenCalledWith('found')
  })
})
