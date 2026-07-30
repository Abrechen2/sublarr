/**
 * DryRunModal — preview what the automation pipeline would download.
 *
 * Runs POST /wanted/dry-run for one wanted item: the full pipeline executes
 * (profile gates, provider search, upgrade decision) but nothing is written
 * to disk or the DB. Shows the provider/score/format/path a real run would
 * produce.
 */

import { useEffect } from 'react'
import { createPortal } from 'react-dom'
import { useQuery } from '@tanstack/react-query'
import { X, Loader2, FlaskConical, CheckCircle2, CircleSlash, AlertCircle } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { dryRunWanted, type WantedDryRunResult } from '@/api/wanted'

interface DryRunModalProps {
  open: boolean
  itemId?: number
  itemTitle: string
  onClose: () => void
}

function ResultBody({ result, t }: { result: WantedDryRunResult; t: (key: string, opts?: Record<string, unknown>) => string }) {
  if (result.status === 'found') {
    return (
      <div className="space-y-3">
        <div className="flex items-center gap-2 text-sm" style={{ color: 'var(--success)' }}>
          <CheckCircle2 size={16} />
          <span className="font-medium">{t('wanted_row.dry_run_found')}</span>
        </div>
        <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5 text-xs">
          <dt style={{ color: 'var(--text-muted)' }}>{t('interactive_search.col_provider')}</dt>
          <dd className="capitalize" style={{ color: 'var(--text-primary)', fontFamily: 'var(--font-mono)' }}>{result.provider}</dd>
          <dt style={{ color: 'var(--text-muted)' }}>{t('interactive_search.col_score')}</dt>
          <dd style={{ color: 'var(--text-primary)', fontFamily: 'var(--font-mono)' }}>{result.score}</dd>
          <dt style={{ color: 'var(--text-muted)' }}>{t('interactive_search.col_format')}</dt>
          <dd className="uppercase" style={{ color: 'var(--text-primary)', fontFamily: 'var(--font-mono)' }}>{result.format}</dd>
          <dt style={{ color: 'var(--text-muted)' }}>{t('wanted_row.dry_run_target')}</dt>
          <dd className="break-all" style={{ color: 'var(--text-secondary)', fontFamily: 'var(--font-mono)' }}>{result.output_path}</dd>
        </dl>
      </div>
    )
  }
  if (result.status === 'not_found') {
    return (
      <div className="flex items-center gap-2 text-sm" style={{ color: 'var(--text-secondary)' }}>
        <CircleSlash size={16} />
        {t('wanted_row.dry_run_not_found')}
      </div>
    )
  }
  if (result.status === 'skipped') {
    return (
      <div className="flex items-start gap-2 text-sm" style={{ color: 'var(--text-secondary)' }}>
        <CircleSlash size={16} className="shrink-0 mt-0.5" />
        <span>{t('wanted_row.dry_run_skipped')}{result.reason ? ` — ${result.reason}` : ''}</span>
      </div>
    )
  }
  return (
    <div className="flex items-start gap-2 text-sm" style={{ color: 'var(--error)' }}>
      <AlertCircle size={16} className="shrink-0 mt-0.5" />
      <span>{result.error ?? t('wanted_row.dry_run_failed')}</span>
    </div>
  )
}

export function DryRunModal({ open, itemId, itemTitle, onClose }: DryRunModalProps) {
  const { t } = useTranslation('library')

  const query = useQuery({
    queryKey: ['wanted-dry-run', itemId],
    queryFn: () => dryRunWanted([itemId!]),
    enabled: open && !!itemId,
    staleTime: 0,
    gcTime: 60_000,
    retry: false,
  })

  useEffect(() => {
    if (!open) return
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [open, onClose])

  if (!open) return null

  const result = query.data?.results?.[0]
  const isLoading = query.isLoading || query.isFetching

  return createPortal(
    <>
      <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm" onClick={onClose} />
      <div
        className="fixed inset-0 z-50 flex items-center justify-center p-4 pointer-events-none"
        aria-modal="true"
        role="dialog"
      >
        <div
          className="pointer-events-auto w-full max-w-lg rounded-lg shadow-2xl overflow-hidden"
          style={{ backgroundColor: 'var(--bg-elevated)', border: '1px solid var(--border)' }}
          onClick={(e) => e.stopPropagation()}
        >
          {/* Header */}
          <div className="flex items-center justify-between px-5 py-4 border-b border-[var(--border)]">
            <div className="flex items-center gap-3 min-w-0">
              <FlaskConical className="w-5 h-5 text-teal-400 shrink-0" />
              <div className="min-w-0">
                <p className="text-xs uppercase tracking-wider" style={{ color: 'var(--text-muted)' }}>
                  {t('wanted_row.dry_run_title')}
                </p>
                <h2 className="text-sm font-semibold truncate" style={{ color: 'var(--text-primary)' }}>{itemTitle}</h2>
              </div>
            </div>
            <button onClick={onClose} className="p-1 rounded" style={{ color: 'var(--text-muted)' }}>
              <X size={16} />
            </button>
          </div>

          {/* Body */}
          <div className="px-5 py-4">
            {isLoading ? (
              <div className="flex items-center gap-2 text-sm py-2" style={{ color: 'var(--text-secondary)' }}>
                <Loader2 size={16} className="animate-spin" />
                {t('wanted_row.dry_run_running')}
              </div>
            ) : query.isError ? (
              <div className="flex items-center gap-2 text-sm" style={{ color: 'var(--error)' }}>
                <AlertCircle size={16} />
                {t('wanted_row.dry_run_failed')}
              </div>
            ) : result ? (
              <ResultBody result={result} t={t} />
            ) : null}
            <p className="text-[11px] mt-4" style={{ color: 'var(--text-muted)' }}>
              {t('wanted_row.dry_run_note')}
            </p>
          </div>
        </div>
      </div>
    </>,
    document.body
  )
}
