/**
 * applyCueTiming — replace a single cue's start/end timing in a subtitle
 * file's text body without affecting any other line (Plan B8 Task 11).
 *
 * Used by SubtitleEditorModal to write WaveformEditor drag-end commits
 * back into the modal's content state. Pure function, no I/O.
 *
 * Supported formats: 'srt' and 'ass'. Other formats throw — the caller
 * should fall back to read-only mode.
 *
 * Both SRT and ASS keep cue ordering by file position; the `cueIndex`
 * argument is 0-based and matches `useSubtitleParse(...).cues[i]`.
 */

export interface ApplyCueTimingArgs {
  content: string
  format: string
  cueIndex: number
  /** New start time in seconds. */
  start: number
  /** New end time in seconds. */
  end: number
}

export class UnsupportedFormatError extends Error {
  constructor(format: string) {
    super(`applyCueTiming: format "${format}" is not supported`)
    this.name = 'UnsupportedFormatError'
  }
}

export class CueIndexOutOfRangeError extends Error {
  constructor(index: number, total: number) {
    super(`applyCueTiming: cueIndex ${index} out of range (have ${total} cues)`)
    this.name = 'CueIndexOutOfRangeError'
  }
}

/** Format `secs` as "HH:MM:SS,mmm" (SRT). */
function fmtSrt(secs: number): string {
  const total = Math.max(0, Math.round(secs * 1000))
  const ms = total % 1000
  const s = Math.floor(total / 1000) % 60
  const m = Math.floor(total / 60_000) % 60
  const h = Math.floor(total / 3_600_000)
  return `${pad2(h)}:${pad2(m)}:${pad2(s)},${pad3(ms)}`
}

/** Format `secs` as "H:MM:SS.cs" (ASS — centiseconds). */
function fmtAss(secs: number): string {
  const total = Math.max(0, Math.round(secs * 100))
  const cs = total % 100
  const s = Math.floor(total / 100) % 60
  const m = Math.floor(total / 6_000) % 60
  const h = Math.floor(total / 360_000)
  return `${h}:${pad2(m)}:${pad2(s)}.${pad2(cs)}`
}

function pad2(n: number): string {
  return n < 10 ? `0${n}` : String(n)
}

function pad3(n: number): string {
  if (n < 10) return `00${n}`
  if (n < 100) return `0${n}`
  return String(n)
}

/**
 * Match a single SRT timing pair, capturing the arrow + spacing so we can
 * preserve odd whitespace styles. Not anchored to start-of-string so the
 * `block.replace(...)` path matches when the timing line is line 1 of a
 * multi-line cue block.
 */
const SRT_TIMING_RE =
  /(\d{1,2}:\d{2}:\d{2}[,.]\d{3})(\s*-->\s*)(\d{1,2}:\d{2}:\d{2}[,.]\d{3})/

function applySrt(content: string, idx: number, start: number, end: number): string {
  // Detect line-ending style and preserve it.
  const eol = content.includes('\r\n') ? '\r\n' : '\n'
  // SRT cues are separated by blank lines. Allow leading blank-line noise.
  const blocks = content.split(new RegExp(`${eol}${eol}+`, 'g'))

  let cueCounter = 0
  let targetBlock = -1
  for (let i = 0; i < blocks.length; i++) {
    const lines = blocks[i].split(eol)
    // A valid SRT cue has at least: index line, timing line, text line.
    // We probe by looking for the timing pattern on any of the first 3 lines.
    const hasTiming = lines.slice(0, 3).some((l) => SRT_TIMING_RE.test(l))
    if (!hasTiming) continue
    if (cueCounter === idx) {
      targetBlock = i
      break
    }
    cueCounter++
  }

  if (targetBlock === -1) {
    // Compute total cue count for the error message.
    let total = 0
    for (const b of blocks) {
      if (b.split(eol).slice(0, 3).some((l) => SRT_TIMING_RE.test(l))) total++
    }
    throw new CueIndexOutOfRangeError(idx, total)
  }

  const block = blocks[targetBlock]
  const updated = block.replace(SRT_TIMING_RE, (_match, _from, arrow) => {
    return `${fmtSrt(start)}${arrow}${fmtSrt(end)}`
  })
  blocks[targetBlock] = updated
  return blocks.join(`${eol}${eol}`)
}

const ASS_DIALOGUE_PREFIX = 'Dialogue:'

function applyAss(content: string, idx: number, start: number, end: number): string {
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

  // ASS Dialogue line:
  //   Dialogue: <Layer>, <Start>, <End>, <Style>, <Name>, <Marg L/R/V>, <Effect>, <Text>
  // The first 9 commas separate the 10 fields; <Text> may contain commas, so
  // we split limited to 10 parts.
  const head = lines[targetLine].slice(ASS_DIALOGUE_PREFIX.length)
  // Match leading whitespace so we can preserve it on rebuild.
  const leadMatch = /^(\s*)/.exec(head)
  const lead = leadMatch ? leadMatch[1] : ' '
  const body = head.slice(lead.length)

  const parts = body.split(',')
  if (parts.length < 10) {
    throw new Error(`applyCueTiming: malformed ASS Dialogue at line ${targetLine + 1}`)
  }
  parts[1] = fmtAss(start)
  parts[2] = fmtAss(end)
  // Re-glue while preserving any commas in the <Text> field (which lives in
  // parts[9..]).
  const head9 = parts.slice(0, 9).join(',')
  const text = parts.slice(9).join(',')
  lines[targetLine] = `${ASS_DIALOGUE_PREFIX}${lead}${head9},${text}`

  return lines.join(eol)
}

export function applyCueTiming({
  content,
  format,
  cueIndex,
  start,
  end,
}: ApplyCueTimingArgs): string {
  const fmt = format.toLowerCase()
  if (fmt === 'srt') return applySrt(content, cueIndex, start, end)
  if (fmt === 'ass' || fmt === 'ssa') return applyAss(content, cueIndex, start, end)
  throw new UnsupportedFormatError(format)
}
