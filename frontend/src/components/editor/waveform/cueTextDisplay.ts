/**
 * Helpers for rendering subtitle cue text on the waveform editor —
 * either as a single-line region label (`formatCueTextForRegion`) or
 * as a multi-line panel above the waveform (`formatCueTextForDisplay`).
 *
 * ASS source carries `{\\override}` tags and `\\N` line breaks that
 * would clutter the visual surface, so both helpers strip them.
 */

const ASS_OVERRIDE_RE = /\{[^}]*\}/g
// Matches both \N (hard break) and \n (soft break) used in ASS event text.
const ASS_LINE_BREAK_RE = /\\[Nn]/g
const WHITESPACE_RUN_RE = /\s+/g

/**
 * Strip ASS override tags AND collapse `\\N`/`\\n` line breaks into a
 * single space, then collapse all whitespace runs. Output is always
 * single-line.
 */
export function stripAssOverrideTags(input: string): string {
  if (!input) return ''
  return input
    .replace(ASS_OVERRIDE_RE, '')
    .replace(ASS_LINE_BREAK_RE, ' ')
    .replace(WHITESPACE_RUN_RE, ' ')
    .trim()
}

/**
 * For the active-cue bar above the waveform: keep visible line breaks
 * so the editor can read multi-line dialogue normally. Real `\n` from
 * the source is preserved; ASS `\\N` is converted to a real newline.
 */
export function formatCueTextForDisplay(input: string): string {
  if (!input) return ''
  return input
    .replace(ASS_OVERRIDE_RE, '')
    .replace(ASS_LINE_BREAK_RE, '\n')
    .split('\n')
    .map((line) => line.replace(WHITESPACE_RUN_RE, ' ').trim())
    .filter((line) => line.length > 0)
    .join('\n')
}

/**
 * Single-line label for a region overlay: strips tags + line breaks,
 * truncates at `maxLength` (default 60) and appends `…` when cropped.
 */
export function formatCueTextForRegion(input: string, maxLength = 60): string {
  const flat = stripAssOverrideTags(input)
  if (flat.length <= maxLength) return flat
  return flat.slice(0, maxLength) + '…'
}
