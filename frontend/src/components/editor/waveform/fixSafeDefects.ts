/**
 * fixSafeDefects — plan one-click timing fixes for the "safe" defect classes
 * the waveform editor already detects: overlaps, tight gaps and too-short
 * cues (waveform-expansion roadmap, Phase 1 last open item).
 *
 * "Safe" means a fix is only proposed when it fully resolves the defect
 * WITHOUT creating a new one:
 *   - Overlaps / tight gaps are resolved by shortening the earlier cue's end
 *     to leave `targetGapMs` before the next cue — but only if the shortened
 *     cue keeps a readable window (≥ minDisplaySec for text cues) and does
 *     not become too fast to read (CPS ≤ warnMax).
 *   - Too-short cues are extended to `minDisplaySec` — but only if there is
 *     room before the next cue (again keeping `targetGapMs`).
 * Anything that cannot be fixed under these constraints is skipped and left
 * for manual editing. Pure module: no React, no wavesurfer.
 *
 * Text is never modified; only cue start/end timings (and in fact only ends —
 * starts are audio-sync anchors and are never moved).
 */

import { classifyReadingSpeed, CPS_WARN_MAX, MIN_DISPLAY_SEC } from './readingSpeed'

export interface FixableCue {
  /** Start time in seconds. */
  start: number
  /** End time in seconds. */
  end: number
  text: string
}

export type SafeDefectKind = 'overlap' | 'tightGap' | 'tooShort'

export interface CueTimingFix {
  /** 0-based index into the original (unsorted) cue list. */
  cueIndex: number
  kind: SafeDefectKind
  before: { start: number; end: number }
  after: { start: number; end: number }
}

export interface FixSafeDefectsOptions {
  /** Gap (ms) at or below which an inter-cue gap counts as a defect. Default 80. */
  gapToleranceMs?: number
  /** Gap (ms) fixes aim for between cues. Must exceed gapToleranceMs. Default 120. */
  targetGapMs?: number
  /** Minimum on-screen window (s) for cues with text. Default MIN_DISPLAY_SEC. */
  minDisplaySec?: number
  /** CPS above which a shortened cue would become unreadable. Default CPS_WARN_MAX. */
  cpsWarnMax?: number
  /** Minimum duration (s) kept on text-free cues when shortening. Default 0.1. */
  minBareDurationSec?: number
}

const DEFAULT_GAP_TOLERANCE_MS = 80
const DEFAULT_TARGET_GAP_MS = 120
const DEFAULT_MIN_BARE_DURATION_SEC = 0.1

/** Round to whole milliseconds so float noise can't produce 79.999 ms gaps. */
function roundMs(sec: number): number {
  return Math.round(sec * 1000) / 1000
}

/**
 * Compute the list of safe, fully-resolving timing fixes for `cues`.
 * The returned fixes reference cues by their index in the input list and
 * are internally consistent: applying all of them together neither leaves
 * the targeted defects in place nor introduces new overlaps/tight gaps.
 */
export function planSafeDefectFixes(
  cues: readonly FixableCue[],
  opts: FixSafeDefectsOptions = {},
): CueTimingFix[] {
  const gapTolSec = (opts.gapToleranceMs ?? DEFAULT_GAP_TOLERANCE_MS) / 1000
  const targetGapSec = Math.max(
    (opts.targetGapMs ?? DEFAULT_TARGET_GAP_MS) / 1000,
    gapTolSec + 0.001,
  )
  const minDisplaySec = opts.minDisplaySec ?? MIN_DISPLAY_SEC
  const cpsWarnMax = opts.cpsWarnMax ?? CPS_WARN_MAX
  const minBareSec = opts.minBareDurationSec ?? DEFAULT_MIN_BARE_DURATION_SEC

  // Work on a mutable copy sorted by start (same ordering the detector uses)
  // so later checks see the effect of earlier fixes.
  const working = cues.map((c, i) => ({ index: i, start: c.start, end: c.end, text: c.text }))
  working.sort((a, b) => a.start - b.start || a.end - b.end)

  const fixes: CueTimingFix[] = []

  const isSafeDuration = (cue: { start: number; text: string }, newEnd: number): boolean => {
    const dur = newEnd - cue.start
    if (cue.text.trim().length === 0) return dur >= minBareSec
    if (dur < minDisplaySec) return false
    const rs = classifyReadingSpeed(cue.text, cue.start, newEnd, { warnMax: cpsWarnMax })
    return rs.cps !== null && rs.cps <= cpsWarnMax
  }

  // Pass 1 — overlaps and tight gaps: shorten the earlier cue's end.
  for (let i = 0; i < working.length - 1; i++) {
    const prev = working[i]
    const next = working[i + 1]
    const gap = next.start - prev.end
    if (gap > gapTolSec) continue

    // Layered/contained cues (same start, or next ends inside prev) are a
    // deliberate ASS pattern — signs, karaoke, top+bottom dialogue. Never
    // "fix" those; only trim genuine sequential collisions.
    if (next.start <= prev.start || next.end <= prev.end) continue

    const kind: SafeDefectKind = gap < 0 ? 'overlap' : 'tightGap'
    const newEnd = roundMs(next.start - targetGapSec)
    if (newEnd >= prev.end) continue // would lengthen — not this defect's fix
    if (!isSafeDuration(prev, newEnd)) continue

    fixes.push({
      cueIndex: prev.index,
      kind,
      before: { start: prev.start, end: prev.end },
      after: { start: prev.start, end: newEnd },
    })
    prev.end = newEnd
  }

  // Pass 2 — too-short cues: extend the end to the minimum display window,
  // as long as the target gap to the (possibly already fixed) next cue holds.
  for (let i = 0; i < working.length; i++) {
    const cue = working[i]
    if (cue.text.trim().length === 0) continue
    if (cue.end - cue.start >= minDisplaySec) continue

    const newEnd = roundMs(cue.start + minDisplaySec)
    const next = working[i + 1]
    if (next && newEnd > next.start - targetGapSec) continue

    fixes.push({
      cueIndex: cue.index,
      kind: 'tooShort',
      before: { start: cue.start, end: cue.end },
      after: { start: cue.start, end: newEnd },
    })
    cue.end = newEnd
  }

  fixes.sort((a, b) => a.cueIndex - b.cueIndex)
  return fixes
}
