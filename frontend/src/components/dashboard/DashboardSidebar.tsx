import React from 'react'
import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import {
  useProviders,
  useHealth,
  useCleanupStats,
  useRefreshWanted,
  useStartWantedBatch,
  useWantedBatchStatus,
  useWantedSummary,
} from '@/hooks/useApi'
import { formatBytes } from '@/lib/diskUtils'

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

function ProviderHealthPanel() {
  const { t } = useTranslation('dashboard')
  const { data: providersData, isLoading } = useProviders()
  const providers = (providersData?.providers ?? []).filter((p: { enabled: boolean }) => p.enabled).slice(0, 5)

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
      {providers.map(
        (p: { name: string; stats?: { success_rate?: number } }) => {
          const healthy = (p.stats?.success_rate ?? 0) >= 80
          const pct = Math.round(p.stats?.success_rate ?? (healthy ? 100 : 0))
          return (
            <div
              key={p.name}
              style={{ display: 'flex', alignItems: 'center', gap: '7px', marginBottom: '5px' }}
            >
              <span
                data-testid={`provider-dot-${p.name}`}
                data-healthy={String(healthy)}
                style={{
                  width: 6,
                  height: 6,
                  borderRadius: '50%',
                  background: healthy ? 'var(--success)' : 'var(--error)',
                  flexShrink: 0,
                }}
              />
              <span style={{ flex: 1, fontSize: '12px', color: 'var(--text-secondary)' }}>
                {p.name}
              </span>
              <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>{pct}%</span>
            </div>
          )
        }
      )}
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
                {stats.total_files.toLocaleString()}
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
                {stats.duplicate_files}
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
  const isBatching = startBatch.isPending || Boolean(batchStatus?.is_running)

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
      style={{
        width: '260px',
        flexShrink: 0,
        background: 'var(--bg-surface)',
        border: '1px solid var(--border)',
        borderRadius: 'var(--radius-lg)',
        overflow: 'hidden',
        display: 'flex',
        flexDirection: 'column',
      }}
    >
      <ProviderHealthPanel />
      <ServiceStatusPanel />
      <DiskSpacePanel />
      <QuickActionsPanel />
    </div>
  )
}
