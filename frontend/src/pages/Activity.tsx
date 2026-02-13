import { useState } from 'react'
import { useJobs } from '@/hooks/useApi'
import { StatusBadge } from '@/components/shared/StatusBadge'
import { formatRelativeTime, truncatePath } from '@/lib/utils'
import { ChevronLeft, ChevronRight } from 'lucide-react'

export function ActivityPage() {
  const [page, setPage] = useState(1)
  const [statusFilter, setStatusFilter] = useState<string | undefined>()
  const { data: jobs, isLoading } = useJobs(page, 50, statusFilter)

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between flex-wrap gap-4">
        <h1>Activity</h1>
        <div className="flex gap-1.5">
          {['all', 'completed', 'failed', 'running', 'queued'].map((s) => {
            const isActive = (s === 'all' && !statusFilter) || statusFilter === s
            return (
              <button
                key={s}
                onClick={() => setStatusFilter(s === 'all' ? undefined : s)}
                className="px-3 py-1.5 rounded-md text-xs font-medium transition-all duration-150"
                style={{
                  backgroundColor: isActive ? 'var(--accent-bg)' : 'var(--bg-surface)',
                  color: isActive ? 'var(--accent)' : 'var(--text-secondary)',
                  border: `1px solid ${isActive ? 'var(--accent-dim)' : 'var(--border)'}`,
                }}
              >
                {s.charAt(0).toUpperCase() + s.slice(1)}
              </button>
            )
          })}
        </div>
      </div>

      <div
        className="rounded-lg overflow-hidden"
        style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)' }}
      >
        <div className="overflow-x-auto">
          <table className="w-full min-w-[600px]">
            <thead>
              <tr style={{ borderBottom: '1px solid var(--border)' }}>
                <th className="text-left text-[11px] font-semibold uppercase tracking-wider px-4 py-2.5" style={{ color: 'var(--text-muted)' }}>File</th>
                <th className="text-left text-[11px] font-semibold uppercase tracking-wider px-3 py-2.5" style={{ color: 'var(--text-muted)' }}>Status</th>
                <th className="text-left text-[11px] font-semibold uppercase tracking-wider px-3 py-2.5 hidden sm:table-cell" style={{ color: 'var(--text-muted)' }}>Format</th>
                <th className="text-left text-[11px] font-semibold uppercase tracking-wider px-3 py-2.5 hidden md:table-cell" style={{ color: 'var(--text-muted)' }}>Time</th>
                <th className="text-left text-[11px] font-semibold uppercase tracking-wider px-3 py-2.5 hidden lg:table-cell" style={{ color: 'var(--text-muted)' }}>Error</th>
              </tr>
            </thead>
            <tbody>
              {isLoading ? (
                Array.from({ length: 5 }).map((_, i) => (
                  <tr key={i} style={{ borderBottom: '1px solid var(--border)' }}>
                    <td className="px-4 py-3"><div className="skeleton h-4 w-48 rounded" /></td>
                    <td className="px-3 py-3"><div className="skeleton h-5 w-20 rounded-full" /></td>
                    <td className="px-3 py-3 hidden sm:table-cell"><div className="skeleton h-4 w-10 rounded" /></td>
                    <td className="px-3 py-3 hidden md:table-cell"><div className="skeleton h-4 w-14 rounded" /></td>
                    <td className="px-3 py-3 hidden lg:table-cell"><div className="skeleton h-4 w-32 rounded" /></td>
                  </tr>
                ))
              ) : jobs?.data?.length ? (
                jobs.data.map((job) => (
                  <tr
                    key={job.id}
                    className="transition-colors duration-100"
                    style={{ borderBottom: '1px solid var(--border)' }}
                    onMouseEnter={(e) => (e.currentTarget.style.backgroundColor = 'var(--bg-surface-hover)')}
                    onMouseLeave={(e) => (e.currentTarget.style.backgroundColor = 'transparent')}
                  >
                    <td className="px-4 py-2.5" title={job.file_path}>
                      <div
                        className="truncate max-w-xs text-sm"
                        style={{ fontFamily: 'var(--font-mono)', fontSize: '12px' }}
                      >
                        {truncatePath(job.file_path)}
                      </div>
                    </td>
                    <td className="px-3 py-2.5">
                      <StatusBadge status={job.status} />
                    </td>
                    <td
                      className="px-3 py-2.5 text-xs uppercase hidden sm:table-cell"
                      style={{ color: 'var(--text-secondary)', fontFamily: 'var(--font-mono)' }}
                    >
                      {job.source_format || '\u2014'}
                    </td>
                    <td
                      className="px-3 py-2.5 text-xs tabular-nums hidden md:table-cell"
                      style={{ color: 'var(--text-secondary)', fontFamily: 'var(--font-mono)' }}
                    >
                      {job.created_at ? formatRelativeTime(job.created_at) : ''}
                    </td>
                    <td className="px-3 py-2.5 text-xs hidden lg:table-cell" style={{ color: 'var(--error)' }}>
                      <div className="truncate max-w-xs">{job.error || ''}</div>
                    </td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan={5} className="px-4 py-8 text-center text-sm" style={{ color: 'var(--text-secondary)' }}>
                    No jobs found
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        {/* Pagination */}
        {jobs && jobs.total_pages > 1 && (
          <div
            className="flex items-center justify-between px-4 py-2.5"
            style={{ borderTop: '1px solid var(--border)' }}
          >
            <span className="text-xs" style={{ color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
              Page {jobs.page} of {jobs.total_pages} ({jobs.total} total)
            </span>
            <div className="flex gap-1.5">
              <button
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page <= 1}
                className="p-1.5 rounded-md transition-all duration-150"
                style={{
                  border: '1px solid var(--border)',
                  backgroundColor: 'var(--bg-primary)',
                  color: 'var(--text-secondary)',
                }}
                onMouseEnter={(e) => {
                  if (!e.currentTarget.disabled) e.currentTarget.style.borderColor = 'var(--accent-dim)'
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.borderColor = 'var(--border)'
                }}
              >
                <ChevronLeft size={14} />
              </button>
              <button
                onClick={() => setPage((p) => Math.min(jobs.total_pages, p + 1))}
                disabled={page >= jobs.total_pages}
                className="p-1.5 rounded-md transition-all duration-150"
                style={{
                  border: '1px solid var(--border)',
                  backgroundColor: 'var(--bg-primary)',
                  color: 'var(--text-secondary)',
                }}
                onMouseEnter={(e) => {
                  if (!e.currentTarget.disabled) e.currentTarget.style.borderColor = 'var(--accent-dim)'
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.borderColor = 'var(--border)'
                }}
              >
                <ChevronRight size={14} />
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
