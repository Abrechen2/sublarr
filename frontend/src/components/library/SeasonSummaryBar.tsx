import type { EpisodeInfo } from '@/lib/types'

interface SeasonSummaryBarProps {
  season: number
  episodes: EpisodeInfo[]
  targetLanguages: string[]
}

const LOW_SCORE_THRESHOLD = 60

type EpisodeStatus = 'ok' | 'low' | 'missing'

function getEpisodeStatus(ep: EpisodeInfo, targetLanguages: string[]): EpisodeStatus {
  if (!ep.has_file) return 'ok' // no file → not applicable, don't count as missing
  if (targetLanguages.length === 0) return 'ok'

  const hasMissing = targetLanguages.some((lang) => {
    const fmt = ep.subtitles[lang]
    return fmt == null || fmt === ''
  })
  if (hasMissing) return 'missing'

  // Has subtitles — check if any target language has a low score
  const hasLowScore = targetLanguages.some((lang) => {
    const score = ep.subtitle_scores?.[lang]
    // null score treated as ok (no score recorded)
    return score !== undefined && score !== null && score < LOW_SCORE_THRESHOLD
  })

  return hasLowScore ? 'low' : 'ok'
}

export function SeasonSummaryBar({ season, episodes, targetLanguages }: SeasonSummaryBarProps) {
  const fileEpisodes = episodes.filter((ep) => ep.has_file)
  const total = fileEpisodes.length

  if (total === 0) return null

  const statuses = fileEpisodes.map((ep) => getEpisodeStatus(ep, targetLanguages))
  const okCount = statuses.filter((s) => s === 'ok').length
  const lowCount = statuses.filter((s) => s === 'low').length
  const missCount = statuses.filter((s) => s === 'missing').length

  const okPercent = total > 0 ? (okCount / total) * 100 : 0
  const lowPercent = total > 0 ? (lowCount / total) * 100 : 0
  const missPercent = total > 0 ? (missCount / total) * 100 : 0

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

      {/* 3-segment progress bar */}
      <div
        style={{
          flex: 1,
          height: '6px',
          background: 'rgba(255,255,255,0.05)',
          borderRadius: '3px',
          overflow: 'hidden',
          display: 'flex',
        }}
        title={`${okCount} ok, ${lowCount} low, ${missCount} missing`}
      >
        <div style={{ height: '100%', width: `${okPercent}%`, background: 'var(--success)' }} />
        <div style={{ height: '100%', width: `${lowPercent}%`, background: 'var(--warning)' }} />
        <div style={{ height: '100%', width: `${missPercent}%`, background: 'var(--error)', opacity: 0.7 }} />
      </div>

      {/* Legend dots + counts */}
      <div style={{ display: 'flex', gap: '12px', fontSize: '11px' }} className="flex-shrink-0">
        {okCount > 0 && (
          <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
            <span style={{ width: '6px', height: '6px', borderRadius: '50%', background: 'var(--success)', display: 'inline-block' }} />
            {okCount} OK
          </span>
        )}
        {lowCount > 0 && (
          <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
            <span style={{ width: '6px', height: '6px', borderRadius: '50%', background: 'var(--warning)', display: 'inline-block' }} />
            {lowCount} Low
          </span>
        )}
        {missCount > 0 && (
          <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
            <span style={{ width: '6px', height: '6px', borderRadius: '50%', background: 'var(--error)', display: 'inline-block' }} />
            {missCount} Missing
          </span>
        )}
      </div>
    </div>
  )
}
