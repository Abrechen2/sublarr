/**
 * SubtitleTimeline -- visual cue timeline bar for subtitle files.
 *
 * Renders each cue as a positioned block on a horizontal time axis.
 * Color-coded by style classification: teal for dialog, amber for signs/songs.
 * Clicking a cue fires onCueClick with the cue index for scroll-to-line.
 */

import type { SubtitleCue } from '@/lib/types'

interface SubtitleTimelineProps {
  cues: SubtitleCue[]
  totalDuration: number
  onCueClick: (index: number) => void
  styles?: Record<string, string> | null  // style classification for color-coding
  className?: string
}

/** Convert seconds to H:MM:SS or MM:SS display format. */
function formatTime(seconds: number): string {
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  const s = Math.floor(seconds % 60)
  if (h > 0) {
    return `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
  }
  return `${m}:${String(s).padStart(2, '0')}`
}

/** Determine cue color based on style classification. */
function getCueColor(style: string, styles: Record<string, string> | null | undefined): string {
  if (!styles || !style) return 'bg-teal-500'
  const classification = styles[style]
  if (classification === 'signs' || classification === 'songs') return 'bg-amber-500'
  return 'bg-teal-500'
}

export default function SubtitleTimeline({
  cues,
  totalDuration,
  onCueClick,
  styles,
  className = '',
}: SubtitleTimelineProps) {
  if (totalDuration === 0 || cues.length === 0) {
    return (
      <div className={`relative h-8 rounded overflow-hidden bg-elevated flex items-center justify-center text-xs text-muted ${className}`}>
        No cues
      </div>
    )
  }

  // Calculate time ruler labels (evenly spaced)
  const labelCount = Math.min(Math.max(Math.floor(totalDuration / 300), 2), 10)  // one label every ~5 min, 2-10 labels
  const labelInterval = totalDuration / labelCount
  const labels: { time: number; left: number }[] = []
  for (let i = 0; i <= labelCount; i++) {
    const time = i * labelInterval
    labels.push({ time, left: (time / totalDuration) * 100 })
  }

  return (
    <div className={className}>
      {/* Cue bar */}
      <div className="relative h-8 rounded overflow-hidden bg-elevated">
        {cues.map((cue, index) => {
          const left = (cue.start / totalDuration) * 100
          const width = Math.max(((cue.end - cue.start) / totalDuration) * 100, 0.3)
          const color = getCueColor(cue.style, styles)
          return (
            <div
              key={index}
              className={`absolute top-0 h-full ${color} opacity-60 hover:opacity-100 cursor-pointer transition-opacity`}
              style={{ left: `${left}%`, width: `${width}%` }}
              title={`${formatTime(cue.start)} - ${formatTime(cue.end)}`}
              onClick={() => onCueClick(index)}
            />
          )
        })}
      </div>

      {/* Time ruler */}
      <div className="relative h-4 mt-0.5">
        {labels.map(({ time, left }, i) => (
          <span
            key={i}
            className="absolute text-[10px] text-muted -translate-x-1/2"
            style={{ left: `${left}%` }}
          >
            {formatTime(time)}
          </span>
        ))}
      </div>
    </div>
  )
}
