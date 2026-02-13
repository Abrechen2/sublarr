import {
  Activity,
  CheckCircle2,
  XCircle,
  Clock,
  Zap,
  Server,
} from 'lucide-react'
import { useHealth, useStats, useJobs, useBazarrStatus } from '@/hooks/useApi'
import { StatusBadge } from '@/components/shared/StatusBadge'
import { formatDuration, formatRelativeTime, truncatePath } from '@/lib/utils'

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
  const { data: health, isLoading: healthLoading } = useHealth()
  const { data: stats, isLoading: statsLoading } = useStats()
  const { data: bazarr } = useBazarrStatus()
  const { data: recentJobs } = useJobs(1, 10)

  return (
    <div className="space-y-5">
      <h1>Dashboard</h1>

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
              label="Ollama"
              value={health?.services?.ollama === 'OK' ? 'Online' : 'Offline'}
              color={health?.services?.ollama === 'OK' ? 'var(--success)' : 'var(--error)'}
              delay={0}
            />
            <StatCard
              icon={Zap}
              label="Bazarr"
              value={bazarr?.configured ? (bazarr.reachable ? 'Connected' : 'Error') : 'N/A'}
              color={bazarr?.reachable ? 'var(--success)' : bazarr?.configured ? 'var(--error)' : 'var(--text-muted)'}
              delay={0.04}
            />
            <StatCard
              icon={CheckCircle2}
              label="Translated Today"
              value={stats?.today_translated ?? 0}
              color="var(--accent)"
              delay={0.08}
            />
            <StatCard
              icon={Clock}
              label="Queue"
              value={stats?.pending_jobs ?? 0}
              color="var(--warning)"
              delay={0.12}
            />
          </>
        )}
      </div>

      {/* Service Status */}
      {health?.services && (
        <div
          className="rounded-lg p-4"
          style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)' }}
        >
          <h2 className="text-xs font-semibold mb-3 uppercase tracking-wider" style={{ color: 'var(--text-muted)' }}>
            Service Connections
          </h2>
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-5 gap-2">
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

      {/* Quick Stats */}
      {stats && (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          <div
            className="rounded-lg p-4"
            style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)' }}
          >
            <div className="text-xs font-semibold mb-3 uppercase tracking-wider" style={{ color: 'var(--text-muted)' }}>
              Total Stats
            </div>
            <div className="space-y-2">
              <div className="flex justify-between text-sm">
                <span>Translated</span>
                <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--success)' }}>{stats.total_translated}</span>
              </div>
              <div className="flex justify-between text-sm">
                <span>Failed</span>
                <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--error)' }}>{stats.total_failed}</span>
              </div>
              <div className="flex justify-between text-sm">
                <span>Skipped</span>
                <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-secondary)' }}>{stats.total_skipped}</span>
              </div>
            </div>
          </div>

          <div
            className="rounded-lg p-4"
            style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)' }}
          >
            <div className="text-xs font-semibold mb-3 uppercase tracking-wider" style={{ color: 'var(--text-muted)' }}>
              By Format
            </div>
            <div className="space-y-2">
              {Object.entries(stats.by_format || {}).map(([fmt, count]) => (
                <div key={fmt} className="flex justify-between text-sm">
                  <span className="uppercase">{fmt}</span>
                  <span style={{ fontFamily: 'var(--font-mono)' }}>{count}</span>
                </div>
              ))}
              {Object.keys(stats.by_format || {}).length === 0 && (
                <div className="text-sm" style={{ color: 'var(--text-secondary)' }}>No data yet</div>
              )}
            </div>
          </div>

          <div
            className="rounded-lg p-4"
            style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)' }}
          >
            <div className="text-xs font-semibold mb-3 uppercase tracking-wider" style={{ color: 'var(--text-muted)' }}>
              System
            </div>
            <div className="space-y-2">
              <div className="flex justify-between text-sm">
                <span>Uptime</span>
                <span style={{ fontFamily: 'var(--font-mono)' }}>{formatDuration(stats.uptime_seconds)}</span>
              </div>
              <div className="flex justify-between text-sm">
                <span>Batch Running</span>
                <span>{stats.batch_running ? 'Yes' : '\u2014'}</span>
              </div>
              <div className="flex justify-between text-sm">
                <span>Quality Warnings</span>
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
            Recent Activity
          </h2>
          <a href="/activity" className="text-xs font-medium" style={{ color: 'var(--accent)' }}>
            View All &rarr;
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
              No recent activity
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
