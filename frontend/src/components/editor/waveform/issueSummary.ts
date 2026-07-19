/**
 * File-level quality summary for the waveform editor.
 *
 * Composes the two existing signal sources — adjacent-cue defects
 * (`detectGapsAndOverlaps`) and per-cue reading speed (`classifyReadingSpeed`)
 * — into a single at-a-glance count so the editor knows how much work a
 * subtitle needs and can jump straight to the first problem. Pure module.
 */

import { detectGapsAndOverlaps } from './gapOverlap'
import { classifyReadingSpeed, type ReadingSpeedOptions } from './readingSpeed'

export interface IssueSummaryCue {
  start: number
  end: number
  text: string
}

export interface IssueSummary {
  overlaps: number
  tightGaps: number
  tooFast: number
  tooShort: number
  total: number
  /** Earliest issue time in seconds, or `null` when there are none. */
  firstIssueSec: number | null
}

export interface IssueSummaryOptions {
  gapToleranceMs?: number
  reading?: ReadingSpeedOptions
}

/**
 * Count timing/readability issues across a whole cue list. Each cue contributes
 * at most one reading-speed issue (too-fast takes precedence over too-short) so
 * the counts don't double-report the same line.
 */
export function summarizeIssues(
  cues: readonly IssueSummaryCue[],
  opts: IssueSummaryOptions = {},
): IssueSummary {
  const ranges = cues.map((c, i) => ({ id: String(i), start: c.start, end: c.end }))
  const { overlaps, tightGaps } = detectGapsAndOverlaps(ranges, {
    gapToleranceMs: opts.gapToleranceMs,
  })

  const issueTimes: number[] = [
    ...overlaps.map((o) => o.start),
    ...tightGaps.map((g) => g.start),
  ]

  let tooFast = 0
  let tooShort = 0
  for (const c of cues) {
    const rs = classifyReadingSpeed(c.text, c.start, c.end, opts.reading)
    if (rs.level === 'tooFast') {
      tooFast++
      issueTimes.push(c.start)
    } else if (rs.tooShort) {
      tooShort++
      issueTimes.push(c.start)
    }
  }

  const total = overlaps.length + tightGaps.length + tooFast + tooShort
  const firstIssueSec = issueTimes.length > 0 ? Math.min(...issueTimes) : null

  return {
    overlaps: overlaps.length,
    tightGaps: tightGaps.length,
    tooFast,
    tooShort,
    total,
    firstIssueSec,
  }
}
