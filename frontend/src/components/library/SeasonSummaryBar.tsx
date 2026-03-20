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
      className="flex items-center"
      style={{
        padding: '10px 16px',
        backgroundColor: 'var(--bg-surface)',
        border: '1px solid var(--border)',
        borderRadius: 'var(--radius-md)',
        marginBottom: '10px',
        gap: '14px',
        fontSize: '12px',
      }}
      aria-label={`Season ${season} summary`}
    >
      <span
        className="flex-shrink-0"
        style={{ color: 'var(--text-muted)' }}
      >
        Season {season} &mdash; {total} episodes
      </span>

      {/* Segmented progress bar */}
      <div
        className="flex-1 flex overflow-hidden"
        style={{
          height: '6px',
          borderRadius: '3px',
          backgroundColor: 'rgba(255,255,255,0.05)',
        }}
        title={`${ok} ok, ${missing} missing`}
      >
        {ok > 0 && (
          <div
            className="transition-all duration-500"
            style={{ width: `${okPct}%`, height: '100%', backgroundColor: 'var(--success)' }}
          />
        )}
        {missing > 0 && (
          <div
            className="transition-all duration-500"
            style={{ width: `${missingPct}%`, height: '100%', backgroundColor: 'var(--error)', opacity: 0.7 }}
          />
        )}
      </div>

      {/* Legend dots + counts */}
      <div className="flex items-center flex-shrink-0" style={{ gap: '12px', fontSize: '11px' }}>
        {ok > 0 && (
          <span className="flex items-center" style={{ gap: '4px' }}>
            <span style={{ width: '6px', height: '6px', borderRadius: '50%', backgroundColor: 'var(--success)', display: 'inline-block' }} />
            {ok} OK
          </span>
        )}
        {missing > 0 && (
          <span className="flex items-center" style={{ gap: '4px' }}>
            <span style={{ width: '6px', height: '6px', borderRadius: '50%', backgroundColor: 'var(--error)', display: 'inline-block' }} />
            {missing} Missing
          </span>
        )}
      </div>
    </div>
  )
}
