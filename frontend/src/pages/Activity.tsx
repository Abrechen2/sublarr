import { useState } from 'react'
import { useJobs, useRetryJob } from '@/hooks/useApi'
import { StatusBadge } from '@/components/shared/StatusBadge'
import { formatRelativeTime, truncatePath } from '@/lib/utils'
import { toast } from '@/components/shared/Toast'
import { ChevronLeft, ChevronRight, ChevronDown, ChevronUp, RotateCcw, Loader2 } from 'lucide-react'
import type { Job } from '@/lib/types'

function ExpandedRow({ job }: { job: Job }) {
  return (
    <tr style={{ backgroundColor: 'var(--bg-primary)' }}>
      <td colSpan={6} className="px-4 py-3">
        <div className="space-y-2 text-xs">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            <div>
              <span className="font-semibold" style={{ color: 'var(--text-muted)' }}>Full Path:</span>
              <div className="mt-0.5" style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-secondary)', wordBreak: 'break-all' }}>
                {job.file_path}
              </div>
            </div>
            <div>
              <span className="font-semibold" style={{ color: 'var(--text-muted)' }}>Output:</span>
              <div className="mt-0.5" style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-secondary)', wordBreak: 'break-all' }}>
                {job.output_path || '\u2014'}
              </div>
            </div>
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
            <div>
              <span className="font-semibold" style={{ color: 'var(--text-muted)' }}>Format:</span>
              <span className="ml-1 uppercase" style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-secondary)' }}>
                {job.source_format || '\u2014'}
              </span>
            </div>
            <div>
              <span className="font-semibold" style={{ color: 'var(--text-muted)' }}>Force:</span>
              <span className="ml-1" style={{ color: 'var(--text-secondary)' }}>
                {job.force ? 'Yes' : 'No'}
              </span>
            </div>
            <div>
              <span className="font-semibold" style={{ color: 'var(--text-muted)' }}>Created:</span>
              <span className="ml-1 tabular-nums" style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-secondary)' }}>
                {job.created_at ? formatRelativeTime(job.created_at) : '\u2014'}
              </span>
            </div>
            <div>
              <span className="font-semibold" style={{ color: 'var(--text-muted)' }}>Completed:</span>
              <span className="ml-1 tabular-nums" style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-secondary)' }}>
                {job.completed_at ? formatRelativeTime(job.completed_at) : '\u2014'}
              </span>
            </div>
          </div>

          {job.error && (
            <div>
              <span className="font-semibold" style={{ color: 'var(--text-muted)' }}>Error:</span>
              <div
                className="mt-0.5 px-2.5 py-1.5 rounded"
                style={{
                  backgroundColor: 'var(--error-bg)',
                  color: 'var(--error)',
                  fontFamily: 'var(--font-mono)',
                  whiteSpace: 'pre-wrap',
                  wordBreak: 'break-all',
                }}
              >
                {job.error}
              </div>
            </div>
          )}

          {job.stats && Object.keys(job.stats).length > 0 && (
            <div>
              <span className="font-semibold" style={{ color: 'var(--text-muted)' }}>Stats:</span>
              <div className="mt-0.5 flex flex-wrap gap-2">
                {Object.entries(job.stats).map(([key, val]) => (
                  <span
                    key={key}
                    className="px-2 py-0.5 rounded"
                    style={{ backgroundColor: 'var(--bg-surface)', fontFamily: 'var(--font-mono)' }}
                  >
                    {key}: {String(val)}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
      </td>
    </tr>
  )
}

export function ActivityPage() {
  const [page, setPage] = useState(1)
  const [statusFilter, setStatusFilter] = useState<string | undefined>()
  const [expandedId, setExpandedId] = useState<string | null>(null)
  const { data: jobs, isLoading } = useJobs(page, 50, statusFilter)
  const retryJob = useRetryJob()

  const handleRetry = (jobId: string) => {
    retryJob.mutate(jobId, {
      onSuccess: () => toast('Retry started'),
      onError: () => toast('Retry failed', 'error'),
    })
  }

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
          <table className="w-full min-w-[700px]">
            <thead>
              <tr style={{ borderBottom: '1px solid var(--border)' }}>
                <th className="text-left text-[11px] font-semibold uppercase tracking-wider px-4 py-2.5" style={{ color: 'var(--text-muted)' }}>File</th>
                <th className="text-left text-[11px] font-semibold uppercase tracking-wider px-3 py-2.5" style={{ color: 'var(--text-muted)' }}>Status</th>
                <th className="text-left text-[11px] font-semibold uppercase tracking-wider px-3 py-2.5 hidden sm:table-cell" style={{ color: 'var(--text-muted)' }}>Format</th>
                <th className="text-left text-[11px] font-semibold uppercase tracking-wider px-3 py-2.5 hidden md:table-cell" style={{ color: 'var(--text-muted)' }}>Time</th>
                <th className="text-left text-[11px] font-semibold uppercase tracking-wider px-3 py-2.5 hidden lg:table-cell" style={{ color: 'var(--text-muted)' }}>Error</th>
                <th className="text-right text-[11px] font-semibold uppercase tracking-wider px-4 py-2.5" style={{ color: 'var(--text-muted)' }}>Actions</th>
              </tr>
            </thead>
            {isLoading ? (
              <tbody>
                {Array.from({ length: 5 }).map((_, i) => (
                  <tr key={i} style={{ borderBottom: '1px solid var(--border)' }}>
                    <td className="px-4 py-3"><div className="skeleton h-4 w-48 rounded" /></td>
                    <td className="px-3 py-3"><div className="skeleton h-5 w-20 rounded-full" /></td>
                    <td className="px-3 py-3 hidden sm:table-cell"><div className="skeleton h-4 w-10 rounded" /></td>
                    <td className="px-3 py-3 hidden md:table-cell"><div className="skeleton h-4 w-14 rounded" /></td>
                    <td className="px-3 py-3 hidden lg:table-cell"><div className="skeleton h-4 w-32 rounded" /></td>
                    <td className="px-4 py-3"><div className="skeleton h-6 w-12 rounded ml-auto" /></td>
                  </tr>
                ))}
              </tbody>
            ) : jobs?.data?.length ? (
              jobs.data.map((job) => {
                const isExpanded = expandedId === job.id
                return (
                  <tbody key={job.id}>
                    <tr
                        className="transition-colors duration-100 cursor-pointer"
                        style={{
                          borderBottom: isExpanded ? 'none' : '1px solid var(--border)',
                          backgroundColor: isExpanded ? 'var(--bg-surface-hover)' : undefined,
                        }}
                        onClick={() => setExpandedId(isExpanded ? null : job.id)}
                        onMouseEnter={(e) => {
                          if (!isExpanded) e.currentTarget.style.backgroundColor = 'var(--bg-surface-hover)'
                        }}
                        onMouseLeave={(e) => {
                          if (!isExpanded) e.currentTarget.style.backgroundColor = 'transparent'
                        }}
                      >
                        <td className="px-4 py-2.5" title={job.file_path}>
                          <div className="flex items-center gap-1.5">
                            {isExpanded ? (
                              <ChevronUp size={12} style={{ color: 'var(--accent)', flexShrink: 0 }} />
                            ) : (
                              <ChevronDown size={12} style={{ color: 'var(--text-muted)', flexShrink: 0 }} />
                            )}
                            <span
                              className="truncate max-w-xs text-sm"
                              style={{ fontFamily: 'var(--font-mono)', fontSize: '12px' }}
                            >
                              {truncatePath(job.file_path)}
                            </span>
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
                        <td className="px-4 py-2.5 text-right" onClick={(e) => e.stopPropagation()}>
                          {job.status === 'failed' && (
                            <button
                              onClick={() => handleRetry(job.id)}
                              disabled={retryJob.isPending}
                              className="p-1.5 rounded transition-all duration-150"
                              title="Retry job"
                              style={{ color: 'var(--text-muted)' }}
                              onMouseEnter={(e) => {
                                e.currentTarget.style.color = 'var(--accent)'
                                e.currentTarget.style.backgroundColor = 'var(--accent-subtle)'
                              }}
                              onMouseLeave={(e) => {
                                e.currentTarget.style.color = 'var(--text-muted)'
                                e.currentTarget.style.backgroundColor = ''
                              }}
                            >
                              {retryJob.isPending ? (
                                <Loader2 size={14} className="animate-spin" />
                              ) : (
                                <RotateCcw size={14} />
                              )}
                            </button>
                          )}
                        </td>
                      </tr>
                    {isExpanded && <ExpandedRow job={job} />}
                  </tbody>
                )
              })
            ) : (
              <tbody>
                <tr>
                  <td colSpan={6} className="px-4 py-8 text-center text-sm" style={{ color: 'var(--text-secondary)' }}>
                    No jobs found
                  </td>
                </tr>
              </tbody>
            )}
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
