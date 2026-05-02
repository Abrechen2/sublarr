import { describe, it, expect } from 'vitest'
import { detectGapsAndOverlaps, type CueRange } from '../gapOverlap'

const cue = (start: number, end: number, id: string = String(start)): CueRange => ({
  id,
  start,
  end,
})

describe('detectGapsAndOverlaps', () => {
  it('returns empty arrays for fewer than 2 cues', () => {
    expect(detectGapsAndOverlaps([])).toEqual({ overlaps: [], tightGaps: [] })
    expect(detectGapsAndOverlaps([cue(0, 1)])).toEqual({ overlaps: [], tightGaps: [] })
  })

  it('detects an overlap between two cues', () => {
    // cue A ends at 2.0, cue B starts at 1.5 → overlap [1.5, 2.0]
    const r = detectGapsAndOverlaps([cue(0, 2.0, 'A'), cue(1.5, 3.0, 'B')])
    expect(r.overlaps).toEqual([{ start: 1.5, end: 2.0, prevId: 'A', nextId: 'B' }])
    expect(r.tightGaps).toEqual([])
  })

  it('detects a tight gap (< 80 ms) between adjacent cues', () => {
    const r = detectGapsAndOverlaps([cue(0, 1.0, 'A'), cue(1.04, 2.0, 'B')])
    expect(r.tightGaps).toEqual([{ start: 1.0, end: 1.04, prevId: 'A', nextId: 'B' }])
    expect(r.overlaps).toEqual([])
  })

  it('does not flag a comfortable gap (>= 80 ms) by default', () => {
    const r = detectGapsAndOverlaps([cue(0, 1.0, 'A'), cue(1.1, 2.0, 'B')])
    expect(r.overlaps).toEqual([])
    expect(r.tightGaps).toEqual([])
  })

  it('flags zero-gap as tight (touching cues)', () => {
    // start == end of previous: classic snap-to-neighbour result; usually
    // wanted, but flagging it lets the editor verify it was intentional.
    const r = detectGapsAndOverlaps([cue(0, 1.0, 'A'), cue(1.0, 2.0, 'B')])
    expect(r.tightGaps).toEqual([{ start: 1.0, end: 1.0, prevId: 'A', nextId: 'B' }])
    expect(r.overlaps).toEqual([])
  })

  it('handles unsorted input (sorts internally before pairing)', () => {
    const r = detectGapsAndOverlaps([cue(2.0, 3.0, 'B'), cue(0, 2.5, 'A')])
    // Sorted: A(0–2.5), B(2.0–3.0) → overlap [2.0, 2.5]
    expect(r.overlaps).toEqual([{ start: 2.0, end: 2.5, prevId: 'A', nextId: 'B' }])
  })

  it('honours a custom gapToleranceMs', () => {
    // With 200 ms tolerance, a 100 ms gap counts as tight
    const r = detectGapsAndOverlaps(
      [cue(0, 1.0, 'A'), cue(1.1, 2.0, 'B')],
      { gapToleranceMs: 200 },
    )
    expect(r.tightGaps).toHaveLength(1)
    expect(r.tightGaps[0]).toEqual({ start: 1.0, end: 1.1, prevId: 'A', nextId: 'B' })
  })

  it('reports multiple defects in one pass', () => {
    const r = detectGapsAndOverlaps([
      cue(0, 1.0, 'A'),
      cue(0.9, 2.0, 'B'), // overlap A-B
      cue(2.05, 3.0, 'C'), // tight gap B-C
      cue(3.5, 4.0, 'D'), // comfortable gap C-D
    ])
    expect(r.overlaps).toEqual([{ start: 0.9, end: 1.0, prevId: 'A', nextId: 'B' }])
    expect(r.tightGaps).toEqual([{ start: 2.0, end: 2.05, prevId: 'B', nextId: 'C' }])
  })
})
