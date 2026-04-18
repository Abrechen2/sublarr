import { useCallback, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useWantedBatchStatus, useWantedBatchProbeStatus, useScannerStatus } from '@/hooks/useApi'
import { useWebSocket } from '@/hooks/useWebSocket'
import { ProgressBar } from '@/components/shared/ProgressBar'
import { truncatePath } from '@/lib/utils'
import { Layers, ListVideo, ScanSearch, Search } from 'lucide-react'

interface ProviderSummary {
  active: number
  throttled: number
  circuit_open: number
  throttled_providers: { name: string; remaining_seconds: number }[]
}

export function QueuePage() {
  const { t } = useTranslation('activity')
  const { data: wantedBatch } = useWantedBatchStatus()
  const { data: probe } = useWantedBatchProbeStatus()
  const { data: scanner } = useScannerStatus()

  // Track provider summary from WebSocket search progress events
  const [providerSummary, setProviderSummary] = useState<ProviderSummary | null>(null)
  const handleSearchProgress = useCallback((data: unknown) => {
    const d = data as { provider_summary?: ProviderSummary }
    if (d?.provider_summary) setProviderSummary(d.provider_summary)
  }, [])
  const handleSearchCompleted = useCallback(() => setProviderSummary(null), [])
  useWebSocket({
    onWantedSearchProgress: handleSearchProgress,
    onWantedSearchCompleted: handleSearchCompleted,
  })

  const isActive = wantedBatch?.running || probe?.running || scanner?.is_scanning || scanner?.is_searching

  return (
    <div className="space-y-5">
      {/* Wanted Batch Search Status */}
      {wantedBatch?.running && (
        <div className="rounded-lg p-4 bg-surface border border-border border-l-[3px] border-l-warning">
          <div className="flex items-center gap-2 mb-3">
            <Search size={16} className="animate-pulse text-warning" />
            <h2 className="text-sm font-semibold">{t('queue.wanted_batch_searching')}</h2>
          </div>
          <ProgressBar value={wantedBatch.processed} max={wantedBatch.total} className="mb-3" />
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-5 gap-3 text-sm">
            <div>
              <span className="text-muted">{t('queue.total')}: </span>
              <span className="font-mono">{wantedBatch.total}</span>
            </div>
            <div>
              <span className="text-muted">{t('queue.processed')}: </span>
              <span className="font-mono">{wantedBatch.processed}</span>
            </div>
            <div>
              <span className="text-muted">{t('queue.succeeded')}: </span>
              <span className="font-mono text-success">{wantedBatch.found}</span>
            </div>
            <div>
              <span className="text-muted">{t('queue.failed')}: </span>
              <span className="font-mono text-error">{wantedBatch.failed}</span>
            </div>
            <div>
              <span className="text-muted">{t('queue.skipped')}: </span>
              <span className="font-mono">{wantedBatch.skipped}</span>
            </div>
          </div>
          {wantedBatch.current_item && (
            <div className="mt-3 text-xs truncate text-muted font-mono">
              {t('queue.current')}: {truncatePath(wantedBatch.current_item, 80)}
            </div>
          )}
          {providerSummary && (
            <ProviderStatusLine summary={providerSummary} />
          )}
        </div>
      )}

      {/* Batch Probe Status */}
      {probe?.running && (
        <div className="rounded-lg p-4 bg-surface border border-border border-l-[3px] border-l-accent">
          <div className="flex items-center gap-2 mb-3">
            <Layers size={16} className="animate-pulse text-accent" />
            <h2 className="text-sm font-semibold">{t('queue.batch_probe_running')}</h2>
          </div>
          <ProgressBar value={probe.extracted ?? 0} max={probe.total} className="mb-3" />
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-sm">
            <div>
              <span className="text-muted">{t('queue.total')}: </span>
              <span className="font-mono">{probe.total}</span>
            </div>
            <div>
              <span className="text-muted">{t('queue.found')}: </span>
              <span className="font-mono text-success">{probe.found}</span>
            </div>
            <div>
              <span className="text-muted">{t('queue.extracted')}: </span>
              <span className="font-mono">{probe.extracted}</span>
            </div>
            <div>
              <span className="text-muted">{t('queue.failed')}: </span>
              <span className="font-mono text-error">{probe.failed}</span>
            </div>
          </div>
          {probe.current_item && (
            <div className="mt-3 text-xs truncate text-muted font-mono">
              {t('queue.current')}: {truncatePath(probe.current_item, 80)}
            </div>
          )}
        </div>
      )}

      {/* Wanted Scanner Status */}
      {(scanner?.is_scanning || scanner?.is_searching) && (
        <div className="rounded-lg p-4 bg-surface border border-border border-l-[3px] border-l-success">
          <div className="flex items-center gap-2 mb-3">
            <ScanSearch size={16} className="animate-pulse text-success" />
            <h2 className="text-sm font-semibold">{t('queue.scanner_running')}</h2>
            {scanner.progress.phase && (
              <span className="text-xs px-2 py-0.5 rounded bg-page text-muted">
                {scanner.progress.phase}
              </span>
            )}
          </div>
          {scanner.progress.total > 0 && (
            <ProgressBar value={scanner.progress.current} max={scanner.progress.total} className="mb-3" />
          )}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-sm">
            <div>
              <span className="text-muted">{t('queue.progress')}: </span>
              <span className="font-mono">
                {scanner.progress.current}/{scanner.progress.total}
              </span>
            </div>
            <div>
              <span className="text-muted">{t('queue.added')}: </span>
              <span className="font-mono text-success">{scanner.progress.added}</span>
            </div>
            <div>
              <span className="text-muted">{t('queue.updated')}: </span>
              <span className="font-mono">{scanner.progress.updated}</span>
            </div>
          </div>
        </div>
      )}

      {/* Scanner provider status (if search running but no batch) */}
      {scanner?.is_searching && !wantedBatch?.running && providerSummary && (
        <ProviderStatusLine summary={providerSummary} />
      )}

      {/* Empty state */}
      {!isActive && (
        <div className="rounded-lg p-8 text-center bg-surface border border-border">
          <ListVideo size={32} className="mx-auto mb-3 text-muted" />
          <p className="text-sm text-secondary">
            {t('queue.empty', 'No active subtitle searches. Use "Search All" on the Wanted page to start.')}
          </p>
        </div>
      )}
    </div>
  )
}

// ─── Provider Status Line ────────────────────────────────────────────────────

function ProviderStatusLine({ summary }: { summary: ProviderSummary }) {
  const { throttled, circuit_open, active, throttled_providers } = summary
  const problemCount = throttled + circuit_open

  if (problemCount === 0) {
    return (
      <div className="mt-3 text-xs text-muted">
        <span className="text-success">&#9889;</span>{' '}
        {active} Provider aktiv
      </div>
    )
  }

  const isMostlyThrottled = problemCount > active

  // Show up to 3 throttled provider names with remaining seconds
  const throttledNames = throttled_providers
    .filter((p) => p.remaining_seconds > 0)
    .slice(0, 3)
    .map((p) => `${p.name} ${p.remaining_seconds}s`)
    .join(', ')

  return (
    <div className={`mt-3 text-xs ${isMostlyThrottled ? 'text-warning' : 'text-muted'}`}>
      {isMostlyThrottled ? (
        <>
          <span>&#9888;&#65039;</span> {active} aktiv &middot; {problemCount} gedrosselt &mdash; Suche verlangsamt
        </>
      ) : (
        <>
          <span className="text-warning">&#9203;</span>{' '}
          {active} aktiv &middot; {problemCount} gedrosselt
          {throttledNames && (
            <span className="text-muted ml-1">
              ({throttledNames})
            </span>
          )}
        </>
      )}
    </div>
  )
}
