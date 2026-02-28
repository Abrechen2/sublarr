import { memo } from 'react'
import { useTranslation } from 'react-i18next'
import { useJobs, useBatchStatus, useWantedBatchStatus, useWantedBatchProbeStatus, useScannerStatus } from '@/hooks/useApi'
import { StatusBadge } from '@/components/shared/StatusBadge'
import { ProgressBar } from '@/components/shared/ProgressBar'
import { truncatePath } from '@/lib/utils'
import { Layers, Loader2, ScanSearch, Search } from 'lucide-react'

const QueueJobRow = memo(function QueueJobRow({ file_path, status }: { file_path: string; status: 'running' | 'queued' }) {
  return (
    <div className="px-4 py-2.5 flex items-center gap-3">
      {status === 'running' ? (
        <Loader2 size={14} className="animate-spin" style={{ color: 'var(--accent)' }} />
      ) : (
        <div className="w-3.5 h-3.5 rounded-full shrink-0" style={{ border: '2px solid var(--warning)' }} />
      )}
      <span
        className="flex-1 truncate"
        title={file_path}
        style={{ fontFamily: 'var(--font-mono)', fontSize: '12px' }}
      >
        {truncatePath(file_path)}
      </span>
      <StatusBadge status={status} />
    </div>
  )
})

export function QueuePage() {
  const { t } = useTranslation('activity')
  const { data: activeJobs } = useJobs(1, 20, 'running', 3000)
  const { data: queuedJobs } = useJobs(1, 20, 'queued', 3000)
  const { data: batch } = useBatchStatus()
  const { data: wantedBatch } = useWantedBatchStatus()
  const { data: probe } = useWantedBatchProbeStatus()
  const { data: scanner } = useScannerStatus()

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

      {/* Wanted Batch Search Status */}
      {wantedBatch?.running && (
        <div
          className="rounded-lg p-4"
          style={{
            backgroundColor: 'var(--bg-surface)',
            border: '1px solid var(--border)',
            borderLeft: '3px solid var(--warning)',
          }}
        >
          <div className="flex items-center gap-2 mb-3">
            <Search size={16} className="animate-pulse" style={{ color: 'var(--warning)' }} />
            <h2 className="text-sm font-semibold">{t('queue.wanted_batch_searching')}</h2>
          </div>
          <ProgressBar value={wantedBatch.processed} max={wantedBatch.total} className="mb-3" />
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-5 gap-3 text-sm">
            <div>
              <span style={{ color: 'var(--text-muted)' }}>{t('queue.total')}: </span>
              <span style={{ fontFamily: 'var(--font-mono)' }}>{wantedBatch.total}</span>
            </div>
            <div>
              <span style={{ color: 'var(--text-muted)' }}>{t('queue.processed')}: </span>
              <span style={{ fontFamily: 'var(--font-mono)' }}>{wantedBatch.processed}</span>
            </div>
            <div>
              <span style={{ color: 'var(--text-muted)' }}>{t('queue.succeeded')}: </span>
              <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--success)' }}>{wantedBatch.found}</span>
            </div>
            <div>
              <span style={{ color: 'var(--text-muted)' }}>{t('queue.failed')}: </span>
              <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--error)' }}>{wantedBatch.failed}</span>
            </div>
            <div>
              <span style={{ color: 'var(--text-muted)' }}>{t('queue.skipped')}: </span>
              <span style={{ fontFamily: 'var(--font-mono)' }}>{wantedBatch.skipped}</span>
            </div>
          </div>
          {wantedBatch.current_item && (
            <div
              className="mt-3 text-xs truncate"
              style={{ color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}
            >
              {t('queue.current')}: {truncatePath(wantedBatch.current_item, 80)}
            </div>
          )}
        </div>
      )}

      {/* Batch Probe Status */}
      {probe?.running && (
        <div
          className="rounded-lg p-4"
          style={{
            backgroundColor: 'var(--bg-surface)',
            border: '1px solid var(--border)',
            borderLeft: '3px solid var(--accent)',
          }}
        >
          <div className="flex items-center gap-2 mb-3">
            <Layers size={16} className="animate-pulse" style={{ color: 'var(--accent)' }} />
            <h2 className="text-sm font-semibold">{t('queue.batch_probe_running')}</h2>
          </div>
          <ProgressBar value={probe.extracted ?? 0} max={probe.total} className="mb-3" />
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-sm">
            <div>
              <span style={{ color: 'var(--text-muted)' }}>{t('queue.total')}: </span>
              <span style={{ fontFamily: 'var(--font-mono)' }}>{probe.total}</span>
            </div>
            <div>
              <span style={{ color: 'var(--text-muted)' }}>{t('queue.found')}: </span>
              <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--success)' }}>{probe.found}</span>
            </div>
            <div>
              <span style={{ color: 'var(--text-muted)' }}>{t('queue.extracted')}: </span>
              <span style={{ fontFamily: 'var(--font-mono)' }}>{probe.extracted}</span>
            </div>
            <div>
              <span style={{ color: 'var(--text-muted)' }}>{t('queue.failed')}: </span>
              <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--error)' }}>{probe.failed}</span>
            </div>
          </div>
          {probe.current_item && (
            <div
              className="mt-3 text-xs truncate"
              style={{ color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}
            >
              {t('queue.current')}: {truncatePath(probe.current_item, 80)}
            </div>
          )}
        </div>
      )}

      {/* Wanted Scanner Status */}
      {(scanner?.is_scanning || scanner?.is_searching) && (
        <div
          className="rounded-lg p-4"
          style={{
            backgroundColor: 'var(--bg-surface)',
            border: '1px solid var(--border)',
            borderLeft: '3px solid var(--success)',
          }}
        >
          <div className="flex items-center gap-2 mb-3">
            <ScanSearch size={16} className="animate-pulse" style={{ color: 'var(--success)' }} />
            <h2 className="text-sm font-semibold">{t('queue.scanner_running')}</h2>
            {scanner.progress.phase && (
              <span
                className="text-xs px-2 py-0.5 rounded"
                style={{ backgroundColor: 'var(--bg-primary)', color: 'var(--text-muted)' }}
              >
                {scanner.progress.phase}
              </span>
            )}
          </div>
          {scanner.progress.total > 0 && (
            <ProgressBar value={scanner.progress.current} max={scanner.progress.total} className="mb-3" />
          )}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-sm">
            <div>
              <span style={{ color: 'var(--text-muted)' }}>{t('queue.progress')}: </span>
              <span style={{ fontFamily: 'var(--font-mono)' }}>
                {scanner.progress.current}/{scanner.progress.total}
              </span>
            </div>
            <div>
              <span style={{ color: 'var(--text-muted)' }}>{t('queue.added')}: </span>
              <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--success)' }}>{scanner.progress.added}</span>
            </div>
            <div>
              <span style={{ color: 'var(--text-muted)' }}>{t('queue.updated')}: </span>
              <span style={{ fontFamily: 'var(--font-mono)' }}>{scanner.progress.updated}</span>
            </div>
          </div>
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
              <QueueJobRow key={job.id} file_path={job.file_path} status="running" />
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
              <QueueJobRow key={job.id} file_path={job.file_path} status="queued" />
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
