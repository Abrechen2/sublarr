/**
 * Active-cue bar — large readable panel that sits above the waveform
 * showing the currently selected cue's index, timing and text.
 *
 * Inspired by Aegisub's audio-editor "current line" bar: the editor
 * never has to switch tabs to know what they're aligning. When no cue
 * is selected, a short hint instructs the user to pick one.
 */

import { formatCueTextForDisplay } from './cueTextDisplay'

interface WaveformActiveCueBarProps {
  cueIndex: number | null
  cueCount: number
  startSec: number
  endSec: number
  text: string
}

/** Format a non-negative number of seconds as `HH:MM:SS.mmm`. */
function formatTimecode(sec: number): string {
  if (!Number.isFinite(sec) || sec < 0) sec = 0
  const totalMs = Math.round(sec * 1000)
  const ms = totalMs % 1000
  const totalSec = Math.floor(totalMs / 1000)
  const s = totalSec % 60
  const totalMin = Math.floor(totalSec / 60)
  const m = totalMin % 60
  const h = Math.floor(totalMin / 60)
  const pad2 = (n: number) => n.toString().padStart(2, '0')
  const pad3 = (n: number) => n.toString().padStart(3, '0')
  return `${pad2(h)}:${pad2(m)}:${pad2(s)}.${pad3(ms)}`
}

export function WaveformActiveCueBar({
  cueIndex,
  cueCount,
  startSec,
  endSec,
  text,
}: WaveformActiveCueBarProps) {
  if (cueIndex === null) {
    return (
      <div
        role="status"
        aria-live="polite"
        className="rounded border border-dashed border-border bg-surface px-4 py-3 text-sm text-muted"
      >
        {cueCount === 0
          ? 'Diese Datei enthält keine Cues / no cues to edit.'
          : 'Wähle einen Cue im "Cues"-Tab oder klick eine Region — Select a cue to edit.'}
      </div>
    )
  }

  const lines = formatCueTextForDisplay(text).split('\n')
  const duration = Math.max(0, endSec - startSec)

  return (
    <div className="rounded border border-accent-dim bg-accent-bg/30 px-4 py-3">
      <div className="flex items-baseline gap-3 text-xs text-muted mb-1.5 flex-wrap">
        <span className="font-medium text-accent">Cue {cueIndex + 1} / {cueCount}</span>
        <span className="tabular-nums">{formatTimecode(startSec)}</span>
        <span aria-hidden="true">→</span>
        <span className="tabular-nums">{formatTimecode(endSec)}</span>
        <span className="text-muted/70">({duration.toFixed(3)} s)</span>
      </div>
      <div className="text-base leading-snug text-primary">
        {lines.length === 0 || (lines.length === 1 && lines[0] === '') ? (
          <span className="italic text-muted">(leerer Cue / empty cue)</span>
        ) : (
          lines.map((line, i) => (
            <div key={i}>{line}</div>
          ))
        )}
      </div>
    </div>
  )
}
