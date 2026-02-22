import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useJobs, useRetryJob } from '@/hooks/useApi'
import { StatusBadge } from '@/components/shared/StatusBadge'
import { formatRelativeTime, truncatePath } from '@/lib/utils'
import { toast } from '@/components/shared/Toast'
import { ChevronLeft, ChevronRight, ChevronDown, ChevronUp, RotateCcw, Loader2 } from 'lucide-react'
import type { Job } from '@/lib/types'

function ExpandedRow({ job, t }: { job: Job; t: (key: string, opts?: Record<string, unknown>) => string }) {
  return (
    <tr style={{ backgroundColor: 'var(--bg-primary)' }}>
      <td colSpan={6} className="px-4 py-3">
        <div className="space-y-2 text-xs">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            <div>
              <span className="font-semibold" style={{ color: 'var(--text-muted)' }}>{t('expanded.full_path')}:</span>
              <div className="mt-0.5" style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-secondary)', wordBreak: 'break-all' }}>
                {job.file_path}
              </div>
            </div>
            <div>
              <span className="font-semibold" style={{ color: 'var(--text-muted)' }}>{t('expanded.output')}:</span>
              <div className="mt-0.5" style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-secondary)', wordBreak: 'break-all' }}>
                {job.output_path || '\u2014'}
              </div>
            </div>
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
            <div>
              <span className="font-semibold" style={{ color: 'var(--text-muted)' }}>{t('expanded.format')}:</span>
              <span className="ml-1 uppercase" style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-secondary)' }}>
                {job.source_format || '\u2014'}
              </span>
            </div>
            <div>
              <span className="font-semibold" style={{ color: 'var(--text-muted)' }}>{t('expanded.force')}:</span>
              <span className="ml-1" style={{ color: 'var(--text-secondary)' }}>
                {job.force ? t('expanded.force_yes') : t('expanded.force_no')}
              </span>
            </div>
            <div>
              <span className="font-semibold" style={{ color: 'var(--text-muted)' }}>{t('expanded.created')}:</span>
              <span className="ml-1 tabular-nums" style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-secondary)' }}>
                {job.created_at ? formatRelativeTime(job.created_at) : '\u2014'}
              </span>
            </div>
            <div>
              <span className="font-semibold" style={{ color: 'var(--text-muted)' }}>{t('expanded.completed')}:</span>
              <span className="ml-1 tabular-nums" style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-secondary)' }}>
                {job.completed_at ? formatRelativeTime(job.completed_at) : '\u2014'}
              </span>
            </div>
          </div>

          {job.error && (
            <div>
              <span className="font-semibold" style={{ color: 'var(--text-muted)' }}>{t('expanded.error')}:</span>
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
              <span className="font-semibold" style={{ color: 'var(--text-muted)' }}>{t('expanded.stats')}:</span>
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
              {/* Quality score summary chips — shown when translation quality data is present */}
              {job.stats?.avg_quality !== undefined && (() => {
                const avgQ = Number(job.stats?.avg_quality ?? 0)
                const lowLines = Number(job.stats?.low_quality_lines ?? 0)
                const qualityColor = avgQ >= 75
                  ? { bg: 'rgba(16,185,129,0.12)', text: 'rgb(16 185 129)' }
                  : avgQ >= 50
                    ? { bg: 'rgba(245,158,11,0.12)', text: 'rgb(245 158 11)' }
                    : { bg: 'rgba(239,68,68,0.12)', text: 'rgb(239 68 68)' }
                return (
                  <div className="mt-1.5 flex flex-wrap gap-2">
                    <span
                      className="px-2 py-0.5 rounded text-xs font-medium"
                      style={{ backgroundColor: qualityColor.bg, color: qualityColor.text, fontFamily: 'var(--font-mono)' }}
                    >
                      Avg quality: {avgQ.toFixed(1)}%
                    </span>
                    {lowLines > 0 && (
                      <span
                        className="px-2 py-0.5 rounded text-xs font-medium"
                        style={{ backgroundColor: 'rgba(239,68,68,0.10)', color: 'rgb(239 68 68)', fontFamily: 'var(--font-mono)' }}
                      >
                        Low: {lowLines} line{lowLines !== 1 ? 's' : ''}
                      </span>
                    )}
                  </div>
                )
              })()}
            </div>
          )}
        </div>
      </td>
    </tr>
  )
}

export function ActivityPage() {
  const { t } = useTranslation('activity')
  const [page, setPage] = useState(1)
  const [statusFilter, setStatusFilter] = useState<string | undefined>()
  const [expandedId, setExpandedId] = useState<string | null>(null)
  const { data: jobs, isLoading } = useJobs(page, 50, statusFilter)
  const retryJob = useRetryJob()

  const handleRetry = (jobId: string) => {
    retryJob.mutate(jobId, {
      onSuccess: () => toast(t('retry_started')),
      onError: () => toast(t('retry_failed'), 'error'),
    })
  }

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between flex-wrap gap-4">
        <h1>{t('title')}</h1>
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
                {t(`filter.${s}`)}
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
                <th className="text-left text-[11px] font-semibold uppercase tracking-wider px-4 py-2.5" style={{ color: 'var(--text-muted)' }}>{t('table.file')}</th>
                <th className="text-left text-[11px] font-semibold uppercase tracking-wider px-3 py-2.5" style={{ color: 'var(--text-muted)' }}>{t('table.status')}</th>
                <th className="text-left text-[11px] font-semibold uppercase tracking-wider px-3 py-2.5 hidden sm:table-cell" style={{ color: 'var(--text-muted)' }}>{t('table.format')}</th>
                <th className="text-left text-[11px] font-semibold uppercase tracking-wider px-3 py-2.5 hidden md:table-cell" style={{ color: 'var(--text-muted)' }}>{t('table.time')}</th>
                <th className="text-left text-[11px] font-semibold uppercase tracking-wider px-3 py-2.5 hidden lg:table-cell" style={{ color: 'var(--text-muted)' }}>{t('table.error')}</th>
                <th className="text-right text-[11px] font-semibold uppercase tracking-wider px-4 py-2.5" style={{ color: 'var(--text-muted)' }}>{t('table.actions')}</th>
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
                              title={t('retry_job')}
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
                    {isExpanded && <ExpandedRow job={job} t={t} />}
                  </tbody>
                )
              })
            ) : (
              <tbody>
                <tr>
                  <td colSpan={6} className="px-4 py-8 text-center text-sm" style={{ color: 'var(--text-secondary)' }}>
                    {t('no_jobs')}
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
              {t('page_info', { page: jobs.page, totalPages: jobs.total_pages, total: jobs.total })}
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
