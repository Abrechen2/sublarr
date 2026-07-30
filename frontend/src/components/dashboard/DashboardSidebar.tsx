import React from 'react'
import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import {
  useProviders,
  useHealth,
  useDetailedHealth,
  useCleanupStats,
  useRefreshWanted,
  useStartWantedBatch,
  useWantedBatchStatus,
  useWantedSummary,
} from '@/hooks/useApi'
import type { DetailedSubsystem } from '@/api/health'
import { formatBytes } from '@/lib/diskUtils'
import { formatProviderName, formatNumber } from '@/lib/utils'

// ─── Shared panel shell ───────────────────────────────────────────────────────

interface PanelProps {
  readonly testId: string
  readonly title: string
  readonly children: React.ReactNode
}

function Panel({ testId, title, children }: PanelProps) {
  return (
    <div
      data-testid={testId}
      style={{
        padding: '10px 14px',
        borderBottom: '1px solid var(--border)',
      }}
    >
      <div
        style={{
          fontSize: '9px',
          fontWeight: 700,
          color: 'var(--text-muted)',
          textTransform: 'uppercase',
          letterSpacing: '0.5px',
          marginBottom: '8px',
        }}
      >
        {title}
      </div>
      {children}
    </div>
  )
}

// ─── Provider Health Panel ────────────────────────────────────────────────────

interface ProviderStatus {
  name: string
  enabled: boolean
  healthy: boolean
  stats?: { success_rate?: number; auto_disabled?: boolean }
  circuit_breaker_state?: string
  throttled_until?: string | null
  throttle_reason?: string | null
}

function getProviderVisual(p: ProviderStatus): {
  dot: string
  dotColor: string
  label: string
  labelColor: string
  sortKey: number
} {
  const cbState = p.circuit_breaker_state ?? 'closed'
  const isThrottled = !!p.throttled_until
  const isAutoDisabled = !!p.stats?.auto_disabled

  if (isAutoDisabled || (p.throttle_reason === 'auto_disabled')) {
    return { dot: '✕', dotColor: 'var(--error)', label: 'Disabled', labelColor: 'var(--error)', sortKey: 0 }
  }
  if (cbState === 'open') {
    return { dot: '◆', dotColor: 'var(--warning)', label: 'Circuit Open', labelColor: 'var(--warning)', sortKey: 1 }
  }
  if (isThrottled && p.throttle_reason === 'rate_limited') {
    return { dot: '◆', dotColor: 'var(--warning)', label: '', labelColor: 'var(--warning)', sortKey: 2 }
  }
  if (cbState === 'half_open') {
    return { dot: '◆', dotColor: 'var(--warning)', label: 'Recovering', labelColor: 'var(--warning)', sortKey: 3 }
  }

  // Dot color reflects connectivity health (reachable, no failure streak) —
  // NOT the lifetime download-conversion rate. A provider with few downloads
  // is still "green" as long as it responds; the percentage is shown as a
  // separate, tooltipped figure.
  const pct = Math.round((p.stats?.success_rate ?? 0) * 100)
  const isHealthy = p.healthy !== false
  return {
    dot: '●',
    dotColor: isHealthy ? 'var(--success)' : 'var(--error)',
    label: `${pct}%`,
    labelColor: 'var(--text-muted)',
    sortKey: isHealthy ? 10 : 5,
  }
}

function ThrottleCountdown({ until }: { until: string }) {
  const [remaining, setRemaining] = React.useState(0)

  React.useEffect(() => {
    const target = new Date(until).getTime()
    const tick = () => setRemaining(Math.max(0, Math.round((target - Date.now()) / 1000)))
    tick()
    const id = setInterval(tick, 1000)
    return () => clearInterval(id)
  }, [until])

  if (remaining <= 0) return null
  return <span style={{ fontSize: '11px', color: 'var(--warning)' }}>Throttled {remaining}s</span>
}

function ProviderHealthPanel() {
  const { t } = useTranslation('dashboard')
  const { data: providersData, isLoading } = useProviders()
  const allEnabled = (providersData?.providers ?? []).filter((p: ProviderStatus) => p.enabled) as ProviderStatus[]

  // Sort: problems first, then by success rate descending. Show ALL enabled
  // providers — a hidden tail made the panel disagree with the Services
  // panel's "N/N active" count.
  const providers = [...allEnabled].sort((a, b) => {
    const va = getProviderVisual(a)
    const vb = getProviderVisual(b)
    if (va.sortKey !== vb.sortKey) return va.sortKey - vb.sortKey
    return ((b.stats?.success_rate ?? 0) - (a.stats?.success_rate ?? 0))
  })

  if (isLoading) {
    return (
      <Panel testId="panel-providers" title={t('sidebar.providers')}>
        {[1, 2, 3].map((i) => (
          <div
            key={i}
            style={{
              height: '16px',
              background: 'var(--bg-secondary)',
              borderRadius: '4px',
              marginBottom: '4px',
            }}
          />
        ))}
      </Panel>
    )
  }

  return (
    <Panel testId="panel-providers" title={t('sidebar.providers')}>
      {providers.map((p) => {
        const vis = getProviderVisual(p)
        return (
          <div
            key={p.name}
            style={{ display: 'flex', alignItems: 'center', gap: '7px', marginBottom: '5px' }}
          >
            <span
              data-testid={`provider-dot-${p.name}`}
              data-healthy={String(p.healthy)}
              style={{
                width: vis.dot === '●' ? 6 : 'auto',
                height: vis.dot === '●' ? 6 : 'auto',
                borderRadius: vis.dot === '●' ? '50%' : undefined,
                background: vis.dot === '●' ? vis.dotColor : undefined,
                color: vis.dotColor,
                fontSize: vis.dot !== '●' ? '10px' : undefined,
                lineHeight: 1,
                flexShrink: 0,
              }}
            >
              {vis.dot !== '●' ? vis.dot : ''}
            </span>
            <span style={{ flex: 1, fontSize: '12px', color: 'var(--text-secondary)' }}>
              {formatProviderName(p.name)}
            </span>
            {p.throttled_until && p.throttle_reason === 'rate_limited' ? (
              <ThrottleCountdown until={p.throttled_until} />
            ) : (
              <span
                style={{ fontSize: '11px', color: vis.labelColor }}
                title={vis.label.endsWith('%') ? t('sidebar.successRateTooltip') : undefined}
              >
                {vis.label}
              </span>
            )}
          </div>
        )
      })}
    </Panel>
  )
}

// ─── Service Status Panel ─────────────────────────────────────────────────────

function formatServiceName(key: string): string {
  const name = key.includes(':') ? key.split(':').slice(1).join(':') : key
  return name.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
}

function ServiceStatusPanel() {
  const { t } = useTranslation('dashboard')
  const { data: health, isLoading } = useHealth()

  if (isLoading || !health?.services) {
    return (
      <Panel testId="panel-services" title={t('sidebar.services')}>
        {[1, 2, 3].map((i) => (
          <div
            key={i}
            style={{
              height: '16px',
              background: 'var(--bg-secondary)',
              borderRadius: '4px',
              marginBottom: '4px',
            }}
          />
        ))}
      </Panel>
    )
  }

  return (
    <Panel testId="panel-services" title={t('sidebar.services')}>
      {Object.entries(health.services as Record<string, string>).map(([name, status]) => {
        const isNotConfigured = status === 'not configured'
        const isError =
          !isNotConfigured &&
          ['error', 'fail', 'failed', 'disconnected'].includes(status as string)
        const isOk = !isNotConfigured && !isError
        const dotColor = isOk
          ? 'var(--success)'
          : isNotConfigured
            ? 'var(--text-muted)'
            : 'var(--error)'

        return (
          <div
            key={name}
            style={{ display: 'flex', alignItems: 'center', gap: '7px', marginBottom: '5px' }}
          >
            <span
              data-testid={`service-dot-${name}`}
              style={{
                width: 6,
                height: 6,
                borderRadius: '50%',
                background: dotColor,
                flexShrink: 0,
              }}
            />
            <span style={{ flex: 1, fontSize: '12px', color: 'var(--text-secondary)' }}>
              {formatServiceName(name)}
            </span>
            <span
              style={{ fontSize: '11px', color: isOk ? 'var(--text-muted)' : 'var(--error)' }}
            >
              {isNotConfigured ? '—' : typeof status === 'string' ? status : 'OK'}
            </span>
          </div>
        )
      })}
    </Panel>
  )
}

// ─── System Health Panel (from /health/detailed) ─────────────────────────────

interface HealthRow {
  key: string
  label: string
  healthy: boolean
  detail: string
}

function buildHealthRows(
  subsystems: Record<string, DetailedSubsystem>,
  t: (key: string, opts?: Record<string, unknown>) => string,
): HealthRow[] {
  const rows: HealthRow[] = []

  const db = subsystems.database
  if (db) {
    rows.push({
      key: 'database',
      label: t('sidebar.healthDatabase'),
      healthy: db.healthy,
      detail: db.healthy
        ? [db.backend, db.size_bytes ? formatBytes(db.size_bytes) : '']
            .filter(Boolean)
            .join(' · ')
        : db.message ?? '',
    })
  }

  for (const diskKey of ['disk_config', 'disk_media'] as const) {
    const disk = subsystems[diskKey]
    if (disk && disk.percent !== undefined) {
      rows.push({
        key: diskKey,
        label: diskKey === 'disk_config' ? t('sidebar.healthDiskConfig') : t('sidebar.healthDiskMedia'),
        healthy: disk.healthy,
        detail: `${Math.round(disk.percent)}%${disk.free_bytes ? ` · ${formatBytes(disk.free_bytes)} ${t('sidebar.healthFree')}` : ''}`,
      })
    }
  }

  const arr = subsystems.arr_connectivity
  if (arr) {
    for (const inst of arr.sonarr ?? []) {
      rows.push({
        key: `sonarr-${inst.instance_name}`,
        label: `Sonarr · ${inst.instance_name}`,
        healthy: inst.healthy,
        detail: inst.healthy ? t('sidebar.healthConnected') : inst.message,
      })
    }
    for (const inst of arr.radarr ?? []) {
      rows.push({
        key: `radarr-${inst.instance_name}`,
        label: `Radarr · ${inst.instance_name}`,
        healthy: inst.healthy,
        detail: inst.healthy ? t('sidebar.healthConnected') : inst.message,
      })
    }
  }

  const ms = subsystems.media_servers
  for (const inst of ms?.instances ?? []) {
    rows.push({
      key: `ms-${inst.type}-${inst.name}`,
      label: inst.name || inst.type,
      healthy: inst.healthy,
      detail: inst.healthy ? t('sidebar.healthConnected') : inst.message,
    })
  }

  return rows
}

function SystemHealthPanel() {
  const { t } = useTranslation('dashboard')
  const { data: detailed, isLoading } = useDetailedHealth()

  if (isLoading || !detailed?.subsystems) {
    return (
      <Panel testId="panel-system-health" title={t('sidebar.systemHealth')}>
        {[1, 2].map((i) => (
          <div
            key={i}
            style={{
              height: '16px',
              background: 'var(--bg-secondary)',
              borderRadius: '4px',
              marginBottom: '4px',
            }}
          />
        ))}
      </Panel>
    )
  }

  const rows = buildHealthRows(detailed.subsystems, t)
  const degraded = detailed.status !== 'healthy'

  return (
    <Panel testId="panel-system-health" title={t('sidebar.systemHealth')}>
      {degraded && (
        <div
          data-testid="system-health-degraded"
          style={{
            fontSize: '10px',
            fontWeight: 600,
            color: 'var(--warning)',
            marginBottom: '6px',
          }}
        >
          {t('sidebar.healthDegraded')}
        </div>
      )}
      {rows.map((row) => (
        <div
          key={row.key}
          style={{ display: 'flex', alignItems: 'center', gap: '7px', marginBottom: '5px' }}
        >
          <span
            data-testid={`health-dot-${row.key}`}
            data-healthy={String(row.healthy)}
            style={{
              width: 6,
              height: 6,
              borderRadius: '50%',
              background: row.healthy ? 'var(--success)' : 'var(--error)',
              flexShrink: 0,
            }}
          />
          <span style={{ flex: 1, fontSize: '12px', color: 'var(--text-secondary)' }}>
            {row.label}
          </span>
          <span
            title={row.detail}
            style={{
              fontSize: '11px',
              color: row.healthy ? 'var(--text-muted)' : 'var(--error)',
              maxWidth: '110px',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
            }}
          >
            {row.detail}
          </span>
        </div>
      ))}
    </Panel>
  )
}

// ─── Disk Space Panel ─────────────────────────────────────────────────────────

function DiskSpacePanel() {
  const { t } = useTranslation('dashboard')
  const { data: stats, isLoading } = useCleanupStats()

  return (
    <Panel testId="panel-disk" title={t('sidebar.disk')}>
      {isLoading || !stats ? (
        <div
          style={{ height: '32px', background: 'var(--bg-secondary)', borderRadius: '4px' }}
        />
      ) : (
        <>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '6px' }}>
            <div style={{ textAlign: 'center' }}>
              <div
                data-testid="disk-total-files"
                style={{
                  fontSize: '16px',
                  fontWeight: 700,
                  color: 'var(--text-primary)',
                  fontFamily: 'var(--font-mono)',
                }}
              >
                {formatNumber(stats.total_files)}
              </div>
              <div
                style={{
                  fontSize: '9px',
                  color: 'var(--text-muted)',
                  textTransform: 'uppercase',
                }}
              >
                {t('sidebar.diskFiles')}
              </div>
            </div>
            <div style={{ textAlign: 'center' }}>
              <div
                style={{
                  fontSize: '16px',
                  fontWeight: 700,
                  color:
                    stats.duplicate_files > 0 ? 'var(--warning)' : 'var(--text-primary)',
                  fontFamily: 'var(--font-mono)',
                }}
              >
                {formatNumber(stats.duplicate_files)}
              </div>
              <div
                style={{
                  fontSize: '9px',
                  color: 'var(--text-muted)',
                  textTransform: 'uppercase',
                }}
              >
                {t('sidebar.diskDuplicates')}
              </div>
            </div>
          </div>
          {stats.potential_savings_bytes > 0 && (
            <div
              style={{ fontSize: '10px', color: 'var(--success)', textAlign: 'center' }}
            >
              {formatBytes(stats.potential_savings_bytes)} {t('sidebar.diskSavings')}
            </div>
          )}
        </>
      )}
    </Panel>
  )
}

// ─── Quick Actions Panel ──────────────────────────────────────────────────────

function QuickActionsPanel() {
  const { t } = useTranslation('dashboard')
  const { data: wantedSummary } = useWantedSummary()
  const { data: batchStatus } = useWantedBatchStatus()
  const refreshWanted = useRefreshWanted()
  const startBatch = useStartWantedBatch()

  const isScanning = refreshWanted.isPending || Boolean(wantedSummary?.scan_running)
  const isBatching = startBatch.isPending || Boolean(batchStatus?.running)

  const btnStyle = (disabled: boolean): React.CSSProperties => ({
    width: '100%',
    padding: '6px 10px',
    marginBottom: '4px',
    fontSize: '11px',
    fontWeight: 500,
    borderRadius: '6px',
    border: '1px solid var(--border)',
    background: 'var(--bg-primary)',
    color: disabled ? 'var(--text-muted)' : 'var(--text-secondary)',
    cursor: disabled ? 'not-allowed' : 'pointer',
    opacity: disabled ? 0.6 : 1,
    textAlign: 'left' as const,
  })

  return (
    <Panel testId="panel-actions" title={t('sidebar.actions')}>
      <button
        data-testid="btn-scan-library"
        disabled={isScanning}
        onClick={() => refreshWanted.mutate(undefined)}
        style={btnStyle(isScanning)}
      >
        {isScanning ? t('sidebar.scanning') : t('sidebar.scanLibrary')}
      </button>
      <button
        data-testid="btn-batch-search"
        disabled={isBatching}
        onClick={() => startBatch.mutate(undefined)}
        style={btnStyle(isBatching)}
      >
        {isBatching ? t('sidebar.searching') : t('sidebar.batchSearch')}
      </button>
      <Link
        data-testid="link-wanted"
        to="/wanted"
        style={{
          ...btnStyle(false),
          display: 'block',
          textDecoration: 'none',
          marginBottom: '4px',
        }}
      >
        {t('sidebar.wantedList')}
      </Link>
      <Link
        data-testid="link-logs"
        to="/activity"
        style={{
          ...btnStyle(false),
          display: 'block',
          textDecoration: 'none',
          marginBottom: '8px',
        }}
      >
        {t('sidebar.viewLogs')}
      </Link>
      <button
        data-testid="btn-run-now-sidebar"
        disabled={isScanning}
        onClick={() => refreshWanted.mutate(undefined)}
        style={{
          width: '100%',
          padding: '7px 10px',
          fontSize: '11px',
          fontWeight: 600,
          borderRadius: '6px',
          border: '1px solid var(--accent)',
          background: 'var(--accent)',
          color: 'var(--bg-primary)',
          cursor: isScanning ? 'not-allowed' : 'pointer',
          opacity: isScanning ? 0.6 : 1,
        }}
      >
        {t('sidebar.runNow')}
      </button>
    </Panel>
  )
}

// ─── DashboardSidebar ─────────────────────────────────────────────────────────

export function DashboardSidebar() {
  return (
    <div
      data-testid="dashboard-sidebar"
      className="w-full md:w-[260px] shrink-0 flex flex-col overflow-hidden"
      style={{
        background: 'var(--bg-surface)',
        border: '1px solid var(--border)',
        borderRadius: 'var(--radius-lg)',
      }}
    >
      <ProviderHealthPanel />
      <ServiceStatusPanel />
      <SystemHealthPanel />
      <DiskSpacePanel />
      <QuickActionsPanel />
    </div>
  )
}
