/**
 * Detect adjacent-cue defects: overlaps (next.start < prev.end) and
 * tight gaps (next.start - prev.end < tolerance).
 *
 * Both classes are reported as time intervals so the renderer can paint
 * them on the waveform without recomputing positions. Pure / sorted
 * internally so callers don't have to pre-sort.
 */

export interface CueRange {
  id: string
  /** Start time in seconds. */
  start: number
  /** End time in seconds. */
  end: number
}

export interface GapOverlapInterval {
  /** Defect start in seconds. */
  start: number
  /** Defect end in seconds. */
  end: number
  /** Cue immediately before the defect. */
  prevId: string
  /** Cue immediately after the defect. */
  nextId: string
}

export interface GapOverlapResult {
  overlaps: GapOverlapInterval[]
  tightGaps: GapOverlapInterval[]
}

export interface DetectOptions {
  /** Maximum gap (in ms) that still counts as "tight" — default 80 ms. */
  gapToleranceMs?: number
}

const DEFAULT_GAP_TOLERANCE_MS = 80

export function detectGapsAndOverlaps(
  cues: CueRange[],
  opts: DetectOptions = {},
): GapOverlapResult {
  const tolSec = (opts.gapToleranceMs ?? DEFAULT_GAP_TOLERANCE_MS) / 1000

  const overlaps: GapOverlapInterval[] = []
  const tightGaps: GapOverlapInterval[] = []

  if (cues.length < 2) return { overlaps, tightGaps }

  // Stable sort by start; tie-break on end keeps two zero-duration cues
  // at the same start in their original order.
  const sorted = [...cues].sort((a, b) => a.start - b.start || a.end - b.end)

  for (let i = 0; i < sorted.length - 1; i++) {
    const prev = sorted[i]
    const next = sorted[i + 1]
    if (next.start < prev.end) {
      overlaps.push({
        start: next.start,
        end: prev.end,
        prevId: prev.id,
        nextId: next.id,
      })
    } else if (next.start - prev.end <= tolSec) {
      tightGaps.push({
        start: prev.end,
        end: next.start,
        prevId: prev.id,
        nextId: next.id,
      })
    }
  }

  return { overlaps, tightGaps }
}
