import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { ProgressBar } from '@/components/shared/ProgressBar'

describe('ProgressBar', () => {
  it('renders progress percentage', () => {
    render(<ProgressBar value={50} max={100} />)
    expect(screen.getByText('50%')).toBeInTheDocument()
  })

  it('calculates percentage correctly', () => {
    render(<ProgressBar value={25} max={100} />)
    expect(screen.getByText('25%')).toBeInTheDocument()
  })

  it('handles zero max value', () => {
    render(<ProgressBar value={0} max={0} />)
    expect(screen.getByText('0%')).toBeInTheDocument()
  })

  it('hides label when showLabel is false', () => {
    const { container } = render(<ProgressBar value={50} max={100} showLabel={false} />)
    expect(container.querySelector('span')).toBeNull()
  })
})
