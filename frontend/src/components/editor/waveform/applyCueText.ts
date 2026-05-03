/**
 * applyCueText — replace a single cue's text body in a subtitle file
 * without touching its timing or any sibling cue.
 *
 * Used by the WaveformCueList for inline text edits. Pure function, no I/O.
 *
 * Supported formats: 'srt' and 'ass'/'ssa'. For ASS, override tags
 * ({\b1}, {\i1}, positioning, fades, etc.) inside the cue's Text field
 * are NOT preserved when the user types over them — we throw a dedicated
 * `CueTextHasStylingError` so the caller can surface a "edit this cue
 * in the source view" hint instead of silently destroying styling.
 *
 * Both SRT and ASS keep cue ordering by file position; the `cueIndex`
 * argument is 0-based and matches `useSubtitleParse(...).cues[i]`.
 */

import { UnsupportedFormatError, CueIndexOutOfRangeError } from './applyCueTiming'

export interface ApplyCueTextArgs {
  content: string
  format: string
  cueIndex: number
  /** New cue text. May contain '\n' for line breaks (always real newlines, not "\N"). */
  text: string
}

export class CueTextHasStylingError extends Error {
  constructor(idx: number) {
    super(`applyCueText: cue ${idx} contains ASS override tags; refusing to overwrite`)
    this.name = 'CueTextHasStylingError'
  }
}

const SRT_TIMING_RE =
  /^\d{1,2}:\d{2}:\d{2}[,.]\d{3}\s*-->\s*\d{1,2}:\d{2}:\d{2}[,.]\d{3}/

function applySrt(content: string, idx: number, text: string): string {
  const eol = content.includes('\r\n') ? '\r\n' : '\n'
  const blocks = content.split(new RegExp(`${eol}${eol}+`, 'g'))

  let cueCounter = 0
  let targetBlock = -1
  for (let i = 0; i < blocks.length; i++) {
    const lines = blocks[i].split(eol)
    const hasTiming = lines.slice(0, 3).some((l) => SRT_TIMING_RE.test(l))
    if (!hasTiming) continue
    if (cueCounter === idx) {
      targetBlock = i
      break
    }
    cueCounter++
  }

  if (targetBlock === -1) {
    let total = 0
    for (const b of blocks) {
      if (b.split(eol).slice(0, 3).some((l) => SRT_TIMING_RE.test(l))) total++
    }
    throw new CueIndexOutOfRangeError(idx, total)
  }

  // Keep header lines up to + including the timing line; replace everything
  // after with the user's text. SRT supports an optional index line on
  // line 1, so the timing line index varies — find it.
  const blockLines = blocks[targetBlock].split(eol)
  let timingLineIdx = -1
  for (let i = 0; i < Math.min(blockLines.length, 3); i++) {
    if (SRT_TIMING_RE.test(blockLines[i])) {
      timingLineIdx = i
      break
    }
  }
  if (timingLineIdx === -1) {
    // Should never happen given the hasTiming probe above.
    throw new Error(`applyCueText: SRT cue ${idx} has no timing line`)
  }

  const header = blockLines.slice(0, timingLineIdx + 1).join(eol)
  // Normalize incoming line breaks to the file's EOL style.
  const normalizedText = text.replace(/\r\n/g, '\n').split('\n').join(eol)
  blocks[targetBlock] = header + (normalizedText.length > 0 ? eol + normalizedText : '')
  return blocks.join(`${eol}${eol}`)
}

const ASS_DIALOGUE_PREFIX = 'Dialogue:'
const ASS_OVERRIDE_RE = /\{[^}]*\}/

function applyAss(content: string, idx: number, text: string): string {
  const eol = content.includes('\r\n') ? '\r\n' : '\n'
  const lines = content.split(eol)

  let cueCounter = 0
  let targetLine = -1
  for (let i = 0; i < lines.length; i++) {
    if (!lines[i].startsWith(ASS_DIALOGUE_PREFIX)) continue
    if (cueCounter === idx) {
      targetLine = i
      break
    }
    cueCounter++
  }

  if (targetLine === -1) {
    const total = lines.filter((l) => l.startsWith(ASS_DIALOGUE_PREFIX)).length
    throw new CueIndexOutOfRangeError(idx, total)
  }

  const head = lines[targetLine].slice(ASS_DIALOGUE_PREFIX.length)
  const leadMatch = /^(\s*)/.exec(head)
  const lead = leadMatch ? leadMatch[1] : ' '
  const body = head.slice(lead.length)

  const parts = body.split(',')
  if (parts.length < 10) {
    throw new Error(`applyCueText: malformed ASS Dialogue at line ${targetLine + 1}`)
  }
  const head9 = parts.slice(0, 9).join(',')
  const originalText = parts.slice(9).join(',')

  // Refuse to overwrite styling tags — the cue list doesn't render them,
  // so the user wouldn't know they're about to be lost.
  if (ASS_OVERRIDE_RE.test(originalText)) {
    throw new CueTextHasStylingError(idx)
  }

  // Convert real newlines → ASS hard-break syntax. Keep the user's other
  // characters as-is. Strip stray '\r' the user might have pasted.
  const assText = text.replace(/\r\n?/g, '\n').split('\n').join('\\N')
  lines[targetLine] = `${ASS_DIALOGUE_PREFIX}${lead}${head9},${assText}`
  return lines.join(eol)
}

export function applyCueText({
  content,
  format,
  cueIndex,
  text,
}: ApplyCueTextArgs): string {
  const fmt = format.toLowerCase()
  if (fmt === 'srt') return applySrt(content, cueIndex, text)
  if (fmt === 'ass' || fmt === 'ssa') return applyAss(content, cueIndex, text)
  throw new UnsupportedFormatError(format)
}
