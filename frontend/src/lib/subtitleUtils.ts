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
