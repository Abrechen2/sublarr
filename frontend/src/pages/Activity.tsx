import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useJobs, useRetryJob } from '@/hooks/useApi'
import { StatusBadge } from '@/components/shared/StatusBadge'
import { formatRelativeTime, parseMediaTitle } from '@/lib/utils'
import { toast } from '@/components/shared/Toast'
import { ChevronLeft, ChevronRight, ChevronDown, ChevronUp, RotateCcw, Loader2 } from 'lucide-react'
import type { Job } from '@/lib/types'

const SOURCE_LABELS: Record<string, string> = {
  embedded_ass: 'Embedded (ASS)',
  embedded_srt: 'Embedded (SRT)',
  embedded: 'Embedded',
  sidecar_ass: 'Sidecar (ASS)',
  sidecar_srt: 'Sidecar (SRT)',
  downloaded_ass: 'Downloaded (ASS)',
  downloaded_srt: 'Downloaded (SRT)',
}

function QualityChip({ avgQuality }: { avgQuality: number }) {
  const color =
    avgQuality >= 75 ? 'rgb(16 185 129)' : avgQuality >= 50 ? 'rgb(245 158 11)' : 'rgb(239 68 68)'
  const bg =
    avgQuality >= 75
      ? 'rgba(16,185,129,0.12)'
      : avgQuality >= 50
        ? 'rgba(245,158,11,0.12)'
        : 'rgba(239,68,68,0.12)'
  return (
    <span
      className="px-1.5 py-0.5 rounded text-[10px] font-medium tabular-nums shrink-0"
      style={{ backgroundColor: bg, color, fontFamily: 'var(--font-mono)' }}
    >
      ⌀ {avgQuality.toFixed(1)}%
    </span>
  )
}

function ExpandedRow({ job, t }: { job: Job; t: (key: string, opts?: Record<string, unknown>) => string }) {
  const stats = job.stats ?? {}
  const avgQuality = stats.avg_quality !== undefined ? Number(stats.avg_quality) : null
  const lowLines = Number(stats.low_quality_lines ?? 0)
  const source = String(stats.source ?? '')
  const backendName = String(stats.backend_name ?? '')
  const totalEvents = Number(stats.total_events ?? 0)
  const translated = Number(stats.translated ?? 0)

  const qualityBarColor =
    avgQuality === null
      ? 'var(--text-muted)'
      : avgQuality >= 75
        ? 'rgb(16 185 129)'
        : avgQuality >= 50
          ? 'rgb(245 158 11)'
          : 'rgb(239 68 68)'

  const sourceLabel = SOURCE_LABELS[source] || (source ? source.replace(/_/g, ' ') : null)

  return (
    <tr style={{ backgroundColor: 'var(--bg-primary)' }}>
      <td colSpan={6} className="px-4 py-3">
        <div className="space-y-3 text-xs">

          {/* Paths */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            <div>
              <div className="font-semibold mb-0.5" style={{ color: 'var(--text-muted)' }}>
                {t('expanded.full_path')}
              </div>
              <div style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-secondary)', wordBreak: 'break-all' }}>
                {job.file_path}
              </div>
            </div>
            {job.output_path && (
              <div>
                <div className="font-semibold mb-0.5" style={{ color: 'var(--text-muted)' }}>
                  {t('expanded.output')}
                </div>
                <div style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-secondary)', wordBreak: 'break-all' }}>
                  {job.output_path}
                </div>
              </div>
            )}
          </div>

          {/* Translation quality */}
          {avgQuality !== null && (
            <div className="space-y-1.5">
              <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
                {sourceLabel && (
                  <span>
                    <span style={{ color: 'var(--text-muted)' }}>{t('expanded.source')}: </span>
                    <span style={{ color: 'var(--text-secondary)' }}>{sourceLabel}</span>
                  </span>
                )}
                {backendName && (
                  <span
                    className="px-1.5 py-0.5 rounded text-[10px] font-medium uppercase"
                    style={{ backgroundColor: 'var(--accent-bg)', color: 'var(--accent)', fontFamily: 'var(--font-mono)' }}
                  >
                    {backendName}
                  </span>
                )}
                {totalEvents > 0 && (
                  <span style={{ color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
                    {translated}/{totalEvents} {t('expanded.lines')}
                  </span>
                )}
              </div>
              <div className="flex items-center gap-2">
                <div
                  className="flex-1 rounded-full overflow-hidden"
                  style={{ height: '4px', backgroundColor: 'var(--border)' }}
                >
                  <div
                    className="h-full rounded-full"
                    style={{ width: `${Math.min(100, avgQuality)}%`, backgroundColor: qualityBarColor }}
                  />
                </div>
                <span
                  className="tabular-nums font-medium"
                  style={{ fontFamily: 'var(--font-mono)', color: qualityBarColor, minWidth: '3.5rem', textAlign: 'right' }}
                >
                  {avgQuality.toFixed(1)}%
                </span>
                {lowLines > 0 && (
                  <span
                    className="px-1.5 py-0.5 rounded text-[10px]"
                    style={{ backgroundColor: 'rgba(239,68,68,0.10)', color: 'rgb(239 68 68)' }}
                  >
                    {lowLines} low
                  </span>
                )}
              </div>
            </div>
          )}

          {/* Job details */}
          <div className="flex flex-wrap gap-x-4 gap-y-1" style={{ color: 'var(--text-secondary)' }}>
            {job.source_format && (
              <span>
                <span style={{ color: 'var(--text-muted)' }}>{t('expanded.format')}: </span>
                <span className="uppercase" style={{ fontFamily: 'var(--font-mono)' }}>{job.source_format}</span>
              </span>
            )}
            <span>
              <span style={{ color: 'var(--text-muted)' }}>{t('expanded.force')}: </span>
              {job.force ? t('expanded.force_yes') : t('expanded.force_no')}
            </span>
            {job.created_at && (
              <span>
                <span style={{ color: 'var(--text-muted)' }}>{t('expanded.created')}: </span>
                <span style={{ fontFamily: 'var(--font-mono)' }}>{formatRelativeTime(job.created_at)}</span>
              </span>
            )}
            {job.completed_at && (
              <span>
                <span style={{ color: 'var(--text-muted)' }}>{t('expanded.completed')}: </span>
                <span style={{ fontFamily: 'var(--font-mono)' }}>{formatRelativeTime(job.completed_at)}</span>
              </span>
            )}
          </div>

          {/* Error */}
          {job.error && (
            <div
              className="px-2.5 py-1.5 rounded"
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
                <th className="text-left text-[11px] font-semibold uppercase tracking-wider px-4 py-2.5" style={{ color: 'var(--text-muted)' }}>{t('table.content')}</th>
                <th className="text-left text-[11px] font-semibold uppercase tracking-wider px-3 py-2.5" style={{ color: 'var(--text-muted)' }}>{t('table.status')}</th>
                <th className="text-left text-[11px] font-semibold uppercase tracking-wider px-3 py-2.5 hidden sm:table-cell" style={{ color: 'var(--text-muted)' }}>{t('table.lang')}</th>
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
                    <td className="px-3 py-3 hidden sm:table-cell"><div className="skeleton h-4 w-14 rounded" /></td>
                    <td className="px-3 py-3 hidden md:table-cell"><div className="skeleton h-4 w-14 rounded" /></td>
                    <td className="px-3 py-3 hidden lg:table-cell"><div className="skeleton h-4 w-32 rounded" /></td>
                    <td className="px-4 py-3"><div className="skeleton h-6 w-12 rounded ml-auto" /></td>
                  </tr>
                ))}
              </tbody>
            ) : jobs?.data?.length ? (
              jobs.data.map((job) => {
                const isExpanded = expandedId === job.id
                const media = parseMediaTitle(job.file_path)
                const avgQuality = job.stats?.avg_quality !== undefined ? Number(job.stats.avg_quality) : null
                const srcLang = job.arr_context?.source_language as string | undefined
                const tgtLang = job.arr_context?.target_language as string | undefined
                const langLabel =
                  srcLang && tgtLang
                    ? `${srcLang.toUpperCase()} → ${tgtLang.toUpperCase()}`
                    : srcLang
                      ? srcLang.toUpperCase()
                      : null
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
                        <div className="flex items-start gap-1.5">
                          {isExpanded ? (
                            <ChevronUp size={12} className="mt-1 shrink-0" style={{ color: 'var(--accent)' }} />
                          ) : (
                            <ChevronDown size={12} className="mt-1 shrink-0" style={{ color: 'var(--text-muted)' }} />
                          )}
                          <div className="min-w-0">
                            <div
                              className="font-medium text-sm truncate max-w-xs"
                              style={{ color: 'var(--text-primary)' }}
                            >
                              {media.title}
                            </div>
                            {(media.episodeCode || avgQuality !== null) && (
                              <div className="flex items-center gap-1.5 mt-0.5">
                                {media.episodeCode && (
                                  <span
                                    className="text-[11px] truncate max-w-[180px]"
                                    style={{ color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}
                                  >
                                    {media.episodeCode}{media.episodeTitle ? ` · ${media.episodeTitle}` : ''}
                                  </span>
                                )}
                                {avgQuality !== null && <QualityChip avgQuality={avgQuality} />}
                              </div>
                            )}
                          </div>
                        </div>
                      </td>
                      <td className="px-3 py-2.5">
                        <StatusBadge status={job.status} />
                      </td>
                      <td className="px-3 py-2.5 hidden sm:table-cell">
                        {langLabel ? (
                          <span
                            className="text-xs font-medium tabular-nums"
                            style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-secondary)' }}
                          >
                            {langLabel}
                          </span>
                        ) : (
                          <span style={{ color: 'var(--text-muted)' }}>—</span>
                        )}
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
