/**
 * Pure-function tests for `snap()` (Plan B8 Task 4).
 *
 * The snap helper is the single source of truth for "where should this
 * timestamp land on the waveform" — it's used by both drag-end commits
 * (Task 3) and the L/R click-map (Task 4 Step 1). Testing it as a pure
 * function avoids touching WaveSurfer entirely.
 */

import { describe, expect, it } from 'vitest'
import { snap } from '../snap'

describe('snap()', () => {
  it('returns identity when there are no targets', () => {
    const r = snap(1000, {
      keyframesMs: [],
      neighborsMs: [],
      minGapMs: 0,
    })
    expect(r.value).toBe(1000)
    expect(r.snappedTo).toBe('none')
  })

  it('snaps to a keyframe within tolerance', () => {
    const r = snap(1000, {
      keyframesMs: [950],
      neighborsMs: [],
      minGapMs: 0,
      keyframeToleranceMs: 150,
    })
    expect(r.value).toBe(950)
    expect(r.snappedTo).toBe('keyframe')
  })

  it('does not snap when keyframe is outside tolerance', () => {
    const r = snap(1000, {
      keyframesMs: [800],
      neighborsMs: [],
      minGapMs: 0,
      keyframeToleranceMs: 150,
    })
    expect(r.value).toBe(1000)
    expect(r.snappedTo).toBe('none')
  })

  it('snaps to a neighbor within tolerance', () => {
    const r = snap(1000, {
      keyframesMs: [],
      neighborsMs: [1050],
      minGapMs: 0,
      neighborToleranceMs: 80,
    })
    expect(r.value).toBe(1050)
    expect(r.snappedTo).toBe('neighbor')
  })

  it('prefers the closer target when both keyframe and neighbor are in range', () => {
    const r = snap(1000, {
      keyframesMs: [900], // 100 ms away
      neighborsMs: [970], // 30 ms away — closer
      minGapMs: 0,
      keyframeToleranceMs: 150,
      neighborToleranceMs: 80,
    })
    expect(r.value).toBe(970)
    expect(r.snappedTo).toBe('neighbor')
  })

  it('breaks ties in favour of the keyframe (Aegisub convention)', () => {
    const r = snap(1000, {
      keyframesMs: [950], // 50 ms away
      neighborsMs: [1050], // 50 ms away
      minGapMs: 0,
      keyframeToleranceMs: 80,
      neighborToleranceMs: 80,
    })
    expect(r.value).toBe(950)
    expect(r.snappedTo).toBe('keyframe')
  })

  it('returns identity (and snappedTo=none) when both are out of range', () => {
    const r = snap(1000, {
      keyframesMs: [500],
      neighborsMs: [1500],
      minGapMs: 0,
      keyframeToleranceMs: 150,
      neighborToleranceMs: 80,
    })
    expect(r.value).toBe(1000)
    expect(r.snappedTo).toBe('none')
  })

  it('pushes away from a neighbor when the snap would violate min-gap', () => {
    // Snap candidate is 1050 (within neighbor tolerance), but min-gap is 80
    // and the nearest neighbor is at 1080 -> result would be 30ms apart.
    // Pushed away to keep 80ms gap: 1080 - 80 = 1000.
    const r = snap(1050, {
      keyframesMs: [],
      neighborsMs: [1080],
      minGapMs: 80,
      neighborToleranceMs: 80,
    })
    expect(r.value).toBe(1000)
    // Even though we ended up adjusting, the snap origin was the neighbor
    expect(r.snappedTo).toBe('neighbor')
  })

  it('keeps an exact-match keyframe identity', () => {
    const r = snap(1000, {
      keyframesMs: [1000],
      neighborsMs: [],
      minGapMs: 0,
      keyframeToleranceMs: 150,
    })
    expect(r.value).toBe(1000)
    expect(r.snappedTo).toBe('keyframe')
  })
})
