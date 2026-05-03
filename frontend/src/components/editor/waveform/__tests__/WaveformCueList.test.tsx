import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'

import { WaveformCueList, type CueListRow } from '../WaveformCueList'

beforeEach(() => {
  Element.prototype.scrollIntoView = vi.fn()
})

const sampleCues: CueListRow[] = [
  { start: 5.0, end: 7.5, text: 'First cue text' },
  { start: 7.6, end: 9.5, text: 'Second cue text' },
  { start: 12.0, end: 14.0, text: 'Third cue, much later' },
]

describe('WaveformCueList — read-only first pass', () => {
  it('renders one row per cue with 1-based index, timecodes and text', () => {
    render(
      <WaveformCueList
        cues={sampleCues}
        selectedCueIdx={null}
        onSelectCue={() => {}}
      />,
    )
    expect(screen.getByText('1')).toBeInTheDocument()
    expect(screen.getByText('2')).toBeInTheDocument()
    expect(screen.getByText('3')).toBeInTheDocument()
    expect(screen.getByText('First cue text')).toBeInTheDocument()
    expect(screen.getByText('Second cue text')).toBeInTheDocument()
    expect(screen.getByText('Third cue, much later')).toBeInTheDocument()
    expect(screen.getAllByRole('option')).toHaveLength(3)
    expect(screen.getByText('00:00:05.000')).toBeInTheDocument()
    expect(screen.getByText(/00:00:07\.500/)).toBeInTheDocument()
    expect(screen.getByText(/00:00:14\.000/)).toBeInTheDocument()
  })

  it('highlights the row whose index matches selectedCueIdx', () => {
    render(
      <WaveformCueList
        cues={sampleCues}
        selectedCueIdx={1}
        onSelectCue={() => {}}
      />,
    )
    const activeRow = screen.getByRole('option', { selected: true })
    expect(activeRow).toHaveTextContent('Second cue text')
  })

  it('emits onSelectCue with idx + "list" origin when a row is clicked', () => {
    const handler = vi.fn()
    render(
      <WaveformCueList
        cues={sampleCues}
        selectedCueIdx={null}
        onSelectCue={handler}
      />,
    )
    fireEvent.click(screen.getByText('Third cue, much later').closest('[role="option"]')!)
    expect(handler).toHaveBeenCalledWith(2, 'list')
  })

  it('strips ASS override tags from displayed text', () => {
    render(
      <WaveformCueList
        cues={[{ start: 0, end: 1, text: '{\\an8}{\\fad(150,150)}Top text' }]}
        selectedCueIdx={null}
        onSelectCue={() => {}}
      />,
    )
    expect(screen.getByText('Top text')).toBeInTheDocument()
    expect(screen.queryByText(/\\an8|\\fad/)).not.toBeInTheDocument()
  })

  it('renders an N-line text when the source has explicit \\N breaks', () => {
    render(
      <WaveformCueList
        cues={[{ start: 0, end: 1, text: 'Line one\\NLine two' }]}
        selectedCueIdx={null}
        onSelectCue={() => {}}
      />,
    )
    expect(screen.getByText('Line one')).toBeInTheDocument()
    expect(screen.getByText('Line two')).toBeInTheDocument()
  })

  it('marks a tight inter-cue gap (< 80 ms) with a "gap" indicator dot', () => {
    render(
      <WaveformCueList
        cues={[
          { start: 0, end: 1.0, text: 'A' },
          { start: 1.04, end: 2.0, text: 'B' }, // 40 ms gap to A → tight
        ]}
        selectedCueIdx={null}
        onSelectCue={() => {}}
      />,
    )
    expect(screen.getByTestId('quality-dot-gap-0')).toBeInTheDocument()
  })

  it('marks an overlap with the next cue with an "overlap" indicator dot', () => {
    render(
      <WaveformCueList
        cues={[
          { start: 0, end: 2.0, text: 'A' },
          { start: 1.5, end: 3.0, text: 'B' }, // overlap on A
        ]}
        selectedCueIdx={null}
        onSelectCue={() => {}}
      />,
    )
    expect(screen.getByTestId('quality-dot-overlap-0')).toBeInTheDocument()
  })

  it('auto-scrolls the active row into view when selection origin is NOT "list"', () => {
    const { rerender } = render(
      <WaveformCueList
        cues={sampleCues}
        selectedCueIdx={0}
        selectionOrigin="wave"
        onSelectCue={() => {}}
      />,
    )
    rerender(
      <WaveformCueList
        cues={sampleCues}
        selectedCueIdx={2}
        selectionOrigin="wave"
        onSelectCue={() => {}}
      />,
    )
    expect(Element.prototype.scrollIntoView).toHaveBeenCalledWith(
      expect.objectContaining({ block: 'center' }),
    )
  })

  it('does NOT auto-scroll when the user just clicked a row themselves (origin="list")', () => {
    const { rerender } = render(
      <WaveformCueList
        cues={sampleCues}
        selectedCueIdx={0}
        selectionOrigin="wave"
        onSelectCue={() => {}}
      />,
    )
    ;(Element.prototype.scrollIntoView as ReturnType<typeof vi.fn>).mockClear()
    rerender(
      <WaveformCueList
        cues={sampleCues}
        selectedCueIdx={2}
        selectionOrigin="list"
        onSelectCue={() => {}}
      />,
    )
    expect(Element.prototype.scrollIntoView).not.toHaveBeenCalled()
  })

  it('hides the row container entirely when collapsed=true', () => {
    const { container, rerender } = render(
      <WaveformCueList
        cues={sampleCues}
        selectedCueIdx={null}
        collapsed={false}
        onSelectCue={() => {}}
      />,
    )
    expect(container.querySelectorAll('[role="option"]').length).toBe(3)
    rerender(
      <WaveformCueList
        cues={sampleCues}
        selectedCueIdx={null}
        collapsed={true}
        onSelectCue={() => {}}
      />,
    )
    expect(container.querySelectorAll('[role="option"]').length).toBe(0)
  })

  it('renders an empty-state message when there are no cues', () => {
    render(
      <WaveformCueList cues={[]} selectedCueIdx={null} onSelectCue={() => {}} />,
    )
    expect(screen.getByText(/keine Cues|no cues/i)).toBeInTheDocument()
  })
})
