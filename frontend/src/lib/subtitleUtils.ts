/**
 * Subtitle format detection and SRT → ASS conversion.
 * libass-wasm (SubtitleOctopus) only supports ASS/SSA format, so SRT files
 * must be converted before passing to the worker.
 */

/** True if the content looks like SRT (starts with an index number + timestamp). */
export function isSrt(content: string): boolean {
  return /^\s*\d+\r?\n\d{2}:\d{2}:\d{2},\d{3}/.test(content)
}

/** Convert SRT timestamp "HH:MM:SS,mmm" to ASS timestamp "H:MM:SS.cc". */
function toAssTimestamp(srt: string): string {
  const [hms, ms] = srt.split(',')
  const [h, m, s] = hms.split(':')
  return `${parseInt(h)}:${m}:${s}.${ms.slice(0, 2)}`
}

const ASS_HEADER = `[Script Info]
ScriptType: v4.00+
PlayResX: 1280
PlayResY: 720
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,48,&H00FFFFFF,&H000000FF,&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,2,2,2,10,10,10,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
`

/** True if the browser is Firefox (libass-wasm createTrack crashes in Firefox). */
export const isFirefox = /Firefox\//i.test(navigator.userAgent)

/** Convert ASS timestamp "H:MM:SS.cc" to VTT timestamp "HH:MM:SS.ccc". */
function assTimestampToVtt(ass: string): string {
  const parts = ass.trim().split(':')
  if (parts.length !== 3) return '00:00:00.000'
  const [h, m, rest] = parts
  const [s, cs] = rest.split('.')
  return `${h.padStart(2, '0')}:${m}:${s}.${(cs ?? '0').padEnd(3, '0')}`
}

/** Convert SRT timestamp "HH:MM:SS,mmm" to VTT timestamp "HH:MM:SS.mmm". */
function srtTimestampToVtt(srt: string): string {
  return srt.replace(',', '.')
}

/** Convert ASS/SSA subtitle content to WebVTT for native browser rendering. */
export function assToVtt(ass: string): string {
  const lines: string[] = ['WEBVTT', '']
  const dialogueRe =
    /^Dialogue:\s*\d+,\s*([^,]+),\s*([^,]+),\s*[^,]*,\s*[^,]*,\s*\d+,\s*\d+,\s*\d+,\s*[^,]*,(.*)/
  for (const line of ass.split(/\r?\n/)) {
    const m = line.match(dialogueRe)
    if (!m) continue
    const start = assTimestampToVtt(m[1])
    const end = assTimestampToVtt(m[2])
    const text = m[3]
      .replace(/\\N/g, '\n')
      .replace(/\\n/g, '\n')
      .replace(/\{[^}]*\}/g, '') // strip ASS override tags
      .trim()
    if (!text) continue
    lines.push(`${start} --> ${end}`, text, '')
  }
  return lines.join('\n')
}

/** Convert SRT subtitle content to WebVTT for native browser rendering. */
export function srtToVtt(srt: string): string {
  const lines: string[] = ['WEBVTT', '']
  for (const block of srt.trim().split(/\r?\n\r?\n/)) {
    const blockLines = block.trim().split(/\r?\n/)
    if (blockLines.length < 3) continue
    const tcMatch = blockLines[1].match(
      /^(\d{2}:\d{2}:\d{2},\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2},\d{3})/,
    )
    if (!tcMatch) continue
    const start = srtTimestampToVtt(tcMatch[1])
    const end = srtTimestampToVtt(tcMatch[2])
    const text = blockLines
      .slice(2)
      .join('\n')
      .replace(/<[^>]+>/g, '')
    lines.push(`${start} --> ${end}`, text, '')
  }
  return lines.join('\n')
}

/** Convert SRT subtitle content to ASS format compatible with libass-wasm. */
export function srtToAss(srt: string): string {
  const dialogues = srt
    .trim()
    .split(/\r?\n\r?\n/)
    .flatMap((block): string[] => {
      const lines = block.trim().split(/\r?\n/)
      if (lines.length < 3) return []
      const tcMatch = lines[1].match(
        /^(\d{2}:\d{2}:\d{2},\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2},\d{3})/,
      )
      if (!tcMatch) return []
      const start = toAssTimestamp(tcMatch[1])
      const end = toAssTimestamp(tcMatch[2])
      const text = lines
        .slice(2)
        .join('\\N')
        .replace(/<[^>]+>/g, '') // strip HTML tags
      return [`Dialogue: 0,${start},${end},Default,,0,0,0,,${text}`]
    })

  return ASS_HEADER + dialogues.join('\n') + '\n'
}
