import { useTranslation } from 'react-i18next'
import { useStats } from '@/hooks/useSystemApi'
import { useWantedSummary } from '@/hooks/useWantedApi'
import { formatNumber } from '@/lib/utils'

interface MetricCellProps {
  readonly testId: string
  readonly value: string | number
  readonly label: string
  readonly valueColor: string
  /** Responsive border classes — the grid is 2×2 on phones and 1×4 on md+. */
  readonly className?: string
}

function MetricCell({ testId, value, label, valueColor, className }: MetricCellProps) {
  return (
    <div
      role="group"
      aria-label={label}
      data-testid={testId}
      className={className}
      style={{
        padding: '12px 18px',
        display: 'flex',
        flexDirection: 'column',
        gap: '2px',
      }}
    >
      <span
        data-testid={`${testId}-value`}
        style={{
          fontSize: '22px',
          fontWeight: 700,
          letterSpacing: '-0.5px',
          color: valueColor,
          lineHeight: 1,
          fontFamily: 'var(--font-mono)',
        }}
      >
        {value}
      </span>
      <span
        style={{
          fontSize: '10px',
          color: 'var(--text-muted)',
          textTransform: 'uppercase',
          letterSpacing: '0.4px',
        }}
      >
        {label}
      </span>
    </div>
  )
}

export function MetricsRow() {
  const { t } = useTranslation('dashboard')
  const { data: stats, isLoading: statsLoading } = useStats()
  const { data: wantedSummary, isLoading: wantedLoading } = useWantedSummary()

  const isLoading = statsLoading || wantedLoading

  const missingNum = wantedSummary?.total
  const lowScoreNum = stats?.low_score_count

  const total: string | number = isLoading ? '—' : formatNumber(stats?.total_subtitles)
  const missing: string | number = isLoading ? '—' : formatNumber(missingNum)
  const avgScore: string | number = isLoading
    ? '—'
    : stats?.average_score != null
      ? stats.average_score.toFixed(1)
      : '—'
  const lowScore: string | number = isLoading ? '—' : formatNumber(lowScoreNum)

  return (
    <div
      data-testid="metrics-row"
      className="grid grid-cols-2 md:grid-cols-4"
      style={{
        background: 'var(--bg-surface)',
        border: '1px solid var(--border)',
        borderRadius: 'var(--radius-lg)',
        overflow: 'hidden',
      }}
    >
      <MetricCell
        testId="metric-total"
        value={total}
        label={t('metrics.total')}
        valueColor="var(--text-primary)"
      />
      <MetricCell
        testId="metric-missing"
        value={missing}
        label={t('metrics.missing')}
        valueColor={(missingNum ?? 0) > 0 ? 'var(--warning)' : 'var(--text-primary)'}
        className="border-l border-border"
      />
      <MetricCell
        testId="metric-avg-score"
        value={avgScore}
        label={t('metrics.avgScore')}
        valueColor="var(--accent)"
        className="border-t border-border md:border-t-0 md:border-l"
      />
      <MetricCell
        testId="metric-low-score"
        value={lowScore}
        label={t('metrics.lowScore')}
        valueColor={(lowScoreNum ?? 0) > 0 ? 'var(--upgrade, var(--accent))' : 'var(--text-primary)'}
        className="border-l border-t border-border md:border-t-0"
      />
    </div>
  )
}
