/**
 * AutomationBanner — full-width card at top of dashboard.
 *
 * Left:   pulsing green dot (active) or gray dot (paused) + "Automation" title
 * Center: stats — success rate %, today's download count, needs-attention count
 * Right:  "Pause" / "Run Now" buttons
 */
import { useTranslation } from 'react-i18next'
import { cn } from '@/lib/utils'
import { useScannerStatus, useWantedSummary, useRefreshWanted } from '@/hooks/useWantedApi'
import { useStats } from '@/hooks/useSystemApi'

// ─── Types ────────────────────────────────────────────────────────────────────

interface StatCellProps {
  readonly value: number | string
  readonly label: string
  readonly testId: string
  readonly valueColor?: string
}

// ─── Sub-components ───────────────────────────────────────────────────────────

function StatCell({ value, label, testId, valueColor }: StatCellProps) {
  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        gap: '2px',
      }}
    >
      <span
        data-testid={testId}
        style={{
          fontSize: '18px',
          fontWeight: 700,
          fontFamily: 'var(--font-mono)',
          color: valueColor ?? 'var(--text-primary)',
          lineHeight: 1,
        }}
      >
        {value}
      </span>
      <span
        style={{
          fontSize: '10px',
          color: 'var(--text-muted)',
          whiteSpace: 'nowrap',
          textTransform: 'uppercase',
          letterSpacing: '0.3px',
        }}
      >
        {label}
      </span>
    </div>
  )
}

// ─── AutomationBanner ─────────────────────────────────────────────────────────

export function AutomationBanner() {
  const { t } = useTranslation(['dashboard', 'common'])
  const { data: scannerStatus } = useScannerStatus()
  const { data: stats } = useStats()
  const { data: wantedSummary } = useWantedSummary()
  const refreshWanted = useRefreshWanted()

  const isActive = Boolean(scannerStatus?.is_scanning || scannerStatus?.is_searching)

  // Extended fields not yet in Stats type definition
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const extStats = stats as any

  const successRate = extStats?.success_rate ?? 0
  const downloadsToday = extStats?.downloads_today ?? 0
  const needsAttention = wantedSummary?.total ?? 0

  return (
    <div
      data-testid="automation-banner"
      style={{
        width: '100%',
        background: 'var(--bg-surface)',
        border: '1px solid var(--border)',
        borderRadius: 'var(--radius-lg)',
        padding: '14px 20px',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        gap: '14px',
        flexWrap: 'wrap',
      }}
    >
      {/* Left: dot + title + subtitle */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '4px', flexShrink: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <span
            data-testid="status-dot"
            className={cn(
              'inline-block rounded-full',
              isActive && 'automation-pulse',
            )}
            style={{
              width: '10px',
              height: '10px',
              borderRadius: '50%',
              flexShrink: 0,
              backgroundColor: isActive ? 'var(--success)' : 'var(--text-muted)',
              color: isActive ? 'var(--success)' : 'var(--text-muted)',
              animation: isActive ? 'automationPulse 2s ease-in-out infinite' : 'none',
            }}
          />
          <span style={{ fontSize: '14px', fontWeight: 600, color: 'var(--text-primary)' }}>
            {t('automation.title')}
          </span>
        </div>
        <span
          style={{
            fontSize: '11px',
            color: 'var(--text-muted)',
            marginLeft: '20px',
          }}
        >
          Next scan in 23 min · Last completed: 7 min ago
        </span>
      </div>

      {/* Center: stats */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '24px',
          flexGrow: 1,
          justifyContent: 'center',
        }}
      >
        <StatCell
          testId="stat-success-rate"
          value={`${successRate}`}
          label={t('automation.successRate')}
          valueColor="var(--success)"
        />
        <StatCell
          testId="stat-downloads-today"
          value={downloadsToday}
          label={t('automation.today')}
        />
        <StatCell
          testId="stat-needs-attention"
          value={needsAttention}
          label={t('automation.needsAttention')}
          valueColor={needsAttention > 0 ? 'var(--warning)' : undefined}
        />
      </div>

      {/* Right: action buttons */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexShrink: 0 }}>
        <button
          data-testid="btn-pause"
          onClick={() => {
            // Pause is a no-op placeholder — config-level toggle to be wired
          }}
          style={{
            padding: '5px 11px',
            fontSize: '11px',
            fontWeight: 500,
            borderRadius: '6px',
            border: '1px solid var(--border)',
            background: 'var(--bg-primary)',
            color: 'var(--text-secondary)',
            cursor: 'pointer',
          }}
        >
          {t('automation.pause')}
        </button>

        <button
          data-testid="btn-run-now"
          onClick={() => refreshWanted.mutate(undefined)}
          disabled={refreshWanted.isPending}
          style={{
            padding: '5px 11px',
            fontSize: '11px',
            fontWeight: 600,
            borderRadius: '6px',
            border: `1px solid var(--accent)`,
            background: 'var(--accent)',
            color: '#000',
            cursor: refreshWanted.isPending ? 'not-allowed' : 'pointer',
            opacity: refreshWanted.isPending ? 0.6 : 1,
          }}
        >
          {t('automation.runNow')}
        </button>
      </div>
    </div>
  )
}

export default AutomationBanner
