import type { EpisodeInfo } from '@/lib/types'

interface SeasonSummaryBarProps {
  season: number
  episodes: EpisodeInfo[]
  targetLanguages: string[]
}

type EpisodeStatus = 'ok' | 'missing'

function getEpisodeStatus(ep: EpisodeInfo, targetLanguages: string[]): EpisodeStatus {
  if (!ep.has_file) return 'ok' // no file → not applicable, don't count as missing
  if (targetLanguages.length === 0) return 'ok'
  const hasMissing = targetLanguages.some((lang) => {
    const fmt = ep.subtitles[lang]
    return fmt == null || fmt === ''
  })
  return hasMissing ? 'missing' : 'ok'
}

export function SeasonSummaryBar({ season, episodes, targetLanguages }: SeasonSummaryBarProps) {
  const fileEpisodes = episodes.filter((ep) => ep.has_file)
  const total = fileEpisodes.length

  if (total === 0) return null

  const missing = fileEpisodes.filter(
    (ep) => getEpisodeStatus(ep, targetLanguages) === 'missing'
  ).length
  const ok = total - missing

  const okPct = total > 0 ? (ok / total) * 100 : 0
  const missingPct = total > 0 ? (missing / total) * 100 : 0

  return (
    <div
      className="flex items-center gap-3 px-4 py-2"
      style={{ borderBottom: '1px solid var(--border)' }}
      aria-label={`Season ${season} summary`}
    >
      <span
        className="text-[11px] font-semibold uppercase tracking-wider flex-shrink-0 w-20"
        style={{ color: 'var(--text-muted)' }}
      >
        S{String(season).padStart(2, '0')} subs
      </span>

      {/* Segmented progress bar */}
      <div
        className="flex-1 h-2 rounded-full overflow-hidden flex"
        style={{ backgroundColor: 'var(--bg-primary)' }}
        title={`${ok} ok, ${missing} missing`}
      >
        {ok > 0 && (
          <div
            className="h-full transition-all duration-500"
            style={{ width: `${okPct}%`, backgroundColor: 'var(--success)' }}
          />
        )}
        {missing > 0 && (
          <div
            className="h-full transition-all duration-500"
            style={{ width: `${missingPct}%`, backgroundColor: 'var(--error)' }}
          />
        )}
      </div>

      {/* Counts */}
      <div className="flex items-center gap-2 flex-shrink-0 text-[11px] font-medium tabular-nums">
        {ok > 0 && (
          <span style={{ color: 'var(--success)' }} title="With subtitles">
            {ok} ok
          </span>
        )}
        {missing > 0 && (
          <span style={{ color: 'var(--error)' }} title="Missing subtitles">
            {missing} missing
          </span>
        )}
      </div>
    </div>
  )
}
