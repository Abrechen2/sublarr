import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ScoreBreakdown } from '../components/shared/ScoreBreakdown'

const mockBreakdown = { series: 180, season: 30, episode: 30, format_bonus: 50 }

describe('ScoreBreakdown', () => {
  it('renders the total score', () => {
    render(<ScoreBreakdown score={290} breakdown={mockBreakdown} />)
    expect(screen.getByText('290')).toBeInTheDocument()
  })

  it('shows breakdown on hover', async () => {
    const user = userEvent.setup()
    render(<ScoreBreakdown score={290} breakdown={mockBreakdown} />)
    await user.hover(screen.getByText('290'))
    expect(screen.getByText(/series/i)).toBeInTheDocument()
    expect(screen.getByText(/\+180/)).toBeInTheDocument()
  })

  it('uses success color class for score >= 300', () => {
    const { container } = render(<ScoreBreakdown score={310} breakdown={mockBreakdown} />)
    expect(container.innerHTML).toContain('success')
  })

  it('uses warning color class for score 200-299', () => {
    const { container } = render(<ScoreBreakdown score={240} breakdown={mockBreakdown} />)
    expect(container.innerHTML).toContain('warning')
  })

  it('shows "No breakdown available" for empty breakdown', async () => {
    const user = userEvent.setup()
    render(<ScoreBreakdown score={0} breakdown={{}} />)
    await user.hover(screen.getByText('0'))
    expect(screen.getByText(/no breakdown/i)).toBeInTheDocument()
  })
})
