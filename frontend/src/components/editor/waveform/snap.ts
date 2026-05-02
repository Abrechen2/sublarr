/**
 * Pure snap helper (Plan B8 Task 4).
 *
 * Used by drag-end commits and the Aegisub-style L/R click-map to decide
 * where a cue boundary lands on the waveform. Three rules:
 *
 *   1. Snap to the closer of (nearest keyframe within keyframe tolerance,
 *      nearest neighbor within neighbor tolerance). Ties go to the keyframe
 *      (Aegisub convention — keyframes are stronger anchors than neighbor
 *      cues).
 *   2. If neither is within range, return the input unchanged.
 *   3. After snapping, if the result would land closer than `minGapMs` to
 *      any neighbor cue, push the value away from that neighbor by exactly
 *      `minGapMs`. This guarantees no two cues end up overlapping after a
 *      snap-driven adjustment.
 *
 * All inputs are in milliseconds. Tolerances default to 150 ms (keyframe)
 * and 80 ms (neighbor) — matching SubtitleEdit's defaults.
 */

export interface SnapOptions {
  /** Sorted (or unsorted — we don't assume order) keyframe targets in ms. */
  keyframesMs: number[]
  /** Sorted-or-not neighbor cue boundaries in ms. */
  neighborsMs: number[]
  /** Minimum gap to any neighbor after snap. 0 disables the gap-check. */
  minGapMs: number
  /** Snap range around a keyframe; default 150 ms. */
  keyframeToleranceMs?: number
  /** Snap range around a neighbor; default 80 ms. */
  neighborToleranceMs?: number
}

export interface SnapResult {
  value: number
  snappedTo: 'keyframe' | 'neighbor' | 'none'
}

const DEFAULT_KEYFRAME_TOLERANCE_MS = 150
const DEFAULT_NEIGHBOR_TOLERANCE_MS = 80

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

export function snap(targetMs: number, opts: SnapOptions): SnapResult {
  const keyframeTol = opts.keyframeToleranceMs ?? DEFAULT_KEYFRAME_TOLERANCE_MS
  const neighborTol = opts.neighborToleranceMs ?? DEFAULT_NEIGHBOR_TOLERANCE_MS

  const kfHit = closestWithin(targetMs, opts.keyframesMs, keyframeTol)
  const nbHit = closestWithin(targetMs, opts.neighborsMs, neighborTol)

  let value = targetMs
  let snappedTo: SnapResult['snappedTo'] = 'none'

  if (kfHit && nbHit) {
    // Tie -> prefer keyframe. Strict less-than for neighbor wins.
    if (nbHit.distance < kfHit.distance) {
      value = nbHit.value
      snappedTo = 'neighbor'
    } else {
      value = kfHit.value
      snappedTo = 'keyframe'
    }
  } else if (kfHit) {
    value = kfHit.value
    snappedTo = 'keyframe'
  } else if (nbHit) {
    value = nbHit.value
    snappedTo = 'neighbor'
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
