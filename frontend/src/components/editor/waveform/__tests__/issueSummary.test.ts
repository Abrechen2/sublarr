import { describe, it, expect } from 'vitest'

import { summarizeIssues, type IssueSummaryCue } from '../issueSummary'

describe('summarizeIssues', () => {
  it('returns an all-zero summary for a clean subtitle', () => {
    const cues: IssueSummaryCue[] = [
      { start: 0, end: 3, text: 'Comfortable line one' },
      { start: 4, end: 7, text: 'Comfortable line two' },
    ]
    const s = summarizeIssues(cues)
    expect(s.total).toBe(0)
    expect(s.firstIssueSec).toBeNull()
  })

  it('counts an overlap between adjacent cues', () => {
    const cues: IssueSummaryCue[] = [
      { start: 0, end: 2, text: 'A' },
      { start: 1.5, end: 3, text: 'B' }, // overlaps A
    ]
    const s = summarizeIssues(cues)
    expect(s.overlaps).toBe(1)
    expect(s.total).toBe(1)
    expect(s.firstIssueSec).toBeCloseTo(1.5) // overlap interval starts at next.start
  })

  it('counts a tight gap under the tolerance', () => {
    const cues: IssueSummaryCue[] = [
      { start: 0, end: 1.0, text: 'A' },
      { start: 1.04, end: 2.0, text: 'B' }, // 40 ms gap
    ]
    const s = summarizeIssues(cues)
    expect(s.tightGaps).toBe(1)
    expect(s.total).toBe(1)
  })

  it('counts a too-fast cue', () => {
    const cues: IssueSummaryCue[] = [{ start: 0, end: 1, text: 'x'.repeat(40) }]
    const s = summarizeIssues(cues)
    expect(s.tooFast).toBe(1)
    expect(s.total).toBe(1)
    expect(s.firstIssueSec).toBe(0)
  })

  it('counts a too-short cue that is not too fast', () => {
    // 2 chars over 0.3 s → not too fast (CPS ~6.7) but below MIN_DISPLAY_SEC
    const cues: IssueSummaryCue[] = [{ start: 0, end: 0.3, text: 'hi' }]
    const s = summarizeIssues(cues)
    expect(s.tooShort).toBe(1)
    expect(s.tooFast).toBe(0)
    expect(s.total).toBe(1)
  })

  it('does not double-count a cue that is both too fast and too short', () => {
    // 40 chars over 0.3 s → too fast AND too short → counted once as tooFast
    const cues: IssueSummaryCue[] = [{ start: 0, end: 0.3, text: 'x'.repeat(40) }]
    const s = summarizeIssues(cues)
    expect(s.tooFast).toBe(1)
    expect(s.tooShort).toBe(0)
    expect(s.total).toBe(1)
  })

  it('aggregates mixed issues and reports the earliest one', () => {
    const cues: IssueSummaryCue[] = [
      { start: 0, end: 3, text: 'Fine line here now' }, // ok
      { start: 3.5, end: 5, text: 'A' }, // ok — 0.5 s gap from previous
      { start: 4.9, end: 6, text: 'B' }, // overlap with previous at 4.9
      { start: 10, end: 11, text: 'x'.repeat(40) }, // too fast
    ]
    const s = summarizeIssues(cues)
    expect(s.overlaps).toBe(1)
    expect(s.tooFast).toBe(1)
    expect(s.total).toBe(2)
    expect(s.firstIssueSec).toBeCloseTo(4.9)
  })

  it('handles an empty cue list', () => {
    const s = summarizeIssues([])
    expect(s.total).toBe(0)
    expect(s.firstIssueSec).toBeNull()
  })
})
