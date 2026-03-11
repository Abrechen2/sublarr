import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { StatusBadge } from '@/components/shared/StatusBadge'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key.split('.').pop() ?? key,
    i18n: { language: 'en', changeLanguage: vi.fn() },
  }),
}))

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

  it('renders an SVG icon for completed status', () => {
    const { container } = render(<StatusBadge status="completed" />)
    expect(container.querySelector('svg')).toBeInTheDocument()
  })

  it('renders an SVG icon for failed status', () => {
    const { container } = render(<StatusBadge status="failed" />)
    expect(container.querySelector('svg')).toBeInTheDocument()
  })

  it('renders an SVG icon for running status', () => {
    const { container } = render(<StatusBadge status="running" />)
    expect(container.querySelector('svg')).toBeInTheDocument()
  })

  it('renders an SVG icon for queued status', () => {
    const { container } = render(<StatusBadge status="queued" />)
    expect(container.querySelector('svg')).toBeInTheDocument()
  })

  it('renders an SVG icon for wanted status', () => {
    const { container } = render(<StatusBadge status="wanted" />)
    expect(container.querySelector('svg')).toBeInTheDocument()
  })
})
