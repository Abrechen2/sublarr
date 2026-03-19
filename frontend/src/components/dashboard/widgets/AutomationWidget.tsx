/**
 * AutomationWidget — shows automation status, today's stats, and a Run Now button.
 *
 * Exports both:
 * - `AutomationWidget` (presentational, props-driven — for testing)
 * - `default` (connected to hooks, for the widget registry)
 */
import { Zap, ZapOff, Loader2 } from 'lucide-react'
import { useConfig, useWantedSummary, useRefreshWanted } from '@/hooks/useApi'

// ─── Types ────────────────────────────────────────────────────────────────────

interface WantedSummaryData {
  wanted_count: number
  found_today: number
  failed_today: number
  last_search_at: string | null
}

interface AutomationWidgetProps {
  enabled: boolean
  intervalHours: number
  summary: WantedSummaryData
  onRunNow: () => void
  isRunning: boolean
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

function formatTimeAgo(iso: string | null): string {
  if (!iso) return 'Never'
  const diff = Date.now() - new Date(iso).getTime()
  const m = Math.floor(diff / 60_000)
  if (m < 1) return 'Just now'
  if (m < 60) return `${m}m ago`
  const h = Math.floor(m / 60)
  return h < 24 ? `${h}h ago` : `${Math.floor(h / 24)}d ago`
}

function formatNextRun(lastIso: string | null, hours: number): string {
  if (!lastIso) return 'Soon'
  const diff = new Date(lastIso).getTime() + hours * 3_600_000 - Date.now()
  if (diff <= 0) return 'Overdue'
  const m = Math.floor(diff / 60_000)
  if (m < 60) return `in ${m}m`
  const h = Math.floor(m / 60)
  const rem = m % 60
  return rem > 0 ? `in ${h}h ${rem}m` : `in ${h}h`
}

// ─── Presentational component (testable) ──────────────────────────────────────

export function AutomationWidget({
  enabled, intervalHours, summary, onRunNow, isRunning,
}: AutomationWidgetProps) {
  const statusColor = enabled ? 'var(--success)' : 'var(--text-muted)'
  const StatusIcon = enabled ? Zap : ZapOff

  return (
    <div style={{
      background: 'var(--bg-secondary)', border: '1px solid var(--border)',
      borderRadius: '8px', padding: '14px 16px',
      display: 'flex', flexDirection: 'column', gap: '12px',
    }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <StatusIcon size={15} style={{ color: statusColor }} />
          <span style={{ fontSize: '13px', fontWeight: 600 }}>Automation</span>
          <span style={{
            fontSize: '11px', padding: '1px 7px', borderRadius: '9999px',
            background: enabled
              ? 'color-mix(in srgb, var(--success) 12%, transparent)'
              : 'color-mix(in srgb, var(--text-muted) 12%, transparent)',
            color: statusColor,
            border: `1px solid ${enabled ? 'var(--success)' : 'var(--border)'}`,
          }}>
            {enabled ? 'Active' : 'Disabled'}
          </span>
        </div>
        <button
          onClick={onRunNow}
          disabled={isRunning || !enabled}
          aria-label={isRunning ? 'Searching\u2026' : 'Run now'}
          style={{
            display: 'flex', alignItems: 'center', gap: '5px',
            padding: '4px 10px', fontSize: '12px', borderRadius: '5px',
            border: '1px solid var(--border)', background: 'var(--bg-primary)',
            color: 'var(--text-secondary)',
            cursor: isRunning || !enabled ? 'not-allowed' : 'pointer',
            opacity: isRunning || !enabled ? 0.5 : 1,
          }}
        >
          {isRunning
            ? <><Loader2 size={12} className="animate-spin" /> Searching\u2026</>
            : <>Run now</>}
        </button>
      </div>

      {/* Stats */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '8px' }}>
        {[
          { label: 'Found today',  value: summary.found_today,  color: 'var(--success)' },
          { label: 'Failed today', value: summary.failed_today, color: summary.failed_today > 0 ? 'var(--error)' : 'var(--text-muted)' },
          { label: 'Wanted',       value: summary.wanted_count, color: 'var(--text-muted)' },
        ].map(({ label, value, color }) => (
          <div key={label} style={{
            background: 'var(--bg-primary)', border: '1px solid var(--border)',
            borderRadius: '6px', padding: '8px 10px', textAlign: 'center',
          }}>
            <div style={{ fontSize: '18px', fontWeight: 700, fontFamily: 'var(--font-mono)', color }}>
              {value}
            </div>
            <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: '2px' }}>{label}</div>
          </div>
        ))}
      </div>

      {/* Last/next run */}
      {enabled && (
        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '12px', color: 'var(--text-muted)' }}>
          <span>Last: {formatTimeAgo(summary.last_search_at)}</span>
          <span>Next: {formatNextRun(summary.last_search_at, intervalHours)}</span>
        </div>
      )}
    </div>
  )
}

// ─── Connected component (used by widget registry) ────────────────────────────

export default function AutomationWidgetConnected() {
  const { data: config } = useConfig()
  const { data: summary } = useWantedSummary()
  const refresh = useRefreshWanted()

  const enabled = config?.automation_enabled === 'true' || config?.automation_enabled === '1'
  const intervalHours = parseInt(config?.search_interval_hours ?? '6', 10)

  return (
    <AutomationWidget
      enabled={enabled}
      intervalHours={intervalHours}
      summary={summary ?? { wanted_count: 0, found_today: 0, failed_today: 0, last_search_at: null }}
      onRunNow={() => refresh.mutate()}
      isRunning={refresh.isPending}
    />
  )
}
