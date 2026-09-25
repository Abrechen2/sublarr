import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { TRACK_REASONS, TrackVerdictList } from '../TrackVerdictList'
import '@/i18n'

describe('TrackVerdictList', () => {
  it('labels every reason code the backend can send', () => {
    for (const reason of TRACK_REASONS) {
      render(<TrackVerdictList verdicts={[{ index: 1, sub_index: 0, language: 'en', fmt: 'ass', kind: 'full', keep: reason.startsWith('kept'), reason }]} />)
    }
    expect(screen.queryByText(/cleanup\.reason\./)).toBeNull()
  })

  it('marks stripped tracks', () => {
    render(<TrackVerdictList verdicts={[{ index: 6, sub_index: 2, language: 'en', fmt: 'image', kind: 'sdh', keep: false, reason: 'stripped_variant' }]} />)
    expect(screen.getByText('EN')).toBeInTheDocument()
    expect(screen.getByTestId('verdict-6').dataset.keep).toBe('false')
  })
})
