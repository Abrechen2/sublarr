/**
 * Reading-speed (CPS — characters per second) diagnostics for subtitle cues.
 *
 * Sublarr's core flow is EN→DE translation, and German text expands ~30% over
 * English. A line whose *timing* is perfectly synced to the audio can still be
 * unreadable because the translated text is too long for its on-screen window.
 * CPS is the standard readability metric for exactly that problem, so we surface
 * it right where the editor is already looking (active-cue bar + cue list).
 *
 * Pure module — no React, no wavesurfer — so the thresholds and classification
 * are unit-testable in isolation.
 */

import { stripAssOverrideTags } from './cueTextDisplay'

/** At or below this CPS a line reads comfortably (Netflix targets ~17). */
export const CPS_OK_MAX = 17
/** Between OK and this it is fast-but-tolerable; above it, too fast to read. */
export const CPS_WARN_MAX = 21
/** Cues shorter than this (with text) are flagged as too-short to read. */
export const MIN_DISPLAY_SEC = 0.7

export type ReadingSpeedLevel = 'ok' | 'fast' | 'tooFast'

export interface ReadingSpeed {
  /** Readable character count (ASS tags + line breaks stripped). */
  chars: number
  /** Cue duration in seconds (clamped to ≥ 0). */
  durationSec: number
  /**
   * Characters per second, or `null` when the duration is non-positive
   * (rate undefined — there is no window to read the text in).
   */
  cps: number | null
  level: ReadingSpeedLevel
  /** True when there is text but the on-screen window is below MIN_DISPLAY_SEC. */
  tooShort: boolean
}

export interface ReadingSpeedOptions {
  okMax?: number
  warnMax?: number
  minDisplaySec?: number
}

/**
 * Count the characters a viewer actually reads: ASS override tags and `\N`/`\n`
 * line breaks are removed and whitespace runs collapsed (same normalization the
 * region label uses), then the length is taken — spaces included, matching the
 * Netflix/BBC convention.
 */
export function countReadableChars(text: string): number {
  return stripAssOverrideTags(text).length
}

/**
 * Classify a cue's reading speed. `cps > warnMax` ⇒ `tooFast`, `cps > okMax`
 * ⇒ `fast`, otherwise `ok`. A cue with text but no positive duration is
 * `tooFast` (unreadable); an empty cue is always `ok`.
 */
export function classifyReadingSpeed(
  text: string,
  startSec: number,
  endSec: number,
  opts: ReadingSpeedOptions = {},
): ReadingSpeed {
  const okMax = opts.okMax ?? CPS_OK_MAX
  const warnMax = opts.warnMax ?? CPS_WARN_MAX
  const minDisplaySec = opts.minDisplaySec ?? MIN_DISPLAY_SEC

  const chars = countReadableChars(text)
  const durationSec = Math.max(0, endSec - startSec)
  const tooShort = chars > 0 && durationSec < minDisplaySec

  if (durationSec <= 0) {
    return {
      chars,
      durationSec,
      cps: null,
      level: chars > 0 ? 'tooFast' : 'ok',
      tooShort,
    }
  }

  const cps = chars / durationSec
  let level: ReadingSpeedLevel = 'ok'
  if (cps > warnMax) level = 'tooFast'
  else if (cps > okMax) level = 'fast'

  return { chars, durationSec, cps, level, tooShort }
}

/** Compact CPS label for the UI: one decimal, or `∞` when the rate is undefined. */
export function formatCps(cps: number | null): string {
  if (cps === null || !Number.isFinite(cps)) return '∞'
  return cps.toFixed(1)
}
