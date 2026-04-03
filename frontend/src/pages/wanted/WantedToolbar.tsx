import { useTranslation } from 'react-i18next'
import { RefreshCw, Search, ScanSearch, Download, Languages, Loader2 } from 'lucide-react'

export interface WantedToolbarProps {
  summaryTotal: number
  scanRunning: boolean | undefined
  batchRunning: boolean | undefined
  startBatchPending: boolean
  refreshPending: boolean
  startProbePending: boolean
  probeRunning: boolean | undefined
  cleanupPending: boolean
  batchTranslatePending: boolean
  translationEnabled: boolean
  onRefresh: () => void
  onBatchSearch: () => void
  onStartProbe: () => void
  onShowCleanupConfirm: () => void
  onBatchTranslate: () => void
}

export function WantedToolbar({
  summaryTotal,
  scanRunning,
  batchRunning,
  startBatchPending,
  refreshPending,
  startProbePending,
  probeRunning,
  cleanupPending,
  batchTranslatePending,
  translationEnabled,
  onRefresh,
  onBatchSearch,
  onStartProbe,
  onShowCleanupConfirm,
  onBatchTranslate,
}: WantedToolbarProps) {
  const { t } = useTranslation('library')

  return (
    <div className="flex items-center justify-between flex-wrap gap-4">
      <div>
        <h1>{t('wanted.title')}</h1>
        <p className="text-sm mt-1" style={{ color: 'var(--text-secondary)' }}>
          {t('wanted.items_missing', { count: summaryTotal })}
        </p>
      </div>
      <div className="flex items-center gap-2">
        <button
          onClick={onStartProbe}
          disabled={startProbePending || probeRunning || batchRunning}
          className="flex items-center gap-2 px-4 py-2 rounded-md text-sm font-medium hover:opacity-90"
          title="Scan for embedded subtitles in all unresolved items"
          style={{
            backgroundColor: 'var(--bg-surface)',
            color: 'var(--text-primary)',
            border: '1px solid var(--border)',
          }}
        >
          <ScanSearch size={14} />
          {probeRunning ? t('wanted.scanning') : t('wanted.scan_embedded')}
        </button>
        <button
          onClick={onShowCleanupConfirm}
          disabled={cleanupPending}
          className="flex items-center gap-2 px-4 py-2 rounded-md text-sm font-medium hover:opacity-90"
          title={t('wanted.cleanup')}
          data-testid="wanted-cleanup-btn"
          style={{
            backgroundColor: 'var(--bg-surface)',
            color: 'var(--text-primary)',
            border: '1px solid var(--border)',
          }}
        >
          <Download size={14} />
          {t('wanted.cleanup')}
        </button>
        {translationEnabled && (
          <button
            onClick={onBatchTranslate}
            disabled={batchTranslatePending}
            className="flex items-center gap-2 px-4 py-2 rounded-md text-sm font-medium hover:opacity-90"
            title="Batch translate downloaded subtitles"
            data-testid="batch-translate-btn"
            style={{
              backgroundColor: 'var(--bg-surface)',
              color: 'var(--text-primary)',
              border: '1px solid var(--border)',
            }}
          >
            <Languages size={14} />
            Batch Translate
          </button>
        )}
        <button
          onClick={onBatchSearch}
          disabled={startBatchPending || batchRunning}
          className="flex items-center gap-2 px-4 py-2 rounded-md text-sm font-medium hover:opacity-90"
          style={{
            backgroundColor: 'var(--bg-surface)',
            color: 'var(--text-primary)',
            border: '1px solid var(--border)',
          }}
        >
          <Search size={14} />
          {batchRunning ? t('wanted.searching') : t('wanted.search_all')}
        </button>
        <button
          onClick={onRefresh}
          disabled={refreshPending || scanRunning}
          className="flex items-center gap-2 px-4 py-2 rounded-md text-sm font-medium text-white hover:opacity-90"
          data-testid="wanted-refresh-btn"
          style={{ backgroundColor: 'var(--accent)' }}
        >
          <RefreshCw
            size={14}
            className={refreshPending || scanRunning ? 'animate-spin' : ''}
          />
          {scanRunning ? t('wanted.scanning') : t('wanted.refresh')}
        </button>
      </div>
    </div>
  )
}
