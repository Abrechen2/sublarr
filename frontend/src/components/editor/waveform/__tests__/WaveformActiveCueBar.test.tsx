import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { WaveformActiveCueBar } from '../WaveformActiveCueBar'

describe('WaveformActiveCueBar', () => {
  it('renders cue index, timing, and text when a cue is selected', () => {
    render(
      <WaveformActiveCueBar
        cueIndex={5}
        cueCount={471}
        startSec={83.4}
        endSec={85.8}
        text="Hallo, das ist Cue eins."
      />,
    )
    expect(screen.getByText(/Cue 6\s*\/\s*471/)).toBeInTheDocument()
    expect(screen.getByText(/00:01:23\.400/)).toBeInTheDocument()
    expect(screen.getByText(/00:01:25\.800/)).toBeInTheDocument()
    expect(screen.getByText('Hallo, das ist Cue eins.')).toBeInTheDocument()
  })

  it('renders 1-based cue index even when cueIndex is 0', () => {
    render(
      <WaveformActiveCueBar cueIndex={0} cueCount={10} startSec={0} endSec={1} text="first" />,
    )
    expect(screen.getByText(/Cue 1\s*\/\s*10/)).toBeInTheDocument()
  })

  it('formats sub-second precision to milliseconds (3 decimal places)', () => {
    render(
      <WaveformActiveCueBar cueIndex={0} cueCount={1} startSec={0.5} endSec={1.234} text="x" />,
    )
    expect(screen.getByText(/00:00:00\.500/)).toBeInTheDocument()
    expect(screen.getByText(/00:00:01\.234/)).toBeInTheDocument()
  })

  it('strips ASS override tags from the displayed text', () => {
    render(
      <WaveformActiveCueBar
        cueIndex={0}
        cueCount={1}
        startSec={0}
        endSec={1}
        text="{\\an8}Top text"
      />,
    )
    expect(screen.getByText('Top text')).toBeInTheDocument()
    expect(screen.queryByText(/\\an8/)).not.toBeInTheDocument()
  })

  it('renders multiple lines when ASS \\N breaks are present', () => {
    const { container } = render(
      <WaveformActiveCueBar
        cueIndex={0}
        cueCount={1}
        startSec={0}
        endSec={1}
        text="Line one\\NLine two"
      />,
    )
    // Both lines must be rendered as separate text nodes
    const html = container.innerHTML
    expect(html).toContain('Line one')
    expect(html).toContain('Line two')
  })

  it('shows hint copy when no cue is selected', () => {
    render(<WaveformActiveCueBar cueIndex={null} cueCount={471} startSec={0} endSec={0} text="" />)
    expect(screen.getByText(/Wähle einen Cue|Select a cue/i)).toBeInTheDocument()
  })

  it('renders for the empty-cues case (cueCount=0) with a sensible label', () => {
    render(<WaveformActiveCueBar cueIndex={null} cueCount={0} startSec={0} endSec={0} text="" />)
    expect(screen.getByText(/keine Cues|no cues/i)).toBeInTheDocument()
  })

  it('shows a CPS reading-speed badge for the selected cue', () => {
    // "Hallo Welt" = 10 chars over 2 s = 5.0 CPS
    render(
      <WaveformActiveCueBar
        cueIndex={0}
        cueCount={1}
        startSec={0}
        endSec={2}
        text="Hallo Welt"
      />,
    )
    expect(screen.getByText(/5\.0 CPS/)).toBeInTheDocument()
  })

  it('flags an unreadable (too fast) cue in the CPS badge title', () => {
    // 40 chars over 1 s = 40 CPS → tooFast
    render(
      <WaveformActiveCueBar
        cueIndex={0}
        cueCount={1}
        startSec={0}
        endSec={1}
        text={'x'.repeat(40)}
      />,
    )
    const badge = screen.getByText(/40\.0 CPS/)
    expect(badge).toBeInTheDocument()
    expect(badge.getAttribute('title')).toMatch(/too fast/i)
  })
})
