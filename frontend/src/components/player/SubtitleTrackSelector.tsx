import { ChevronDown } from 'lucide-react'
import { PlayerSubtitleTrack } from '@/lib/types'

interface Props {
  tracks: PlayerSubtitleTrack[]
  activeIndex: number | null
  onChange: (index: number | null) => void
}

export function SubtitleTrackSelector({ tracks, activeIndex, onChange }: Props) {
  if (tracks.length === 0) return null

  return (
    <div className="relative inline-flex items-center gap-1">
      <select
        value={activeIndex ?? -1}
        onChange={(e) => {
          const val = parseInt(e.target.value, 10)
          onChange(val === -1 ? null : val)
        }}
        className="appearance-none bg-transparent text-sm text-[var(--text-muted)] pr-6 cursor-pointer hover:text-[var(--text-primary)] transition-colors"
        aria-label="Subtitle track"
      >
        <option value={-1}>Off</option>
        {tracks.map((t, i) => (
          <option key={t.path} value={i}>
            {t.label}
          </option>
        ))}
      </select>
      <ChevronDown size={12} className="pointer-events-none absolute right-0 text-[var(--text-muted)]" />
    </div>
  )
}
