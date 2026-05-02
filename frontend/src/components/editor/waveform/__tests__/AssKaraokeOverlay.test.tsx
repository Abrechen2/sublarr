/**
 * Tests for `AssKaraokeOverlay` (Plan B8 Task 9 Step 2).
 *
 * The overlay renders one `<g data-syllable-index>` group per syllable
 * positioned at percent-of-duration. The math under test:
 *   leftPct = (cueStartSec + syllable.start) / durationSec * 100
 * because the overlay spans the full waveform width and uses absolute
 * timeline positions, not cue-relative ones.
 */

import { describe, expect, it } from 'vitest'
import { render } from '@testing-library/react'

import { AssKaraokeOverlay } from '../AssKaraokeOverlay'
import type { SubtitleCueSyllable } from '@/types/system'

const TWO_SYLLABLES: SubtitleCueSyllable[] = [
  { text: 'Hel', start: 0, end: 0.5 },
  { text: 'lo', start: 0.5, end: 1.1 },
]

describe('AssKaraokeOverlay', () => {
  it('renders one <g> marker per syllable', () => {
    const { container } = render(
      <AssKaraokeOverlay syllables={TWO_SYLLABLES} cueStartSec={0} durationSec={10} />,
    )
    const groups = container.querySelectorAll('g[data-syllable-index]')
    expect(groups).toHaveLength(2)
  })

  it('positions ticks using absolute timeline percent, not cue-relative', () => {
    // cueStartSec=2, durationSec=10 → first syllable absStart=2, leftPct=20
    const { container } = render(
      <AssKaraokeOverlay syllables={TWO_SYLLABLES} cueStartSec={2} durationSec={10} />,
    )
    const lines = container.querySelectorAll('line')
    expect(lines[0].getAttribute('x1')).toBe('20%')
    // second syllable absStart = 2 + 0.5 = 2.5 → 25%
    expect(lines[1].getAttribute('x1')).toBe('25%')
  })

  it('renders nothing when the syllable list is empty', () => {
    const { container } = render(
      <AssKaraokeOverlay syllables={[]} cueStartSec={0} durationSec={10} />,
    )
    expect(container).toBeEmptyDOMElement()
  })

  it('renders nothing when duration is zero or invalid', () => {
    const { container: zeroDur } = render(
      <AssKaraokeOverlay syllables={TWO_SYLLABLES} cueStartSec={0} durationSec={0} />,
    )
    expect(zeroDur).toBeEmptyDOMElement()

    const { container: nanDur } = render(
      <AssKaraokeOverlay syllables={TWO_SYLLABLES} cueStartSec={0} durationSec={NaN} />,
    )
    expect(nanDur).toBeEmptyDOMElement()
  })

  it('omits text labels by default', () => {
    const { container } = render(
      <AssKaraokeOverlay syllables={TWO_SYLLABLES} cueStartSec={0} durationSec={10} />,
    )
    expect(container.querySelectorAll('text')).toHaveLength(0)
  })

  it('renders text labels when showLabels is true', () => {
    const { container } = render(
      <AssKaraokeOverlay
        syllables={TWO_SYLLABLES}
        cueStartSec={0}
        durationSec={10}
        showLabels
      />,
    )
    const labels = container.querySelectorAll('text')
    expect(labels).toHaveLength(2)
    expect(labels[0].textContent).toBe('Hel')
    expect(labels[1].textContent).toBe('lo')
  })

  it('skips syllables that fall outside the duration window', () => {
    // durationSec=1, second syllable absStart=1.5 → out of range
    const syllables: SubtitleCueSyllable[] = [
      { text: 'A', start: 0, end: 0.4 },
      { text: 'B', start: 1.5, end: 2.0 },
    ]
    const { container } = render(
      <AssKaraokeOverlay syllables={syllables} cueStartSec={0} durationSec={1} />,
    )
    expect(container.querySelectorAll('g[data-syllable-index]')).toHaveLength(1)
  })
})
