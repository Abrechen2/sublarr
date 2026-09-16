/**
 * MtPendingModal — review surface for pending-original notifications
 * (feature #8b Phase 2, Task 3/4).
 *
 * When a provisional machine-translation's re-seek job runs in
 * `mt_on_original_found="notify"` mode and finds a genuine original, the
 * item is flagged rather than auto-replaced. This modal lists every such
 * item and lets the user approve (install the original, trash the MT) or
 * reject (keep the MT, pin it so it's never re-notified) — one at a time, or
 * approve a selection in the background.
 */
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { X, Loader2, Check, XCircle, CheckCheck } from 'lucide-react'
import {
  useMtPendingItems,
  useApproveMtPending,
  useApproveMtPendingBatch,
  useRejectMtPending,
} from '@/hooks/useApi'
import { toast } from '@/components/shared/Toast'
import { formatRelativeTime } from '@/lib/utils'

interface MtPendingModalProps {
  open: boolean
  onClose: () => void
}

const httpStatus = (err: unknown) => (err as { response?: { status?: number } }).response?.status

export function MtPendingModal({ open, onClose }: MtPendingModalProps) {
  const { t } = useTranslation('library')
  const { data, isLoading, isError } = useMtPendingItems()
  const approve = useApproveMtPending()
  const approveBatch = useApproveMtPendingBatch()
  const reject = useRejectMtPending()
  const [selected, setSelected] = useState<ReadonlySet<number>>(new Set())

  if (!open) return null

  const items = data?.data ?? []
  const batch = data?.batch
  const batchRunning = batch?.running ?? false
  const busy = approve.isPending || reject.isPending || approveBatch.isPending || batchRunning
  // Only ids still listed count: approved items drop out of the list.
  const selectedIds = items.map((item) => item.id).filter((id) => selected.has(id))
  const allSelected = items.length > 0 && selectedIds.length === items.length

  const toggle = (itemId: number) => {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(itemId)) next.delete(itemId)
      else next.add(itemId)
      return next
    })
  }

  const toggleAll = () => {
    setSelected(allSelected ? new Set() : new Set(items.map((item) => item.id)))
  }

  const handleApprove = (itemId: number) => {
    approve.mutate(itemId, {
      onSuccess: () => toast(t('mt_pending.approve_success'), 'success'),
      onError: (err: unknown) => {
        // 409: the original could not be installed and the backend put the
        // machine translation back — say so, the generic text implies loss.
        toast(
          t(httpStatus(err) === 409 ? 'mt_pending.approve_not_installed' : 'mt_pending.approve_failed'),
          'error',
        )
      },
    })
  }

  const handleApproveSelected = () => {
    approveBatch.mutate(selectedIds, {
      onSuccess: (result) => {
        toast(t('mt_pending.batch_started', { count: result?.accepted?.length ?? selectedIds.length }), 'success')
        setSelected(new Set())
      },
      onError: (err: unknown) => {
        toast(t(httpStatus(err) === 409 ? 'mt_pending.batch_conflict' : 'mt_pending.batch_failed'), 'error')
      },
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
        className="w-full max-w-5xl max-h-[85vh] rounded-lg flex flex-col bg-surface border border-border"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-3 border-b border-border">
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
        <div className="flex-1 overflow-y-auto overflow-x-hidden px-5 py-3 space-y-3">
          <p className="text-sm text-secondary">{t('mt_pending.description')}</p>

          {batch && batch.total > 0 && (
            <div
              data-testid="mt-pending-batch-progress"
              className="flex items-center gap-2 rounded-md border border-border px-3 py-2 text-sm text-secondary"
            >
              {batch.running && <Loader2 size={14} className="animate-spin shrink-0" />}
              {t(batch.running ? 'mt_pending.batch_progress' : 'mt_pending.batch_done', {
                done: batch.done,
                total: batch.total,
                installed: batch.installed,
                kept: batch.kept,
              })}
            </div>
          )}

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
            <table className="w-full table-fixed text-sm">
              <colgroup>
                <col className="w-10" />
                <col />
                <col className="w-28" />
                <col className="w-16" />
                <col className="w-28" />
                <col className="w-48" />
              </colgroup>
              <thead>
                <tr className="text-left text-[11px] font-semibold uppercase tracking-wider text-muted">
                  <th scope="col" className="px-2 py-1.5">
                    <input
                      type="checkbox"
                      checked={allSelected}
                      onChange={toggleAll}
                      disabled={busy}
                      aria-label={t('mt_pending.select_all')}
                      data-testid="mt-pending-select-all"
                      className="align-middle"
                    />
                  </th>
                  <th scope="col" className="px-2 py-1.5">{t('mt_pending.col_title')}</th>
                  <th scope="col" className="px-2 py-1.5">{t('mt_pending.col_provider')}</th>
                  <th scope="col" className="px-2 py-1.5">{t('mt_pending.col_score')}</th>
                  <th scope="col" className="px-2 py-1.5">{t('mt_pending.col_found')}</th>
                  <th scope="col" className="px-2 py-1.5 text-right">{t('wanted.actions_col')}</th>
                </tr>
              </thead>
              <tbody>
                {items.map((item) => {
                  const label = `${item.title}${item.season_episode ? ` — ${item.season_episode}` : ''}`
                  return (
                    <tr key={item.id} className="border-t border-border">
                      <td className="px-2 py-2 align-top">
                        <input
                          type="checkbox"
                          checked={selected.has(item.id)}
                          onChange={() => toggle(item.id)}
                          disabled={busy}
                          aria-label={t('mt_pending.select_item', { title: label })}
                          data-testid={`mt-pending-select-${item.id}`}
                          className="mt-0.5"
                        />
                      </td>
                      <td className="px-2 py-2 align-top">
                        <div className="font-medium text-foreground break-words">{label}</div>
                        <div className="text-xs text-muted break-all">{item.file_path}</div>
                      </td>
                      <td className="px-2 py-2 align-top text-secondary break-words">
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
                        <div className="flex flex-wrap items-center justify-end gap-2">
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
                  )
                })}
              </tbody>
            </table>
          )}
        </div>

        {/* Footer — bulk approval */}
        {items.length > 0 && (
          <div className="flex items-center justify-between gap-3 px-5 py-3 border-t border-border">
            <span data-testid="mt-pending-selected-count" className="text-sm text-secondary">
              {t('mt_pending.selected_count', { count: selectedIds.length })}
            </span>
            <button
              onClick={handleApproveSelected}
              disabled={busy || selectedIds.length === 0}
              data-testid="mt-pending-approve-selected"
              className="flex items-center gap-1.5 px-3 py-1.5 rounded text-sm font-medium text-white bg-success hover:opacity-90 disabled:opacity-50"
            >
              <CheckCheck size={14} />
              {t('mt_pending.approve_selected')}
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
