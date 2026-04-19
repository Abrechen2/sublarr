import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { X, ChevronRight } from 'lucide-react'
import { useSchedulerJobRuns } from '@/hooks/useSchedulerJobRuns'
import type { SchedulerStatus } from '@/lib/types'
import { StatusBadge } from './StatusBadge'

const STATUS_FILTERS: (SchedulerStatus | 'all')[] = [
  'all', 'ok', 'error', 'timeout', 'missed', 'skipped_overlap',
]

export function JobHistoryDrawer({
  jobId,
  open,
  onClose,
}: {
  jobId: string
  open: boolean
  onClose: () => void
}) {
  const { t } = useTranslation('settings')
  const [status, setStatus] = useState<SchedulerStatus | 'all'>('all')
  const [expanded, setExpanded] = useState<number | null>(null)
  const { data, isLoading } = useSchedulerJobRuns(
    jobId,
    { limit: 50, status: status === 'all' ? undefined : status },
    open,
  )

  if (!open) return null

  return (
    <div className="fixed inset-0 z-40 flex">
      <div
        className="flex-1 bg-black/40"
        onClick={onClose}
        role="presentation"
      />
      <div className="flex w-full max-w-2xl flex-col bg-surface shadow-lg">
        <div className="flex items-center justify-between border-b border-border p-4">
          <h2 className="font-medium">
            {t('scheduler.history_for', { job: jobId })}
          </h2>
          <button onClick={onClose} aria-label={t('common.close', { defaultValue: 'Close' })}>
            <X size={20} />
          </button>
        </div>

        <div className="flex gap-1 overflow-x-auto border-b border-border p-2">
          {STATUS_FILTERS.map((s) => (
            <button
              key={s}
              onClick={() => setStatus(s)}
              className={`rounded-full px-3 py-1 text-xs ${
                status === s
                  ? 'bg-accent text-white'
                  : 'hover:bg-surface-hover'
              }`}
            >
              {t(`scheduler.status.${s}`, { defaultValue: s })}
            </button>
          ))}
        </div>

        <div className="flex-1 overflow-y-auto">
          {isLoading && (
            <div className="p-4 text-muted">
              {t('common.loading', { defaultValue: 'Loading...' })}
            </div>
          )}
          {data && data.runs.length === 0 && (
            <div className="p-4 text-muted">{t('scheduler.no_runs')}</div>
          )}
          {data &&
            data.runs.map((r) => (
              <div key={r.id} className="border-b border-border">
                <button
                  onClick={() => setExpanded(expanded === r.id ? null : r.id)}
                  className="flex w-full items-center gap-3 px-4 py-2 text-left hover:bg-surface-hover"
                >
                  <ChevronRight
                    size={14}
                    className={`transition-transform ${
                      expanded === r.id ? 'rotate-90' : ''
                    }`}
                  />
                  <StatusBadge status={r.status} />
                  <span className="font-mono text-xs text-muted">
                    {r.started_at && new Date(r.started_at).toLocaleString()}
                  </span>
                  <span className="ml-auto text-xs text-muted">
                    {r.duration_ms != null ? `${r.duration_ms}ms` : '—'}
                  </span>
                </button>
                {expanded === r.id && (r.error_msg || r.error_type) && (
                  <div className="bg-elevated px-10 py-2 font-mono text-xs">
                    {r.error_type && (
                      <div className="font-semibold">{r.error_type}</div>
                    )}
                    {r.error_msg && (
                      <pre className="mt-1 whitespace-pre-wrap break-words text-muted">
                        {r.error_msg}
                      </pre>
                    )}
                  </div>
                )}
              </div>
            ))}
        </div>
      </div>
    </div>
  )
}
