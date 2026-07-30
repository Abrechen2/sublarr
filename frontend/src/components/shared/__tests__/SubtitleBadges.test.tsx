import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import {
  ResultFlagBadges,
  SourceBadge,
  SyncedBadge,
  TrustBadge,
} from '../SubtitleBadges'

describe('SubtitleBadges', () => {
  it('renders MT, HI and forced flags', () => {
    render(
      <ResultFlagBadges
        flags={{ machine_translated: true, mt_confidence: 87, hearing_impaired: true, forced: true }}
      />
    )
    expect(screen.getByText('MT 87%')).toBeInTheDocument()
    expect(screen.getByText('HI')).toBeInTheDocument()
    expect(screen.getByText('F')).toBeInTheDocument()
  })

  it('renders trust badge only for positive bonus', () => {
    const { container } = render(<TrustBadge bonus={0} />)
    expect(container.textContent).toBe('')
    render(<TrustBadge bonus={12.4} />)
    expect(screen.getByText('+12 Trust')).toBeInTheDocument()
  })

  it('renders nothing for default provider source', () => {
    const { container } = render(<SourceBadge source="provider" />)
    expect(container.textContent).toBe('')
  })

  it('renders a badge for whisper source', () => {
    const { container } = render(<SourceBadge source="whisper" />)
    expect(container.textContent).not.toBe('')
  })

  it('renders synced badge', () => {
    const { container } = render(<SyncedBadge engine="ffsubsync" />)
    expect(container.textContent).toContain('⇄')
  })
})
