/**
 * QuickActionsWidget -- Scan Library and Search Wanted action buttons.
 *
 * Self-contained: fetches own data via useWantedSummary, useWantedBatchStatus.
 * Uses mutation hooks for scan/search triggers.
 */
import { useTranslation } from 'react-i18next'
import { RefreshCw, Search, Loader2 } from 'lucide-react'
import {
  useWantedSummary,
  useRefreshWanted,
  useStartWantedBatch,
  useWantedBatchStatus,
} from '@/hooks/useApi'
import { toast } from '@/components/shared/Toast'

export default function QuickActionsWidget() {
  const { t } = useTranslation('dashboard')
  const { data: wantedSummary } = useWantedSummary()
  const { data: batchStatus } = useWantedBatchStatus()
  const refreshWanted = useRefreshWanted()
  const startBatch = useStartWantedBatch()

  return (
    <div className="flex flex-wrap gap-2">
      <button
        onClick={() => {
          refreshWanted.mutate(undefined, {
            onSuccess: () => toast(t('toast.scan_started')),
            onError: () => toast(t('toast.scan_failed'), 'error'),
          })
        }}
        disabled={refreshWanted.isPending || wantedSummary?.scan_running}
        className="flex items-center gap-2 px-4 py-2 rounded-md text-sm font-medium transition-all duration-150 hover:opacity-90"
        style={{
          backgroundColor: 'var(--bg-primary)',
          border: '1px solid var(--border)',
          color: 'var(--text-primary)',
        }}
      >
        {refreshWanted.isPending || wantedSummary?.scan_running ? (
          <Loader2 size={14} className="animate-spin" />
        ) : (
          <RefreshCw size={14} />
        )}
        {wantedSummary?.scan_running
          ? t('quick_actions.scanning')
          : t('quick_actions.scan_library')}
      </button>
      <button
        onClick={() => {
          startBatch.mutate(undefined, {
            onSuccess: () => toast(t('toast.search_started')),
            onError: () => toast(t('toast.search_failed'), 'error'),
          })
        }}
        disabled={startBatch.isPending || batchStatus?.running}
        className="flex items-center gap-2 px-4 py-2 rounded-md text-sm font-medium transition-all duration-150 hover:opacity-90"
        style={{
          backgroundColor: 'var(--bg-primary)',
          border: '1px solid var(--border)',
          color: 'var(--text-primary)',
        }}
      >
        {startBatch.isPending || batchStatus?.running ? (
          <Loader2 size={14} className="animate-spin" />
        ) : (
          <Search size={14} />
        )}
        {batchStatus?.running
          ? t('quick_actions.searching')
          : t('quick_actions.search_wanted')}
      </button>
    </div>
  )
}
