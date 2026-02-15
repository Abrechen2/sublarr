import { useState, useEffect, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import {
  Activity,
  CheckCircle2,
  XCircle,
  Clock,
  Zap,
  Server,
  RefreshCw,
  Search,
  Loader2,
} from 'lucide-react'
import { useHealth, useStats, useJobs, useWantedSummary, useRefreshWanted, useStartWantedBatch, useWantedBatchStatus, useProviders } from '@/hooks/useApi'
import { StatusBadge } from '@/components/shared/StatusBadge'
import { formatDuration, formatRelativeTime, truncatePath } from '@/lib/utils'
import { toast } from '@/components/shared/Toast'

function StatCard({ icon: Icon, label, value, color, delay }: {
  icon: typeof Activity
  label: string
  value: string | number
  color: string
  delay: number
}) {
  return (
    <div
      className="rounded-lg p-4 flex items-center gap-4 transition-all duration-200 hover:shadow-md cursor-default animate-in"
      style={{
        backgroundColor: 'var(--bg-surface)',
        border: '1px solid var(--border)',
        animationDelay: `${delay}s`,
      }}
      onMouseEnter={(e) => {
        e.currentTarget.style.borderColor = color
        e.currentTarget.style.transform = 'translateY(-1px)'
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.borderColor = 'var(--border)'
        e.currentTarget.style.transform = 'translateY(0)'
      }}
    >
      <div
        className="p-2.5 rounded-lg"
        style={{ backgroundColor: `${color}12` }}
      >
        <Icon size={20} style={{ color }} />
      </div>
      <div>
        <div
          className="text-xl font-bold tabular-nums"
          style={{ fontFamily: 'var(--font-mono)' }}
        >
          {value}
        </div>
        <div className="text-xs" style={{ color: 'var(--text-secondary)' }}>{label}</div>
      </div>
    </div>
  )
}

function SkeletonCard() {
  return (
    <div className="rounded-lg p-4 flex items-center gap-4" style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)' }}>
      <div className="skeleton w-10 h-10 rounded-lg" />
      <div className="space-y-2 flex-1">
        <div className="skeleton h-5 w-16 rounded" />
        <div className="skeleton h-3 w-24 rounded" />
      </div>
    </div>
  )
}

export function Dashboard() {
  const { t } = useTranslation('dashboard')
  const { data: health, isLoading: healthLoading } = useHealth()
  const { data: stats, isLoading: statsLoading } = useStats()
  const { data: wantedSummary } = useWantedSummary()
  const { data: recentJobs } = useJobs(1, 10)
  const { data: providersData } = useProviders()
  const { data: batchStatus } = useWantedBatchStatus()
  const refreshWanted = useRefreshWanted()
  const startBatch = useStartWantedBatch()

  const providers = providersData?.providers ?? []

  // Live Uptime Counter
  const [currentUptime, setCurrentUptime] = useState<number | null>(null)
  const initialUptimeRef = useRef<number | null>(null)
  const lastUpdateTimeRef = useRef<number | null>(null)

  useEffect(() => {
    if (stats?.uptime_seconds !== undefined) {
      // Wenn sich der initiale Uptime-Wert ändert (z.B. nach Server-Neustart), aktualisiere die Referenzen
      if (initialUptimeRef.current !== stats.uptime_seconds) {
        initialUptimeRef.current = stats.uptime_seconds
        lastUpdateTimeRef.current = Date.now()
        setCurrentUptime(stats.uptime_seconds)
      }
    }
  }, [stats?.uptime_seconds])

  useEffect(() => {
    if (initialUptimeRef.current === null || lastUpdateTimeRef.current === null) {
      return
    }

    const interval = setInterval(() => {
      const now = Date.now()
      const elapsed = (now - lastUpdateTimeRef.current!) / 1000
      setCurrentUptime(initialUptimeRef.current! + elapsed)
    }, 1000)

    return () => clearInterval(interval)
  }, [])

  return (
    <div className="space-y-5">
      <h1>{t('title')}</h1>

      {/* Status Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
        {healthLoading || statsLoading ? (
          <>
            <SkeletonCard />
            <SkeletonCard />
            <SkeletonCard />
            <SkeletonCard />
          </>
        ) : (
          <>
            <StatCard
              icon={Server}
              label={t('stats.ollama')}
              value={health?.services?.ollama === 'OK' ? t('stats.online') : t('stats.offline')}
              color={health?.services?.ollama === 'OK' ? 'var(--success)' : 'var(--error)'}
              delay={0}
            />
            <StatCard
              icon={Zap}
              label={t('stats.wanted')}
              value={wantedSummary?.by_status?.wanted ?? 0}
              color={wantedSummary?.total ? 'var(--warning)' : 'var(--text-muted)'}
              delay={0.04}
            />
            <StatCard
              icon={CheckCircle2}
              label={t('stats.translated_today')}
              value={stats?.today_translated ?? 0}
              color="var(--accent)"
              delay={0.08}
            />
            <StatCard
              icon={Clock}
              label={t('stats.queue')}
              value={stats?.pending_jobs ?? 0}
              color="var(--warning)"
              delay={0.12}
            />
          </>
        )}
      </div>

      {/* Quick Actions */}
      <div
        className="rounded-lg p-4"
        style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)' }}
      >
        <h2 className="text-xs font-semibold mb-3 uppercase tracking-wider" style={{ color: 'var(--text-muted)' }}>
          {t('quick_actions.title')}
        </h2>
        <div className="flex flex-wrap gap-2">
          <button
            onClick={() => {
              refreshWanted.mutate(undefined, {
                onSuccess: () => toast('Library scan started'),
                onError: () => toast('Scan failed', 'error'),
              })
            }}
            disabled={refreshWanted.isPending || wantedSummary?.scan_running}
            className="flex items-center gap-2 px-4 py-2 rounded-md text-sm font-medium transition-all duration-150 hover:opacity-90"
            style={{
              backgroundColor: 'var(--bg-primary)',
              border: '1px solid var(--border)',
              color: 'var(--text-primary)',
            }}
          >
            {refreshWanted.isPending || wantedSummary?.scan_running ? (
              <Loader2 size={14} className="animate-spin" />
            ) : (
              <RefreshCw size={14} />
            )}
            {wantedSummary?.scan_running ? t('quick_actions.scanning') : t('quick_actions.scan_library')}
          </button>
          <button
            onClick={() => {
              startBatch.mutate(undefined, {
                onSuccess: () => toast('Wanted search started'),
                onError: () => toast('Search failed', 'error'),
              })
            }}
            disabled={startBatch.isPending || batchStatus?.running}
            className="flex items-center gap-2 px-4 py-2 rounded-md text-sm font-medium transition-all duration-150 hover:opacity-90"
            style={{
              backgroundColor: 'var(--bg-primary)',
              border: '1px solid var(--border)',
              color: 'var(--text-primary)',
            }}
          >
            {startBatch.isPending || batchStatus?.running ? (
              <Loader2 size={14} className="animate-spin" />
            ) : (
              <Search size={14} />
            )}
            {batchStatus?.running ? t('quick_actions.searching') : t('quick_actions.search_wanted')}
          </button>
        </div>
      </div>

      {/* Service Status + Provider Health */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        {health?.services && (
          <div
            className="rounded-lg p-4"
            style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)' }}
          >
            <h2 className="text-xs font-semibold mb-3 uppercase tracking-wider" style={{ color: 'var(--text-muted)' }}>
              {t('services.title')}
            </h2>
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
              {Object.entries(health.services).map(([name, status]) => {
                const isOk = status === 'OK' || status.startsWith('OK')
                const isNotConfigured = status === 'not configured'
                return (
                  <div
                    key={name}
                    className="flex items-center gap-2 px-2.5 py-1.5 rounded-md"
                    style={{ backgroundColor: 'var(--bg-primary)' }}
                  >
                    <div
                      className="w-1.5 h-1.5 rounded-full shrink-0"
                      style={{
                        backgroundColor: isOk ? 'var(--success)' : isNotConfigured ? 'var(--text-muted)' : 'var(--error)',
                      }}
                    />
                    <span className="text-xs capitalize truncate">{name}</span>
                  </div>
                )
              })}
            </div>
          </div>
        )}

        {providers.length > 0 && (
          <div
            className="rounded-lg p-4"
            style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)' }}
          >
            <h2 className="text-xs font-semibold mb-3 uppercase tracking-wider" style={{ color: 'var(--text-muted)' }}>
              {t('providers.title')}
            </h2>
            <div className="space-y-1.5">
              {providers.map((p) => {
                const statusColor = !p.enabled
                  ? 'var(--text-muted)'
                  : p.healthy
                    ? 'var(--success)'
                    : 'var(--error)'
                return (
                  <div
                    key={p.name}
                    className="flex items-center justify-between px-2.5 py-1.5 rounded-md"
                    style={{ backgroundColor: 'var(--bg-primary)' }}
                  >
                    <div className="flex items-center gap-2">
                      <div
                        className="w-1.5 h-1.5 rounded-full shrink-0"
                        style={{ backgroundColor: statusColor }}
                      />
                      <span className="text-xs capitalize">{p.name}</span>
                    </div>
                    <span
                      className="text-[10px] font-medium"
                      style={{ color: statusColor }}
                    >
                      {!p.enabled ? t('providers.disabled') : p.healthy ? t('providers.healthy') : t('providers.error')}
                    </span>
                  </div>
                )
              })}
            </div>
          </div>
        )}
      </div>

      {/* Quick Stats */}
      {stats && (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          <div
            className="rounded-lg p-4"
            style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)' }}
          >
            <div className="text-xs font-semibold mb-3 uppercase tracking-wider" style={{ color: 'var(--text-muted)' }}>
              {t('total_stats.title')}
            </div>
            <div className="space-y-2">
              <div className="flex justify-between text-sm">
                <span>{t('total_stats.translated')}</span>
                <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--success)' }}>{stats.total_translated}</span>
              </div>
              <div className="flex justify-between text-sm">
                <span>{t('total_stats.failed')}</span>
                <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--error)' }}>{stats.total_failed}</span>
              </div>
              <div className="flex justify-between text-sm">
                <span>{t('total_stats.skipped')}</span>
                <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-secondary)' }}>{stats.total_skipped}</span>
              </div>
            </div>
          </div>

          <div
            className="rounded-lg p-4"
            style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)' }}
          >
            <div className="text-xs font-semibold mb-3 uppercase tracking-wider" style={{ color: 'var(--text-muted)' }}>
              {t('by_format.title')}
            </div>
            <div className="space-y-2">
              {Object.entries(stats.by_format || {}).map(([fmt, count]) => (
                <div key={fmt} className="flex justify-between text-sm">
                  <span className="uppercase">{fmt}</span>
                  <span style={{ fontFamily: 'var(--font-mono)' }}>{count}</span>
                </div>
              ))}
              {Object.keys(stats.by_format || {}).length === 0 && (
                <div className="text-sm" style={{ color: 'var(--text-secondary)' }}>{t('by_format.no_data')}</div>
              )}
            </div>
          </div>

          <div
            className="rounded-lg p-4"
            style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)' }}
          >
            <div className="text-xs font-semibold mb-3 uppercase tracking-wider" style={{ color: 'var(--text-muted)' }}>
              {t('system.title')}
            </div>
            <div className="space-y-2">
              <div className="flex justify-between text-sm">
                <span>{t('system.uptime')}</span>
                <span style={{ fontFamily: 'var(--font-mono)' }}>
                  {currentUptime !== null ? formatDuration(currentUptime) : stats?.uptime_seconds !== undefined ? formatDuration(stats.uptime_seconds) : '—'}
                </span>
              </div>
              <div className="flex justify-between text-sm">
                <span>{t('system.batch_running')}</span>
                <span>{stats.batch_running ? t('system.yes') : '\u2014'}</span>
              </div>
              <div className="flex justify-between text-sm">
                <span>{t('system.quality_warnings')}</span>
                <span
                  style={{
                    fontFamily: 'var(--font-mono)',
                    color: stats.quality_warnings > 0 ? 'var(--warning)' : 'inherit',
                  }}
                >
                  {stats.quality_warnings}
                </span>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Recent Activity */}
      <div
        className="rounded-lg overflow-hidden"
        style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)' }}
      >
        <div
          className="px-4 py-3 flex items-center justify-between"
          style={{ borderBottom: '1px solid var(--border)' }}
        >
          <h2 className="text-xs font-semibold uppercase tracking-wider" style={{ color: 'var(--text-muted)' }}>
            {t('recent_activity.title')}
          </h2>
          <a href="/activity" className="text-xs font-medium" style={{ color: 'var(--accent)' }}>
            {t('recent_activity.view_all')} &rarr;
          </a>
        </div>
        <div className="divide-y" style={{ borderColor: 'var(--border)' }}>
          {recentJobs?.data?.length ? (
            recentJobs.data.map((job) => (
              <div
                key={job.id}
                className="px-4 py-2.5 flex items-center gap-3 transition-colors duration-150"
                onMouseEnter={(e) => {
                  e.currentTarget.style.backgroundColor = 'var(--bg-surface-hover)'
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.backgroundColor = 'transparent'
                }}
              >
                {job.status === 'completed' ? (
                  <CheckCircle2 size={14} style={{ color: 'var(--success)' }} />
                ) : job.status === 'failed' ? (
                  <XCircle size={14} style={{ color: 'var(--error)' }} />
                ) : (
                  <Activity size={14} style={{ color: 'var(--accent)' }} />
                )}
                <span
                  className="text-sm flex-1 truncate"
                  title={job.file_path}
                  style={{ fontFamily: 'var(--font-mono)', fontSize: '12px' }}
                >
                  {truncatePath(job.file_path)}
                </span>
                <StatusBadge status={job.status} />
                <span
                  className="text-xs tabular-nums hidden sm:inline"
                  style={{ color: 'var(--text-muted)', fontFamily: 'var(--font-mono)', fontSize: '11px' }}
                >
                  {job.created_at ? formatRelativeTime(job.created_at) : ''}
                </span>
              </div>
            ))
          ) : (
            <div className="px-4 py-8 text-center text-sm" style={{ color: 'var(--text-secondary)' }}>
              {t('recent_activity.no_activity')}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
