import { FileVideo, RefreshCw, Settings, Loader2, Sparkles, FileText } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import type { TFunction } from 'i18next'
import type { SeriesDetail } from '@/lib/types'

interface SeriesHeroProps {
  readonly series: SeriesDetail
  readonly missingCount: number
  readonly withSubsCount: number
  readonly lowScoreCount: number
  readonly isMissingSearchPending: boolean
  readonly missingSearchStarted: boolean
  readonly onSearchAllMissing: () => void
  readonly onRescan: () => void
  readonly isRescanning?: boolean
  readonly onNfoExport?: () => void
  readonly onSeriesSettings: () => void
}

function buildMetaTags(series: SeriesDetail, t: TFunction<'library'>): string[] {
  const tags: string[] = []
  const knownGenres = ['anime', 'fantasy', 'action', 'drama', 'comedy', 'sci-fi', 'thriller']
  for (const tag of (series.tags ?? [])) {
    const lower = tag.toLowerCase()
    if (knownGenres.includes(lower)) {
      tags.push(tag.charAt(0).toUpperCase() + tag.slice(1))
    }
  }
  // Season count (regular seasons only — specials/season 0 are not counted)
  if ((series.season_count ?? 0) > 0) {
    tags.push(t('series_detail.season_count', { count: series.season_count }))
  }
  // Format preference — infer from profile name
  const profile = (series.profile_name ?? '').toLowerCase()
  if (profile.includes('ass')) tags.push('ASS preferred')
  else if (profile.includes('srt')) tags.push('SRT preferred')
  return tags
}

export function SeriesHero({
  series,
  missingCount,
  withSubsCount,
  lowScoreCount,
  isMissingSearchPending,
  missingSearchStarted,
  onSearchAllMissing,
  onRescan,
  isRescanning = false,
  onNfoExport,
  onSeriesSettings,
}: SeriesHeroProps) {
  const { t } = useTranslation('library')
  const totalEps = series.episode_file_count ?? 0
  const metaTags = buildMetaTags(series, t)

  return (
    <div
      className="rounded-lg overflow-hidden relative"
      style={{ border: '1px solid var(--border)', marginBottom: '16px' }}
    >
      {/* Fanart background */}
      {series.fanart && (
        <div
          className="absolute inset-0"
          style={{
            backgroundImage: `url(${series.fanart})`,
            backgroundSize: 'cover',
            backgroundPosition: 'center',
            opacity: 0.15,
            filter: 'blur(2px)',
          }}
        />
      )}
      <div
        className="absolute inset-0"
        style={{
          background:
            'linear-gradient(135deg, rgba(23,25,35,0.95) 0%, rgba(30,33,48,0.85) 100%)',
        }}
      />

      <div className="relative flex gap-6 p-5">
        {/* Poster */}
        <div
          className="flex-shrink-0 rounded-lg overflow-hidden shadow-lg"
          style={{
            width: '180px',
            minWidth: '180px',
            aspectRatio: '2/3',
            border: '1px solid var(--border)',
          }}
        >
          {series.poster ? (
            <img
              src={series.poster}
              alt={series.title}
              className="w-full h-full object-cover"
            />
          ) : (
            <div
              className="w-full h-full flex items-center justify-center"
              style={{ backgroundColor: 'var(--bg-surface)' }}
            >
              <FileVideo size={32} style={{ color: 'var(--text-muted)' }} />
            </div>
          )}
        </div>

        {/* Info */}
        <div className="flex-1 min-w-0 flex flex-col gap-3">
          {/* Title + year */}
          <div className="flex items-center gap-2.5">
            <h1
              data-testid="series-title"
              style={{ fontSize: '24px', fontWeight: 700, letterSpacing: '-0.5px' }}
            >
              {series.title}
            </h1>
            {series.year && (
              <span className="text-sm" style={{ color: 'var(--text-muted)', fontWeight: 400 }}>
                {series.year}
              </span>
            )}
          </div>

          {/* Meta tags row */}
          <div className="flex flex-wrap gap-1.5">
            {metaTags.map((tag) => (
              <span
                key={tag}
                style={{
                  padding: '3px 10px',
                  borderRadius: '6px',
                  fontSize: '11px',
                  fontWeight: 500,
                  backgroundColor: 'var(--bg-elevated)',
                  border: '1px solid var(--border)',
                  color: 'var(--text-secondary)',
                }}
              >
                {tag}
              </span>
            ))}
          </div>

          {/* Stat boxes */}
          <div
            style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '10px' }}
          >
            {(
              [
                { label: 'Episodes', value: totalEps, color: 'var(--accent)' },
                { label: 'With Subs', value: withSubsCount, color: 'var(--success)' },
                {
                  label: 'Missing',
                  value: missingCount,
                  color: missingCount > 0 ? 'var(--error)' : 'var(--success)',
                },
                {
                  label: 'Low Score',
                  value: lowScoreCount,
                  color: lowScoreCount > 0 ? 'var(--warning)' : 'var(--text-muted)',
                },
              ] as const
            ).map(({ label, value, color }) => (
              <div
                key={label}
                className="flex flex-col items-center text-center"
                style={{
                  backgroundColor: 'var(--bg-surface)',
                  border: '1px solid var(--border)',
                  borderRadius: 'var(--radius-md)',
                  padding: '10px 14px',
                }}
              >
                <span
                  style={{
                    fontSize: '20px',
                    fontWeight: 700,
                    color,
                    fontFamily: 'var(--font-mono)',
                  }}
                  className="tabular-nums"
                >
                  {value}
                </span>
                <span
                  style={{
                    fontSize: '10px',
                    color: 'var(--text-muted)',
                    textTransform: 'uppercase',
                    letterSpacing: '0.3px',
                    marginTop: '2px',
                  }}
                >
                  {label}
                </span>
              </div>
            ))}
          </div>

          {/* Action buttons — exactly 3 as per mockup */}
          <div className="flex flex-wrap gap-2">
            <button
              onClick={onSearchAllMissing}
              disabled={isMissingSearchPending || missingSearchStarted || missingCount === 0}
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '6px',
                padding: '7px 14px',
                borderRadius: '6px',
                fontSize: '13px',
                fontWeight: 600,
                backgroundColor: missingSearchStarted
                  ? 'var(--success-bg)'
                  : 'var(--accent)',
                color: missingSearchStarted ? 'var(--success)' : '#fff',
                border: 'none',
                cursor: missingCount === 0 ? 'default' : 'pointer',
                opacity: isMissingSearchPending || missingCount === 0 ? 0.6 : 1,
              }}
            >
              {isMissingSearchPending ? (
                <Loader2 size={13} className="animate-spin" />
              ) : missingSearchStarted ? (
                <Sparkles size={13} />
              ) : (
                '⚡'
              )}
              {missingSearchStarted ? t('series_detail.searching') : t('series_detail.search_all_missing')}
            </button>

            <button
              onClick={onRescan}
              disabled={isRescanning}
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '6px',
                padding: '7px 14px',
                borderRadius: '6px',
                fontSize: '13px',
                fontWeight: 500,
                backgroundColor: 'var(--bg-elevated)',
                color: 'var(--text-secondary)',
                border: '1px solid var(--border)',
                cursor: isRescanning ? 'not-allowed' : 'pointer',
                opacity: isRescanning ? 0.6 : 1,
              }}
            >
              {isRescanning ? (
                <Loader2 size={13} className="animate-spin" />
              ) : (
                <RefreshCw size={13} />
              )}
              {t('series_detail.rescan_series')}
            </button>

            {onNfoExport && (
              <button
                onClick={onNfoExport}
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '6px',
                  padding: '7px 14px',
                  borderRadius: '6px',
                  fontSize: '13px',
                  fontWeight: 500,
                  backgroundColor: 'var(--bg-elevated)',
                  color: 'var(--text-secondary)',
                  border: '1px solid var(--border)',
                  cursor: 'pointer',
                }}
              >
                <FileText size={13} />
                {t('series_detail.nfo_export')}
              </button>
            )}

            <button
              onClick={onSeriesSettings}
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '6px',
                padding: '7px 14px',
                borderRadius: '6px',
                fontSize: '13px',
                fontWeight: 500,
                backgroundColor: 'var(--bg-elevated)',
                color: 'var(--text-secondary)',
                border: '1px solid var(--border)',
                cursor: 'pointer',
              }}
            >
              <Settings size={13} />
              {t('series_detail.series_settings')}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
