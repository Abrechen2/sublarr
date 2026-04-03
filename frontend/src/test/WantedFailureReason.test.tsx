import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { FailureReasonRow, formatRetryCountdown } from '../pages/Wanted'

const FROZEN_NOW = new Date('2026-04-03T12:00:00.000Z').getTime()

describe('formatRetryCountdown', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.setSystemTime(FROZEN_NOW)
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('returns null for null input', () => {
    expect(formatRetryCountdown(null)).toBeNull()
  })

  it('returns null for past timestamps', () => {
    expect(formatRetryCountdown(new Date(FROZEN_NOW - 60_000).toISOString())).toBeNull()
  })

  it('formats hours and minutes', () => {
    const future = new Date(FROZEN_NOW + 3 * 60 * 60 * 1000 + 20 * 60 * 1000).toISOString()
    const result = formatRetryCountdown(future)
    expect(result).toMatch(/3h/)
    expect(result).toMatch(/20m/)
  })

  it('formats minutes only when < 1 hour', () => {
    const future = new Date(FROZEN_NOW + 25 * 60 * 1000).toISOString()
    const result = formatRetryCountdown(future)!
    expect(result).toMatch(/25m/)
    expect(result).not.toMatch(/0h/)
  })
})

describe('FailureReasonRow', () => {
  it('renders error message', () => {
    render(<FailureReasonRow error="All providers returned no results" retryAfter={null} searchCount={3} />)
    expect(screen.getByText(/All providers returned no results/)).toBeInTheDocument()
  })

  it('renders attempt count', () => {
    render(<FailureReasonRow error="Rate limit exceeded" retryAfter={null} searchCount={2} />)
    expect(screen.getByText(/2 attempt/)).toBeInTheDocument()
  })

  it('renders retry countdown when in future', () => {
    const future = new Date(Date.now() + 2 * 60 * 60 * 1000).toISOString()
    render(<FailureReasonRow error="No match" retryAfter={future} searchCount={1} />)
    expect(screen.getByText(/next retry/i)).toBeInTheDocument()
  })

  it('renders nothing when error is empty', () => {
    const { container } = render(<FailureReasonRow error="" retryAfter={null} searchCount={0} />)
    expect(container.firstChild).toBeNull()
  })
})
