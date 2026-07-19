/**
 * Pure snap helper (Plan B8 Task 4 + scene-snap follow-up).
 *
 * Used by drag-end commits and the Aegisub-style L/R click-map to decide
 * where a cue boundary lands on the waveform. Three rules:
 *
 *   1. Snap to the closest in-range target across three pools — keyframes
 *      (default tol 150 ms), scene cuts (default tol 200 ms), and
 *      neighbor cue boundaries (default tol 80 ms). When two pools are
 *      tied on distance, preference order is: keyframe > scene > neighbor
 *      (Aegisub convention — keyframes are the strongest anchor; scene
 *      cuts are stronger than neighbor cues since they reflect the
 *      underlying media, not other subtitle edits).
 *   2. If no pool hits, return the input unchanged.
 *   3. After snapping, if the result would land closer than `minGapMs` to
 *      any neighbor cue, push the value away from that neighbor by exactly
 *      `minGapMs`. This guarantees no two cues end up overlapping after a
 *      snap-driven adjustment.
 *
 * All inputs are in milliseconds.
 */

export interface SnapOptions {
  /** Sorted (or unsorted — we don't assume order) keyframe targets in ms. */
  keyframesMs: number[]
  /** Sorted-or-not neighbor cue boundaries in ms. */
  neighborsMs: number[]
  /** Optional scene-cut boundaries in ms (Plan B8 follow-up). */
  scenesMs?: number[]
  /**
   * Optional VAD speech-segment edges (each segment's start AND end) in ms.
   * Lets a cue boundary snap to where dialogue actually begins/ends — the most
   * relevant anchor for audio-driven subtitle timing (Phase 2 follow-up).
   */
  speechEdgesMs?: number[]
  /** Minimum gap to any neighbor after snap. 0 disables the gap-check. */
  minGapMs: number
  /** Snap range around a keyframe; default 150 ms. */
  keyframeToleranceMs?: number
  /** Snap range around a neighbor; default 80 ms. */
  neighborToleranceMs?: number
  /** Snap range around a scene cut; default 200 ms. */
  sceneToleranceMs?: number
  /** Snap range around a speech edge; default 120 ms. */
  speechToleranceMs?: number
}

export interface SnapResult {
  value: number
  snappedTo: 'keyframe' | 'speech' | 'scene' | 'neighbor' | 'none'
}

const DEFAULT_KEYFRAME_TOLERANCE_MS = 150
const DEFAULT_NEIGHBOR_TOLERANCE_MS = 80
const DEFAULT_SCENE_TOLERANCE_MS = 200
const DEFAULT_SPEECH_TOLERANCE_MS = 120

/**
 * Find the closest target to `target` from `candidates`. Returns null if no
 * candidate is within `tolerance`.
 */
function closestWithin(
  target: number,
  candidates: readonly number[],
  tolerance: number,
): { value: number; distance: number } | null {
  let best: { value: number; distance: number } | null = null
  for (const c of candidates) {
    const d = Math.abs(c - target)
    if (d > tolerance) continue
    if (best === null || d < best.distance) best = { value: c, distance: d }
  }
  return best
}

/** Tie-break priority — lower wins. Keyframe(0) > Speech(1) > Scene(2) > Neighbor(3). */
const PRIORITY = { keyframe: 0, speech: 1, scene: 2, neighbor: 3 } as const
type SnappedPool = keyof typeof PRIORITY

export function snap(targetMs: number, opts: SnapOptions): SnapResult {
  const keyframeTol = opts.keyframeToleranceMs ?? DEFAULT_KEYFRAME_TOLERANCE_MS
  const neighborTol = opts.neighborToleranceMs ?? DEFAULT_NEIGHBOR_TOLERANCE_MS
  const sceneTol = opts.sceneToleranceMs ?? DEFAULT_SCENE_TOLERANCE_MS
  const speechTol = opts.speechToleranceMs ?? DEFAULT_SPEECH_TOLERANCE_MS

  const kfHit = closestWithin(targetMs, opts.keyframesMs, keyframeTol)
  const spHit = closestWithin(targetMs, opts.speechEdgesMs ?? [], speechTol)
  const scHit = closestWithin(targetMs, opts.scenesMs ?? [], sceneTol)
  const nbHit = closestWithin(targetMs, opts.neighborsMs, neighborTol)

  type Hit = { value: number; distance: number; kind: SnapResult['snappedTo'] }
  const hits: Hit[] = []
  if (kfHit) hits.push({ ...kfHit, kind: 'keyframe' })
  if (spHit) hits.push({ ...spHit, kind: 'speech' })
  if (scHit) hits.push({ ...scHit, kind: 'scene' })
  if (nbHit) hits.push({ ...nbHit, kind: 'neighbor' })

  let value = targetMs
  let snappedTo: SnapResult['snappedTo'] = 'none'

  if (hits.length > 0) {
    // Sort by (distance asc, priority asc) — closest wins; ties broken by
    // priority (keyframe < speech < scene < neighbor).
    hits.sort((a, b) => {
      if (a.distance !== b.distance) return a.distance - b.distance
      return PRIORITY[a.kind as SnappedPool] - PRIORITY[b.kind as SnappedPool]
    })
    value = hits[0].value
    snappedTo = hits[0].kind
  }

  // Min-gap enforcement: nudge away from the nearest neighbor if the result
  // sits inside the gap. Direction is determined by the *original* target
  // (the user's intent), not by `value` — when snap collapses onto the
  // neighbor itself, `value` no longer carries direction information.
  if (snappedTo !== 'none' && opts.minGapMs > 0 && opts.neighborsMs.length > 0) {
    const nearestNeighbor = opts.neighborsMs.reduce(
      (best, n) => (Math.abs(n - value) < Math.abs(best - value) ? n : best),
      opts.neighborsMs[0],
    )
    const gap = Math.abs(value - nearestNeighbor)
    if (gap < opts.minGapMs) {
      value =
        targetMs < nearestNeighbor
          ? nearestNeighbor - opts.minGapMs
          : nearestNeighbor + opts.minGapMs
    }
  }

  return { value, snappedTo }
}
