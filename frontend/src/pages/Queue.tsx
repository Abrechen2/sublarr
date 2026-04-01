import { useTranslation } from 'react-i18next'
import { useWantedBatchStatus, useWantedBatchProbeStatus, useScannerStatus } from '@/hooks/useApi'
import { ProgressBar } from '@/components/shared/ProgressBar'
import { truncatePath } from '@/lib/utils'
import { Layers, Loader2, ListVideo, ScanSearch, Search } from 'lucide-react'

export function QueuePage() {
  const { t } = useTranslation('activity')
  const { data: wantedBatch } = useWantedBatchStatus()
  const { data: probe } = useWantedBatchProbeStatus()
  const { data: scanner } = useScannerStatus()

  const isActive = wantedBatch?.running || probe?.running || scanner?.is_scanning || scanner?.is_searching

  return (
    <div className="space-y-5">
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

      {/* Empty state */}
      {!isActive && (
        <div
          className="rounded-lg p-8 text-center"
          style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)' }}
        >
          <ListVideo size={32} className="mx-auto mb-3" style={{ color: 'var(--text-muted)' }} />
          <p className="text-sm" style={{ color: 'var(--text-secondary)' }}>
            {t('queue.empty', 'No active subtitle searches. Use "Search All" on the Wanted page to start.')}
          </p>
        </div>
      )}
    </div>
  )
}
