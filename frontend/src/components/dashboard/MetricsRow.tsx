import { useTranslation } from 'react-i18next'
import { useStats } from '@/hooks/useSystemApi'
import { useWantedSummary } from '@/hooks/useWantedApi'

interface MetricCellProps {
  readonly testId: string
  readonly value: string | number
  readonly label: string
  readonly valueColor: string
  readonly borderLeft?: boolean
}

function MetricCell({ testId, value, label, valueColor, borderLeft }: MetricCellProps) {
  return (
    <div
      role="group"
      aria-label={label}
      data-testid={testId}
      style={{
        padding: '12px 18px',
        display: 'flex',
        flexDirection: 'column',
        gap: '2px',
        borderLeft: borderLeft ? '1px solid var(--border)' : undefined,
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

  const total: string | number = isLoading ? '—' : (stats?.total_subtitles ?? '—')
  const missing: string | number = isLoading ? '—' : (wantedSummary?.total ?? '—')
  const avgScore: string | number = isLoading
    ? '—'
    : stats?.average_score != null
      ? stats.average_score.toFixed(1)
      : '—'
  const lowScore: string | number = isLoading ? '—' : (stats?.low_score_count ?? '—')

  return (
    <div
      data-testid="metrics-row"
      style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(4, 1fr)',
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
        valueColor={typeof missing === 'number' && missing > 0 ? 'var(--warning)' : 'var(--text-primary)'}
        borderLeft
      />
      <MetricCell
        testId="metric-avg-score"
        value={avgScore}
        label={t('metrics.avgScore')}
        valueColor="var(--accent)"
        borderLeft
      />
      <MetricCell
        testId="metric-low-score"
        value={lowScore}
        label={t('metrics.lowScore')}
        valueColor={typeof lowScore === 'number' && lowScore > 0 ? 'var(--upgrade, var(--accent))' : 'var(--text-primary)'}
        borderLeft
      />
    </div>
  )
}
