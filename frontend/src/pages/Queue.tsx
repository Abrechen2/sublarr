import { useTranslation } from 'react-i18next'
import { useJobs, useBatchStatus } from '@/hooks/useApi'
import { StatusBadge } from '@/components/shared/StatusBadge'
import { ProgressBar } from '@/components/shared/ProgressBar'
import { truncatePath } from '@/lib/utils'
import { Loader2 } from 'lucide-react'

export function QueuePage() {
  const { t } = useTranslation('activity')
  const { data: activeJobs } = useJobs(1, 20, 'running')
  const { data: queuedJobs } = useJobs(1, 20, 'queued')
  const { data: batch } = useBatchStatus()

  return (
    <div className="space-y-5">
      <h1>{t('queue.title')}</h1>

      {/* Batch Status */}
      {batch?.running && (
        <div
          className="rounded-lg p-4"
          style={{
            backgroundColor: 'var(--bg-surface)',
            border: '1px solid var(--border)',
            borderLeft: '3px solid var(--accent)',
          }}
        >
          <div className="flex items-center gap-2 mb-3">
            <Loader2 size={16} className="animate-spin" style={{ color: 'var(--accent)' }} />
            <h2 className="text-sm font-semibold">{t('queue.batch_processing')}</h2>
          </div>
          <ProgressBar value={batch.processed} max={batch.total} className="mb-3" />
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-5 gap-3 text-sm">
            <div>
              <span style={{ color: 'var(--text-muted)' }}>{t('queue.total')}: </span>
              <span style={{ fontFamily: 'var(--font-mono)' }}>{batch.total}</span>
            </div>
            <div>
              <span style={{ color: 'var(--text-muted)' }}>{t('queue.processed')}: </span>
              <span style={{ fontFamily: 'var(--font-mono)' }}>{batch.processed}</span>
            </div>
            <div>
              <span style={{ color: 'var(--text-muted)' }}>{t('queue.succeeded')}: </span>
              <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--success)' }}>{batch.succeeded}</span>
            </div>
            <div>
              <span style={{ color: 'var(--text-muted)' }}>{t('queue.failed')}: </span>
              <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--error)' }}>{batch.failed}</span>
            </div>
            <div>
              <span style={{ color: 'var(--text-muted)' }}>{t('queue.skipped')}: </span>
              <span style={{ fontFamily: 'var(--font-mono)' }}>{batch.skipped}</span>
            </div>
          </div>
          {batch.current_file && (
            <div
              className="mt-3 text-xs truncate"
              style={{ color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}
            >
              {t('queue.current')}: {truncatePath(batch.current_file, 80)}
            </div>
          )}
        </div>
      )}

      {/* Active Jobs */}
      <div
        className="rounded-lg overflow-hidden"
        style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)' }}
      >
        <div className="px-4 py-3" style={{ borderBottom: '1px solid var(--border)' }}>
          <h2 className="text-xs font-semibold uppercase tracking-wider" style={{ color: 'var(--text-muted)' }}>
            {t('queue.running_count', { count: activeJobs?.data?.length ?? 0 })}
          </h2>
        </div>
        <div className="divide-y" style={{ borderColor: 'var(--border)' }}>
          {activeJobs?.data?.length ? (
            activeJobs.data.map((job) => (
              <div key={job.id} className="px-4 py-2.5 flex items-center gap-3">
                <Loader2 size={14} className="animate-spin" style={{ color: 'var(--accent)' }} />
                <span
                  className="flex-1 truncate"
                  title={job.file_path}
                  style={{ fontFamily: 'var(--font-mono)', fontSize: '12px' }}
                >
                  {truncatePath(job.file_path)}
                </span>
                <StatusBadge status="running" />
              </div>
            ))
          ) : (
            <div className="px-4 py-6 text-center text-sm" style={{ color: 'var(--text-secondary)' }}>
              {t('queue.no_active')}
            </div>
          )}
        </div>
      </div>

      {/* Queued Jobs */}
      <div
        className="rounded-lg overflow-hidden"
        style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)' }}
      >
        <div className="px-4 py-3" style={{ borderBottom: '1px solid var(--border)' }}>
          <h2 className="text-xs font-semibold uppercase tracking-wider" style={{ color: 'var(--text-muted)' }}>
            {t('queue.queued_count', { count: queuedJobs?.data?.length ?? 0 })}
          </h2>
        </div>
        <div className="divide-y" style={{ borderColor: 'var(--border)' }}>
          {queuedJobs?.data?.length ? (
            queuedJobs.data.map((job) => (
              <div key={job.id} className="px-4 py-2.5 flex items-center gap-3">
                <div
                  className="w-3.5 h-3.5 rounded-full shrink-0"
                  style={{ border: '2px solid var(--warning)' }}
                />
                <span
                  className="flex-1 truncate"
                  title={job.file_path}
                  style={{ fontFamily: 'var(--font-mono)', fontSize: '12px' }}
                >
                  {truncatePath(job.file_path)}
                </span>
                <StatusBadge status="queued" />
              </div>
            ))
          ) : (
            <div className="px-4 py-6 text-center text-sm" style={{ color: 'var(--text-secondary)' }}>
              {t('queue.no_queued')}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
