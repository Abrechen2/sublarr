/**
 * Unit tests for `planSafeDefectFixes` — the pure planner behind the
 * one-click "fix safe defects" batch.
 */

import { describe, expect, it } from 'vitest'

import { planSafeDefectFixes, type FixableCue } from '../fixSafeDefects'
import { detectGapsAndOverlaps } from '../gapOverlap'

/** Short readable text — never trips the CPS guard at ≥0.7 s. */
const TXT = 'Hallo!'

function cue(start: number, end: number, text = TXT): FixableCue {
  return { start, end, text }
}

/** Apply fixes to a copy of the cue list. */
function applied(cues: FixableCue[], fixes = planSafeDefectFixes(cues)): FixableCue[] {
  const out = cues.map((c) => ({ ...c }))
  for (const f of fixes) {
    out[f.cueIndex].start = f.after.start
    out[f.cueIndex].end = f.after.end
  }
  return out
}

describe('planSafeDefectFixes', () => {
  it('returns no fixes for a clean file', () => {
    const cues = [cue(0, 1.5), cue(2, 3.5), cue(4, 5.5)]
    expect(planSafeDefectFixes(cues)).toEqual([])
  })

  it('trims the earlier cue of a small overlap to the target gap', () => {
    const cues = [cue(0, 2.05), cue(2, 4)]
    const fixes = planSafeDefectFixes(cues)

    expect(fixes).toHaveLength(1)
    expect(fixes[0]).toMatchObject({ cueIndex: 0, kind: 'overlap' })
    expect(fixes[0].after.end).toBeCloseTo(2 - 0.12, 5)
    // The batch fully resolves the defect set.
    const after = applied(cues, fixes)
    const det = detectGapsAndOverlaps(after.map((c, i) => ({ id: String(i), ...c })))
    expect(det.overlaps).toHaveLength(0)
    expect(det.tightGaps).toHaveLength(0)
  })

  it('widens a tight gap', () => {
    const cues = [cue(0, 1.98), cue(2, 4)]
    const fixes = planSafeDefectFixes(cues)

    expect(fixes).toHaveLength(1)
    expect(fixes[0]).toMatchObject({ cueIndex: 0, kind: 'tightGap' })
    expect(fixes[0].after.end).toBeCloseTo(1.88, 5)
  })

  it('skips an overlap fix that would make the earlier cue too short', () => {
    // Cue 0 is only 0.75 s; trimming 0.17 s would drop it below 0.7 s.
    const cues = [cue(0, 0.75), cue(0.7, 2)]
    expect(planSafeDefectFixes(cues)).toEqual([])
  })

  it('skips an overlap fix that would push CPS into too-fast', () => {
    // Long text over 1.5 s ⇒ trimming to ~0.98 s would exceed 21 CPS.
    const longText = 'Das ist ein wirklich sehr langer Beispielsatz!' // 46 chars
    const cues = [cue(0, 1.6, longText), cue(1.5, 3)]
    expect(planSafeDefectFixes(cues)).toEqual([])
  })

  it('never touches layered/contained ASS cues (signs, karaoke)', () => {
    // Same start (layered) and full containment.
    const layered = [cue(0, 2), cue(0, 5)]
    expect(planSafeDefectFixes(layered)).toEqual([])
    const contained = [cue(0, 5), cue(1, 3)]
    expect(planSafeDefectFixes(contained)).toEqual([])
  })

  it('extends a too-short cue to the minimum display window', () => {
    const cues = [cue(0, 0.3), cue(5, 6)]
    const fixes = planSafeDefectFixes(cues)

    expect(fixes).toHaveLength(1)
    expect(fixes[0]).toMatchObject({ cueIndex: 0, kind: 'tooShort' })
    expect(fixes[0].after.end).toBeCloseTo(0.7, 5)
  })

  it('skips a too-short extension when the next cue is in the way', () => {
    const cues = [cue(0, 0.3), cue(0.5, 2)]
    const fixes = planSafeDefectFixes(cues)
    expect(fixes.filter((f) => f.kind === 'tooShort')).toEqual([])
  })

  it('ignores too-short cues without text', () => {
    const cues = [cue(0, 0.2, '   '), cue(5, 6)]
    expect(planSafeDefectFixes(cues)).toEqual([])
  })

  it('combines independent fixes of different kinds in one batch', () => {
    // Cue 0 gets a too-short extension; cue 1 overlaps cue 2 and gets an
    // overlap trim. Both land in the same plan, sorted by cue index.
    const cues = [cue(0, 0.4), cue(5, 7.05, TXT), cue(7, 9)]
    const fixes = planSafeDefectFixes(cues)

    expect(fixes).toHaveLength(2)
    expect(fixes[0]).toMatchObject({ cueIndex: 0, kind: 'tooShort' })
    expect(fixes[1]).toMatchObject({ cueIndex: 1, kind: 'overlap' })
  })

  it('reports fixes against original indices for an unsorted input list', () => {
    const cues = [cue(5, 7.05), cue(0, 1), cue(7, 9)]
    const fixes = planSafeDefectFixes(cues)

    expect(fixes).toHaveLength(1)
    expect(fixes[0].cueIndex).toBe(0) // the 5–7.05 cue, index 0 in input order
    expect(fixes[0].kind).toBe('overlap')
  })

  it('applying the batch leaves no fixable defects behind (property)', () => {
    const cues = [
      cue(0, 1.02), // tight gap to next
      cue(1.1, 2.5),
      cue(2.4, 3.6), // overlapped by prev
      cue(4, 4.2), // too short
      cue(6, 7),
    ]
    const fixes = planSafeDefectFixes(cues)
    expect(fixes.length).toBeGreaterThan(0)

    const after = applied(cues, fixes)
    // Re-planning on the fixed list must be a no-op.
    expect(planSafeDefectFixes(after)).toEqual([])
  })
})
