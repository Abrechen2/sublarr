import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { TriStateToggle } from '../TriStateToggle'

describe('TriStateToggle', () => {
  it('renders three buttons with correct labels', () => {
    render(<TriStateToggle value={null} inheritLabel="Inherit (off)" onChange={() => {}} />)
    expect(screen.getByRole('button', { name: /inherit/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /^off$/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /^on$/i })).toBeInTheDocument()
  })

  it('marks the active state', () => {
    const { rerender } = render(<TriStateToggle value={null} onChange={() => {}} />)
    expect(screen.getByRole('button', { name: /inherit/i })).toHaveAttribute('aria-pressed', 'true')
    rerender(<TriStateToggle value={true} onChange={() => {}} />)
    expect(screen.getByRole('button', { name: /^on$/i })).toHaveAttribute('aria-pressed', 'true')
  })

  it('calls onChange with null when Inherit clicked', () => {
    const onChange = vi.fn()
    render(<TriStateToggle value={true} onChange={onChange} />)
    fireEvent.click(screen.getByRole('button', { name: /inherit/i }))
    expect(onChange).toHaveBeenCalledWith(null)
  })

  it('calls onChange with false when Off clicked', () => {
    const onChange = vi.fn()
    render(<TriStateToggle value={null} onChange={onChange} />)
    fireEvent.click(screen.getByRole('button', { name: /^off$/i }))
    expect(onChange).toHaveBeenCalledWith(false)
  })

  it('calls onChange with true when On clicked', () => {
    const onChange = vi.fn()
    render(<TriStateToggle value={null} onChange={onChange} />)
    fireEvent.click(screen.getByRole('button', { name: /^on$/i }))
    expect(onChange).toHaveBeenCalledWith(true)
  })
})
