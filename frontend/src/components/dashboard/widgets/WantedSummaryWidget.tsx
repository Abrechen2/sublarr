/**
 * WantedSummaryWidget -- Wanted items breakdown by status.
 *
 * Self-contained: fetches own data via useWantedSummary.
 * Shows total count prominently and per-status breakdown.
 */
import { useTranslation } from 'react-i18next'
import { useWantedSummary } from '@/hooks/useApi'

export default function WantedSummaryWidget() {
  const { t } = useTranslation('dashboard')
  const { data: summary, isLoading } = useWantedSummary()

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="skeleton w-full h-24 rounded" />
      </div>
    )
  }

  const byStatus = summary?.by_status ?? {}
  const total = summary?.total ?? 0

  const statusItems: Array<{ key: string; label: string; color: string }> = [
    { key: 'wanted', label: t('stats.wanted'), color: 'var(--warning)' },
    { key: 'searching', label: t('quick_actions.searching').replace('...', ''), color: 'var(--accent)' },
    { key: 'downloaded', label: t('total_stats.translated'), color: 'var(--success)' },
    { key: 'failed', label: t('total_stats.failed'), color: 'var(--error)' },
  ]

  return (
    <div className="flex flex-col h-full">
      {/* Total count */}
      <div className="text-center mb-3">
        <div
          className="text-3xl font-bold tabular-nums"
          style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-primary)' }}
        >
          {total}
        </div>
        <div className="text-xs" style={{ color: 'var(--text-muted)' }}>
          {t('stats.wanted')}
        </div>
      </div>

      {/* Per-status breakdown */}
      <div className="space-y-1.5 flex-1">
        {statusItems.map((item) => {
          const count = (byStatus as Record<string, number>)[item.key] ?? 0
          return (
            <div
              key={item.key}
              className="flex items-center justify-between px-2.5 py-1 rounded-md"
              style={{ backgroundColor: 'var(--bg-primary)' }}
            >
              <div className="flex items-center gap-2">
                <div
                  className="w-1.5 h-1.5 rounded-full shrink-0"
                  style={{ backgroundColor: item.color }}
                />
                <span className="text-xs">{item.label}</span>
              </div>
              <span
                className="text-xs tabular-nums font-medium"
                style={{ fontFamily: 'var(--font-mono)' }}
              >
                {count}
              </span>
            </div>
          )
        })}
      </div>
    </div>
  )
}
