import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { StatusBadge } from '@/components/shared/StatusBadge'

describe('StatusBadge', () => {
  it('renders status text', () => {
    render(<StatusBadge status="completed" />)
    expect(screen.getByText('completed')).toBeInTheDocument()
  })

  it('renders different statuses', () => {
    const { rerender } = render(<StatusBadge status="running" />)
    expect(screen.getByText('running')).toBeInTheDocument()

    rerender(<StatusBadge status="failed" />)
    expect(screen.getByText('failed')).toBeInTheDocument()
  })

  it('applies custom className', () => {
    const { container } = render(<StatusBadge status="completed" className="custom-class" />)
    expect(container.firstChild).toHaveClass('custom-class')
  })
})
