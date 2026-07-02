import { memo } from 'react'
import { useTranslation } from 'react-i18next'
import { useJobs, useBatchStatus, useCancelJob, useClearQueuedJobs } from '@/hooks/useApi'
import { StatusBadge } from '@/components/shared/StatusBadge'
import { ProgressBar } from '@/components/shared/ProgressBar'
import { toast } from '@/components/shared/Toast'
import { truncatePath } from '@/lib/utils'
import { Layers, Loader2, X } from 'lucide-react'

const TranslationJobRow = memo(function TranslationJobRow({
  file_path,
  status,
  cancelLabel,
  onCancel,
  cancelDisabled,
}: {
  file_path: string
  status: 'running' | 'queued'
  cancelLabel?: string
  onCancel?: () => void
  cancelDisabled?: boolean
}) {
  return (
    <div className="px-4 py-2.5 flex items-center gap-3">
      {status === 'running' ? (
        <Loader2 size={14} className="animate-spin" style={{ color: 'var(--accent)' }} />
      ) : (
        <div
          className="w-3.5 h-3.5 rounded-full shrink-0"
          style={{ border: '2px solid var(--warning)' }}
        />
      )}
      <span
        className="flex-1 truncate"
        title={file_path}
        style={{ fontFamily: 'var(--font-mono)', fontSize: '12px' }}
      >
        {truncatePath(file_path)}
      </span>
      <StatusBadge status={status} />
      {onCancel && (
        <button
          type="button"
          aria-label={cancelLabel}
          title={cancelLabel}
          onClick={onCancel}
          disabled={cancelDisabled}
          className="shrink-0 p-1 rounded-md text-muted hover:text-error hover:bg-surface-hover transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
        >
          <X size={14} />
        </button>
      )}
    </div>
  )
})

export function TranslationsTab() {
  const { t } = useTranslation('activity')
  const { data: activeJobs } = useJobs(1, 20, 'running', 3000)
  const { data: queuedJobs } = useJobs(1, 20, 'queued', 3000)
  const { data: batch } = useBatchStatus()
  const cancelJob = useCancelJob()
  const clearQueued = useClearQueuedJobs()

  const queuedCount = queuedJobs?.data?.length ?? 0

  const handleCancelJob = (jobId: string) => {
    cancelJob.mutate(jobId, {
      onSuccess: () => toast(t('translations.cancel_success'), 'success'),
      onError: () => toast(t('translations.cancel_failed'), 'error'),
    })
  }

  const handleClearQueued = () => {
    clearQueued.mutate(undefined, {
      onSuccess: (res) => toast(t('translations.clear_success', { n: res.cancelled }), 'success'),
      onError: () => toast(t('translations.clear_failed'), 'error'),
    })
  }

  const hasActivity =
    batch?.running ||
    (activeJobs?.data?.length ?? 0) > 0 ||
    (queuedJobs?.data?.length ?? 0) > 0

  return (
    <div className="space-y-5">
      {/* Batch Processing Status */}
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
              <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--success)' }}>
                {batch.succeeded}
              </span>
            </div>
            <div>
              <span style={{ color: 'var(--text-muted)' }}>{t('queue.failed')}: </span>
              <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--error)' }}>
                {batch.failed}
              </span>
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

      {/* Active Translation Jobs */}
      <div
        className="rounded-lg overflow-hidden"
        style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)' }}
      >
        <div className="px-4 py-3" style={{ borderBottom: '1px solid var(--border)' }}>
          <h2
            className="text-xs font-semibold uppercase tracking-wider"
            style={{ color: 'var(--text-muted)' }}
          >
            {t('queue.running_count', { count: activeJobs?.data?.length ?? 0 })}
          </h2>
        </div>
        <div className="divide-y" style={{ borderColor: 'var(--border)' }}>
          {activeJobs?.data?.length ? (
            activeJobs.data.map((job) => (
              <TranslationJobRow key={job.id} file_path={job.file_path} status="running" />
            ))
          ) : (
            <div className="px-4 py-6 text-center text-sm" style={{ color: 'var(--text-secondary)' }}>
              {t('translations.no_active', 'No active translation jobs')}
            </div>
          )}
        </div>
      </div>

      {/* Queued Translation Jobs */}
      <div
        className="rounded-lg overflow-hidden"
        style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)' }}
      >
        <div
          className="px-4 py-3 flex items-center justify-between gap-3"
          style={{ borderBottom: '1px solid var(--border)' }}
        >
          <h2
            className="text-xs font-semibold uppercase tracking-wider"
            style={{ color: 'var(--text-muted)' }}
          >
            {t('queue.queued_count', { count: queuedCount })}
          </h2>
          <button
            type="button"
            onClick={handleClearQueued}
            disabled={clearQueued.isPending || queuedCount === 0}
            className="text-xs px-2 py-1 rounded-md border border-border text-secondary hover:bg-surface-hover transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {t('translations.clear_queued')}
          </button>
        </div>
        <div className="divide-y" style={{ borderColor: 'var(--border)' }}>
          {queuedJobs?.data?.length ? (
            queuedJobs.data.map((job) => (
              <TranslationJobRow
                key={job.id}
                file_path={job.file_path}
                status="queued"
                cancelLabel={t('translations.cancel_job')}
                onCancel={() => handleCancelJob(job.id)}
                cancelDisabled={cancelJob.isPending}
              />
            ))
          ) : (
            <div className="px-4 py-6 text-center text-sm" style={{ color: 'var(--text-secondary)' }}>
              {t('translations.no_queued', 'No queued translation jobs')}
            </div>
          )}
        </div>
      </div>

      {/* Empty state when nothing is happening */}
      {!hasActivity && (
        <div
          className="rounded-lg p-8 text-center"
          style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)' }}
        >
          <Layers size={32} className="mx-auto mb-3" style={{ color: 'var(--text-muted)' }} />
          <p className="text-sm" style={{ color: 'var(--text-secondary)' }}>
            {t(
              'translations.empty',
              'No translation jobs running. Translations start automatically after subtitle download.',
            )}
          </p>
        </div>
      )}
    </div>
  )
}
