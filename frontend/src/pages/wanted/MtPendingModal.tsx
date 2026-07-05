/**
 * MtPendingModal — review surface for pending-original notifications
 * (feature #8b Phase 2, Task 3/4).
 *
 * When a provisional machine-translation's re-seek job runs in
 * `mt_on_original_found="notify"` mode and finds a genuine original, the
 * item is flagged rather than auto-replaced. This modal lists every such
 * item and lets the user approve (install the original, trash the MT) or
 * reject (keep the MT, pin it so it's never re-notified).
 */
import { useTranslation } from 'react-i18next'
import { X, Loader2, Check, XCircle } from 'lucide-react'
import { useMtPendingItems, useApproveMtPending, useRejectMtPending } from '@/hooks/useApi'
import { toast } from '@/components/shared/Toast'
import { formatRelativeTime } from '@/lib/utils'

interface MtPendingModalProps {
  open: boolean
  onClose: () => void
}

export function MtPendingModal({ open, onClose }: MtPendingModalProps) {
  const { t } = useTranslation('library')
  const { data, isLoading, isError } = useMtPendingItems()
  const approve = useApproveMtPending()
  const reject = useRejectMtPending()

  if (!open) return null

  const items = data?.data ?? []
  const busy = approve.isPending || reject.isPending

  const handleApprove = (itemId: number) => {
    approve.mutate(itemId, {
      onSuccess: () => toast(t('mt_pending.approve_success'), 'success'),
      onError: () => toast(t('mt_pending.approve_failed'), 'error'),
    })
  }

  const handleReject = (itemId: number) => {
    reject.mutate(itemId, {
      onSuccess: () => toast(t('mt_pending.reject_success'), 'success'),
      onError: () => toast(t('mt_pending.reject_failed'), 'error'),
    })
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60"
      onClick={(e) => { if (e.target === e.currentTarget) onClose() }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="mt-pending-title"
        className="w-full max-w-2xl max-h-[80vh] rounded-lg flex flex-col bg-surface border border-border"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-border">
          <h2 id="mt-pending-title" className="font-semibold text-sm text-foreground">
            {t('mt_pending.title')}
          </h2>
          <button
            onClick={onClose}
            aria-label={t('mt_pending.close')}
            className="p-1 rounded text-muted hover:text-foreground"
          >
            <X size={16} />
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto px-4 py-3 space-y-3">
          <p className="text-sm text-secondary">{t('mt_pending.description')}</p>

          {isLoading ? (
            <div className="flex items-center gap-2 text-sm py-4 text-secondary">
              <Loader2 size={14} className="animate-spin" />
              {t('mt_pending.loading')}
            </div>
          ) : isError ? (
            <p className="text-sm py-4 text-center text-error">{t('mt_pending.load_failed')}</p>
          ) : items.length === 0 ? (
            <p className="text-sm py-4 text-center text-muted">{t('mt_pending.empty')}</p>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-[11px] font-semibold uppercase tracking-wider text-muted">
                  <th scope="col" className="px-2 py-1.5">{t('mt_pending.col_title')}</th>
                  <th scope="col" className="px-2 py-1.5">{t('mt_pending.col_provider')}</th>
                  <th scope="col" className="px-2 py-1.5">{t('mt_pending.col_score')}</th>
                  <th scope="col" className="px-2 py-1.5">{t('mt_pending.col_found')}</th>
                  <th scope="col" className="px-2 py-1.5 text-right">{t('wanted.actions_col')}</th>
                </tr>
              </thead>
              <tbody>
                {items.map((item) => (
                  <tr key={item.id} className="border-t border-border">
                    <td className="px-2 py-2 align-top">
                      <div className="font-medium text-foreground">
                        {item.title}
                        {item.season_episode ? ` — ${item.season_episode}` : ''}
                      </div>
                      <div className="text-xs text-muted truncate max-w-[280px]">{item.file_path}</div>
                    </td>
                    <td className="px-2 py-2 align-top text-secondary">
                      {item.mt_pending_original.provider || '—'}
                    </td>
                    <td className="px-2 py-2 align-top tabular-nums text-secondary">
                      {item.mt_pending_original.score ?? '—'}
                    </td>
                    <td className="px-2 py-2 align-top text-secondary">
                      {item.mt_pending_original.found_at
                        ? formatRelativeTime(item.mt_pending_original.found_at)
                        : '—'}
                    </td>
                    <td className="px-2 py-2 align-top">
                      <div className="flex items-center justify-end gap-2">
                        <button
                          onClick={() => handleApprove(item.id)}
                          disabled={busy}
                          data-testid={`mt-pending-approve-${item.id}`}
                          className="flex items-center gap-1 px-2.5 py-1 rounded text-xs font-medium text-white bg-success hover:opacity-90 disabled:opacity-50"
                        >
                          <Check size={12} />
                          {t('mt_pending.approve')}
                        </button>
                        <button
                          onClick={() => handleReject(item.id)}
                          disabled={busy}
                          data-testid={`mt-pending-reject-${item.id}`}
                          className="flex items-center gap-1 px-2.5 py-1 rounded text-xs font-medium text-white bg-error hover:opacity-90 disabled:opacity-50"
                        >
                          <XCircle size={12} />
                          {t('mt_pending.reject')}
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  )
}
