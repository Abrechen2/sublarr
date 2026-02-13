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

function StatCard({ icon: Icon, label, value, color }: {
  icon: typeof Activity
  label: string
  value: string | number
  color: string
}) {
  return (
    <div
      className="rounded-xl p-5 flex items-center gap-4 transition-all duration-200 hover:shadow-md cursor-default"
      style={{ 
        backgroundColor: 'var(--bg-surface)', 
        border: '1px solid var(--border)',
        boxShadow: '0 1px 3px 0 rgba(0, 0, 0, 0.1), 0 1px 2px 0 rgba(0, 0, 0, 0.06)',
      }}
      onMouseEnter={(e) => {
        e.currentTarget.style.borderColor = color
        e.currentTarget.style.transform = 'translateY(-2px)'
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.borderColor = 'var(--border)'
        e.currentTarget.style.transform = 'translateY(0)'
      }}
    >
      <div className="p-3 rounded-lg transition-all duration-200" style={{ backgroundColor: `${color}15` }}>
        <Icon size={22} style={{ color }} />
      </div>
      <div>
        <div className="text-2xl font-bold tabular-nums">{value}</div>
        <div className="text-xs" style={{ color: 'var(--text-secondary)' }}>{label}</div>
      </div>
    </div>
  )
}

export function Dashboard() {
  const { data: health } = useHealth()
  const { data: stats } = useStats()
  const { data: bazarr } = useBazarrStatus()
  const { data: recentJobs } = useJobs(1, 10)

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Dashboard</h1>

      {/* Status Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          icon={Server}
          label="Ollama"
          value={health?.services?.ollama === 'OK' ? 'Online' : 'Offline'}
          color={health?.services?.ollama === 'OK' ? '#22c55e' : '#ef4444'}
        />
        <StatCard
          icon={Zap}
          label="Bazarr"
          value={bazarr?.configured ? (bazarr.reachable ? 'Connected' : 'Error') : 'N/A'}
          color={bazarr?.reachable ? '#22c55e' : bazarr?.configured ? '#ef4444' : '#8b8f96'}
        />
        <StatCard
          icon={CheckCircle2}
          label="Translated Today"
          value={stats?.today_translated ?? 0}
          color="#1DB8D4"
        />
        <StatCard
          icon={Clock}
          label="Queue"
          value={stats?.pending_jobs ?? 0}
          color="#f59e0b"
        />
      </div>

      {/* Service Status */}
      {health?.services && (
        <div
          className="rounded-xl p-5 shadow-sm transition-all duration-200"
          style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)' }}
        >
          <h2 className="text-sm font-semibold mb-4" style={{ color: 'var(--text-secondary)' }}>
            Service Connections
          </h2>
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-5 gap-3">
            {Object.entries(health.services).map(([name, status]) => (
              <div key={name} className="flex items-center gap-2">
                <div
                  className="w-2 h-2 rounded-full"
                  style={{
                    backgroundColor: status === 'OK' || status.startsWith('OK')
                      ? 'var(--success)'
                      : status === 'not configured'
                        ? 'var(--text-secondary)'
                        : 'var(--error)',
                  }}
                />
                <span className="text-sm capitalize">{name}</span>
                <span className="text-xs ml-auto" style={{ color: 'var(--text-secondary)' }}>
                  {status === 'OK' ? '✓' : status === 'not configured' ? '—' : '✗'}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Quick Stats */}
      {stats && (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div
            className="rounded-xl p-5 shadow-sm transition-all duration-200 hover:shadow-md"
            style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)' }}
          >
            <div className="text-sm mb-2" style={{ color: 'var(--text-secondary)' }}>Total Stats</div>
            <div className="space-y-2">
              <div className="flex justify-between text-sm">
                <span>Translated</span>
                <span className="font-mono" style={{ color: 'var(--success)' }}>{stats.total_translated}</span>
              </div>
              <div className="flex justify-between text-sm">
                <span>Failed</span>
                <span className="font-mono" style={{ color: 'var(--error)' }}>{stats.total_failed}</span>
              </div>
              <div className="flex justify-between text-sm">
                <span>Skipped</span>
                <span className="font-mono" style={{ color: 'var(--text-secondary)' }}>{stats.total_skipped}</span>
              </div>
            </div>
          </div>

          <div
            className="rounded-xl p-5 shadow-sm transition-all duration-200 hover:shadow-md"
            style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)' }}
          >
            <div className="text-sm mb-2" style={{ color: 'var(--text-secondary)' }}>By Format</div>
            <div className="space-y-2">
              {Object.entries(stats.by_format || {}).map(([fmt, count]) => (
                <div key={fmt} className="flex justify-between text-sm">
                  <span className="uppercase">{fmt}</span>
                  <span className="font-mono">{count}</span>
                </div>
              ))}
              {Object.keys(stats.by_format || {}).length === 0 && (
                <div className="text-sm" style={{ color: 'var(--text-secondary)' }}>No data yet</div>
              )}
            </div>
          </div>

          <div
            className="rounded-xl p-5 shadow-sm transition-all duration-200 hover:shadow-md"
            style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)' }}
          >
            <div className="text-sm mb-2" style={{ color: 'var(--text-secondary)' }}>System</div>
            <div className="space-y-2">
              <div className="flex justify-between text-sm">
                <span>Uptime</span>
                <span className="font-mono">{formatDuration(stats.uptime_seconds)}</span>
              </div>
              <div className="flex justify-between text-sm">
                <span>Batch Running</span>
                <span>{stats.batch_running ? '🔄 Yes' : '—'}</span>
              </div>
              <div className="flex justify-between text-sm">
                <span>Quality Warnings</span>
                <span className="font-mono" style={{ color: stats.quality_warnings > 0 ? 'var(--warning)' : 'inherit' }}>
                  {stats.quality_warnings}
                </span>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Recent Activity */}
      <div
        className="rounded-xl overflow-hidden shadow-sm"
        style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)' }}
      >
        <div className="px-5 py-4 flex items-center justify-between"
          style={{ borderBottom: '1px solid var(--border)' }}>
          <h2 className="text-sm font-semibold">Recent Activity</h2>
          <a href="/activity" className="text-xs" style={{ color: 'var(--accent)' }}>View All →</a>
        </div>
        <div className="divide-y" style={{ borderColor: 'var(--border)' }}>
          {recentJobs?.data?.length ? (
            recentJobs.data.map((job) => (
              <div 
                key={job.id} 
                className="px-5 py-3 flex items-center gap-3 transition-colors duration-200 hover:bg-opacity-50"
                style={{ backgroundColor: 'transparent' }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.backgroundColor = 'rgba(29, 184, 212, 0.05)'
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.backgroundColor = 'transparent'
                }}
              >
                {job.status === 'completed' ? (
                  <CheckCircle2 size={16} style={{ color: 'var(--success)' }} />
                ) : job.status === 'failed' ? (
                  <XCircle size={16} style={{ color: 'var(--error)' }} />
                ) : (
                  <Activity size={16} style={{ color: 'var(--accent)' }} />
                )}
                <span className="text-sm flex-1 truncate" title={job.file_path}>
                  {truncatePath(job.file_path)}
                </span>
                <StatusBadge status={job.status} />
                <span className="text-xs tabular-nums hidden sm:inline" style={{ color: 'var(--text-secondary)' }}>
                  {job.created_at ? formatRelativeTime(job.created_at) : ''}
                </span>
              </div>
            ))
          ) : (
            <div className="px-5 py-8 text-center text-sm" style={{ color: 'var(--text-secondary)' }}>
              No recent activity
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
