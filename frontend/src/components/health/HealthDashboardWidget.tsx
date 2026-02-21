import { ShieldCheck } from 'lucide-react'
import { LineChart, Line, ResponsiveContainer } from 'recharts'
import { useTranslation } from 'react-i18next'
import { useQualityTrends } from '@/hooks/useApi'
import { HealthBadge } from './HealthBadge'

interface HealthDashboardWidgetProps {
  className?: string
}

function SkeletonWidget() {
  return (
    <div
      className="rounded-lg p-4"
      style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)' }}
    >
      <div className="flex items-center gap-2 mb-3">
        <div className="skeleton w-4 h-4 rounded" />
        <div className="skeleton h-3 w-28 rounded" />
      </div>
      <div className="flex items-center gap-4 mb-3">
        <div className="skeleton h-8 w-12 rounded" />
        <div className="skeleton h-3 w-20 rounded" />
        <div className="skeleton h-3 w-20 rounded" />
      </div>
      <div className="skeleton h-[80px] w-full rounded" />
    </div>
  )
}

export function HealthDashboardWidget({ className }: HealthDashboardWidgetProps) {
  const { t } = useTranslation('dashboard')
  const { data, isLoading } = useQualityTrends(30)

  if (isLoading) {
    return <SkeletonWidget />
  }

  const trends = data?.trends ?? []

  if (trends.length === 0) {
    return (
      <div
        className={`rounded-lg p-4 ${className ?? ''}`}
        style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)' }}
      >
        <div className="flex items-center gap-2 mb-3">
          <ShieldCheck size={14} style={{ color: 'var(--accent)' }} />
          <span
            className="text-xs font-semibold uppercase tracking-wider"
            style={{ color: 'var(--text-muted)' }}
          >
            {t('widgets.quality')}
          </span>
        </div>
        <div className="text-xs text-center py-4" style={{ color: 'var(--text-muted)' }}>
          {t('widgets.quality_no_data')}
        </div>
      </div>
    )
  }

  // Compute summary from latest data point
  const latest = trends[trends.length - 1]
  const totalIssues = trends.reduce((sum, t) => sum + t.issues_count, 0)
  const totalChecked = trends.reduce((sum, t) => sum + t.files_checked, 0)

  return (
    <div
      className={`rounded-lg p-4 transition-all duration-200 hover:shadow-md ${className ?? ''}`}
      style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)' }}
    >
      {/* Header */}
      <div className="flex items-center gap-2 mb-3">
        <ShieldCheck size={14} style={{ color: 'var(--accent)' }} />
        <span
          className="text-xs font-semibold uppercase tracking-wider"
          style={{ color: 'var(--text-muted)' }}
        >
          {t('widgets.quality')}
        </span>
      </div>

      {/* Summary row */}
      <div className="flex items-center gap-4 mb-3">
        <div className="flex items-center gap-2">
          <span
            className="text-2xl font-bold tabular-nums"
            style={{ fontFamily: 'var(--font-mono)' }}
          >
            {Math.round(latest.avg_score)}
          </span>
          <HealthBadge score={Math.round(latest.avg_score)} size="sm" />
        </div>
        <div className="text-xs space-y-0.5" style={{ color: 'var(--text-secondary)' }}>
          <div>
            <span style={{ fontFamily: 'var(--font-mono)' }}>{totalChecked}</span>{' '}
            {t('widgets.quality_files_checked')}
          </div>
          <div>
            <span
              style={{
                fontFamily: 'var(--font-mono)',
                color: totalIssues > 0 ? 'var(--warning)' : 'inherit',
              }}
            >
              {totalIssues}
            </span>{' '}
            {t('widgets.quality_issues_found')}
          </div>
        </div>
      </div>

      {/* Mini sparkline */}
      <ResponsiveContainer width="100%" height={80}>
        <LineChart data={trends}>
          <Line
            type="monotone"
            dataKey="avg_score"
            stroke="var(--accent)"
            strokeWidth={2}
            dot={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}
