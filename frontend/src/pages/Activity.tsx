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
    <div className="space-y-6">
      <div className="flex items-center justify-between flex-wrap gap-4">
        <h1 className="text-2xl font-bold">Activity</h1>
        <div className="flex gap-2">
          <div className="flex flex-wrap gap-2">
            {['all', 'completed', 'failed', 'running', 'queued'].map((s) => (
              <button
                key={s}
                onClick={() => setStatusFilter(s === 'all' ? undefined : s)}
                className="px-3 py-1.5 rounded-lg text-xs font-medium transition-all duration-200 hover:shadow-sm"
                style={{
                  backgroundColor: (s === 'all' && !statusFilter) || statusFilter === s
                    ? 'rgba(29, 184, 212, 0.15)'
                    : 'transparent',
                  color: (s === 'all' && !statusFilter) || statusFilter === s
                    ? 'var(--accent)'
                    : 'var(--text-secondary)',
                  border: '1px solid var(--border)',
                }}
              >
                {s.charAt(0).toUpperCase() + s.slice(1)}
              </button>
            ))}
          </div>
        </div>
      </div>

      <div
        className="rounded-xl overflow-hidden shadow-sm"
        style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)' }}
      >
        <div className="overflow-x-auto">
          <table className="w-full min-w-[600px]">
          <thead>
            <tr style={{ borderBottom: '1px solid var(--border)' }}>
            <th className="text-left text-xs font-medium px-5 py-3" style={{ color: 'var(--text-secondary)' }}>File</th>
            <th className="text-left text-xs font-medium px-3 py-3" style={{ color: 'var(--text-secondary)' }}>Status</th>
            <th className="text-left text-xs font-medium px-3 py-3 hidden sm:table-cell" style={{ color: 'var(--text-secondary)' }}>Format</th>
            <th className="text-left text-xs font-medium px-3 py-3 hidden md:table-cell" style={{ color: 'var(--text-secondary)' }}>Time</th>
            <th className="text-left text-xs font-medium px-3 py-3 hidden lg:table-cell" style={{ color: 'var(--text-secondary)' }}>Error</th>
            </tr>
          </thead>
          <tbody>
            {isLoading ? (
              <tr>
                <td colSpan={5} className="px-5 py-8 text-center text-sm" style={{ color: 'var(--text-secondary)' }}>
                  Loading...
                </td>
              </tr>
            ) : jobs?.data?.length ? (
              jobs.data.map((job) => (
                <tr
                  key={job.id}
                  className="transition-colors"
                  style={{ borderBottom: '1px solid var(--border)' }}
                  onMouseEnter={(e) => (e.currentTarget.style.backgroundColor = 'var(--bg-surface-hover)')}
                  onMouseLeave={(e) => (e.currentTarget.style.backgroundColor = 'transparent')}
                >
                  <td className="px-5 py-3 text-sm truncate max-w-xs" title={job.file_path}>
                    {truncatePath(job.file_path)}
                  </td>
                  <td className="px-3 py-3">
                    <StatusBadge status={job.status} />
                  </td>
                  <td className="px-3 py-3 text-sm uppercase hidden sm:table-cell" style={{ color: 'var(--text-secondary)' }}>
                    {job.source_format || '—'}
                  </td>
                  <td className="px-3 py-3 text-xs tabular-nums hidden md:table-cell" style={{ color: 'var(--text-secondary)' }}>
                    {job.created_at ? formatRelativeTime(job.created_at) : ''}
                  </td>
                  <td className="px-3 py-3 text-xs truncate max-w-xs hidden lg:table-cell" style={{ color: 'var(--error)' }}>
                    {job.error || ''}
                  </td>
                </tr>
              ))
            ) : (
              <tr>
                <td colSpan={5} className="px-5 py-8 text-center text-sm" style={{ color: 'var(--text-secondary)' }}>
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
            className="flex items-center justify-between px-5 py-3"
            style={{ borderTop: '1px solid var(--border)' }}
          >
            <span className="text-xs" style={{ color: 'var(--text-secondary)' }}>
              Page {jobs.page} of {jobs.total_pages} ({jobs.total} total)
            </span>
            <div className="flex gap-2">
              <button
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page <= 1}
                className="p-1.5 rounded-lg transition-all duration-200 hover:shadow-sm disabled:opacity-30 disabled:cursor-not-allowed"
                style={{ 
                  border: '1px solid var(--border)',
                  backgroundColor: 'var(--bg-primary)',
                }}
                onMouseEnter={(e) => {
                  if (!e.currentTarget.disabled) {
                    e.currentTarget.style.borderColor = 'var(--accent)'
                  }
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.borderColor = 'var(--border)'
                }}
              >
                <ChevronLeft size={16} />
              </button>
              <button
                onClick={() => setPage((p) => Math.min(jobs.total_pages, p + 1))}
                disabled={page >= jobs.total_pages}
                className="p-1.5 rounded-lg transition-all duration-200 hover:shadow-sm disabled:opacity-30 disabled:cursor-not-allowed"
                style={{ 
                  border: '1px solid var(--border)',
                  backgroundColor: 'var(--bg-primary)',
                }}
                onMouseEnter={(e) => {
                  if (!e.currentTarget.disabled) {
                    e.currentTarget.style.borderColor = 'var(--accent)'
                  }
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.borderColor = 'var(--border)'
                }}
              >
                <ChevronRight size={16} />
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
