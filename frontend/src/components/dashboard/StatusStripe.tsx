import { useTranslation } from 'react-i18next'
import { useScannerStatus, useWantedSummary, useRefreshWanted } from '@/hooks/useWantedApi'
import { useStats } from '@/hooks/useSystemApi'
import { formatRelativeTime } from '@/lib/utils'

export function StatusStripe() {
  const { t } = useTranslation('dashboard')
  const { data: scannerStatus } = useScannerStatus()
  const { data: stats } = useStats()
  const { data: wantedSummary } = useWantedSummary()
  const refreshWanted = useRefreshWanted()

  const isActive = Boolean(scannerStatus?.is_scanning || scannerStatus?.is_searching)
  const lastActivity = scannerStatus?.last_scan_at ?? scannerStatus?.last_search_at ?? null
  const lastText = lastActivity
    ? `${t('statusStripe.lastScan')}: ${formatRelativeTime(lastActivity)}`
    : t('statusStripe.neverScanned')

  const missingCount = wantedSummary?.total ?? 0

  return (
    <div
      data-testid="status-stripe"
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: '16px',
        padding: '7px 18px',
        background: 'var(--bg-surface)',
        border: '1px solid var(--border)',
        borderRadius: 'var(--radius-lg)',
        flexWrap: 'wrap',
      }}
    >
      {/* Status dot + label */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
        <span
          data-testid="status-dot"
          className={isActive ? 'automation-pulse' : undefined}
          style={{
            width: 7,
            height: 7,
            borderRadius: '50%',
            flexShrink: 0,
            backgroundColor: isActive ? 'var(--success)' : 'var(--text-muted)',
          }}
        />
        <span
          data-testid="status-label"
          style={{
            fontSize: '11px',
            fontWeight: 700,
            letterSpacing: '0.5px',
            color: isActive ? 'var(--success)' : 'var(--text-muted)',
          }}
        >
          {isActive ? t('statusStripe.active') : t('statusStripe.paused')}
        </span>
      </div>

      <span
        data-testid="status-last"
        style={{ fontSize: '11px', color: 'var(--text-muted)' }}
      >
        {lastText}
      </span>

      <div style={{ width: 1, height: 14, background: 'var(--border)', flexShrink: 0 }} />

      <span data-testid="status-total" style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>
        <strong style={{ color: 'var(--text-primary)' }}>{stats?.total_subtitles ?? '—'}</strong>{' '}
        {t('statusStripe.subtitles')}
      </span>

      <span data-testid="status-rate" style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>
        <strong style={{ color: 'var(--success)' }}>{stats?.success_rate ?? '—'}%</strong>{' '}
        {t('statusStripe.successRate')}
      </span>

      <span data-testid="status-today" style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>
        <strong style={{ color: 'var(--accent)' }}>+{stats?.downloads_today ?? 0}</strong>{' '}
        {t('statusStripe.today')}
      </span>

      <span data-testid="status-missing" style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>
        <strong style={{ color: missingCount > 0 ? 'var(--warning)' : 'var(--text-primary)' }}>
          {missingCount}
        </strong>{' '}
        {t('statusStripe.missing')}
      </span>

      <div style={{ marginLeft: 'auto' }}>
        <button
          data-testid="btn-run-now"
          onClick={() => refreshWanted.mutate(undefined)}
          disabled={refreshWanted.isPending}
          style={{
            padding: '4px 12px',
            fontSize: '11px',
            fontWeight: 600,
            borderRadius: '6px',
            border: '1px solid var(--accent)',
            background: 'var(--accent)',
            color: 'var(--bg-primary)',
            cursor: refreshWanted.isPending ? 'not-allowed' : 'pointer',
            opacity: refreshWanted.isPending ? 0.6 : 1,
          }}
        >
          {t('statusStripe.runNow')}
        </button>
      </div>
    </div>
  )
}
