/**
 * ForeignTrackCleanupCard — what the foreign-track sweep has cleaned so far:
 * files rewritten, subtitle tracks removed, space freed (total + last 30 days)
 * and where the sweep currently is.
 */
import { useTranslation } from 'react-i18next'
import { Loader2 } from 'lucide-react'
import { useStatForeignTracks } from '@/hooks/useStatistics'
import { formatBytes } from '@/lib/diskUtils'
import { StatTile } from '@/components/statistics/primitives'

export function ForeignTrackCleanupCard() {
  const { t } = useTranslation('statistics')
  const { data, isLoading, isError } = useStatForeignTracks()

  if (isLoading) {
    return (
      <div role="status" aria-label={t('track_cleanup.loading')} className="flex items-center justify-center h-20 text-muted">
        <Loader2 size={16} className="animate-spin" />
      </div>
    )
  }

  if (isError || !data) {
    return <p className="text-xs text-muted">{t('track_cleanup.error')}</p>
  }

  const phaseTile = (
    <StatTile
      label={t('track_cleanup.phase_label')}
      value={t(`track_cleanup.phase.${data.phase}`)}
      sub={data.paused_reason ? `${t('track_cleanup.paused')}: ${data.paused_reason}` : undefined}
    />
  )

  if (data.files_stripped === 0 && data.bytes_freed_total === 0) {
    return (
      <div className="grid grid-cols-1 md:grid-cols-4 gap-2">
        <div className="md:col-span-3 rounded-lg p-3 bg-surface border border-border flex items-center text-xs text-muted">
          {t('track_cleanup.empty')}
        </div>
        {phaseTile}
      </div>
    )
  }

  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
      <StatTile label={t('track_cleanup.files')} value={data.files_stripped.toLocaleString()} />
      <StatTile label={t('track_cleanup.tracks')} value={data.tracks_removed.toLocaleString()} />
      <StatTile
        label={t('track_cleanup.freed')}
        value={formatBytes(data.bytes_freed_total)}
        sub={`${t('track_cleanup.freed_30d')}: ${formatBytes(data.bytes_freed_30d)}`}
      />
      {phaseTile}
    </div>
  )
}
