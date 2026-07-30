import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { RefreshCw, Search, ScanSearch, Download, Languages, Bell, FileDown } from 'lucide-react'

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
  /** Count of provisional-MT items with a pending-original notification (feature #8b). */
  mtPendingCount?: number
  onRefresh: () => void
  onBatchSearch: () => void
  onStartProbe: () => void
  onShowCleanupConfirm: () => void
  onBatchTranslate: () => void
  /** Opens the pending-original review modal. Omit if the feature is not wired up. */
  onOpenMtPending?: () => void
  /** Downloads the wanted list (current filters applied) as CSV or JSON. */
  onExport: (format: 'csv' | 'json') => void
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
  mtPendingCount = 0,
  onRefresh,
  onBatchSearch,
  onStartProbe,
  onShowCleanupConfirm,
  onBatchTranslate,
  onOpenMtPending,
  onExport,
}: WantedToolbarProps) {
  const { t } = useTranslation('library')
  const { t: tc } = useTranslation('common')
  const [exportOpen, setExportOpen] = useState(false)
  const exportRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!exportOpen) return
    const handle = (e: MouseEvent) => {
      if (exportRef.current && !exportRef.current.contains(e.target as Node)) {
        setExportOpen(false)
      }
    }
    document.addEventListener('mousedown', handle)
    return () => document.removeEventListener('mousedown', handle)
  }, [exportOpen])

  return (
    <div className="flex items-center justify-between flex-wrap gap-4">
      <div>
        <h1>{t('wanted.title')}</h1>
        <p className="text-sm mt-1" style={{ color: 'var(--text-secondary)' }}>
          {t('wanted.items_missing', { count: summaryTotal })}
        </p>
      </div>
      <div className="flex items-center gap-2">
        {mtPendingCount > 0 && onOpenMtPending && (
          <button
            onClick={onOpenMtPending}
            data-testid="mt-pending-toolbar-btn"
            title={t('mt_pending.toolbar_button')}
            className="relative flex items-center gap-2 px-4 py-2 rounded-md text-sm font-medium bg-surface text-foreground border border-border hover:opacity-90"
          >
            <Bell size={14} />
            {t('mt_pending.toolbar_button')}
            <span
              data-testid="mt-pending-count"
              className="inline-flex items-center justify-center min-w-[1.25rem] h-5 px-1 rounded-full text-[11px] font-semibold text-white bg-accent"
            >
              {mtPendingCount}
            </span>
          </button>
        )}
        <button
          onClick={onStartProbe}
          disabled={startProbePending || probeRunning || batchRunning}
          className="flex items-center gap-2 px-4 py-2 rounded-md text-sm font-medium hover:opacity-90"
          title={tc('ui.scan_embedded')}
          style={{
            backgroundColor: 'var(--bg-surface)',
            color: 'var(--text-primary)',
            border: '1px solid var(--border)',
          }}
        >
          <ScanSearch size={14} />
          {probeRunning ? t('wanted.scanning') : t('wanted.scan_embedded')}
        </button>
        <div className="relative" ref={exportRef}>
          <button
            onClick={() => setExportOpen((v) => !v)}
            className="flex items-center gap-2 px-4 py-2 rounded-md text-sm font-medium hover:opacity-90"
            title={t('wanted.export')}
            data-testid="wanted-export-btn"
            style={{
              backgroundColor: 'var(--bg-surface)',
              color: 'var(--text-primary)',
              border: '1px solid var(--border)',
            }}
          >
            <FileDown size={14} />
            {t('wanted.export')}
          </button>
          {exportOpen && (
            <div
              className="absolute right-0 top-11 z-50 rounded-lg shadow-lg py-1 min-w-36"
              style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)' }}
            >
              {(['csv', 'json'] as const).map((format) => (
                <button
                  key={format}
                  data-testid={`wanted-export-${format}`}
                  onClick={() => { onExport(format); setExportOpen(false) }}
                  className="w-full flex items-center gap-2 px-3 py-1.5 text-xs text-left transition-colors"
                  style={{ color: 'var(--text-secondary)' }}
                  onMouseEnter={(e) => { e.currentTarget.style.backgroundColor = 'var(--bg-surface-hover)'; e.currentTarget.style.color = 'var(--text-primary)' }}
                  onMouseLeave={(e) => { e.currentTarget.style.backgroundColor = ''; e.currentTarget.style.color = 'var(--text-secondary)' }}
                >
                  {t(`wanted.export_${format}`)}
                </button>
              ))}
            </div>
          )}
        </div>
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
            title={tc('ui.batch_translate_downloaded')}
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
