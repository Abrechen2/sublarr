/**
 * AssKaraokeOverlay — paints per-syllable ticks on the waveform when
 * the active cue is ASS karaoke (Plan B8 Task 9).
 *
 * Display only. Syllable retiming stays Aegisub's domain.
 *
 * Positioning model: the overlay spans the full waveform width and uses
 * percent-of-duration left offsets, so it naturally aligns with the cue's
 * absolute timeline position no matter the current zoom level. The parent
 * passes the cue's absolute start (from the parsed cue list) plus the
 * total audio duration so we can convert each syllable's cue-relative
 * offset into an absolute percent.
 */

import type { SubtitleCueSyllable } from '@/types/system'

export interface AssKaraokeOverlayProps {
  /** Syllables for the currently selected ASS cue, with cue-relative offsets. */
  syllables: SubtitleCueSyllable[]
  /** Absolute cue start in seconds (used to translate syllable offsets to absolute timeline). */
  cueStartSec: number
  /** Total audio duration in seconds — denominator for the percent math. */
  durationSec: number
  /**
   * Whether to label each syllable with its text. Off by default to avoid
   * visual clutter on tiny syllables; turn on for spot-checks.
   */
  showLabels?: boolean
}

export function AssKaraokeOverlay({
  syllables,
  cueStartSec,
  durationSec,
  showLabels = false,
}: AssKaraokeOverlayProps) {
  if (!syllables || syllables.length === 0) return null
  if (!Number.isFinite(durationSec) || durationSec <= 0) return null

  return (
    <svg
      data-testid="ass-karaoke-overlay"
      role="presentation"
      aria-hidden="true"
      className="pointer-events-none absolute inset-0 z-3 w-full h-full"
    >
      {syllables.map((syl, i) => {
        const absStart = cueStartSec + syl.start
        const absEnd = cueStartSec + syl.end
        if (absStart < 0 || absStart > durationSec) return null
        const leftPct = (absStart / durationSec) * 100
        const widthPct = Math.max(0, ((absEnd - absStart) / durationSec) * 100)
        return (
          <g key={i} data-syllable-index={i}>
            <line
              x1={`${leftPct}%`}
              x2={`${leftPct}%`}
              y1="0"
              y2="100%"
              stroke="rgba(168, 85, 247, 0.7)"
              strokeWidth="1"
              strokeDasharray="3 2"
            />
            {showLabels && syl.text && (
              <text
                x={`${leftPct + widthPct / 2}%`}
                y="14"
                textAnchor="middle"
                className="fill-primary text-[10px]"
              >
                {syl.text}
              </text>
            )}
          </g>
        )
      })}
    </svg>
  )
}
