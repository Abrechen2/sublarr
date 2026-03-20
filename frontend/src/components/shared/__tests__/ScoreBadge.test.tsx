import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { ScoreBadge } from '../ScoreBadge'

describe('ScoreBadge', () => {
  it('shows "Missing" for null score', () => {
    const { container } = render(<ScoreBadge score={null} />)
    expect(screen.getByText('Missing')).toBeInTheDocument()
    expect(container.innerHTML).toContain('error')
  })

  it('uses success styling for score >= 70', () => {
    const { container } = render(<ScoreBadge score={85} />)
    expect(screen.getByText('85')).toBeInTheDocument()
    expect(container.innerHTML).toContain('success')
  })

  it('uses accent styling for score 50-69', () => {
    const { container } = render(<ScoreBadge score={60} />)
    expect(screen.getByText('60')).toBeInTheDocument()
    expect(container.innerHTML).toContain('accent')
  })

  it('uses warning styling for score < 50', () => {
    const { container } = render(<ScoreBadge score={30} />)
    expect(screen.getByText('30')).toBeInTheDocument()
    expect(container.innerHTML).toContain('warning')
  })

  it('applies custom className', () => {
    const { container } = render(<ScoreBadge score={70} className="custom" />)
    expect(container.firstChild).toHaveClass('custom')
  })
})
