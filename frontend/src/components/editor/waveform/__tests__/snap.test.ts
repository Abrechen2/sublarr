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

  // ─── B8 follow-up: snap-to-scene ─────────────────────────────────────

  it('snaps to a scene-cut within tolerance', () => {
    const r = snap(1000, {
      keyframesMs: [],
      neighborsMs: [],
      scenesMs: [1100],
      minGapMs: 0,
      sceneToleranceMs: 200,
    })
    expect(r.value).toBe(1100)
    expect(r.snappedTo).toBe('scene')
  })

  it('does not snap to a scene-cut outside tolerance', () => {
    const r = snap(1000, {
      keyframesMs: [],
      neighborsMs: [],
      scenesMs: [1500],
      minGapMs: 0,
      sceneToleranceMs: 200,
    })
    expect(r.value).toBe(1000)
    expect(r.snappedTo).toBe('none')
  })

  it('prefers a closer scene over a farther keyframe within tolerance', () => {
    const r = snap(1000, {
      keyframesMs: [880], // 120 ms away
      neighborsMs: [],
      scenesMs: [1020], // 20 ms away — closer
      minGapMs: 0,
      keyframeToleranceMs: 150,
      sceneToleranceMs: 200,
    })
    expect(r.value).toBe(1020)
    expect(r.snappedTo).toBe('scene')
  })

  it('breaks tie keyframe-vs-scene in favour of the keyframe', () => {
    const r = snap(1000, {
      keyframesMs: [950], // 50 ms away
      neighborsMs: [],
      scenesMs: [1050], // 50 ms away
      minGapMs: 0,
      keyframeToleranceMs: 80,
      sceneToleranceMs: 80,
    })
    expect(r.value).toBe(950)
    expect(r.snappedTo).toBe('keyframe')
  })

  it('breaks tie scene-vs-neighbor in favour of the scene', () => {
    const r = snap(1000, {
      keyframesMs: [],
      neighborsMs: [950],
      scenesMs: [1050],
      minGapMs: 0,
      neighborToleranceMs: 80,
      sceneToleranceMs: 80,
    })
    expect(r.value).toBe(1050)
    expect(r.snappedTo).toBe('scene')
  })
})

describe('snap() — speech edges (VAD)', () => {
  it('snaps to a speech edge within tolerance', () => {
    const r = snap(1000, {
      keyframesMs: [],
      neighborsMs: [],
      speechEdgesMs: [1080],
      minGapMs: 0,
      speechToleranceMs: 120,
    })
    expect(r.value).toBe(1080)
    expect(r.snappedTo).toBe('speech')
  })

  it('does not snap to a speech edge outside tolerance', () => {
    const r = snap(1000, {
      keyframesMs: [],
      neighborsMs: [],
      speechEdgesMs: [1200],
      minGapMs: 0,
      speechToleranceMs: 120,
    })
    expect(r.snappedTo).toBe('none')
    expect(r.value).toBe(1000)
  })

  it('is inert when speechEdgesMs is omitted (backward compatible)', () => {
    const r = snap(1000, {
      keyframesMs: [950],
      neighborsMs: [],
      minGapMs: 0,
      keyframeToleranceMs: 150,
    })
    expect(r.snappedTo).toBe('keyframe')
  })

  it('prefers a speech edge over an equidistant scene cut', () => {
    // both 40 ms away; speech(1) beats scene(2) on the priority tie-break
    const r = snap(1000, {
      keyframesMs: [],
      neighborsMs: [],
      speechEdgesMs: [1040],
      scenesMs: [960],
      minGapMs: 0,
      speechToleranceMs: 120,
      sceneToleranceMs: 200,
    })
    expect(r.snappedTo).toBe('speech')
    expect(r.value).toBe(1040)
  })

  it('lets a keyframe still win over an equidistant speech edge', () => {
    const r = snap(1000, {
      keyframesMs: [1040],
      neighborsMs: [],
      speechEdgesMs: [960],
      minGapMs: 0,
      keyframeToleranceMs: 150,
      speechToleranceMs: 120,
    })
    expect(r.snappedTo).toBe('keyframe')
    expect(r.value).toBe(1040)
  })

  it('takes the strictly closer speech edge over a farther keyframe', () => {
    const r = snap(1000, {
      keyframesMs: [1130], // 130 ms away
      neighborsMs: [],
      speechEdgesMs: [1030], // 30 ms away — closer wins regardless of priority
      minGapMs: 0,
      keyframeToleranceMs: 150,
      speechToleranceMs: 120,
    })
    expect(r.snappedTo).toBe('speech')
    expect(r.value).toBe(1030)
  })
})
